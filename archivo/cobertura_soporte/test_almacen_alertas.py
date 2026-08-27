# ARCHIVO — esta prueba vivía en tools/test_almacen_alertas.py y se retiró en
# agosto de 2026 junto con la cobertura de soporte. Su reemplazo actual es
# tools/test_almacen.py (presencia, estados, novedades y resumen).
#
# Prueba de la trazabilidad de "Requieren cobertura" (episodios de alarma y
# tiempo de respuesta de soporte) en un SQLite temporal, sin tocar el real.
# Uso: python tools/test_almacen_alertas.py
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

# --- Episodio 1: Ana entra en "Requieren cobertura" ---
almacen.registrar_alertas_activas(["Ana"])
with almacen._con() as cx:
    fila = cx.execute("SELECT * FROM alertas WHERE clave=? AND fecha=?", ("ana", hoy)).fetchone()
chk(fila is not None and fila["ts_fin"] is None, "Se abre un episodio para Ana al entrar a Requieren cobertura")

# Llamarlo de nuevo con Ana todavía activa NO debe duplicar el episodio.
almacen.registrar_alertas_activas(["Ana"])
with almacen._con() as cx:
    n = cx.execute("SELECT COUNT(*) c FROM alertas WHERE clave=? AND fecha=?", ("ana", hoy)).fetchone()["c"]
chk(n == 1, f"Llamarlo de nuevo con Ana activa no duplica el episodio (hay {n})")

# Simula que pasaron 10 minutos desde que empezó el episodio.
with almacen._con() as cx:
    cx.execute("UPDATE alertas SET ts_inicio=? WHERE clave=? AND fecha=?",
               (time.time() - 10 * 60, "ana", hoy))

# Soporte la cubre AHORA.
almacen.abrir_cobertura("Ana", "Mariana")
# Y ya no aparece en la lista activa -> se cierra el episodio.
almacen.registrar_alertas_activas([])
with almacen._con() as cx:
    fila = cx.execute("SELECT * FROM alertas WHERE clave=? AND fecha=?", ("ana", hoy)).fetchone()
chk(fila["ts_fin"] is not None, "El episodio se cierra en cuanto Ana deja de estar en la lista activa")

resumen_min = almacen.minutos_sin_cobertura(hoy, hoy)
chk("ana" in resumen_min and 9 <= resumen_min["ana"]["minutos"] <= 11,
    f"minutos_sin_cobertura calcula ~10 min para Ana: {resumen_min.get('ana')}")

resp = almacen.tiempos_respuesta(hoy, hoy)
chk("mariana" in resp and resp["mariana"]["veces"] == 1 and 9 <= resp["mariana"]["min_promedio"] <= 11,
    f"tiempos_respuesta calcula ~10 min de respuesta para Mariana: {resp.get('mariana')}")

# --- Episodio 2, mismo día: Ana vuelve a caer en rojo (la cobertura venció) ---
almacen.cerrar_cobertura("Ana")  # libera la cobertura anterior
almacen.registrar_alertas_activas(["Ana"])
with almacen._con() as cx:
    n = cx.execute("SELECT COUNT(*) c FROM alertas WHERE clave=? AND fecha=?", ("ana", hoy)).fetchone()["c"]
chk(n == 2, f"Un segundo episodio el mismo día se registra aparte (hay {n})")

# Este segundo episodio queda ABIERTO (no se cubrió) — debe seguir contando
# minutos hasta "ahora" en el resumen, no perderse.
resumen_min2 = almacen.minutos_sin_cobertura(hoy, hoy)
chk(resumen_min2["ana"]["episodios"] == 2 and resumen_min2["ana"]["minutos"] >= 10,
    f"Un episodio abierto sigue sumando minutos hasta ahora, sin perderse: {resumen_min2.get('ana')}")

# --- resumen() integra todo junto ---
r = almacen.resumen(hoy, hoy)
personas = {p["nombre"]: p for p in r["personas"]}
chk("Ana" in personas and personas["Ana"]["minutos_sin_cobertura"] >= 10,
    f"resumen() incluye minutos_sin_cobertura para Ana: {personas.get('Ana')}")
chk("Mariana" in personas and personas["Mariana"]["veces_respondio"] == 1,
    f"resumen() incluye veces_respondio para Mariana: {personas.get('Mariana')}")

# --- Cobertura de HOY nunca liberada: cuenta hasta ahora en resumen() ---
almacen.abrir_cobertura("Beto", "Mariana")
r_hoy = almacen.resumen(hoy, hoy)
beto = {p["nombre"]: p for p in r_hoy["personas"]}.get("Beto")
chk(beto is not None and beto["minutos_cubierto"] >= 0,
    f"Cobertura de hoy sin liberar cuenta hasta ahora en resumen(): {beto}")

# --- Cobertura VIEJA (de hace días) nunca liberada: NO debe crecer sin limite
# cada vez que se corre el resumen (bug real: antes usaba time.time() sin
# chequear la fecha, así que sumaba minutos contra "ahora" para siempre).
with almacen._con() as cx:
    cx.execute("""INSERT INTO coberturas (clave_titular, titular, clave_soporte, soporte, fecha, desde)
                  VALUES (?,?,?,?,?,?)""",
               ("carla", "Carla", "mariana", "Mariana", "2020-01-01", time.time() - 999999 * 60))
r_vieja = almacen.resumen("2020-01-01", "2020-01-01")
carla = {p["nombre"]: p for p in r_vieja["personas"]}.get("Carla")
chk(carla is not None and carla["minutos_cubierto"] == 0,
    f"Cobertura vieja sin liberar cuenta 0 min, no crece contra el reloj actual: {carla}")

# --- Episodio de alertas huérfano de un día anterior: se autocierra en 0 min
# la próxima vez que se llama registrar_alertas_activas (cualquier día), en
# vez de quedar con ts_fin NULL para siempre y leerse distinto según cuándo
# se consulte (mientras "hoy" seguía siendo ese día sumaba tiempo real; en
# cuanto avanza la fecha, minutos_sin_cobertura lo leía en 0 — el bug era ESE
# cambio de lectura, no el 0 en sí).
with almacen._con() as cx:
    cx.execute("INSERT INTO alertas (clave, nombre, fecha, ts_inicio) VALUES (?,?,?,?)",
               ("dario", "Dario", "2020-01-01", time.time() - 999999 * 60))
almacen.registrar_alertas_activas([])  # cualquier llamada normal debe autocurar lo huérfano
with almacen._con() as cx:
    fila_huerfana = cx.execute(
        "SELECT * FROM alertas WHERE clave=? AND fecha=?", ("dario", "2020-01-01")).fetchone()
chk(fila_huerfana is not None and fila_huerfana["ts_fin"] == fila_huerfana["ts_inicio"],
    f"Episodio huérfano de otro día se autocierra en 0 min, no queda NULL para siempre: {dict(fila_huerfana) if fila_huerfana else None}")
min_dario = almacen.minutos_sin_cobertura("2020-01-01", "2020-01-01")
chk(min_dario.get("dario", {}).get("minutos") == 0,
    f"El episodio huérfano ya cerrado se lee igual (0 min) sin importar cuándo se consulte: {min_dario.get('dario')}")

shutil.rmtree(_TMP, ignore_errors=True)

print("\nRESULTADO:", "[X] HAY FALLOS" if fallos else "[OK] TODO CORRECTO")
sys.exit(1 if fallos else 0)
