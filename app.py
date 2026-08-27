"""Calculadora Napo — versión WEB (FastAPI).

Reutiliza EXACTAMENTE los mismos módulos de cálculo del escritorio
(core/cotizacion_logic.py y core/mayorista_logic.py), así que los resultados
son idénticos. El navegador nunca ve las credenciales: el servidor habla con
Google Sheets y solo devuelve resultados.

Ejecutar en desarrollo:
    pip install -r requirements.txt
    uvicorn app:app --reload --port 8000
"""
import os
import re
import time
import hmac
import secrets
import logging
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.cotizacion_logic import calcular_cotizacion
from core.mayorista_logic import obtener_precios_sheets, calcular_cotizacion_mayorista
from core.tabla_precios import obtener_tabla_precios
from core.tienda_logic import obtener_tarifas_gramo, calcular_precio_tienda
from core.turnos import (
    obtener_horario, calcular_panel, personas_del_horario, horario_desde_equipo,
    es_auxiliar_bodega,
    # El rótulo de la semana también hace falta cuando NO hay horario que
    # mostrar (misma convención de import "privado" que usa tabla_precios).
    _semana_actual,
)
from core import almacen

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("calculadora_napo")

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")

app = FastAPI(title="Calculadora Napo Web", version="2.0.1-web")

# --- Caché de precios en memoria (compartida por todos los usuarios) ---
_precios = {"datos": None, "hora": None, "tarifas_faltantes": [], "tarifas_gramo": None, "calidades_tienda": []}

# Protección de la API de Google contra abuso: el espejo se refresca cada 5 min
# del lado de Google, así que servir caché dentro de esa ventana no pierde nada,
# y un atacante en loop no puede agotar la cuota de lecturas de Sheets.
_COOLDOWN_PRECIOS = 60        # seg mínimos entre lecturas reales de precios
_TTL_TABLA = 300              # seg de vida de la tabla en caché
_ult_lectura_precios = 0.0    # time.monotonic() de la última lectura real
_tabla_cache = {"bloques": None, "ts": 0.0}


def _error_publico(res, contexto):
    """Loguea el error real (puede traer IDs/emails de la API de Google) y
    devuelve al navegador un mensaje genérico sin detalles internos."""
    log.warning("%s: %s", contexto, res.get("error"))
    return "No se pudo conectar con la fuente de precios. Intente de nuevo en unos minutos."


# =======================================================
# ACCESO POR PIN
# =======================================================
# El PIN NO se guarda en el código (el repo es público): llega por variable de
# entorno (APP_PIN en el .env del servidor). El navegador nunca lo ve; solo lo
# envía una vez y el servidor devuelve una cookie de sesión que exigen todos
# los endpoints de datos. Sin cookie válida → 401.
PIN = os.environ.get("APP_PIN", "").strip()
# PIN aparte para la jefa de ventas: da el mismo acceso más su vista de gestión.
# Si no se configura, nadie puede entrar como jefa (la vista queda deshabilitada).
PIN_JEFA = os.environ.get("APP_PIN_JEFA", "").strip()
COOKIE_SECURE = os.environ.get("PIN_COOKIE_SECURE", "1") != "0"  # 0 solo para dev local en http
NOMBRE_COOKIE = "sesion"
_TTL_SESION = 7 * 24 * 3600      # la sesión dura 7 días
_GRACIA = 2                      # fallos sin penalización (errores de dedo)
_ESPERA_BASE = 5                 # seg del primer bloqueo
_ESPERA_TOPE = 300               # tope del bloqueo (5 min)

# Rutas de la API que NO exigen sesión (todo lo demás bajo /api/ sí).
# El puente de la Torre no usa cookie: se autentica con su propio token, así que
# se excluye aquí y valida por su cuenta.
_API_PUBLICA = {"/api/acceso", "/api/sesion", "/api/torre/historial"}

# Estado en memoria (single container). Un reinicio limpia sesiones y bloqueos:
# aceptable — a lo sumo hay que reingresar el PIN.
_sesiones = {}   # token -> {"exp": time.monotonic, "rol": "asesor"|"jefa"}
_intentos = {}   # ip -> {"fails": int, "hasta": time.monotonic hasta el que está bloqueado}


def _ip_cliente(request):
    """IP real del visitante. Detrás de Traefik, request.client es la IP del
    proxy (una sola para todos), así que se usa X-Forwarded-For para no
    bloquear a todos por culpa de uno."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "desconocido"


def _nueva_sesion(rol="asesor"):
    token = secrets.token_urlsafe(32)
    _sesiones[token] = {"exp": time.monotonic() + _TTL_SESION, "rol": rol}
    return token


def _sesion(request):
    """Devuelve la sesión ({'exp','rol'}) o None si no hay o ya expiró."""
    token = request.cookies.get(NOMBRE_COOKIE)
    if not token:
        return None
    ses = _sesiones.get(token)
    if ses is None:
        return None
    if time.monotonic() > ses["exp"]:
        _sesiones.pop(token, None)
        return None
    return ses


def _sesion_valida(request):
    return _sesion(request) is not None


def _es_jefa(request):
    ses = _sesion(request)
    return bool(ses and ses.get("rol") == "jefa")


@app.middleware("http")
async def _gate_pin(request: Request, call_next):
    """Exige sesión válida para cualquier /api/ excepto login y chequeo de
    sesión. El frontend estático (index, js, css, imágenes) queda libre: no
    contiene datos reservados y necesita cargar para pedir el PIN."""
    path = request.url.path
    if path.startswith("/api/") and path not in _API_PUBLICA:
        if not _sesion_valida(request):
            return JSONResponse({"error": "No autorizado.", "requiere_pin": True}, status_code=401)
    return await call_next(request)


class AccesoReq(BaseModel):
    pin: str = Field("", max_length=12)


@app.get("/api/sesion")
def api_sesion(request: Request):
    """El frontend lo consulta al cargar para decidir si pide el PIN y si debe
    mostrar la vista de gestión (solo con el PIN de la jefa)."""
    ses = _sesion(request)
    return {"autorizado": ses is not None, "rol": (ses or {}).get("rol", "")}


@app.post("/api/acceso")
def api_acceso(req: AccesoReq, request: Request):
    """Verifica el PIN. Bloqueo escalonado por IP: tras _GRACIA fallos, la
    espera se duplica en cada error (5s, 10s, 20s… tope 5 min)."""
    ip = _ip_cliente(request)
    ahora = time.monotonic()

    # ¿IP bloqueada por fallos previos?
    est = _intentos.get(ip)
    if est and ahora < est["hasta"]:
        return JSONResponse(
            {"error": "bloqueado", "espera": int(est["hasta"] - ahora) + 1},
            status_code=429,
        )

    if not PIN:
        log.error("APP_PIN no configurado: el acceso está deshabilitado")
        return JSONResponse({"error": "Acceso no configurado en el servidor."}, status_code=503)

    # Comparación en tiempo constante (evita filtrar el PIN por tiempos).
    # Se prueba primero el de la jefa: si acierta, la sesión lleva su rol.
    enviado = req.pin.strip()
    rol = ""
    if PIN_JEFA and hmac.compare_digest(enviado, PIN_JEFA):
        rol = "jefa"
    elif hmac.compare_digest(enviado, PIN):
        rol = "asesor"

    if rol:
        _intentos.pop(ip, None)
        token = _nueva_sesion(rol)
        resp = JSONResponse({"ok": True, "rol": rol})
        resp.set_cookie(
            NOMBRE_COOKIE, token, max_age=_TTL_SESION,
            httponly=True, samesite="lax", secure=COOKIE_SECURE,
        )
        log.info("Acceso concedido a %s (rol %s)", ip, rol)
        return resp

    # Fallo: contar y, pasada la gracia, imponer espera creciente.
    fails = (est["fails"] if est else 0) + 1
    espera = 0
    if fails > _GRACIA:
        espera = min(_ESPERA_TOPE, _ESPERA_BASE * (2 ** (fails - _GRACIA - 1)))
    _intentos[ip] = {"fails": fails, "hasta": ahora + espera}
    log.warning("PIN incorrecto desde %s (intento %d, espera %ds)", ip, fails, espera)
    return JSONResponse(
        {"error": "pin_incorrecto", "espera": espera, "intentos": fails},
        status_code=401,
    )


@app.post("/api/salir")
def api_salir(request: Request):
    """Cierra la sesión (borra la cookie y el token del servidor)."""
    token = request.cookies.get(NOMBRE_COOKIE)
    if token:
        _sesiones.pop(token, None)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(NOMBRE_COOKIE)
    return resp


def ruta_credenciales():
    """Ubica credenciales/credenciales.json: variable de entorno, carpeta local
    o carpeta padre (compartida con la versión de escritorio)."""
    env = os.environ.get("GOOGLE_CREDS")
    if env and os.path.exists(env):
        return env
    for c in (
        os.path.join(BASE, "credentials", "credenciales.json"),
        os.path.join(BASE, "..", "credentials", "credenciales.json"),
    ):
        if os.path.exists(c):
            return os.path.abspath(c)
    return os.path.join(BASE, "credentials", "credenciales.json")


def _limpiar_nombre(texto):
    """Quita 'Compartir' y saltos de línea que se cuelan al copiar el nombre
    desde la tienda web (igual que en el escritorio)."""
    lineas = [ln.strip() for ln in str(texto or "").splitlines()]
    lineas = [ln for ln in lineas if ln and ln.lower() != "compartir"]
    nombre = " ".join(lineas).strip()
    if nombre.lower().startswith("compartir "):
        nombre = nombre[len("compartir "):].strip()
    return nombre


# =======================================================
# MODELOS DE PETICIÓN
# =======================================================
# Límites de tamaño: por encima de cualquier uso real, pero impiden que una
# petición gigante (listas de miles de joyas, textos de megabytes) consuma
# CPU/RAM del servidor. Si se exceden, FastAPI responde 422 automáticamente.
class JoyaRetail(BaseModel):
    nombre: str = Field("Joya", max_length=300)
    cantidad: int = Field(1, ge=0, le=10000)
    valor_unitario: str = Field("", max_length=30)


class RetailReq(BaseModel):
    joyas: list[JoyaRetail] = Field(default=[], max_length=60)
    medio_pago: str = Field("Transferencia", max_length=40)
    aplicar_envio: bool = False
    tipo_envio: str = Field("Nacional", max_length=40)
    envio_manual: str = Field("", max_length=30)


class JoyaMayorista(BaseModel):
    nombre: str = Field("Joya", max_length=300)
    cantidad: int = Field(1, ge=0, le=10000)
    peso: str = Field("", max_length=30)
    tipo: str = Field("Tipo Oro", max_length=40)
    subtipo: str = Field("Subtipo", max_length=40)
    valor_normal: str = Field("", max_length=30)


class OtroMayorista(BaseModel):
    nombre: str = Field("Extra", max_length=300)
    cantidad: int = Field(1, ge=0, le=10000)
    valor_unitario: str = Field("", max_length=30)


class MayoristaReq(BaseModel):
    joyas: list[JoyaMayorista] = Field(default=[], max_length=60)
    otros: list[OtroMayorista] = Field(default=[], max_length=60)
    aplicar_envio: bool = False
    tipo_envio: str = Field("Nacional", max_length=40)
    envio_manual: str = Field("", max_length=30)


class PrecioTiendaReq(BaseModel):
    peso: str = Field("", max_length=30)
    calidad: str = Field("", max_length=60)
    # Quién está calculando: solo los auxiliares de bodega, y solo mientras
    # estén "En zona presencial", reciben las cifras de EFFI (ver más abajo).
    nombre: str = Field("", max_length=40)


# =======================================================
# ENDPOINTS DE CÁLCULO
# =======================================================
@app.post("/api/retail")
def api_retail(req: RetailReq):
    joyas = []
    for j in req.joyas:
        d = j.model_dump()
        d["nombre"] = _limpiar_nombre(d["nombre"]) or "Joya"
        joyas.append(d)
    return calcular_cotizacion(
        joyas=joyas, medio_pago=req.medio_pago, aplicar_envio=req.aplicar_envio,
        tipo_envio=req.tipo_envio, envio_manual=req.envio_manual,
    )


@app.post("/api/mayorista")
def api_mayorista(req: MayoristaReq):
    if not _precios["datos"]:
        return {"error": "Precios no cargados. Presione 'Actualizar precios'."}
    joyas = []
    for j in req.joyas:
        d = j.model_dump()
        d["nombre"] = _limpiar_nombre(d["nombre"]) or "Joya"
        joyas.append(d)
    otros = []
    for o in req.otros:
        d = o.model_dump()
        d["nombre"] = _limpiar_nombre(d["nombre"]) or "Extra"
        otros.append(d)
    incompletas = sum(
        1 for j in joyas
        if any([j["nombre"] != "Joya", j["peso"].strip(), j["valor_normal"].strip(),
                j["tipo"] != "Tipo Oro"])
        and (j["tipo"] not in ("Nacional", "Italiano", "Bolas")
             or j["subtipo"] in ("Subtipo", "Seleccione...")
             or not j["peso"].strip())
    )
    res = calcular_cotizacion_mayorista(
        joyas=joyas, otros=otros, precios=_precios["datos"],
        aplicar_envio=req.aplicar_envio, tipo_envio=req.tipo_envio,
        envio_manual=req.envio_manual,
    )
    res["incompletas"] = incompletas
    return res


# =======================================================
# PRECIOS Y TABLA (Google Sheets, lado servidor)
# =======================================================
@app.get("/api/estado-precios")
def estado_precios():
    return {
        "cargado": _precios["datos"] is not None,
        "hora": _precios["hora"],
        "tarifas_faltantes": _precios["tarifas_faltantes"],
        "calidades_tienda": _precios["calidades_tienda"],
    }


@app.post("/api/actualizar-precios")
def actualizar_precios():
    global _ult_lectura_precios

    # Cooldown: si ya se leyó hace poco, responder con lo que hay en memoria.
    # El espejo solo cambia cada 5 min, así que el usuario no pierde frescura.
    if _precios["datos"] is not None and time.monotonic() - _ult_lectura_precios < _COOLDOWN_PRECIOS:
        return {
            "ok": True, "hora": _precios["hora"], "tarifas_faltantes": _precios["tarifas_faltantes"],
            "calidades_tienda": _precios["calidades_tienda"],
        }

    res = obtener_precios_sheets(ruta_credenciales())
    if "error" in res:
        return {"error": _error_publico(res, "actualizar-precios"), "cargado": _precios["datos"] is not None}
    _ult_lectura_precios = time.monotonic()
    _precios["datos"] = res["datos"]
    _precios["hora"] = datetime.now().strftime("%d/%m/%Y %I:%M %p")
    _precios["tarifas_faltantes"] = res.get("tarifas_faltantes") or []

    # Tarifas de tienda (pricing_gramo): no crítico si falla — Mayorista sigue
    # funcionando aunque la hoja aún no exista en el espejo.
    res_tienda = obtener_tarifas_gramo(ruta_credenciales())
    if "exito" in res_tienda:
        _precios["tarifas_gramo"] = res_tienda["tarifas"]
        _precios["calidades_tienda"] = res_tienda["calidades"]
    else:
        _precios["tarifas_gramo"] = None
        _precios["calidades_tienda"] = []
        log.warning("No se pudieron cargar tarifas pricing_gramo: %s", res_tienda.get("error"))

    return {
        "ok": True, "hora": _precios["hora"], "tarifas_faltantes": _precios["tarifas_faltantes"],
        "calidades_tienda": _precios["calidades_tienda"],
    }


def _puede_ver_bodega(nombre):
    """Las cifras de costo son solo para los auxiliares de bodega, y solo bajo
    DOS condiciones a la vez: que el nombre elegido en "Soy:" esté en la
    columna 'Auxiliares de bodega' de la hoja, Y que su estado actual sea "En
    zona presencial". Con "En chat" no se activan.

    Se valida acá y no en el navegador, así el costo no viaja al cliente que no
    debe verlo y el bloque no se destapa editando el HTML.

    OJO con el alcance real: "Soy:" es una lista que cualquiera elige, no un
    login. Esto evita que un vendedor se tropiece con el costo trabajando
    normal (que es el problema real: lo confunde con el precio de venta), pero
    NO impide que alguien elija a propósito el nombre de un auxiliar y marque
    "En zona presencial". Para eso haría falta autenticación por persona.
    """
    if not nombre:
        return False
    horario, _err = _horario_actual()
    if not horario or not es_auxiliar_bodega(horario, nombre):
        return False
    estado = (almacen.estados_actuales() or {}).get(almacen.clave(nombre)) or {}
    return estado.get("estado") == almacen.ESTADO_PRESENCIAL


@app.post("/api/precio-tienda")
def api_precio_tienda(req: PrecioTiendaReq):
    if not _precios["tarifas_gramo"]:
        return {"error": "Tarifas no cargadas. Presione 'Actualizar precios'."}
    if not req.calidad:
        return {"error": "Seleccione una calidad."}
    return calcular_precio_tienda(
        req.peso, req.calidad, _precios["tarifas_gramo"],
        con_bodega=_puede_ver_bodega(_limpiar_nombre(req.nombre)),
    )


@app.get("/api/tabla")
def api_tabla():
    # Caché con TTL: sin ella, cada visita golpea la API de Google y un loop
    # de peticiones agota la cuota de lecturas (y los hilos del servidor).
    if _tabla_cache["bloques"] is not None and time.monotonic() - _tabla_cache["ts"] < _TTL_TABLA:
        return {"exito": True, "bloques": _tabla_cache["bloques"]}

    res = obtener_tabla_precios(ruta_credenciales())
    if "error" in res:
        # Si hay una copia vieja en caché, mejor servirla que fallar.
        if _tabla_cache["bloques"] is not None:
            log.warning("api-tabla: fallo la descarga, sirviendo cache: %s", res.get("error"))
            return {"exito": True, "bloques": _tabla_cache["bloques"]}
        return {"error": _error_publico(res, "api-tabla")}
    _tabla_cache["bloques"] = _componer_bloques(res["tabla"])
    _tabla_cache["ts"] = time.monotonic()
    return {"exito": True, "bloques": _tabla_cache["bloques"]}


# --- Reorganización de la tabla (mismo criterio que el escritorio) ---
GAP_BLOQUE, GAP_BANDA, MARGEN = 26, 30, 8


def _componer_bloques(tabla):
    """Omite 'Centro Comercial', pone DÓLAR junto a CLIENTE y agrupa
    Joyerías/Mayoristas/Neoros abajo. Devuelve bloques ya posicionados."""
    col_px, row_px, celdas = tabla["col_px"], tabla["row_px"], tabla["celdas"]

    def bloque(c0, c1, r0, r1):
        cells = [
            {**c, "c": c["c"] - c0, "r": c["r"] - r0}
            for c in celdas if c0 <= c["c"] < c1 and r0 <= c["r"] < r1
        ]
        cpx, rpx = col_px[c0:c1], row_px[r0:r1]
        return {"cells": cells, "col_px": cpx, "row_px": rpx,
                "w": sum(cpx), "h": sum(rpx), "x0": 0, "y0": 0}

    def fin_bloque(c0, c1, r0):
        """Fila siguiente a la última CON TEXTO en ese rango de columnas.

        Se calcula en vez de fijarla porque estos dos bloques crecen hacia
        abajo: cuando se agregó "Recargo +5" a Joyerías y Mayoristas, cada uno
        bajó una fila y el límite fijo dejó afuera justo la fila del valor de
        PLATA 925 — en la app se veía el título sin su precio. Solo se usa acá:
        arriba no serviría, porque las columnas de CLIENTE se solapan con las
        de JOYERÍAS y el bloque se estiraría hasta el final de la hoja.
        """
        filas = [c["r"] for c in celdas
                 if c0 <= c["c"] < c1 and c["r"] >= r0 and c["texto"]]
        return (max(filas) + 1) if filas else r0

    cliente = bloque(1, 9, 0, 25)
    dolar = bloque(19, 27, 0, 25)
    joyer = bloque(6, 9, 27, fin_bloque(6, 9, 27))
    mayor = bloque(15, 18, 27, fin_bloque(15, 18, 27))
    neoros = bloque(29, 34, 1, 9)

    cliente["x0"] = MARGEN; cliente["y0"] = MARGEN
    dolar["x0"] = cliente["x0"] + cliente["w"] + GAP_BLOQUE; dolar["y0"] = MARGEN
    y_inf = MARGEN + max(cliente["h"], dolar["h"]) + GAP_BANDA
    for b, prev in ((joyer, None), (mayor, joyer), (neoros, mayor)):
        b["y0"] = y_inf
        b["x0"] = MARGEN if prev is None else prev["x0"] + prev["w"] + GAP_BLOQUE
    return [cliente, dolar, joyer, mayor, neoros]


# =======================================================
# TURNOS (panel informativo del chat center)
# =======================================================
# El horario cambia una vez por semana: con 2 minutos de caché el panel se
# siente en vivo y no se castiga la cuota de la API de Sheets.
_TTL_HORARIO = 120
_horario_cache = {"datos": None, "ts": 0.0, "error": ""}


def _horario_actual(forzar=False):
    """Horario del día. Dos fuentes posibles, en este orden:

    1. La hoja 'Horarios' de Sheets (la más rica: trae compensatorios y cambios
       por color). Se cachea 2 minutos.
    2. El equipo registrado en la app, si la hoja no existe o no se pudo leer.

    Devuelve (horario, aviso). Si no hay ninguna de las dos, (None, aviso).
    """
    ahora = time.monotonic()
    if not forzar and _horario_cache["datos"] and ahora - _horario_cache["ts"] < _TTL_HORARIO:
        return _horario_cache["datos"], ""

    res = obtener_horario(ruta_credenciales())
    if "error" not in res:
        res["fuente"] = "hoja"
        _horario_cache.update(datos=res, ts=ahora, error="")
        return res, ""

    log.info("Horario: la hoja no está disponible (%s); se usa el equipo de la app",
             res["error"])
    personas = almacen.equipo()
    if personas:
        h = horario_desde_equipo(personas)
        _horario_cache.update(datos=h, ts=ahora, error="")
        return h, ""
    if _horario_cache["datos"]:
        return _horario_cache["datos"], ""
    return None, ("Aún no hay equipo registrado. La jefa de ventas puede agregarlo "
                  "desde el panel, o crear la hoja 'Horarios'.")


class PresenciaReq(BaseModel):
    nombre: str = Field("", max_length=40)


class EstadoReq(BaseModel):
    nombre: str = Field("", max_length=40)
    estado: str = Field("en_chat", max_length=20)


class NovedadReq(BaseModel):
    nombre: str = Field("", max_length=40)
    tipo: str = Field("Ausencia", max_length=30)
    nota: str = Field("", max_length=200)
    reportado_por: str = Field("", max_length=40)
    desde: str = Field("", max_length=5)
    hasta: str = Field("", max_length=5)


@app.get("/api/turnos/estado")
def api_turnos_estado():
    """Lo que ve el panel: quién está en línea, quién tiene una ausencia ya
    explicada, a quién no se espera hoy y las novedades del día. Es
    informativo: nadie tiene que cubrir a nadie."""
    horario, err = _horario_actual()
    novedades = almacen.novedades_del_dia()
    base = {
        # "desconectado" queda fuera: solo lo marca el navegador al cerrar la
        # pestaña (sendBeacon), no es una opción que el asesor elija a mano.
        "estados_posibles": [{"clave": k, "etiqueta": v["etiqueta"], "atiende": v["atiende"]}
                             for k, v in almacen.ESTADOS_ASESOR.items() if k != "desconectado"],
        "tipos_novedad": almacen.TIPOS_NOVEDAD,
        "tipos_ajuste": [{"clave": k, "etiqueta": v["etiqueta"], "pide": v["pide"]}
                         for k, v in almacen.TIPOS_AJUSTE.items()],
    }
    if horario is None:
        # Sin horario todavía se pueden ver y registrar novedades.
        # 'semana' tiene que ir: el pie del panel la concatena sin comprobar,
        # y sin ella se leía un "undefined" en pantalla.
        return {**base, "configurado": False, "aviso": err,
                "novedades": novedades, "personas": [], "ajustes": [],
                "auxiliares": [], "ausencia_informada": [], "en_linea": [],
                "por_entrar": [], "no_se_espera": [],
                "semana": _semana_actual(), "dia": "",
                "hora": datetime.now().strftime("%I:%M %p")}
    # Los roles ya no cambian a quién se muestra (el panel es informativo), pero
    # el panel los sigue enseñando: los del cuadro/hoja Roles pesan sobre los
    # que la jefa registró en Equipo.
    equipo = almacen.equipo()
    roles = {p["clave"]: p["rol"] for p in equipo}
    roles.update(horario.get("roles") or {})
    horario_con_roles = {**horario, "roles": roles}

    datos = calcular_panel(
        horario_con_roles, datetime.now(),
        presencia=almacen.presencia_del_dia(),
        estados=almacen.estados_actuales(),
        novedades=novedades,
        ajustes=almacen.ajustes_del_dia(),
    )
    # El equipo registrado en la app (panel de Gestión) se suma al selector
    # "Soy:" aunque la hoja de Sheets sea la fuente activa del horario — así
    # se puede dar de alta a alguien (ej. una cuenta de pruebas) sin tocar la
    # hoja real de la jefa. Al no estar en las asignaciones del horario, no
    # aparece en ninguna lista del panel.
    personas = sorted(set(personas_del_horario(horario)) | {p["nombre"] for p in equipo})
    datos.update(base, configurado=True, personas=personas,
                 fuente=horario.get("fuente", ""), roles=roles,
                 auxiliares=horario.get("auxiliares") or [])
    return datos


@app.post("/api/turnos/presencia")
def api_turnos_presencia(req: PresenciaReq):
    """Señal de que el asesor está activo (la envía la calculadora sola)."""
    nombre = _limpiar_nombre(req.nombre)
    if not nombre:
        return {"error": "Falta el nombre."}
    almacen.marcar_visto(nombre)
    return {"ok": True}


@app.post("/api/turnos/estado-asesor")
def api_turnos_estado_asesor(req: EstadoReq):
    """El vendedor marca en qué está (en chat, almuerzo, zona presencial). Así
    el panel distingue una ausencia explicada de un silencio sin explicar."""
    nombre = _limpiar_nombre(req.nombre)
    if not nombre:
        return {"error": "Falta el nombre."}
    est = almacen.marcar_estado(nombre, req.estado)
    if not est:
        return {"error": "Estado no válido."}
    return {"ok": True, "estado": est}


@app.post("/api/turnos/novedad")
def api_turnos_novedad(req: NovedadReq):
    nombre = _limpiar_nombre(req.nombre)
    if not nombre:
        return {"error": "Falta el nombre."}
    nov = almacen.reportar_novedad(nombre, req.tipo, req.nota,
                                   _limpiar_nombre(req.reportado_por),
                                   req.desde, req.hasta)
    log.info("Novedad: %s / %s", nov["nombre"], nov["tipo"])
    return {"ok": True, "novedad": nov}


@app.post("/api/turnos/novedad/quitar")
def api_turnos_novedad_quitar(req: NovedadReq):
    nombre = _limpiar_nombre(req.nombre)
    if not nombre:
        return {"error": "Falta el nombre."}
    quitadas = almacen.quitar_novedad(nombre, req.tipo or None)
    return {"ok": True, "quitadas": quitadas}


class AjusteReq(BaseModel):
    nombre: str = Field("", max_length=40)
    tipo: str = Field("turno", max_length=20)
    turno: int | None = Field(None, ge=1, le=3)
    hora: str = Field("", max_length=5)
    nota: str = Field("", max_length=200)
    autor: str = Field("", max_length=40)


@app.post("/api/turnos/ajuste")
def api_turnos_ajuste(req: AjusteReq):
    """Movimiento de horario para HOY (no toca el plan de la semana): cambio de
    turno, entrada más tarde, no viene, o entra alguien no programado."""
    nombre = _limpiar_nombre(req.nombre)
    if not nombre:
        return {"error": "Falta el nombre."}
    aj = almacen.registrar_ajuste(nombre, req.tipo, req.turno, req.hora,
                                  req.nota, _limpiar_nombre(req.autor))
    if not aj:
        return {"error": "Ajuste no válido."}
    log.info("Ajuste del día: %s → %s", aj["nombre"], aj["etiqueta"])
    return {"ok": True, "ajuste": aj}


@app.post("/api/turnos/ajuste/quitar")
def api_turnos_ajuste_quitar(req: AjusteReq):
    nombre = _limpiar_nombre(req.nombre)
    if not nombre:
        return {"error": "Falta el nombre."}
    return {"ok": True, "quitados": almacen.quitar_ajuste(nombre, req.tipo or None)}


# =======================================================
# GESTIÓN (solo con el PIN de la jefa de ventas)
# =======================================================
_FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _solo_jefa(request):
    """None si puede pasar; si no, la respuesta 403 a devolver."""
    if _es_jefa(request):
        return None
    return JSONResponse({"error": "Solo la jefa de ventas puede ver esto."}, status_code=403)


class PersonaReq(BaseModel):
    nombre: str = Field("", max_length=40)
    rol: str = Field("Red social", max_length=30)
    turno: int = Field(1, ge=1, le=3)
    activa: bool = True


@app.get("/api/equipo")
def api_equipo():
    """Lista del equipo. La ve cualquiera con sesión (el panel necesita los
    nombres para el selector); solo la jefa puede modificarla."""
    return {"personas": almacen.equipo(), "roles": almacen.ROLES,
            "puede_editar": False}


@app.get("/api/equipo/gestion")
def api_equipo_gestion(request: Request):
    """Igual que /api/equipo pero incluye las inactivas: es la vista de edición."""
    negado = _solo_jefa(request)
    if negado:
        return negado
    return {"personas": almacen.equipo(solo_activas=False), "roles": almacen.ROLES,
            "puede_editar": True}


@app.post("/api/equipo/guardar")
def api_equipo_guardar(req: PersonaReq, request: Request):
    negado = _solo_jefa(request)
    if negado:
        return negado
    nombre = _limpiar_nombre(req.nombre)
    if not nombre:
        return {"error": "Falta el nombre."}
    p = almacen.guardar_persona(nombre, req.rol, req.turno, req.activa)
    _horario_cache.update(datos=None, ts=0.0)      # el horario cambió
    log.info("Equipo: guardado %s (%s, turno %s)", p["nombre"], p["rol"], p["turno"])
    return {"ok": True, "persona": p}


@app.post("/api/equipo/quitar")
def api_equipo_quitar(req: PersonaReq, request: Request):
    negado = _solo_jefa(request)
    if negado:
        return negado
    nombre = _limpiar_nombre(req.nombre)
    if not nombre:
        return {"error": "Falta el nombre."}
    n = almacen.quitar_persona(nombre)
    _horario_cache.update(datos=None, ts=0.0)
    return {"ok": True, "quitadas": n}


@app.get("/api/gestion/resumen")
def api_gestion_resumen(request: Request, desde: str = "", hasta: str = ""):
    """Resumen por persona de un rango (por defecto, la semana en curso):
    días con señal, hora de entrada típica, novedades y minutos desviados a la
    zona presencial."""
    negado = _solo_jefa(request)
    if negado:
        return negado
    if not (_FECHA_RE.match(desde or "") and _FECHA_RE.match(hasta or "")):
        desde, hasta = almacen.rango_semana()
    res = almacen.resumen(desde, hasta)
    horario, _ = _horario_actual()
    roles = (horario or {}).get("roles") or {}
    equipo_roles = {p["clave"]: p["rol"] for p in almacen.equipo()}
    for p in res["personas"]:
        # La hoja manda; si no está ahí, se usa el rol del panel de Equipo.
        p["rol"] = roles.get(almacen.clave(p["nombre"])) or equipo_roles.get(almacen.clave(p["nombre"]), "")
    return res


@app.get("/api/gestion/dia")
def api_gestion_dia(request: Request, fecha: str = ""):
    """Foto de un día: novedades, presencia y estados (para revisar ayer)."""
    negado = _solo_jefa(request)
    if negado:
        return negado
    f = fecha if _FECHA_RE.match(fecha or "") else almacen.hoy()
    return {
        "fecha": f,
        "novedades": almacen.novedades_del_dia(f, solo_activas=False),
        "presencia": almacen.presencia_del_dia(f),
        "estados": almacen.estados_actuales(f),
    }


# =======================================================
# SELLO DE FECHA Y HORA (para pantallazos de reporte)
# =======================================================
# Se dibuja en el SERVIDOR y se entrega como imagen. Así el asesor puede tomar
# un pantallazo y la fecha/hora no se puede cambiar editando el HTML con las
# herramientas del navegador (que es lo que pasaría con un texto normal).
# Nota honesta: la prueba fuerte es el registro en la base de datos, que también
# lleva la hora del servidor; la imagen es para que el pantallazo sea creíble.
_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]


@app.get("/api/reloj.png")
def api_reloj(t: str = "dark"):
    """PNG con la fecha y hora del servidor. Sin caché: cada carga es real."""
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont

    ahora = datetime.now()
    texto = (f"{_DIAS_ES[ahora.weekday()]} {ahora.day} {_MESES_ES[ahora.month - 1]} "
             f"{ahora.year} · {ahora.strftime('%I:%M %p').lower()}")

    oscuro = t != "light"
    fondo = (35, 35, 35) if oscuro else (255, 255, 255)
    tinta = (230, 230, 230) if oscuro else (26, 26, 26)
    borde = (201, 162, 39)          # dorado de la marca

    try:
        fuente = ImageFont.load_default(size=15)
    except TypeError:               # Pillow antiguo: sin tamaño ajustable
        fuente = ImageFont.load_default()

    tmp = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    caja = tmp.textbbox((0, 0), texto, font=fuente)
    ancho, alto = caja[2] - caja[0] + 20, caja[3] - caja[1] + 14

    img = Image.new("RGB", (ancho, alto), fondo)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, ancho - 1, alto - 1], outline=borde)
    d.text((10 - caja[0], 7 - caja[1]), texto, font=fuente, fill=tinta)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(
        content=buf.getvalue(), media_type="image/png",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


# =======================================================
# PUENTE PARA LA TORRE DE CONTROL
# =======================================================
# La Torre de Control (proyecto Django aparte) hace el análisis profundo. Para
# no tener dos verdades, lee de aquí lo que la calculadora captura. Se autentica
# con un token propio (cabecera X-Token), no con la cookie del navegador.
TOKEN_TORRE = os.environ.get("TORRE_TOKEN", "").strip()


@app.get("/api/torre/historial")
def api_torre_historial(request: Request, desde: str = "", hasta: str = ""):
    """Volcado crudo de presencia, estados y novedades por rango (más las
    coberturas históricas, que la Torre sigue esperando)."""
    token = (request.headers.get("x-token") or "").strip()
    if not TOKEN_TORRE:
        return JSONResponse({"error": "Puente no configurado."}, status_code=503)
    if not token or not hmac.compare_digest(token, TOKEN_TORRE):
        log.warning("Intento de acceso al puente con token inválido desde %s", _ip_cliente(request))
        return JSONResponse({"error": "No autorizado."}, status_code=401)
    if not (_FECHA_RE.match(desde or "") and _FECHA_RE.match(hasta or "")):
        desde, hasta = almacen.rango_semana()
    return almacen.historial(desde, hasta)


# =======================================================
# FRONTEND ESTÁTICO
# =======================================================
# El index, el JS y el CSS tienen que revalidarse SIEMPRE. Sin esto el
# navegador reusa el app.js viejo junto al index.html nuevo después de un
# despliegue y, como ese JS toca elementos que ya no existen en el HTML,
# renderPanel muere a media función: el sello y la semana se pintan, pero el
# selector "Soy:" queda vacío y las listas sin dibujar. Pasó el 27/08/2026 al
# quitar el contador "#n-cob".
#
# "no-cache" no significa "no guardar": el navegador sigue guardando el
# archivo, pero pregunta antes de usarlo. StaticFiles ya manda ETag, así que
# cuando no cambió la respuesta es un 304 sin cuerpo. Las imágenes (logo,
# favicon) no están acá: cambian casi nunca y sí conviene que se cacheen.
_SIN_CACHE = {"/", "/index.html", "/app.js", "/styles.css"}


@app.middleware("http")
async def _revalidar_frontend(request: Request, call_next):
    respuesta = await call_next(request)
    if request.url.path in _SIN_CACHE:
        respuesta.headers["Cache-Control"] = "no-cache, must-revalidate"
    return respuesta


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
def _cargar_precios_al_inicio():
    try:
        actualizar_precios()
        log.info("Precios cargados al iniciar: %s", _precios["hora"])
    except Exception:
        log.warning("No se pudieron cargar precios al iniciar", exc_info=True)
