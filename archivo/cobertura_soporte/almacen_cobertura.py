"""ARCHIVO — coberturas y alertas que vivían en core/almacen.py.

Retirado en agosto de 2026 junto con el rol de soporte. Las TABLAS `coberturas`
y `alertas` NO se borraron de la base de datos (siguen en `_init()` y el
histórico sigue ahí, y la Torre de Control las lee): lo que se quitó son las
funciones que las escribían y las métricas derivadas.

Para reactivar: pegar esto de vuelta en `core/almacen.py` entre la sección
EQUIPO y la de HISTORIAL / MÉTRICAS, y devolver los fragmentos de `resumen()`
que están más abajo.
"""

# =======================================================
# COBERTURAS ("yo lo cubro")
# =======================================================
def abrir_cobertura(titular, soporte):
    """Soporte declara que está cubriendo a un titular. Si ya había una abierta
    para ese titular hoy, se cierra antes (una cobertura activa por persona)."""
    kt, ks = clave(titular), clave(soporte)                      # noqa: F821
    if not kt or not ks:
        return None
    f, ahora = hoy(), time.time()                                # noqa: F821
    with _con() as cx:                                           # noqa: F821
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
    kt, f = clave(titular), hoy()                                # noqa: F821
    with _con() as cx:                                           # noqa: F821
        cur = cx.execute("UPDATE coberturas SET hasta=? WHERE fecha=? AND clave_titular=? AND hasta IS NULL",
                         (time.time(), f, kt))                   # noqa: F821
        return cur.rowcount


def coberturas_activas(fecha=None):
    """{clave_titular: {'soporte':…, 'desde':…}} de las coberturas abiertas."""
    with _con() as cx:                                           # noqa: F821
        filas = cx.execute("""
            SELECT clave_titular, titular, soporte, desde FROM coberturas
            WHERE fecha=? AND hasta IS NULL
        """, (fecha or hoy(),)).fetchall()                       # noqa: F821
    out = {}
    for r in filas:
        d = dict(r)
        d["desde_hora"] = datetime.fromtimestamp(d["desde"]).strftime("%I:%M %p")   # noqa: F821
        out[d["clave_titular"]] = d
    return out


# =======================================================
# ALERTAS ("Requieren cobertura"): trazabilidad de cumplimiento
# =======================================================
# calcular_cobertura() es una función pura (no toca disco), así que quien la
# llama (api_turnos_estado, cada ~8s) es quien avisa aquí quién está AHORA en
# la lista roja. Se abre un episodio la primera vez que alguien aparece ahí y
# se cierra en cuanto deja de estar — así queda el tiempo real que pasó sin
# que nadie confirmara su cobertura, que antes se perdía apenas se refrescaba
# el panel. Sin esto no hay forma de medir qué tan rápido reacciona soporte.
def registrar_alertas_activas(nombres_activos):
    """Sincroniza los episodios abiertos con quién está AHORA mismo en
    'Requieren cobertura'. Idempotente: llamarlo seguido no duplica nada."""
    f, ahora = hoy(), time.time()                                # noqa: F821
    activos = {clave(n): n for n in (nombres_activos or []) if clave(n)}     # noqa: F821
    with _con() as cx:                                           # noqa: F821
        # Episodios de un día anterior que nunca se cerraron (nadie volvió a
        # abrir el panel ese día antes de medianoche): sin una hora de cierre
        # real, cuentan 0 minutos — preferible a dejarlos con ts_fin NULL para
        # siempre, que hace que minutos_sin_cobertura() los lea distinto según
        # cuándo se consulte (mientras "hoy" seguía siendo ese día sí sumaban
        # tiempo real; en cuanto avanza la fecha, se leen como si no hubieran
        # pasado nada, y ese cambio de lectura es el bug real, no el 0 en sí).
        cx.execute("UPDATE alertas SET ts_fin = ts_inicio WHERE fecha != ? AND ts_fin IS NULL", (f,))
        abiertas = {r["clave"]: r["id"] for r in cx.execute(
            "SELECT id, clave FROM alertas WHERE fecha=? AND ts_fin IS NULL", (f,)).fetchall()}
        for k, n in activos.items():
            if k not in abiertas:
                cx.execute("INSERT INTO alertas (clave, nombre, fecha, ts_inicio) VALUES (?,?,?,?)",
                           (k, n, f, ahora))
        for k, id_ in abiertas.items():
            if k not in activos:
                cx.execute("UPDATE alertas SET ts_fin=? WHERE id=?", (ahora, id_))


def minutos_sin_cobertura(desde, hasta):
    """Minutos totales por persona en 'Requieren cobertura' dentro del rango
    (episodios cerrados cuentan su duración real; uno abierto de hoy cuenta
    hasta ahora). Es la métrica de incumplimiento de horario del asesor."""
    with _con() as cx:                                           # noqa: F821
        filas = cx.execute("""
            SELECT clave, nombre, fecha, ts_inicio, ts_fin FROM alertas
            WHERE fecha BETWEEN ? AND ?
        """, (desde, hasta)).fetchall()
    ahora, hoy_txt, out = time.time(), hoy(), {}                 # noqa: F821
    for r in filas:
        fin = r["ts_fin"] if r["ts_fin"] is not None else (ahora if r["fecha"] == hoy_txt else r["ts_inicio"])
        mins = max(0.0, (fin - r["ts_inicio"]) / 60.0)
        d = out.setdefault(r["clave"], {"nombre": r["nombre"], "minutos": 0.0, "episodios": 0})
        d["minutos"] += mins
        d["episodios"] += 1
    for d in out.values():
        d["minutos"] = int(round(d["minutos"]))
    return out


def tiempos_respuesta(desde, hasta):
    """Por cada cobertura reclamada, cuánto tiempo llevaba la persona en
    'Requieren cobertura' antes de que soporte le diera clic — el tiempo de
    respuesta real, no solo un conteo de cuántas veces cubrió."""
    with _con() as cx:                                           # noqa: F821
        cobs = cx.execute("""
            SELECT clave_titular, soporte, desde FROM coberturas
            WHERE fecha BETWEEN ? AND ?
        """, (desde, hasta)).fetchall()
        alertas = cx.execute("""
            SELECT clave, ts_inicio, ts_fin FROM alertas
            WHERE fecha BETWEEN ? AND ?
        """, (desde, hasta)).fetchall()

    por_persona = {}
    for a in alertas:
        por_persona.setdefault(a["clave"], []).append(a)

    resp = {}
    for c in cobs:
        candidatas = [a for a in por_persona.get(c["clave_titular"], [])
                      if a["ts_inicio"] <= c["desde"] and (a["ts_fin"] is None or a["ts_fin"] >= c["desde"] - 5)]
        if not candidatas:
            continue                                # se cubrió sin que hubiera quedado en rojo (poco común)
        alerta = min(candidatas, key=lambda a: c["desde"] - a["ts_inicio"])
        minutos = max(0.0, (c["desde"] - alerta["ts_inicio"]) / 60.0)
        k = clave(c["soporte"])                                  # noqa: F821
        d = resp.setdefault(k, {"nombre": c["soporte"], "veces": 0, "min_totales": 0.0})
        d["veces"] += 1
        d["min_totales"] += minutos
    for d in resp.values():
        d["min_promedio"] = round(d["min_totales"] / d["veces"], 1) if d["veces"] else 0
        d.pop("min_totales", None)
    return resp


# =======================================================
# Fragmentos que se quitaron de resumen()
# =======================================================
# 1) La consulta de coberturas, junto a las de presencia y novedades (y
#    `novs` traía además la columna `cubierto_por`):
#
#         novs = cx.execute("""
#             SELECT clave, nombre, tipo, fecha, cubierto_por FROM novedades
#             WHERE fecha BETWEEN ? AND ? AND activa=1
#         """, (desde, hasta)).fetchall()
#         cobs = cx.execute("""
#             SELECT clave_titular, titular, soporte, desde, hasta, fecha FROM coberturas
#             WHERE fecha BETWEEN ? AND ?
#         """, (desde, hasta)).fetchall()
#
# 2) Los campos del item() por persona:
#
#             personas[k] = {"nombre": nombre, "dias_con_senal": 0, "entradas": [],
#                            "novedades": {}, "total_novedades": 0,
#                            "veces_cubierto": 0, "minutos_cubierto": 0,
#                            "veces_cubriendo": 0, "minutos_presencial": 0,
#                            "minutos_sin_cobertura": 0, "episodios_sin_cobertura": 0,
#                            "veces_respondio": 0, "min_respuesta_prom": 0}
#
# 3) El recorrido de coberturas:
#
#     hoy_txt = hoy()
#     for r in cobs:
#         it = item(r["clave_titular"], r["titular"])
#         it["veces_cubierto"] += 1
#         # Si nunca se liberó (a alguien se le olvidó "dejar de cubrir"), solo
#         # se cuenta hasta ahora mientras sea de HOY — de lo contrario, cada
#         # vez que se abre este resumen la cifra seguiría creciendo contra el
#         # reloj actual para una cobertura de hace semanas. Ver minutos_por_estado.
#         if r["hasta"] is not None:
#             fin = r["hasta"]
#         elif r["fecha"] == hoy_txt:
#             fin = time.time()
#         else:
#             fin = r["desde"]
#         it["minutos_cubierto"] += max(0, int((fin - r["desde"]) / 60))
#         sop = item(clave(r["soporte"]), r["soporte"])
#         sop["veces_cubriendo"] += 1
#
# 4) Las dos métricas derivadas, después de minutos_por_estado:
#
#     # Cumplimiento de horario del asesor: minutos reales en "Requieren
#     # cobertura" (no solo cuántas veces lo cubrieron, sino cuánto tiempo
#     # pasó sin que nadie confirmara).
#     for k, v in minutos_sin_cobertura(desde, hasta).items():
#         it = item(k, v["nombre"])
#         it["minutos_sin_cobertura"] = v["minutos"]
#         it["episodios_sin_cobertura"] = v["episodios"]
#
#     # Desempeño de soporte: qué tan rápido reacciona, no solo cuántas veces.
#     for k, v in tiempos_respuesta(desde, hasta).items():
#         it = item(k, v["nombre"])
#         it["veces_respondio"] = v["veces"]
#         it["min_respuesta_prom"] = v["min_promedio"]
#
# 5) Los totales:
#
#             "totales": {
#                 "novedades": sum(p["total_novedades"] for p in personas.values()),
#                 "minutos_cubierto": sum(p["minutos_cubierto"] for p in personas.values()),
#                 "minutos_presencial": sum(p["minutos_presencial"] for p in personas.values()),
#                 "minutos_sin_cobertura": sum(p["minutos_sin_cobertura"] for p in personas.values()),
#                 "personas": len(personas),
#             }}
#
# 6) En ROLES estaban primero "Soporte" y "Apoyo jefatura / Soporte" (siguen
#    en la lista, pero ya no cambian ningún comportamiento).
