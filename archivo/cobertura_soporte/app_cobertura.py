"""ARCHIVO — endpoints y cableado de cobertura que vivían en app.py.

Retirado en agosto de 2026 junto con el rol de soporte. Para reactivar hay que
devolver estas piezas a `app.py` (y volver a importar `calcular_cobertura` en
vez de `calcular_panel`).
"""

# --- 1) El import de core.turnos era: ---
# from core.turnos import (
#     obtener_horario, calcular_cobertura, personas_del_horario, horario_desde_equipo,
# )


# --- 2) Modelo de la petición ---
class CoberturaReq(BaseModel):                                   # noqa: F821
    titular: str = Field("", max_length=40)                      # noqa: F821
    soporte: str = Field("", max_length=40)                      # noqa: F821


# --- 3) Dentro de /api/turnos/estado ---
#
# La respuesta cuando no hay horario incluía la lista roja:
#
#         return {**base, "configurado": False, "aviso": err,
#                 "novedades": novedades, "personas": [], "ajustes": [],
#                 "requieren_cobertura": [], "ausencia_informada": [], "en_linea": [],
#                 "por_entrar": [], "no_se_espera": [],
#                 "hora": datetime.now().strftime("%I:%M %p")}
#
# Y el motivo de mezclar los roles del panel Equipo con los de la hoja era que
# el rol decidía a quién se le pedía cobertura:
#
#     # El rol de alguien registrado en el panel Equipo (ej. "Venta presencial")
#     # tiene que pesar en la alarma en vivo, no solo en el resumen histórico de
#     # gestión — si no, alguien marcado como no cubrible ahí puede seguir
#     # disparando "Requieren cobertura" porque el horario (hoja/asterisco) no
#     # sabe nada de ese rol. El "*"/hoja manda si dice algo; si no, se usa el
#     # rol de Equipo.
#     equipo = almacen.equipo()
#
# La llamada al cálculo y el registro de trazabilidad:
#
#     datos = calcular_cobertura(
#         horario_con_roles, datetime.now(),
#         presencia=almacen.presencia_del_dia(),
#         estados=almacen.estados_actuales(),
#         novedades=novedades,
#         coberturas=almacen.coberturas_activas(),
#         ajustes=almacen.ajustes_del_dia(),
#     )
#     # Trazabilidad: registra quién está AHORA en "Requieren cobertura" para
#     # poder medir después cuánto tiempo pasó sin que nadie confirmara y qué
#     # tan rápido reaccionó soporte (ver Gestión → resumen).
#     almacen.registrar_alertas_activas([x["nombre"] for x in datos["requieren_cobertura"]])


# --- 4) Al quitar una novedad se liberaba también la cobertura ---
#
# @app.post("/api/turnos/novedad/quitar")
# def api_turnos_novedad_quitar(req: NovedadReq):
#     ...
#     quitadas = almacen.quitar_novedad(nombre, req.tipo or None)
#     almacen.cerrar_cobertura(nombre)
#     return {"ok": True, "quitadas": quitadas}


# --- 5) Los dos endpoints de "Yo lo cubro" ---
@app.post("/api/turnos/cubrir")                                  # noqa: F821
def api_turnos_cubrir(req: CoberturaReq):
    """Soporte declara que está cubriendo a alguien: evita que dos personas
    entren a la misma cuenta y deja el registro de quién cubrió qué."""
    titular = _limpiar_nombre(req.titular)                       # noqa: F821
    soporte = _limpiar_nombre(req.soporte)                       # noqa: F821
    if not titular or not soporte:
        return {"error": "Falta el titular o quién cubre."}
    almacen.abrir_cobertura(titular, soporte)                    # noqa: F821
    return {"ok": True}


@app.post("/api/turnos/cubrir/cerrar")                           # noqa: F821
def api_turnos_cubrir_cerrar(req: CoberturaReq):
    titular = _limpiar_nombre(req.titular)                       # noqa: F821
    if not titular:
        return {"error": "Falta el titular."}
    return {"ok": True, "cerradas": almacen.cerrar_cobertura(titular)}       # noqa: F821


# --- 6) /api/gestion/dia devolvía también las coberturas del día ---
#
#     return {
#         "fecha": f,
#         "novedades": almacen.novedades_del_dia(f, solo_activas=False),
#         "coberturas": list(almacen.coberturas_activas(f).values()),
#         "presencia": almacen.presencia_del_dia(f),
#         "estados": almacen.estados_actuales(f),
#     }
