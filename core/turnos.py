"""Lectura del horario semanal del chat center desde Google Sheets.

La jefe de ventas sigue manteniendo su cuadro semanal como hoy (un bloque por
turno, una columna por día, y COLORES para los estados). Este módulo lo lee tal
cual: valores + colores de fondo, igual que hace tabla_precios.py con la tabla
de precios.

Reparto de responsabilidades:
  - Los HORARIOS de cada turno viven en la constante TURNOS de este archivo
    (cambian muy poco). Si el texto del bloque en la hoja trae horas con am/pm,
    se usan esas y esta constante queda solo como respaldo.
  - Las ASIGNACIONES (quién, qué día, qué turno) y los ESTADOS (por color) se
    leen de la hoja, porque rotan cada semana.

Formato esperado en la hoja (el mismo del cuadro actual):
  - Una fila de encabezado con los días: Lunes, Martes, ... Domingo.
  - Un bloque por turno cuya primera celda contiene "1 Turno ...", "2 Turno ..."
  - Debajo de cada día, los primeros nombres de los asesores.
  - Una leyenda: celda con el texto del estado y, a su derecha, el color.
"""
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta

import gspread

from core.app_config import log
from core.almacen import ESTADOS_ASESOR, ESTADO_PRESENCIAL
# Por defecto se usa el mismo documento espejo al que ya tiene acceso el
# service account; basta agregarle una hoja con el cuadro de horarios.
from core.mayorista_logic import _SPREADSHEET_ID as _ESPEJO_ID

_SHEET_ID = os.environ.get("TURNOS_SHEET_ID", _ESPEJO_ID)
_HOJA = os.environ.get("TURNOS_HOJA", "Horarios")
_HOJA_ROLES = os.environ.get("TURNOS_HOJA_ROLES", "Roles")
# Sin rango fijo: se pide la hoja completa (ver la nota en tabla_precios.py).
# Así, si la jefa agrega columnas a la derecha —como la de auxiliares de
# bodega— o filas abajo, no se pierden por un límite escrito a mano.
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Horarios de cada turno: (hora_inicio, hora_fin) en formato 24h decimal.
# 'sem' = lunes a viernes, 'sab' = sábado, 'dom' = domingo.
# El tercer bloque dejó de ser un turno de ventas: hoy es el de auditoría de
# calidad (10am a 6pm). Como siempre, si el rótulo de la hoja trae horas con
# am/pm, esas mandan y esto queda solo como respaldo.
TURNOS = {
    1: {"sem": (8.0, 16.0), "sab": (8.0, 15.0), "dom": (8.0, 15.0)},
    2: {"sem": (11.0, 19.0), "sab": (10.0, 17.0), "dom": (10.0, 17.0)},
    3: {"sem": (10.0, 18.0), "sab": (9.0, 16.0), "dom": (9.0, 16.0)},
}

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Estados de la leyenda. 'cubrir' indica si, estando en ese estado, se espera
# que la persona esté en su turno (el nombre viene de cuando existía la
# cobertura de soporte; hoy solo distingue "trabaja hoy" de "no viene").
# 'sede' marca las sedes de atención presencial (Santa Fe, El Tesoro,
# Mostrador…): la persona SÍ está trabajando, pero no en chats, así que va
# como ausencia informada y no como "no se espera".
ESTADOS = {
    "normal": {"cubrir": True, "etiqueta": ""},
    "santafe": {"cubrir": True, "sede": True, "etiqueta": "En Santa Fe (CC)"},
    "cc santafe": {"cubrir": True, "sede": True, "etiqueta": "En Santa Fe (CC)"},
    "tesoro": {"cubrir": True, "sede": True, "etiqueta": "En El Tesoro (CC)"},
    "cc tesoro": {"cubrir": True, "sede": True, "etiqueta": "En El Tesoro (CC)"},
    "mostrador": {"cubrir": True, "sede": True, "etiqueta": "En el mostrador"},
    "compensatorio": {"cubrir": False, "etiqueta": "Compensatorio"},
    "ausencia": {"cubrir": False, "etiqueta": "Ausencia"},
    "cambio de horario": {"cubrir": False, "etiqueta": "Cambio de horario"},
}

# Almuerzo por turno (hora_inicio, hora_fin) en formato 24h decimal — respaldo
# si la tabla "Almuerzo | Desde | Hasta" no está en la hoja (la hoja manda si
# existe, igual que con TURNOS).
# El turno 3 no tiene respaldo a propósito: cuando dejó de ser el turno de
# tarde (2pm-9pm) para ser el de auditoría de calidad (10am-6pm), su almuerzo
# viejo de 6:00-6:20pm quedó justo al final de la jornada, así que se encendía
# el instante en que el turno terminaba y no antes. Mientras la hoja no traiga
# la fila "3 Turno" en la tabla de Almuerzo, esa persona no tiene almuerzo
# automático — preferible a inventarle una hora.
ALMUERZOS = {
    1: (12.0, 13.0),
    2: (13.0, 14.0),
}


# Minutos sin señal de la calculadora para dejar de contar a alguien como
# "En línea". Es el único umbral que queda: el panel ya no pide coberturas
# (agosto de 2026 — se eliminó el rol de soporte, todos son vendedores), así
# que no hay tolerancias ni vencimientos que administrar.
UMBRAL_INACTIVO_MIN = 30


def _norm(t):
    """minúsculas sin acentos ni espacios de más."""
    t = unicodedata.normalize("NFKD", str(t or "").strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t)


def _hex(color):
    """Color de la API ({'red':0-1,...}) a '#RRGGBB'. Ojo: la API omite los
    canales en 0, así que un dict presente con canales faltantes vale 0."""
    if color is None:
        return "#FFFFFF"
    r = round(color.get("red", 0) * 255)
    g = round(color.get("green", 0) * 255)
    b = round(color.get("blue", 0) * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def _dist(c1, c2):
    a = (int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16))
    b = (int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16))
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def _es_blanco(c):
    return _dist(c, "#FFFFFF") < 25


def _horas_del_texto(texto):
    """Extrae horarios del rótulo del turno, p. ej.
    '1 Turno 8:00am a 4:00pm, Sábado 8:00am a 3:00pm'.
    Solo acepta rangos con am/pm (sin ellos es ambiguo) y devuelve
    {'sem': (ini,fin)} y/o {'sab': (ini,fin)} según lo que encuentre."""
    t = _norm(texto)
    patron = r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*a\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)"
    res = {}
    for m in re.finditer(patron, t):
        h1 = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
        h1 += int(m.group(2) or 0) / 60
        h2 = int(m.group(4)) % 12 + (12 if m.group(6) == "pm" else 0)
        h2 += int(m.group(5) or 0) / 60
        if h2 <= h1:
            # "10:00pm a 6:00pm" — casi siempre un am/pm mal escrito en la
            # hoja. Adivinar la intención sería peor: se ignora el rango y
            # manda el respaldo de TURNOS, con aviso en el log.
            log.warning("Rótulo de turno con horas incoherentes, se ignora: %r", texto)
            continue
        antes = t[:m.start()]
        clave = "sab" if "sabado" in antes[-25:] else ("sem" if "sem" not in res else "sab")
        res.setdefault(clave, (h1, h2))
    return res


def _hora_simple_a_decimal(texto):
    """'12:00 pm' -> 12.0, '6:20 pm' -> 18.333…"""
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", _norm(texto))
    if not m:
        return None
    h = int(m.group(1)) % 12 + (12 if m.group(3) == "pm" else 0)
    return h + int(m.group(2) or 0) / 60


def _numero_del_turno(texto, orden):
    """Número del bloque a partir de su rótulo, o None si la celda no es un
    rótulo de turno.

    Normalmente el número va delante ("1 Turno 8:00am a 4:00pm"), pero la jefa
    a veces lo escribe sin número ("Turno 10:00am a 6:00pm"): ahí vale la
    posición del bloque en la hoja (`orden`). Ojo con leer el número que va
    DESPUÉS de la palabra: en "Turno 10:00am" el 10 es la hora, no el turno,
    así que solo cuenta si no viene seguido de otro dígito, de ':' ni de am/pm.
    """
    t = _norm(texto)
    if "turno" not in t:
        return None
    m = re.search(r"(\d+)\s*turno", t)
    if m:
        return int(m.group(1))
    m = re.search(r"turno\s*:?\s*(\d+)(?![\d:])(?!\s*(?:am|pm))", t)
    if m:
        return int(m.group(1))
    return orden


def _parsear_almuerzo(grid):
    """Tabla aparte 'Almuerzo | Desde | Hasta', una fila por turno. Puede estar
    debajo de todo el cuadro o al lado (mismas filas que la gente de turno 1) —
    se ubica la columna real de "Almuerzo" en vez de asumir que es la 0, para
    no perder la tabla cuando la jefa la reacomoda a la derecha.
    Devuelve {turno: (inicio_decimal, fin_decimal)}; vacío si la tabla no está
    en la hoja (se usa el respaldo ALMUERZOS)."""
    fila_ini = col_ini = None
    for r, fila in enumerate(grid):
        for c, (t, _bg) in enumerate(fila):
            if _norm(t).startswith("almuerzo"):
                fila_ini, col_ini = r, c
                break
        if fila_ini is not None:
            break
    if fila_ini is None:
        return {}
    almuerzos = {}
    for r in range(fila_ini + 1, len(grid)):
        textos = [t for t, _ in grid[r][col_ini:col_ini + 3]]
        if not any(textos):
            continue
        m = re.search(r"(\d+)\s*turno", _norm(textos[0])) if textos else None
        if not m:
            break  # se acabó la tabla
        desde = _hora_simple_a_decimal(textos[1]) if len(textos) > 1 else None
        hasta = _hora_simple_a_decimal(textos[2]) if len(textos) > 2 else None
        if desde is not None and hasta is not None:
            almuerzos[int(m.group(1))] = (desde, hasta)
    return almuerzos


def _lista_de_columna(grid, prefijo):
    """Lista de nombres escrita debajo de un rótulo, en cualquier columna de la
    hoja: se ubica la celda cuyo texto empieza por `prefijo` y se leen las de
    abajo hasta la primera vacía. Devuelve los nombres tal cual están escritos
    (sin normalizar) — vacía si ese rótulo no está en la hoja.

    Lo usan las columnas 'Vacaciones' y 'Auxiliares de bodega'. Ubicar la
    columna real, en vez de fijarla, es lo que permite que la jefa las mueva
    de sitio sin romper nada.
    """
    fila_ini = col_ini = None
    for r, fila in enumerate(grid):
        for c, (t, _bg) in enumerate(fila):
            if _norm(t).startswith(prefijo):
                fila_ini, col_ini = r, c
                break
        if fila_ini is not None:
            break
    if fila_ini is None:
        return []
    nombres = []
    for r in range(fila_ini + 1, len(grid)):
        fila = grid[r]
        texto = fila[col_ini][0] if col_ini < len(fila) else ""
        if not texto:
            break  # se acabó la lista
        nombres.append(texto.strip())
    return nombres


def parsear_horario(meta, gid=None):
    """Convierte la respuesta de la API (con formato) en la estructura del
    horario. Separado de la descarga para poder probarlo sin red."""
    hojas = meta.get("sheets", [])
    hoja = None
    for s in hojas:
        if s.get("data") and s["data"][0].get("rowData"):
            hoja = s
            break
    if hoja is None:
        return {"error": "La hoja de horarios llegó vacía."}

    filas = hoja["data"][0].get("rowData", [])
    # Matriz de (texto, color) para trabajar cómodo
    grid = []
    for fila in filas:
        celdas = []
        for c in fila.get("values", []):
            texto = (c.get("formattedValue") or "").strip()
            bg = _hex(c.get("effectiveFormat", {}).get("backgroundColor"))
            celdas.append((texto, bg))
        grid.append(celdas)

    def celda(r, c):
        if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
            return grid[r][c]
        return ("", "#FFFFFF")

    # --- 1) Leyenda: texto del estado y color en la celda de al lado ---
    leyenda = {}   # color -> estado normalizado
    for r, fila in enumerate(grid):
        for c, (texto, _bg) in enumerate(fila):
            n = _norm(texto)
            if n in ESTADOS and n != "normal":
                for dc in (1, 2):           # el swatch suele ir a la derecha
                    _t, color = celda(r, c + dc)
                    if not _es_blanco(color):
                        leyenda[color] = n
                        break

    # --- 2) Fila de encabezado con los días ---
    col_dia, fila_encabezado = {}, None
    for r, fila in enumerate(grid):
        encontrados = {}
        for c, (texto, _bg) in enumerate(fila):
            n = _norm(texto)
            for i, d in enumerate(DIAS):
                # "Lunes 27", "Miercoles 29" → empieza por el nombre del día
                if n.startswith(d):
                    encontrados[c] = i
        if len(encontrados) >= 3:
            col_dia, fila_encabezado = encontrados, r
            break
    if not col_dia:
        return {"error": "No se encontró la fila con los días (Lunes, Martes, …)."}

    # --- 3b) Límite del cuadro: la leyenda, la tabla de almuerzo y cualquier
    # nota posterior NO son turnos ni personas — sin este corte, "1 Turno"
    # dentro de la tabla de almuerzo se leía como otro bloque de turno más,
    # y sus horas ("12:00 pm") como si fueran el nombre de un asesor.
    # Se corta en lo primero que aparezca de "Leyenda" o "Almuerzo": la jefa
    # a veces quita el rótulo "Leyenda:" (la reacomoda al lado del turno 1),
    # así que no basta con buscar solo ese texto — la tabla de Almuerzo es
    # el límite más confiable porque siempre tiene que estar para que la
    # app lea las horas.
    # Una fila que todavía tiene gente asignada en las columnas de los días
    # NUNCA es el límite, aunque en otra columna de esa misma fila (más a la
    # derecha) diga "Almuerzo" o "Leyenda" — ese es justo el caso real de la
    # tabla de Almuerzo puesta al lado del turno 1. Solo cuenta como límite
    # una fila donde ya no queda nadie del cuadro.
    fila_fin_cuadro = len(grid)
    for r in range(fila_encabezado + 1, len(grid)):
        if any(celda(r, c)[0] for c in col_dia):
            continue
        if any(_norm(t).startswith(("leyenda", "almuerzo")) for t, _ in grid[r]):
            fila_fin_cuadro = r
            break

    # --- 4) Bloques de turno ---
    # El rótulo del bloque ("1 Turno 8:00am a 4:00pm...") siempre vive en la
    # columna justo antes de que empiecen los días (col_dia). Buscar en TODA
    # la fila es un error: la tabla de Almuerzo usa "1 Turno"/"2 Turno" como
    # clave y, si la jefa la ubica al lado del cuadro (mismas filas que la
    # gente), esas celdas se confunden con el inicio de un bloque nuevo y
    # cortan el turno 1 en solo una fila.
    col_marca = min(col_dia) - 1
    marcas = []   # (fila, numero_turno, texto)
    for r in range(fila_encabezado + 1, fila_fin_cuadro):
        texto, _bg = celda(r, col_marca)
        num = _numero_del_turno(texto, len(marcas) + 1)
        if num:
            marcas.append((r, num, texto))
    if not marcas:
        return {"error": "No se encontraron bloques de turno ('1 Turno …')."}

    asignaciones = []
    horarios = {}
    roles = {}
    for i, (r_ini, num, texto) in enumerate(marcas):
        r_fin = marcas[i + 1][0] if i + 1 < len(marcas) else fila_fin_cuadro
        base = dict(TURNOS.get(num, TURNOS[1]))
        base.update(_horas_del_texto(texto))       # la hoja manda si es clara
        horarios[num] = base
        for r in range(r_ini, r_fin):
            for c, dia_idx in col_dia.items():
                nombre_bruto, color = celda(r, c)
                if not nombre_bruto or len(nombre_bruto) > 30:
                    continue
                if _norm(nombre_bruto).startswith(tuple(DIAS)):
                    continue
                # El "*" al final del nombre marcaba a soporte, rol que ya no
                # existe (todos son vendedores). Se sigue quitando para que
                # "Elvia*" y "Elvia" no cuenten como dos personas distintas.
                nombre = nombre_bruto.rstrip("* ").strip()
                if not nombre:
                    continue
                estado = "normal"
                if not _es_blanco(color):
                    mejor, mejor_d = None, 999
                    for col_ley, est in leyenda.items():
                        d = _dist(color, col_ley)
                        if d < mejor_d:
                            mejor, mejor_d = est, d
                    if mejor and mejor_d < 45:
                        estado = mejor
                asignaciones.append({
                    "nombre": nombre, "turno": num, "dia": dia_idx,
                    "estado": estado, "color": color,
                })

    return {"exito": True, "turnos": horarios,
            "asignaciones": asignaciones,
            "roles": roles,
            "almuerzos": _parsear_almuerzo(grid),
            "vacaciones": _lista_de_columna(grid, "vacacion"),
            # Auxiliares de bodega: no tienen turno en el cuadro (no atienden
            # chats), pero sí usan la calculadora, así que van al selector
            # "Soy:" y desbloquean los valores de bodega en "Valor Tienda".
            "auxiliares": _lista_de_columna(grid, "auxiliar"),
            "estados_leyenda": sorted(set(leyenda.values()))}


def parsear_roles(meta_roles):
    """Hoja opcional 'Roles' con dos columnas: Nombre | Rol."""
    roles = {}
    try:
        filas = meta_roles["sheets"][0]["data"][0].get("rowData", [])
    except (KeyError, IndexError, TypeError):
        return roles
    for fila in filas:
        vals = [(c.get("formattedValue") or "").strip() for c in fila.get("values", [])]
        if len(vals) >= 2 and vals[0] and vals[1]:
            if _norm(vals[0]) in ("nombre", "asesor", "asesora"):
                continue
            roles[_norm(vals[0])] = vals[1]
    return roles


def horario_desde_equipo(personas):
    """Arma un horario a partir del equipo registrado en la app, para funcionar
    sin la hoja de Sheets: cada persona trabaja su turno de lunes a sábado
    (el domingo se deja libre; se ajusta con novedades o con la hoja)."""
    asignaciones, roles = [], {}
    for p in personas:
        roles[_norm(p["nombre"])] = p.get("rol", "")
        for dia in range(0, 6):            # lunes(0) … sábado(5)
            asignaciones.append({
                "nombre": p["nombre"], "turno": int(p.get("turno") or 1),
                "dia": dia, "estado": "normal", "color": "#FFFFFF",
            })
    return {"exito": True, "turnos": dict(TURNOS),
            "asignaciones": asignaciones, "roles": roles,
            "almuerzos": dict(ALMUERZOS), "vacaciones": [], "auxiliares": [],
            "estados_leyenda": [], "fuente": "equipo"}


_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# A partir de esta hora del sábado, el rótulo ya muestra la semana siguiente
# (lunes a domingo), en vez de esperar a que empiece el domingo o el lunes.
_CORTE_SEMANA_DIA, _CORTE_SEMANA_HORA = 5, 23  # 5 = sábado


def _semana_actual(ahora=None):
    """Rango Lunes-Domingo de la semana en curso, calculado (no se lee de la
    hoja): 'Semana del 3 al 9 de Agosto de 2026'. El corte a la semana
    siguiente es el sábado a las 11pm, no la medianoche del domingo."""
    ahora = ahora or datetime.now()
    dow = ahora.weekday()  # 0=lunes … 6=domingo
    # El corte ocurre el sábado a las 11pm y se mantiene todo el domingo (si
    # solo mirara el sábado, el domingo "volvería" a calcular la semana vieja,
    # porque domingo es, calendario en mano, el último día de esa semana).
    corta = dow == 6 or (dow == _CORTE_SEMANA_DIA and ahora.hour >= _CORTE_SEMANA_HORA)
    if corta:
        lunes = ahora + timedelta(days=(7 - dow))  # próximo lunes
    else:
        lunes = ahora - timedelta(days=dow)
    lunes = lunes.replace(hour=0, minute=0, second=0, microsecond=0)
    domingo = lunes + timedelta(days=6)
    mes_ini, mes_fin = _MESES[lunes.month - 1].capitalize(), _MESES[domingo.month - 1].capitalize()
    if lunes.month == domingo.month:
        return f"Semana del {lunes.day} al {domingo.day} de {mes_fin} de {domingo.year}"
    return f"Semana del {lunes.day} de {mes_ini} al {domingo.day} de {mes_fin} de {domingo.year}"



def _fmt_hora(h):
    hh = int(h) % 24
    mm = int(round((h - int(h)) * 60))
    suf = "am" if hh < 12 else "pm"
    h12 = hh % 12 or 12
    return f"{h12}:{mm:02d}{suf}"


def _aplicar_ajustes(asignaciones, ajustes, dia_idx, roles):
    """Superpone los ajustes del día sobre el plan de la semana.

    El plan (la hoja) no se toca: aquí se decide qué rige HOY. Devuelve la lista
    de asignaciones del día ya ajustada, marcando lo que cambió para que se
    entienda por qué el panel dice algo distinto al cuadro.
    """
    del_dia, vistos = [], set()
    for a in asignaciones:
        if a["dia"] != dia_idx:
            continue
        k = _norm(a["nombre"])
        vistos.add(k)
        aj = ajustes.get(k)
        b = dict(a)
        if aj:
            b["ajuste"] = aj["etiqueta"]
            b["ajuste_nota"] = aj.get("nota") or ""
            b["ajuste_autor"] = aj.get("autor") or ""
            if aj["tipo"] == "no_viene":
                b["estado"] = "ausencia"          # no se espera, no alarma
            elif aj["tipo"] == "turno" and aj.get("turno"):
                b["turno"] = int(aj["turno"])
            elif aj["tipo"] == "entrada" and aj.get("hora"):
                b["entrada_ajustada"] = aj["hora"]
        del_dia.append(b)

    # Quien entra extra hoy sin estar en el plan
    for k, aj in ajustes.items():
        if aj["tipo"] == "extra" and k not in vistos:
            del_dia.append({
                "nombre": aj["nombre"], "turno": int(aj.get("turno") or 1),
                "dia": dia_idx, "estado": "normal", "color": "#FFFFFF",
                "ajuste": aj["etiqueta"], "ajuste_nota": aj.get("nota") or "",
                "ajuste_autor": aj.get("autor") or "",
            })
    return del_dia


def _hora_a_decimal(txt):
    try:
        h, m = str(txt).split(":")
        return int(h) + int(m) / 60.0
    except (ValueError, AttributeError):
        return None


def _ts_hoy(ahora, hora_decimal):
    """Timestamp de 'hoy' a la hora decimal dada — para mostrar 'desde
    12:00 pm' en un estado que se marcó solo, sin que nadie lo haya
    seleccionado a esa hora exacta."""
    base = ahora.replace(hour=int(hora_decimal),
                          minute=int(round((hora_decimal - int(hora_decimal)) * 60)),
                          second=0, microsecond=0)
    return base.timestamp()


def calcular_panel(horario, ahora, presencia=None, estados=None,
                   novedades=None, ajustes=None):
    """Cruza el horario del día con la realidad (señal, estado, novedades) y la
    hora actual. No toca red ni disco, y la ventana de turno se prueba con
    cualquier valor de `ahora` — OJO: los "minutos sin señal" sí usan el reloj
    real del proceso (`time.time()`), no `ahora`, porque el único llamador real
    (`app.py`) siempre los pasa sincronizados. Una prueba que fije `ahora`
    lejos de la fecha real dará ese dato incoherente con la ventana de turno.

    El panel es INFORMATIVO: desde agosto de 2026 no existe el rol de soporte
    (todos son vendedores) y nadie tiene que cubrir a nadie, así que no hay
    alarma roja, ni "Yo lo cubro", ni vencimientos. Solo se muestra lo que se
    puede afirmar: quién está conectado, quién avisó por qué no está, y a quién
    no se espera hoy. Quien está en su turno y no ha dado señal no aparece en
    ninguna lista — la falta de registro queda en el historial (y en Gestión),
    no como un aviso que alguien tendría que atender.

    Listas que devuelve:
      - en_linea:            señal reciente (< UMBRAL_INACTIVO_MIN)
      - ausencia_informada:  en turno pero con una explicación — estado propio
        (almuerzo, zona presencial), sede presencial marcada en la hoja
        (Santa Fe, El Tesoro, Mostrador) o una novedad reportada
      - por_entrar:          su turno todavía no empieza
      - no_se_espera:        compensatorio / ausencia / cambio de horario /
        vacaciones, y los turnos que ya terminaron
    """
    presencia = presencia or {}
    estados = estados or {}
    novedades = novedades or []
    ajustes = ajustes or {}

    roles = horario.get("roles") or {}
    dia_idx = ahora.weekday()                      # 0 = lunes … 6 = domingo
    clave_dia = "sem" if dia_idx <= 4 else ("sab" if dia_idx == 5 else "dom")
    ahora_h = ahora.hour + ahora.minute / 60.0

    # Hora de cierre del día = la más tardía entre los turnos. Pasada esa hora
    # no se muestra a nadie: el día operativo terminó.
    _turnos_hoy = {**TURNOS, **(horario.get("turnos") or {})}
    cierre_dia = max(v.get(clave_dia, v.get("sem", (0.0, 0.0)))[1] for v in _turnos_hoy.values())

    vacaciones_set = {_norm(n) for n in horario.get("vacaciones", []) if _norm(n)}

    res = {"ausencia_informada": [], "en_linea": [],
           "por_entrar": [], "no_se_espera": [], "novedades": novedades,
           "ajustes": sorted(ajustes.values(), key=lambda x: x.get("ts", 0)),
           "dia": DIAS[dia_idx], "semana": _semana_actual(ahora),
           "hora": ahora.strftime("%I:%M %p")}

    nov_por_clave = {}
    for n in novedades:
        nov_por_clave.setdefault(n.get("clave"), n)

    asignaciones_hoy = _aplicar_ajustes(
        horario.get("asignaciones", []), ajustes, dia_idx, roles)

    for a in asignaciones_hoy:
        k = _norm(a["nombre"])
        rol = roles.get(k, "")

        # Vacaciones manda sobre cualquier otra cosa que diga el cuadro para
        # esta persona (turno normal, compensatorio, lo que sea).
        if k in vacaciones_set:
            res["no_se_espera"].append(
                {"nombre": a["nombre"], "turno": a["turno"], "rol": rol,
                 "estado_horario": "vacaciones", "etiqueta": "Vacaciones",
                 "desde": "", "hasta": "", "vacaciones": True})
            continue

        info = ESTADOS.get(a["estado"], ESTADOS["normal"])
        ventana = (horario.get("turnos", {}).get(a["turno"])
                   or TURNOS.get(a["turno"], TURNOS[1]))
        ini, fin = ventana.get(clave_dia, ventana.get("sem", (8.0, 16.0)))
        # Un ajuste de entrada tardía corre el inicio de su turno de hoy.
        ini_aj = _hora_a_decimal(a.get("entrada_ajustada"))
        if ini_aj is not None:
            ini = ini_aj
        item = {"nombre": a["nombre"], "turno": a["turno"], "rol": rol,
                "estado_horario": a["estado"], "etiqueta": info["etiqueta"],
                "desde": _fmt_hora(ini), "hasta": _fmt_hora(fin)}
        if a.get("ajuste"):
            item["ajuste"] = a["ajuste"]
            item["ajuste_nota"] = a.get("ajuste_nota", "")

        # Compensatorio / Ausencia / Cambio de horario: hoy no viene.
        if not info["cubrir"]:
            item["no_viene_hoy"] = True
            res["no_se_espera"].append(item)
            continue

        if ahora_h < ini:
            res["por_entrar"].append(item)
            continue

        dentro_turno = ahora_h <= fin  # False = su turno ya terminó, el día sigue

        # Sede presencial marcada en la hoja: está trabajando, pero no en
        # chats, y eso se sabe de antemano — no depende de señal ni de novedad.
        if dentro_turno and info.get("sede"):
            item["estado"] = a["estado"]
            item["estado_etq"] = info["etiqueta"]
            item["sede"] = True
            res["ausencia_informada"].append(item)
            continue

        pres = presencia.get(k) or {}
        ts = pres.get("ts")
        mins = None if not ts else max(0.0, (time.time() - ts) / 60.0)
        item["min_sin_senal"] = None if mins is None else int(mins)
        if pres.get("primera_ts"):
            item["entro"] = datetime.fromtimestamp(pres["primera_ts"]).strftime("%I:%M %p")

        est = estados.get(k)
        nov = nov_por_clave.get(k)

        if dentro_turno:
            # Almuerzo automático: dentro de la ventana de su turno se marca
            # solo, sin que la persona tenga que seleccionarlo — lo único que
            # lo invalida es haber marcado "Desconectado" explícitamente.
            alm_ini, alm_fin = (horario.get("almuerzos", {}).get(a["turno"])
                                or ALMUERZOS.get(a["turno"], (None, None)))
            desconectado = bool(est and est["estado"] == "desconectado")
            if alm_ini is not None and alm_ini <= ahora_h < alm_fin and not desconectado:
                est = {"estado": "almuerzo", "ts": _ts_hoy(ahora, alm_ini)}

            # 1) Estado explícito que dice que no está atendiendo
            if est and not ESTADOS_ASESOR.get(est["estado"], {}).get("atiende", True):
                item["estado"] = est["estado"]
                item["estado_etq"] = ESTADOS_ASESOR[est["estado"]]["etiqueta"]
                item["desde_estado"] = datetime.fromtimestamp(est["ts"]).strftime("%I:%M %p")
                if est["estado"] == ESTADO_PRESENCIAL:
                    item["sede"] = True
                res["ausencia_informada"].append(item)
                continue

        # 2) Señal reciente → está trabajando (o se quedó ayudando tras su
        # turno). Va antes que la novedad: si la persona está dando señal, eso
        # pesa más que un permiso reportado que a lo mejor ya no aplica.
        if mins is not None and mins <= UMBRAL_INACTIVO_MIN:
            if est:
                item["estado"] = est["estado"]
                item["estado_etq"] = ESTADOS_ASESOR.get(est["estado"], {}).get("etiqueta", "")
            res["en_linea"].append(item)
            continue

        # Pasado el cierre del día no queda nada que informar de quien no dio
        # señal: se deja de mostrar hasta que abra el día siguiente. La
        # comprobación va DESPUÉS de "En línea" a propósito — quien sí está
        # dando señal se sigue mostrando aunque sea más tarde del cierre,
        # porque se quedó trabajando y eso es un hecho, no una suposición.
        # (Con el turno 3 en 10am-6pm, el cierre de un día de semana bajó a las
        # 7pm: con la comprobación antes, el panel quedaba en blanco a las 7:01
        # aunque hubiera gente conectada.)
        if ahora_h > cierre_dia:
            continue

        # 3) Novedad reportada (ausencia, llegada tarde, capacitación…)
        if nov:
            item["novedad"] = nov.get("tipo")
            item["nota"] = nov.get("nota", "")
            if nov.get("tipo") == "Apoyo a presencial":
                item["sede"] = True
            res["ausencia_informada"].append(item)
            continue

        # 4) Su turno ya terminó y el día operativo sigue: informativo.
        if not dentro_turno:
            item["turno_terminado"] = True
            res["no_se_espera"].append(item)
            continue

        # En su turno y sin señal ni explicación: no se muestra en ninguna
        # lista. La falta de registro queda en el historial, para Gestión.

    # Vacaciones sin ninguna fila en el cuadro esta semana (persona que solo
    # vive en esa lista, sin turno asignado): igual se muestra.
    nombres_procesados_hoy = {_norm(a["nombre"]) for a in asignaciones_hoy}
    for nombre_original in horario.get("vacaciones", []):
        k = _norm(nombre_original)
        if not k or k in nombres_procesados_hoy:
            continue
        res["no_se_espera"].append(
            {"nombre": nombre_original, "turno": 0, "rol": roles.get(k, ""),
             "estado_horario": "vacaciones", "etiqueta": "Vacaciones",
             "desde": "", "hasta": "", "vacaciones": True})

    res["ausencia_informada"].sort(key=lambda x: x["nombre"])
    res["en_linea"].sort(key=lambda x: x["nombre"])
    res["por_entrar"].sort(key=lambda x: (x["turno"], x["nombre"]))
    res["no_se_espera"].sort(key=lambda x: (x["turno"], x["nombre"]))
    return res


def clave(nombre):
    """Misma normalización que el almacén, para cruzar nombres."""
    return _norm(nombre)


def personas_del_horario(horario):
    """Nombres únicos del horario, para el selector del panel. Incluye a los
    auxiliares de bodega, que usan la calculadora aunque no tengan turno en el
    cuadro (por eso no aparecen en las listas del panel)."""
    vistos, out = set(), []
    nombres = [a["nombre"] for a in horario.get("asignaciones", [])]
    nombres += horario.get("auxiliares") or []
    for nombre in nombres:
        k = _norm(nombre)
        if k and k not in vistos:
            vistos.add(k)
            out.append(nombre)
    return sorted(out)


def es_auxiliar_bodega(horario, nombre):
    """True si ese nombre está en la columna 'Auxiliares de bodega' de la hoja."""
    k = _norm(nombre)
    return bool(k) and k in {_norm(n) for n in (horario.get("auxiliares") or [])}


def obtener_horario(ruta_credenciales):
    """Descarga el horario (y los roles si existen). Devuelve la estructura
    parseada o {'error': ...}."""
    if not ruta_credenciales:
        return {"error": "Falta la ruta al archivo de credenciales."}
    try:
        gc = gspread.service_account(filename=ruta_credenciales, scopes=_SCOPES)
        try:
            gc.http_client.set_timeout(25)
        except AttributeError:
            pass
        ss = gc.open_by_key(_SHEET_ID)

        meta = ss.fetch_sheet_metadata(params={
            "includeGridData": "true", "ranges": f"'{_HOJA}'",
        })
        res = parsear_horario(meta)
        if "error" in res:
            return res

        # Roles: la hoja opcional 'Roles' es hoy la única fuente de roles
        # (el "*" del cuadro dejó de asignar ninguno). Se usa setdefault por
        # si el cuadro vuelve a aportar roles en el futuro: lo que venga de
        # ahí manda sobre una fila vieja o mal tipeada de esta hoja.
        try:
            meta_r = ss.fetch_sheet_metadata(params={
                "includeGridData": "true", "ranges": f"'{_HOJA_ROLES}'!A1:C60",
            })
            for k, v in parsear_roles(meta_r).items():
                res["roles"].setdefault(k, v)
        except Exception:
            pass

        # Almuerzo: si la hoja no trae la tabla, se usa el respaldo por código.
        if not res.get("almuerzos"):
            res["almuerzos"] = dict(ALMUERZOS)
        return res
    except FileNotFoundError:
        return {"error": "No se encontró el archivo de credenciales."}
    except Exception as e:
        log.warning("Fallo al leer el horario de turnos", exc_info=True)
        msg = str(e)
        if "not found" in msg.lower() or "unable to parse range" in msg.lower():
            return {"error": f"No existe la hoja '{_HOJA}' en el documento configurado."}
        return {"error": "No se pudo leer el horario. Verifique la hoja y los permisos."}
