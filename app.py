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
import logging
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.cotizacion_logic import calcular_cotizacion
from core.mayorista_logic import obtener_precios_sheets, calcular_cotizacion_mayorista
from core.tabla_precios import obtener_tabla_precios

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("calculadora_napo")

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")

app = FastAPI(title="Calculadora Napo Web", version="2.0.1-web")

# --- Caché de precios en memoria (compartida por todos los usuarios) ---
_precios = {"datos": None, "hora": None, "tarifas_faltantes": []}


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
class JoyaRetail(BaseModel):
    nombre: str = "Joya"
    cantidad: int = 1
    valor_unitario: str = ""


class RetailReq(BaseModel):
    joyas: list[JoyaRetail] = []
    medio_pago: str = "Transferencia"
    aplicar_envio: bool = False
    tipo_envio: str = "Nacional"
    envio_manual: str = ""


class JoyaMayorista(BaseModel):
    nombre: str = "Joya"
    cantidad: int = 1
    peso: str = ""
    tipo: str = "Tipo Oro"
    subtipo: str = "Subtipo"
    valor_normal: str = ""


class OtroMayorista(BaseModel):
    nombre: str = "Extra"
    cantidad: int = 1
    valor_unitario: str = ""


class MayoristaReq(BaseModel):
    joyas: list[JoyaMayorista] = []
    otros: list[OtroMayorista] = []
    aplicar_envio: bool = False
    tipo_envio: str = "Nacional"
    envio_manual: str = ""


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
    }


@app.post("/api/actualizar-precios")
def actualizar_precios():
    res = obtener_precios_sheets(ruta_credenciales())
    if "error" in res:
        return {"error": res["error"], "cargado": _precios["datos"] is not None}
    _precios["datos"] = res["datos"]
    _precios["hora"] = datetime.now().strftime("%d/%m/%Y %I:%M %p")
    _precios["tarifas_faltantes"] = res.get("tarifas_faltantes") or []
    return {"ok": True, "hora": _precios["hora"], "tarifas_faltantes": _precios["tarifas_faltantes"]}


@app.get("/api/tabla")
def api_tabla():
    res = obtener_tabla_precios(ruta_credenciales())
    if "error" in res:
        return res
    return {"exito": True, "bloques": _componer_bloques(res["tabla"])}


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
