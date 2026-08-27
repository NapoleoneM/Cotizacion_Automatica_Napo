# Prueba del almacén (presencia, estados, novedades y el resumen semanal) en
# un SQLite temporal, sin tocar el real.
#
# Reemplaza a test_almacen_alertas.py: esa probaba la trazabilidad de
# "Requieren cobertura" y el tiempo de respuesta de soporte, que dejaron de
# existir en agosto de 2026 (todos son vendedores, nadie cubre a nadie).
# Uso: python tools/test_almacen.py
import os
import sys
import shutil
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_TMP = tempfile.mkdtemp(prefix="calc_napo_test_")
os.environ["ESTADO_DIR"] = _TMP

from core import almacen  # noqa: E402  (después de fijar ESTADO_DIR)

fallos = 0


def chk(cond, msg):
    global fallos
    print(("[OK] " if cond else "[X]  ") + msg)
    if not cond:
        fallos += 1


hoy = almacen.hoy()

# =====================================================
# Presencia: primera señal del día y última
# =====================================================
almacen.marcar_visto("Ana")
p = almacen.presencia_del_dia()
chk("ana" in p and p["ana"]["primera_ts"] and p["ana"]["ts"],
    f"Marca la presencia de Ana con primera señal y última: {p.get('ana')}")

primera = p["ana"]["primera_ts"]
almacen.marcar_visto("Ana")
p2 = almacen.presencia_del_dia()
chk(p2["ana"]["primera_ts"] == primera,
    "Una segunda señal el mismo día NO mueve la hora de entrada (primera_ts)")

# Los acentos y las mayúsculas no crean dos personas distintas.
almacen.marcar_visto("Angélica")
almacen.marcar_visto("angelica")
p3 = almacen.presencia_del_dia()
chk(len([k for k in p3 if k.startswith("angelica")]) == 1,
    f"'Angélica' y 'angelica' son la misma clave: {sorted(p3)}")

# =====================================================
# Estados: cada cambio queda, y el vigente es el último
# =====================================================
almacen.marcar_estado("Ana", "en_chat")
almacen.marcar_estado("Ana", "almuerzo")
e = almacen.estados_actuales()
chk(e.get("ana", {}).get("estado") == "almuerzo",
    f"El estado vigente es el último marcado: {e.get('ana')}")
chk(almacen.marcar_estado("Ana", "inventado") is None,
    "Un estado que no existe se rechaza (no se guarda basura)")

# =====================================================
# Minutos por estado: un tramo se mide hasta el cambio siguiente
# =====================================================
almacen.marcar_estado("Beto", "presencial")
almacen.marcar_estado("Beto", "en_chat")
with almacen._con() as cx:
    # Simula que el tramo en presencial duró 20 minutos.
    filas = cx.execute("SELECT id, estado FROM estados WHERE clave='beto' ORDER BY ts").fetchall()
    ids = {r["estado"]: r["id"] for r in filas}
    cx.execute("UPDATE estados SET ts=? WHERE id=?", (time.time() - 20 * 60, ids["presencial"]))
m = almacen.minutos_por_estado(hoy, hoy, almacen.ESTADO_PRESENCIAL)
chk("beto" in m and 19 <= m["beto"]["minutos"] <= 21,
    f"El tramo en presencial se mide hasta el cambio siguiente (~20 min): {m.get('beto')}")

# =====================================================
# Novedades: se reportan, se listan y se quitan
# =====================================================
nov = almacen.reportar_novedad("Ana", "Cita médica", "vuelve al mediodía", "Mariana")
chk(nov and nov["tipo"] == "Cita médica" and nov["reportado_por"] == "Mariana",
    f"Reporta la novedad con nota y autor: {nov}")
chk(nov.get("importante") is False,
    "'Cita médica' no es de las que dejan chats sin atender (no suena)")

nov2 = almacen.reportar_novedad("Beto", "Ausencia", "", "Mariana")
chk(nov2.get("importante") is True,
    "'Ausencia' sí es importante (deja chats sin atender)")

activas = {n["nombre"] for n in almacen.novedades_del_dia()}
chk({"Ana", "Beto"} <= activas, f"Las novedades del día se listan: {sorted(activas)}")

chk(almacen.quitar_novedad("Ana") == 1, "Quitar la novedad de Ana devuelve 1")
activas2 = {n["nombre"] for n in almacen.novedades_del_dia()}
chk("Ana" not in activas2 and "Beto" in activas2,
    f"Tras quitarla, Ana ya no está activa y Beto sigue: {sorted(activas2)}")
chk(any(n["nombre"] == "Ana" for n in almacen.novedades_del_dia(solo_activas=False)),
    "La novedad quitada sigue en el historial (no se borra)")

# =====================================================
# Ajustes del día: mueven el horario de HOY, con autor
# =====================================================
aj = almacen.registrar_ajuste("Ana", "entrada", hora="11:00", nota="cita", autor="Mariana")
chk(aj and aj["hora"] == "11:00" and aj["autor"] == "Mariana",
    f"Registra el ajuste de entrada con hora y autor: {aj}")
chk(almacen.registrar_ajuste("Ana", "inventado") is None,
    "Un tipo de ajuste que no existe se rechaza")
chk("ana" in almacen.ajustes_del_dia(),
    f"El ajuste queda vigente para hoy: {sorted(almacen.ajustes_del_dia())}")
chk(almacen.quitar_ajuste("Ana") == 1, "Deshacer el ajuste devuelve 1")
chk("ana" not in almacen.ajustes_del_dia(), "Deshecho, el ajuste ya no rige")

# =====================================================
# Equipo: quitar DESACTIVA, no borra (el historial sigue teniendo sentido)
# =====================================================
almacen.guardar_persona("Laura", "Auditoría de calidad", 3)
chk(any(x["nombre"] == "Laura" and x["turno"] == 3 for x in almacen.equipo()),
    f"Guarda a Laura en el turno 3: {almacen.equipo()}")
almacen.quitar_persona("Laura")
chk(not any(x["nombre"] == "Laura" for x in almacen.equipo()),
    "Quitada, Laura no sale en el equipo activo")
chk(any(x["nombre"] == "Laura" for x in almacen.equipo(solo_activas=False)),
    "Pero sigue existiendo como inactiva (no se borró)")

# =====================================================
# resumen(): lo que ve la jefa — sin métricas de cobertura
# =====================================================
r = almacen.resumen(hoy, hoy)
personas = {p["nombre"]: p for p in r["personas"]}
chk("Ana" in personas and personas["Ana"]["dias_con_senal"] == 1,
    f"resumen() cuenta los días con señal: {personas.get('Ana')}")
chk(personas["Ana"]["entrada_tipica"] != "—",
    f"resumen() calcula la hora de entrada típica: {personas['Ana']['entrada_tipica']}")
chk(personas.get("Beto", {}).get("minutos_presencial", 0) >= 19,
    f"resumen() trae los minutos desviados a presencial: {personas.get('Beto')}")
chk(not (set(personas["Ana"]) & {"minutos_sin_cobertura", "veces_cubierto",
                                 "veces_respondio", "minutos_cubierto"}),
    f"resumen() ya no devuelve métricas de cobertura: {sorted(personas['Ana'])}")
chk("minutos_sin_cobertura" not in r["totales"],
    f"Los totales tampoco: {sorted(r['totales'])}")

# =====================================================
# historial(): el volcado que consume la Torre de Control
# =====================================================
hist = almacen.historial(hoy, hoy)
chk({"presencia", "estados", "novedades", "coberturas"} <= set(hist),
    f"historial() sigue entregando las 4 tablas (coberturas, ya histórica): {sorted(hist)}")
chk(hist["coberturas"] == [],
    "No se escriben coberturas nuevas, así que la tabla llega vacía para hoy")

shutil.rmtree(_TMP, ignore_errors=True)

print("\nRESULTADO:", "[X] HAY FALLOS" if fallos else "[OK] TODO CORRECTO")
sys.exit(1 if fallos else 0)
