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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.cotizacion_logic import calcular_cotizacion
from core.mayorista_logic import obtener_precios_sheets, calcular_cotizacion_mayorista
from core.tabla_precios import obtener_tabla_precios
from core.tienda_logic import obtener_tarifas_gramo, calcular_precio_tienda

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
COOKIE_SECURE = os.environ.get("PIN_COOKIE_SECURE", "1") != "0"  # 0 solo para dev local en http
NOMBRE_COOKIE = "sesion"
_TTL_SESION = 7 * 24 * 3600      # la sesión dura 7 días
_GRACIA = 2                      # fallos sin penalización (errores de dedo)
_ESPERA_BASE = 5                 # seg del primer bloqueo
_ESPERA_TOPE = 300               # tope del bloqueo (5 min)

# Rutas de la API que NO exigen sesión (todo lo demás bajo /api/ sí).
_API_PUBLICA = {"/api/acceso", "/api/sesion"}

# Estado en memoria (single container). Un reinicio limpia sesiones y bloqueos:
# aceptable — a lo sumo hay que reingresar el PIN.
_sesiones = {}   # token -> expiración (time.monotonic)
_intentos = {}   # ip -> {"fails": int, "hasta": time.monotonic hasta el que está bloqueado}


def _ip_cliente(request):
    """IP real del visitante. Detrás de Traefik, request.client es la IP del
    proxy (una sola para todos), así que se usa X-Forwarded-For para no
    bloquear a todos por culpa de uno."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "desconocido"


def _nueva_sesion():
    token = secrets.token_urlsafe(32)
    _sesiones[token] = time.monotonic() + _TTL_SESION
    return token


def _sesion_valida(request):
    token = request.cookies.get(NOMBRE_COOKIE)
    if not token:
        return False
    exp = _sesiones.get(token)
    if exp is None:
        return False
    if time.monotonic() > exp:
        _sesiones.pop(token, None)
        return False
    return True


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
    """El frontend lo consulta al cargar para decidir si pide el PIN."""
    return {"autorizado": _sesion_valida(request)}


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
    if hmac.compare_digest(req.pin.strip(), PIN):
        _intentos.pop(ip, None)
        token = _nueva_sesion()
        resp = JSONResponse({"ok": True})
        resp.set_cookie(
            NOMBRE_COOKIE, token, max_age=_TTL_SESION,
            httponly=True, samesite="lax", secure=COOKIE_SECURE,
        )
        log.info("Acceso concedido a %s", ip)
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


@app.post("/api/precio-tienda")
def api_precio_tienda(req: PrecioTiendaReq):
    if not _precios["tarifas_gramo"]:
        return {"error": "Tarifas no cargadas. Presione 'Actualizar precios'."}
    if not req.calidad:
        return {"error": "Seleccione una calidad."}
    return calcular_precio_tienda(req.peso, req.calidad, _precios["tarifas_gramo"])


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

    cliente = bloque(1, 9, 0, 25)
    dolar = bloque(19, 27, 0, 25)
    joyer = bloque(6, 9, 27, 44)
    mayor = bloque(15, 18, 27, 45)
    neoros = bloque(29, 34, 1, 9)

    cliente["x0"] = MARGEN; cliente["y0"] = MARGEN
    dolar["x0"] = cliente["x0"] + cliente["w"] + GAP_BLOQUE; dolar["y0"] = MARGEN
    y_inf = MARGEN + max(cliente["h"], dolar["h"]) + GAP_BANDA
    for b, prev in ((joyer, None), (mayor, joyer), (neoros, mayor)):
        b["y0"] = y_inf
        b["x0"] = MARGEN if prev is None else prev["x0"] + prev["w"] + GAP_BLOQUE
    return [cliente, dolar, joyer, mayor, neoros]


# =======================================================
# FRONTEND ESTÁTICO
# =======================================================
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
