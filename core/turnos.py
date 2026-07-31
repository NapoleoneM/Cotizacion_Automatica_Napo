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
from core.almacen import ESTADOS_ASESOR
# Por defecto se usa el mismo documento espejo al que ya tiene acceso el
# service account; basta agregarle una hoja con el cuadro de horarios.
from core.mayorista_logic import _SPREADSHEET_ID as _ESPEJO_ID

_SHEET_ID = os.environ.get("TURNOS_SHEET_ID", _ESPEJO_ID)
_HOJA = os.environ.get("TURNOS_HOJA", "Horarios")
_HOJA_ROLES = os.environ.get("TURNOS_HOJA_ROLES", "Roles")
_RANGO = "A1:AH60"
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Horarios de cada turno: (hora_inicio, hora_fin) en formato 24h decimal.
# 'sem' = lunes a viernes, 'sab' = sábado, 'dom' = domingo.
TURNOS = {
    1: {"sem": (8.0, 16.0), "sab": (8.0, 15.0), "dom": (8.0, 15.0)},
    2: {"sem": (11.0, 19.0), "sab": (10.0, 17.0), "dom": (10.0, 17.0)},
    3: {"sem": (14.0, 21.0), "sab": (11.0, 18.0), "dom": (11.0, 18.0)},
}

DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Estados de la leyenda. 'cubrir' indica si, estando en ese estado, se espera
# que la persona esté atendiendo (y por tanto soporte debe cubrirla si falta).
ESTADOS = {
    "normal": {"cubrir": True, "etiqueta": ""},
    "reparte chats": {"cubrir": True, "etiqueta": "Reparte chats"},
    "santafe": {"cubrir": True, "etiqueta": "Santafé"},
    "compensatorio": {"cubrir": False, "etiqueta": "Compensatorio"},
    "ausencia": {"cubrir": False, "etiqueta": "Ausencia"},
    "cambio de horario": {"cubrir": False, "etiqueta": "Cambio de horario"},
}


# Minutos de gracia tras el inicio del turno antes de pedir cobertura, y
# tiempo sin señal de la calculadora para considerar a alguien inactivo.
TOLERANCIA_MIN = 15
UMBRAL_INACTIVO_MIN = 30

# Roles que NO requieren cobertura de soporte (soporte cubre a los de redes).
# Ojo con "jefa" y "jefe": el rol real es "Jefa de ventas", así que hay que
# contemplar las dos formas o la jefatura acabaría en la lista de cobertura.
# "presencial": las vendedoras de la tienda no atienden chats, no se cubren.
_ROLES_NO_CUBRIR = ("soporte", "jefe", "jefa", "coordin", "web", "pagina",
                    "página", "presencial")


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
        antes = t[:m.start()]
        clave = "sab" if "sabado" in antes[-25:] else ("sem" if "sem" not in res else "sab")
        res.setdefault(clave, (h1, h2))
    return res


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

    # --- 4) Bloques de turno ---
    marcas = []   # (fila, numero_turno, texto)
    for r in range(fila_encabezado + 1, len(grid)):
        for texto, _bg in grid[r]:
            m = re.search(r"(\d+)\s*turno|turno\s*:?\s*(\d+)", _norm(texto))
            if m:
                num = int(m.group(1) or m.group(2))
                marcas.append((r, num, texto))
                break
    if not marcas:
        return {"error": "No se encontraron bloques de turno ('1 Turno …')."}

    asignaciones = []
    horarios = {}
    for i, (r_ini, num, texto) in enumerate(marcas):
        r_fin = marcas[i + 1][0] if i + 1 < len(marcas) else len(grid)
        base = dict(TURNOS.get(num, TURNOS[1]))
        base.update(_horas_del_texto(texto))       # la hoja manda si es clara
        horarios[num] = base
        for r in range(r_ini, r_fin):
            for c, dia_idx in col_dia.items():
                nombre, color = celda(r, c)
                if not nombre or len(nombre) > 30:
                    continue
                if _norm(nombre).startswith(tuple(DIAS)):
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


def _rol_cubrible(rol):
    """Soporte cubre a los vendedores de redes. Si no hay rol definido se asume
    que sí (mejor avisar de más que dejar un chat sin atender)."""
    n = _norm(rol)
    return not any(x in n for x in _ROLES_NO_CUBRIR)


def _fmt_hora(h):
    hh = int(h) % 24
    mm = int(round((h - int(h)) * 60))
    suf = "am" if hh < 12 else "pm"
    h12 = hh % 12 or 12
    return f"{h12}:{mm:02d}{suf}"


def _aplicar_ajustes(asignaciones, ajustes, dia_idx, roles):
    """Superpone los ajustes del día sobre el plan de la semana.

    El plan (la hoja) no se toca: aquí se decide qué rige HOY. Devuelve la lista
    de asignaciones del día ya ajustada, marcando lo que cambió para que soporte
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


def calcular_cobertura(horario, ahora, presencia=None, estados=None,
                       novedades=None, coberturas=None, ajustes=None):
    """Cruza el horario del día con la realidad (señal, estado, novedades) y la
    hora actual. Función pura: no toca red ni disco, se prueba con cualquier hora.

    Listas que ve soporte:
      - requieren_cobertura: en turno y SIN explicación → alarma roja
      - ausencia_informada:  en turno pero con estado (almuerzo…) o novedad
      - en_linea:            atendiendo, con señal reciente
      - por_entrar:          su turno aún no empieza (no se alerta)
      - no_se_espera:        compensatorio / ausencia / cambio de horario
    """
    presencia = presencia or {}
    estados = estados or {}
    novedades = novedades or []
    coberturas = coberturas or {}
    ajustes = ajustes or {}

    roles = horario.get("roles") or {}
    dia_idx = ahora.weekday()                      # 0 = lunes … 6 = domingo
    clave_dia = "sem" if dia_idx <= 4 else ("sab" if dia_idx == 5 else "dom")
    ahora_h = ahora.hour + ahora.minute / 60.0

    res = {"requieren_cobertura": [], "ausencia_informada": [], "en_linea": [],
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
        info = ESTADOS.get(a["estado"], ESTADOS["normal"])
        ventana = (horario.get("turnos", {}).get(a["turno"])
                   or TURNOS.get(a["turno"], TURNOS[1]))
        ini, fin = ventana.get(clave_dia, ventana.get("sem", (8.0, 16.0)))
        # Un ajuste de entrada tardía corre el inicio: antes de esa hora no se
        # alerta, porque su llegada más tarde está autorizada.
        ini_aj = _hora_a_decimal(a.get("entrada_ajustada"))
        if ini_aj is not None:
            ini = ini_aj
        item = {"nombre": a["nombre"], "turno": a["turno"], "rol": rol,
                "estado_horario": a["estado"], "etiqueta": info["etiqueta"],
                "desde": _fmt_hora(ini), "hasta": _fmt_hora(fin)}
        if a.get("ajuste"):
            item["ajuste"] = a["ajuste"]
            item["ajuste_nota"] = a.get("ajuste_nota", "")

        cob = coberturas.get(k)
        if cob:
            item["cubierto_por"] = cob.get("soporte")
            item["cubierto_desde"] = cob.get("desde_hora")

        if not info["cubrir"]:
            res["no_se_espera"].append(item)
            continue
        if ahora_h < ini + TOLERANCIA_MIN / 60.0:
            res["por_entrar"].append(item)
            continue
        if ahora_h > fin:
            continue                                # jornada terminada

        pres = presencia.get(k) or {}
        ts = pres.get("ts")
        mins = None if not ts else max(0.0, (time.time() - ts) / 60.0)
        item["min_sin_senal"] = None if mins is None else int(mins)
        if pres.get("primera_ts"):
            item["entro"] = datetime.fromtimestamp(pres["primera_ts"]).strftime("%I:%M %p")

        est = estados.get(k)
        nov = nov_por_clave.get(k)

        # 1) Estado explícito que dice que no está atendiendo → ausencia informada
        if est and not ESTADOS_ASESOR.get(est["estado"], {}).get("atiende", True):
            item["estado"] = est["estado"]
            item["estado_etq"] = ESTADOS_ASESOR[est["estado"]]["etiqueta"]
            item["desde_estado"] = datetime.fromtimestamp(est["ts"]).strftime("%I:%M %p")
            if _rol_cubrible(rol):
                res["ausencia_informada"].append(item)
            continue

        # 2) Novedad reportada (ausencia, llegada tarde…) → ausencia informada
        if nov and (mins is None or mins > UMBRAL_INACTIVO_MIN):
            item["novedad"] = nov.get("tipo")
            item["nota"] = nov.get("nota", "")
            if _rol_cubrible(rol):
                res["ausencia_informada"].append(item)
            continue

        # 3) Señal reciente → está trabajando
        if mins is not None and mins <= UMBRAL_INACTIVO_MIN:
            if est:
                item["estado"] = est["estado"]
                item["estado_etq"] = ESTADOS_ASESOR.get(est["estado"], {}).get("etiqueta", "")
            res["en_linea"].append(item)
            continue

        # 4) Sin explicación → alarma roja
        if not _rol_cubrible(rol):
            continue                                # soporte/jefe/web: no se cubre
        item["motivo"] = ("sin señal desde el inicio del turno" if mins is None
                          else f"sin actividad hace {int(mins)} min")
        res["requieren_cobertura"].append(item)

    res["requieren_cobertura"].sort(key=lambda x: (bool(x.get("cubierto_por")), x["turno"], x["nombre"]))
    res["ausencia_informada"].sort(key=lambda x: (bool(x.get("cubierto_por")), x["nombre"]))
    res["en_linea"].sort(key=lambda x: x["nombre"])
    res["por_entrar"].sort(key=lambda x: (x["turno"], x["nombre"]))
    return res


def clave(nombre):
    """Misma normalización que el almacén, para cruzar nombres."""
    return _norm(nombre)


def personas_del_horario(horario):
    """Nombres únicos del horario, para el selector del panel."""
    vistos, out = set(), []
    for a in horario.get("asignaciones", []):
        k = _norm(a["nombre"])
        if k not in vistos:
            vistos.add(k)
            out.append(a["nombre"])
    return sorted(out)


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
            "includeGridData": "true", "ranges": f"'{_HOJA}'!{_RANGO}",
        })
        res = parsear_horario(meta)
        if "error" in res:
            return res

        # Roles: hoja opcional. Si no existe, no es un problema.
        try:
            meta_r = ss.fetch_sheet_metadata(params={
                "includeGridData": "true", "ranges": f"'{_HOJA_ROLES}'!A1:C60",
            })
            res["roles"] = parsear_roles(meta_r)
        except Exception:
            res["roles"] = {}
        return res
    except FileNotFoundError:
        return {"error": "No se encontró el archivo de credenciales."}
    except Exception as e:
        log.warning("Fallo al leer el horario de turnos", exc_info=True)
        msg = str(e)
        if "not found" in msg.lower() or "unable to parse range" in msg.lower():
            return {"error": f"No existe la hoja '{_HOJA}' en el documento configurado."}
        return {"error": "No se pudo leer el horario. Verifique la hoja y los permisos."}
