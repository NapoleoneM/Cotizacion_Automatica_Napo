"""Almacén del chat center: presencia, estados, novedades y coberturas.

SQLite en el volumen del servidor. A diferencia del almacén anterior (un JSON
que se borraba cada día), aquí **queda historial**: es lo que permite que la
jefa mire puntualidad, reincidencias y minutos sin cobertura por semana, y lo
que la Torre de Control consume para su análisis.

Qué guarda:
  - presencia:  última señal de cada persona por día (la envía la calculadora)
  - estados:    cada cambio de estado del asesor (disponible, almuerzo, …)
  - novedades:  ausencias/retrasos con franja afectada y quién las cubrió
  - coberturas: quién cubrió a quién y por cuánto tiempo

Solo datos de coordinación: primer nombre y marcas de tiempo. Nada sensible.
"""
import os
import re
import sqlite3
import threading
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta

from core.app_config import log

_DIR_DATOS = os.environ.get("ESTADO_DIR", os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "datos"))
_BD = os.path.join(_DIR_DATOS, "chatcenter.sqlite3")

_lock = threading.Lock()
_iniciada = False

# Estados que puede marcar el asesor. 'atiende' = está trabajando en chats.
ESTADOS_ASESOR = {
    "disponible": {"etiqueta": "Disponible", "atiende": True},
    "en_chat": {"etiqueta": "En chat", "atiende": True},
    # Cuando la zona presencial se llena (o falta una vendedora presencial), un
    # vendedor de chats pasa a atender allá. No es una ausencia: es un traslado
    # por prioridad de cliente presencial, y sus chats quedan sin atender, así
    # que soporte debe cubrirlos. Se mide aparte porque frena la operación.
    "presencial": {"etiqueta": "En zona presencial", "atiende": False},
    "bano": {"etiqueta": "Baño", "atiende": False},
    "almuerzo": {"etiqueta": "Almuerzo", "atiende": False},
    "capacitacion": {"etiqueta": "Capacitación", "atiende": False},
    "reunion": {"etiqueta": "Reunión", "atiende": False},
    "desconectado": {"etiqueta": "Desconectado", "atiende": False},
}

# Estado que representa el traslado a la zona presencial (para las métricas).
ESTADO_PRESENCIAL = "presencial"

TIPOS_NOVEDAD = ["Ausencia", "Llegada tarde", "Salida anticipada", "Permiso",
                 "Incapacidad", "Cita médica", "Apoyo a presencial", "Otro"]

# Novedades que dejan un puesto sin atender: el panel suena para avisar a soporte.
# Una "Llegada tarde" o una "Cita médica" avisada no despiertan la alarma.
# "Apoyo a presencial" también avisa: deja chats sin atender aunque la persona
# esté trabajando, y es justo lo que soporte necesita saber para entrar.
TIPOS_IMPORTANTES = {"Ausencia", "Incapacidad", "Salida anticipada",
                     "Apoyo a presencial"}


def clave(nombre):
    """Normaliza el nombre a una clave estable ('Angélica' -> 'angelica')."""
    t = unicodedata.normalize("NFKD", str(nombre or "").strip().lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def hoy():
    return datetime.now().strftime("%Y-%m-%d")


@contextmanager
def _con():
    """Conexión por operación (la carga es baja) protegida por un lock, para no
    pelear entre peticiones concurrentes de uvicorn."""
    _init()
    with _lock:
        cx = sqlite3.connect(_BD, timeout=10)
        cx.row_factory = sqlite3.Row
        try:
            yield cx
            cx.commit()
        finally:
            cx.close()


def _init():
    global _iniciada
    if _iniciada:
        return
    os.makedirs(_DIR_DATOS, exist_ok=True)
    cx = sqlite3.connect(_BD, timeout=10)
    try:
        cx.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS presencia (
            clave TEXT NOT NULL, fecha TEXT NOT NULL,
            nombre TEXT NOT NULL, ts REAL NOT NULL,
            primera_ts REAL NOT NULL,
            PRIMARY KEY (clave, fecha)
        );
        CREATE TABLE IF NOT EXISTS estados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT NOT NULL, nombre TEXT NOT NULL,
            estado TEXT NOT NULL, fecha TEXT NOT NULL, ts REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_estados ON estados(fecha, clave, ts);
        CREATE TABLE IF NOT EXISTS novedades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT NOT NULL, nombre TEXT NOT NULL,
            tipo TEXT NOT NULL, nota TEXT DEFAULT '',
            reportado_por TEXT DEFAULT '',
            fecha TEXT NOT NULL, ts REAL NOT NULL,
            desde TEXT, hasta TEXT,
            cubierto_por TEXT DEFAULT '', activa INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS ix_novedades ON novedades(fecha, clave);
        CREATE TABLE IF NOT EXISTS ajustes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave TEXT NOT NULL, nombre TEXT NOT NULL,
            fecha TEXT NOT NULL, tipo TEXT NOT NULL,
            turno INTEGER, hora TEXT,
            nota TEXT DEFAULT '', autor TEXT DEFAULT '',
            ts REAL NOT NULL, activo INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS ix_ajustes ON ajustes(fecha, clave);
        CREATE TABLE IF NOT EXISTS personas (
            clave TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'Red social',
            turno INTEGER NOT NULL DEFAULT 1,
            activa INTEGER NOT NULL DEFAULT 1,
            orden INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS coberturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            clave_titular TEXT NOT NULL, titular TEXT NOT NULL,
            clave_soporte TEXT NOT NULL, soporte TEXT NOT NULL,
            fecha TEXT NOT NULL, desde REAL NOT NULL, hasta REAL
        );
        CREATE INDEX IF NOT EXISTS ix_coberturas ON coberturas(fecha, clave_titular);
        """)
        cx.commit()
    finally:
        cx.close()
    _iniciada = True


# =======================================================
# EQUIPO (personas del chat center)
# =======================================================
# Permite trabajar SIN la hoja de horarios: la jefa registra aquí a su equipo y
# el panel ya tiene nombres, roles y turnos. Si además existe la hoja, esa manda
# (trae compensatorios y cambios por color).
ROLES = ["Red social", "Página web", "Soporte", "Venta presencial",
         "Apoyo jefatura / Soporte", "Jefa de ventas"]


def guardar_persona(nombre, rol="Red social", turno=1, activa=True, orden=None):
    k, n = clave(nombre), str(nombre or "").strip()[:40]
    if not k:
        return None
    try:
        t = int(turno)
    except (TypeError, ValueError):
        t = 1
    t = t if t in (1, 2, 3) else 1
    r = str(rol or "Red social").strip()[:30]
    with _con() as cx:
        if orden is None:
            fila = cx.execute("SELECT orden FROM personas WHERE clave=?", (k,)).fetchone()
            if fila:
                orden = fila["orden"]
            else:
                mx = cx.execute("SELECT COALESCE(MAX(orden), 0) AS m FROM personas").fetchone()["m"]
                orden = mx + 1
        cx.execute("""
            INSERT INTO personas (clave, nombre, rol, turno, activa, orden)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(clave) DO UPDATE SET
              nombre=excluded.nombre, rol=excluded.rol,
              turno=excluded.turno, activa=excluded.activa
        """, (k, n, r, t, 1 if activa else 0, orden))
    return {"clave": k, "nombre": n, "rol": r, "turno": t, "activa": bool(activa)}


def quitar_persona(nombre):
    """Se desactiva, no se borra: el historial de esa persona sigue teniendo
    sentido (novedades y coberturas viejas la siguen apuntando)."""
    with _con() as cx:
        cur = cx.execute("UPDATE personas SET activa=0 WHERE clave=?", (clave(nombre),))
        return cur.rowcount


def equipo(solo_activas=True):
    q = "SELECT * FROM personas"
    if solo_activas:
        q += " WHERE activa=1"
    q += " ORDER BY turno, orden, nombre"
    with _con() as cx:
        return [dict(r) for r in cx.execute(q).fetchall()]


# =======================================================
# PRESENCIA
# =======================================================
def marcar_visto(nombre):
    """Señal de que la persona está activa (la envía sola la calculadora).
    Guarda también la PRIMERA señal del día, que es la hora de entrada real."""
    k, n = clave(nombre), str(nombre).strip()[:40]
    if not k:
        return
    ahora, f = time.time(), hoy()
    with _con() as cx:
        cx.execute("""
            INSERT INTO presencia (clave, fecha, nombre, ts, primera_ts)
            VALUES (?,?,?,?,?)
            ON CONFLICT(clave, fecha) DO UPDATE SET ts=excluded.ts, nombre=excluded.nombre
        """, (k, f, n, ahora, ahora))


def presencia_del_dia(fecha=None):
    """{clave: {'ts':…, 'primera_ts':…, 'nombre':…}} del día pedido."""
    with _con() as cx:
        filas = cx.execute(
            "SELECT clave, nombre, ts, primera_ts FROM presencia WHERE fecha=?",
            (fecha or hoy(),)).fetchall()
    return {r["clave"]: dict(r) for r in filas}


# =======================================================
# ESTADOS
# =======================================================
def marcar_estado(nombre, estado):
    """Registra un cambio de estado. Devuelve el estado guardado o None."""
    est = str(estado or "").strip().lower()
    if est not in ESTADOS_ASESOR:
        return None
    k, n = clave(nombre), str(nombre).strip()[:40]
    if not k:
        return None
    with _con() as cx:
        cx.execute("INSERT INTO estados (clave, nombre, estado, fecha, ts) VALUES (?,?,?,?,?)",
                   (k, n, est, hoy(), time.time()))
    # Marcar estado también cuenta como señal de vida
    marcar_visto(nombre)
    return est


def estados_actuales(fecha=None):
    """Último estado de cada persona en el día: {clave: {'estado','ts',…}}."""
    with _con() as cx:
        filas = cx.execute("""
            SELECT e.clave, e.nombre, e.estado, e.ts
            FROM estados e
            JOIN (SELECT clave, MAX(ts) AS mx FROM estados WHERE fecha=? GROUP BY clave) u
              ON u.clave = e.clave AND u.mx = e.ts
            WHERE e.fecha=?
        """, (fecha or hoy(), fecha or hoy())).fetchall()
    return {r["clave"]: dict(r) for r in filas}


# =======================================================
# NOVEDADES
# =======================================================
def reportar_novedad(nombre, tipo, nota="", reportado_por="", desde="", hasta=""):
    k, n = clave(nombre), str(nombre).strip()[:40]
    if not k:
        return None
    f, ahora = hoy(), time.time()
    with _con() as cx:
        # Una novedad activa por persona y tipo: la nueva sustituye la anterior
        cx.execute("UPDATE novedades SET activa=0 WHERE fecha=? AND clave=? AND tipo=? AND activa=1",
                   (f, k, str(tipo)[:30]))
        cur = cx.execute("""
            INSERT INTO novedades (clave, nombre, tipo, nota, reportado_por, fecha, ts, desde, hasta)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (k, n, str(tipo)[:30], str(nota)[:200], str(reportado_por)[:40], f, ahora,
              str(desde)[:5] or None, str(hasta)[:5] or None))
        nid = cur.lastrowid
    return novedad(nid)


def novedad(nid):
    with _con() as cx:
        r = cx.execute("SELECT * FROM novedades WHERE id=?", (nid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["hora"] = datetime.fromtimestamp(d["ts"]).strftime("%I:%M %p")
    d["importante"] = d["tipo"] in TIPOS_IMPORTANTES
    return d


def novedades_del_dia(fecha=None, solo_activas=True):
    q = "SELECT * FROM novedades WHERE fecha=?"
    if solo_activas:
        q += " AND activa=1"
    q += " ORDER BY ts DESC"
    with _con() as cx:
        filas = cx.execute(q, (fecha or hoy(),)).fetchall()
    out = []
    for r in filas:
        d = dict(r)
        d["hora"] = datetime.fromtimestamp(d["ts"]).strftime("%I:%M %p")
        d["importante"] = d["tipo"] in TIPOS_IMPORTANTES
        out.append(d)
    return out


def quitar_novedad(nombre, tipo=None, fecha=None):
    """Desactiva (no borra: el historial queda) las novedades de una persona."""
    k = clave(nombre)
    f = fecha or hoy()
    with _con() as cx:
        if tipo:
            cur = cx.execute("UPDATE novedades SET activa=0 WHERE fecha=? AND clave=? AND tipo=? AND activa=1",
                             (f, k, tipo))
        else:
            cur = cx.execute("UPDATE novedades SET activa=0 WHERE fecha=? AND clave=? AND activa=1", (f, k))
        return cur.rowcount


# =======================================================
# AJUSTES DEL DÍA
# =======================================================
# El plan de la semana vive en la hoja de Sheets. Cuando hay que mover algo a
# última hora (no llegó alguien, se corre un turno para tapar el hueco), el
# cambio se registra aquí: aplica SOLO a esa fecha y no toca el plan.
TIPOS_AJUSTE = {
    "turno":    {"etiqueta": "Cambia de turno", "pide": "turno"},
    "entrada":  {"etiqueta": "Entra más tarde", "pide": "hora"},
    "no_viene": {"etiqueta": "Hoy no viene", "pide": None},
    "extra":    {"etiqueta": "Entra extra (no programado)", "pide": "turno"},
}


def registrar_ajuste(nombre, tipo, turno=None, hora="", nota="", autor="", fecha=None):
    """Guarda un ajuste para un día. Uno por persona y tipo: el nuevo reemplaza."""
    t = str(tipo or "").strip().lower()
    if t not in TIPOS_AJUSTE:
        return None
    k, n = clave(nombre), str(nombre or "").strip()[:40]
    if not k:
        return None
    try:
        tn = int(turno) if turno is not None else None
    except (TypeError, ValueError):
        tn = None
    if tn is not None and tn not in (1, 2, 3):
        tn = None
    h = str(hora or "").strip()[:5]
    if h and not re.match(r"^\d{1,2}:\d{2}$", h):
        h = ""
    f = fecha or hoy()
    with _con() as cx:
        cx.execute("UPDATE ajustes SET activo=0 WHERE fecha=? AND clave=? AND tipo=? AND activo=1",
                   (f, k, t))
        cur = cx.execute("""
            INSERT INTO ajustes (clave, nombre, fecha, tipo, turno, hora, nota, autor, ts)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (k, n, f, t, tn, h or None, str(nota)[:200], str(autor)[:40], time.time()))
        nid = cur.lastrowid
    with _con() as cx:
        r = cx.execute("SELECT * FROM ajustes WHERE id=?", (nid,)).fetchone()
    d = dict(r)
    d["etiqueta"] = TIPOS_AJUSTE[t]["etiqueta"]
    return d


def ajustes_del_dia(fecha=None):
    """{clave: {…}} de los ajustes activos del día (uno por persona; si hay
    varios tipos, gana el último registrado)."""
    with _con() as cx:
        filas = cx.execute("""
            SELECT * FROM ajustes WHERE fecha=? AND activo=1 ORDER BY ts
        """, (fecha or hoy(),)).fetchall()
    out = {}
    for r in filas:
        d = dict(r)
        d["etiqueta"] = TIPOS_AJUSTE.get(d["tipo"], {}).get("etiqueta", d["tipo"])
        d["hora_registro"] = datetime.fromtimestamp(d["ts"]).strftime("%I:%M %p")
        out[d["clave"]] = d
    return out


def quitar_ajuste(nombre, tipo=None, fecha=None):
    k, f = clave(nombre), fecha or hoy()
    with _con() as cx:
        if tipo:
            cur = cx.execute("UPDATE ajustes SET activo=0 WHERE fecha=? AND clave=? AND tipo=? AND activo=1",
                             (f, k, tipo))
        else:
            cur = cx.execute("UPDATE ajustes SET activo=0 WHERE fecha=? AND clave=? AND activo=1", (f, k))
        return cur.rowcount


# =======================================================
# COBERTURAS ("yo lo cubro")
# =======================================================
def abrir_cobertura(titular, soporte):
    """Soporte declara que está cubriendo a un titular. Si ya había una abierta
    para ese titular hoy, se cierra antes (una cobertura activa por persona)."""
    kt, ks = clave(titular), clave(soporte)
    if not kt or not ks:
        return None
    f, ahora = hoy(), time.time()
    with _con() as cx:
        cx.execute("UPDATE coberturas SET hasta=? WHERE fecha=? AND clave_titular=? AND hasta IS NULL",
                   (ahora, f, kt))
        cur = cx.execute("""
            INSERT INTO coberturas (clave_titular, titular, clave_soporte, soporte, fecha, desde)
            VALUES (?,?,?,?,?,?)
        """, (kt, str(titular).strip()[:40], ks, str(soporte).strip()[:40], f, ahora))
        # La novedad activa (si hay) queda marcada con quién cubre
        cx.execute("UPDATE novedades SET cubierto_por=? WHERE fecha=? AND clave=? AND activa=1",
                   (str(soporte).strip()[:40], f, kt))
        return cur.lastrowid


def cerrar_cobertura(titular):
    kt, f = clave(titular), hoy()
    with _con() as cx:
        cur = cx.execute("UPDATE coberturas SET hasta=? WHERE fecha=? AND clave_titular=? AND hasta IS NULL",
                         (time.time(), f, kt))
        return cur.rowcount


def coberturas_activas(fecha=None):
    """{clave_titular: {'soporte':…, 'desde':…}} de las coberturas abiertas."""
    with _con() as cx:
        filas = cx.execute("""
            SELECT clave_titular, titular, soporte, desde FROM coberturas
            WHERE fecha=? AND hasta IS NULL
        """, (fecha or hoy(),)).fetchall()
    out = {}
    for r in filas:
        d = dict(r)
        d["desde_hora"] = datetime.fromtimestamp(d["desde"]).strftime("%I:%M %p")
        out[d["clave_titular"]] = d
    return out


# =======================================================
# HISTORIAL / MÉTRICAS (para la jefa y para la Torre)
# =======================================================
def rango_semana(fecha=None):
    """(lunes, domingo) de la semana de la fecha dada, en texto YYYY-MM-DD."""
    d = datetime.strptime(fecha, "%Y-%m-%d") if fecha else datetime.now()
    lunes = d - timedelta(days=d.weekday())
    return lunes.strftime("%Y-%m-%d"), (lunes + timedelta(days=6)).strftime("%Y-%m-%d")


def minutos_por_estado(desde, hasta, estado):
    """Minutos acumulados por persona en un estado, dentro del rango.

    Cada fila de `estados` es un cambio: un tramo dura hasta el cambio siguiente
    del mismo día. Si el día terminó sin otro cambio no se puede saber cuánto
    duró, así que ese tramo cuenta 0 (preferimos quedarnos cortos antes que
    inventar minutos). El tramo abierto de HOY sí cuenta hasta ahora.
    """
    with _con() as cx:
        filas = cx.execute("""
            SELECT clave, nombre, estado, fecha, ts FROM estados
            WHERE fecha BETWEEN ? AND ? ORDER BY clave, ts
        """, (desde, hasta)).fetchall()

    por_persona = {}
    for r in filas:
        por_persona.setdefault(r["clave"], []).append(dict(r))

    ahora, hoy_txt, out = time.time(), hoy(), {}
    for k, lista in por_persona.items():
        total = 0.0
        for i, r in enumerate(lista):
            if r["estado"] != estado:
                continue
            siguiente = lista[i + 1] if i + 1 < len(lista) else None
            if siguiente and siguiente["fecha"] == r["fecha"]:
                fin = siguiente["ts"]
            elif r["fecha"] == hoy_txt:
                fin = ahora                     # tramo abierto de hoy
            else:
                continue                        # no se sabe cuándo terminó
            total += max(0.0, (fin - r["ts"]) / 60.0)
        if total:
            out[k] = {"nombre": lista[0]["nombre"], "minutos": int(total)}
    return out


def resumen(desde, hasta):
    """Métricas por persona en un rango de fechas (inclusive), para el análisis:
    días con señal, hora de entrada más frecuente, novedades por tipo,
    minutos cubierto y veces que fue cubierto."""
    with _con() as cx:
        pres = cx.execute("""
            SELECT clave, nombre, fecha, primera_ts FROM presencia
            WHERE fecha BETWEEN ? AND ? ORDER BY fecha
        """, (desde, hasta)).fetchall()
        novs = cx.execute("""
            SELECT clave, nombre, tipo, fecha, cubierto_por FROM novedades
            WHERE fecha BETWEEN ? AND ? AND activa=1
        """, (desde, hasta)).fetchall()
        cobs = cx.execute("""
            SELECT clave_titular, titular, soporte, desde, hasta FROM coberturas
            WHERE fecha BETWEEN ? AND ?
        """, (desde, hasta)).fetchall()

    personas = {}

    def item(k, nombre):
        if k not in personas:
            personas[k] = {"nombre": nombre, "dias_con_senal": 0, "entradas": [],
                           "novedades": {}, "total_novedades": 0,
                           "veces_cubierto": 0, "minutos_cubierto": 0,
                           "veces_cubriendo": 0, "minutos_presencial": 0}
        return personas[k]

    for r in pres:
        it = item(r["clave"], r["nombre"])
        it["dias_con_senal"] += 1
        it["entradas"].append(datetime.fromtimestamp(r["primera_ts"]).strftime("%H:%M"))

    for r in novs:
        it = item(r["clave"], r["nombre"])
        it["novedades"][r["tipo"]] = it["novedades"].get(r["tipo"], 0) + 1
        it["total_novedades"] += 1

    for r in cobs:
        it = item(r["clave_titular"], r["titular"])
        it["veces_cubierto"] += 1
        fin = r["hasta"] or time.time()
        it["minutos_cubierto"] += max(0, int((fin - r["desde"]) / 60))
        sop = item(clave(r["soporte"]), r["soporte"])
        sop["veces_cubriendo"] += 1

    # Tiempo que se desvió de chats a la zona presencial (prioridad de cliente
    # presencial): es el costo operativo que la jefa necesita ver.
    for k, v in minutos_por_estado(desde, hasta, ESTADO_PRESENCIAL).items():
        item(k, v["nombre"])["minutos_presencial"] = v["minutos"]

    for it in personas.values():
        it["entrada_tipica"] = (sorted(it["entradas"])[len(it["entradas"]) // 2]
                                if it["entradas"] else "—")
        it.pop("entradas", None)

    return {"desde": desde, "hasta": hasta,
            "personas": sorted(personas.values(), key=lambda x: x["nombre"]),
            "totales": {
                "novedades": sum(p["total_novedades"] for p in personas.values()),
                "minutos_cubierto": sum(p["minutos_cubierto"] for p in personas.values()),
                "minutos_presencial": sum(p["minutos_presencial"] for p in personas.values()),
                "personas": len(personas),
            }}


def historial(desde, hasta):
    """Volcado crudo para que la Torre de Control haga su propio análisis."""
    with _con() as cx:
        def tabla(sql):
            return [dict(r) for r in cx.execute(sql, (desde, hasta)).fetchall()]
        return {
            "desde": desde, "hasta": hasta,
            "presencia": tabla("SELECT * FROM presencia WHERE fecha BETWEEN ? AND ?"),
            "estados": tabla("SELECT * FROM estados WHERE fecha BETWEEN ? AND ? ORDER BY ts"),
            "novedades": tabla("SELECT * FROM novedades WHERE fecha BETWEEN ? AND ?"),
            "coberturas": tabla("SELECT * FROM coberturas WHERE fecha BETWEEN ? AND ?"),
        }


def minutos_desde(ts):
    return None if not ts else max(0.0, (time.time() - ts) / 60.0)
