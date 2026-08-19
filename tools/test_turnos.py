# Prueba del lector de horarios y de la lógica de cobertura SIN red:
# construye una réplica del cuadro semanal real (bloques por turno, días en
# columnas y estados por color) y verifica el parseo y las alertas por hora.
# Uso: python tools/test_turnos.py
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import turnos

# --- Colores de la leyenda (como los pinta Google Sheets) ---
AZUL = {"red": 0.235, "green": 0.47, "blue": 0.847}      # Compensatorio
ROSA = {"red": 0.76, "green": 0.48, "blue": 0.63}        # Ausencia
GRIS = {"red": 0.72, "green": 0.72, "blue": 0.72}        # Cambio de Horario
AMAR = {"red": 1.0, "green": 1.0, "blue": 0.0}           # CC Santafe
VERDE = {"red": 0.20, "green": 0.65, "blue": 0.32}       # CC Tesoro
CELESTE = {"red": 0.60, "green": 0.80, "blue": 0.95}     # Mostrador (alias viejo)


def cel(txt="", bg=None):
    c = {"formattedValue": txt} if txt else {}
    if bg:
        c["effectiveFormat"] = {"backgroundColor": bg}
    return c


def fila(*celdas):
    return {"values": list(celdas)}


# Réplica del cuadro: fila de días, 3 bloques de turno y leyenda a la derecha
FILAS = [
    fila(cel(), cel("Semana del 27 de Julio al 2 de Agosto")),
    fila(cel("Horario"), cel("Lunes 27"), cel("Martes 28"), cel("Miercoles 29"),
         cel("Jueves 30"), cel("Viernes 31"), cel("Sábado 1"), cel("Domingo 2")),
    # --- Turno 1 ---
    fila(cel("1 Turno 8:00am a 4:00pm, Sábado 8:00am a 3:00pm"),
         cel("Estefania"), cel("Estefania"), cel("Estefania"), cel("Estefania"),
         cel("Estefania"), cel("Estefania"), cel("Estefania")),
    fila(cel(), cel("Ximena"), cel("Ximena"), cel("Ximena", AZUL), cel("Ximena"),
         cel("Ximena"), cel("Ximena"), cel()),
    fila(cel(), cel("Santiago"), cel("Santiago"), cel("Santiago"), cel("Santiago", CELESTE),
         cel("Santiago"), cel("Santiago"), cel()),
    fila(cel(), cel("Yessika"), cel("Yessika", ROSA), cel("Yessika"), cel("Yessika"),
         cel("Yessika"), cel("Yessika"), cel("Yessika")),
    # Soporte: nombre con "*" al final, ninguna hoja Roles necesaria.
    fila(cel(), cel("Cristian*"), cel("Cristian*"), cel("Cristian*"), cel("Cristian*"),
         cel("Cristian*"), cel("Cristian*"), cel()),
    fila(),
    # --- Turno 2 ---
    fila(cel("2 Turno: 11:00am a 7:00pm, Sábado 10:00am a 5:00pm"),
         cel("Gisela"), cel("Gisela"), cel("Gisela", VERDE), cel("Gisela"),
         cel("Gisela"), cel("Gisela"), cel()),
    fila(cel(), cel("Angelica"), cel("Angelica"), cel("Angelica"), cel("Angelica"),
         cel("Angelica", GRIS), cel("Angelica"), cel()),
    fila(),
    # --- Turno 3 ---
    fila(cel("3 Turno 2:00 a 9:00, Sábado 11:00 a 6:00"),
         cel("Yesid"), cel("Yesid"), cel("Yesid"), cel("Yesid"),
         cel("Yesid"), cel("Yesid"), cel()),
    fila(cel(), cel("Juliana"), cel("Juliana"), cel("Juliana", AMAR), cel("Juliana"),
         cel("Juliana"), cel("Juliana"), cel()),
    fila(),
    fila(),
    # --- Leyenda (texto + color a la derecha) ---
    fila(cel("Leyenda:")),
    fila(cel("Compensatorio"), cel("", AZUL)),
    fila(cel("CC Tesoro"), cel("", VERDE)),
    fila(cel("CC Santafe"), cel("", AMAR)),
    fila(cel("Cambio de horario"), cel("", GRIS)),
    fila(cel("Ausencia"), cel("", ROSA)),
    fila(cel("Mostrador"), cel("", CELESTE)),
    fila(),
    # --- Tabla de almuerzo (DEBAJO de la leyenda): no debe leerse como turno
    # ni sus horas como nombres — es justo el bug que se corrigió.
    fila(cel("Almuerzo"), cel("Desde"), cel("Hasta")),
    fila(cel("1 Turno"), cel("12:00 pm"), cel("1:00 pm")),
    fila(cel("2 Turno"), cel("1:00 pm"), cel("2:00 pm")),
    fila(cel("3 Turno"), cel("6:00 pm"), cel("6:20 pm")),
]

META = {"sheets": [{"data": [{"rowData": FILAS}]}]}

fallos = 0


def chk(cond, msg):
    global fallos
    print(("[OK] " if cond else "[X]  ") + msg)
    if not cond:
        fallos += 1


# =====================================================
# 1) Parseo
# =====================================================
h = turnos.parsear_horario(META)
chk("error" not in h, f"Parsea sin error ({h.get('error','')})")
chk(set(h.get("turnos", {})) == {1, 2, 3}, f"Detecta 3 turnos: {sorted(h.get('turnos', {}))}")
chk(h["turnos"][1]["sem"] == (8.0, 16.0), f"Turno 1 L-V 8:00-16:00 -> {h['turnos'][1]['sem']}")
chk(h["turnos"][1]["sab"] == (8.0, 15.0), f"Turno 1 sábado 8:00-15:00 -> {h['turnos'][1]['sab']}")
chk(h["turnos"][3]["sem"] == (14.0, 21.0), f"Turno 3 usa config (texto ambiguo) -> {h['turnos'][3]['sem']}")

est = {a["estado"] for a in h["asignaciones"]}
chk("compensatorio" in est and "ausencia" in est, f"Lee estados por color: {sorted(est)}")

def busca(nombre, dia):
    return [a for a in h["asignaciones"] if a["nombre"] == nombre and a["dia"] == dia]

chk(busca("Ximena", 2) and busca("Ximena", 2)[0]["estado"] == "compensatorio",
    "Ximena el miércoles = Compensatorio (celda azul)")
chk(busca("Ximena", 0) and busca("Ximena", 0)[0]["estado"] == "normal",
    "Ximena el lunes = normal (celda blanca)")
chk(busca("Yessika", 1) and busca("Yessika", 1)[0]["estado"] == "ausencia",
    "Yessika el martes = Ausencia (celda rosa)")
chk(busca("Juliana", 2) and busca("Juliana", 2)[0]["estado"] == "cc santafe",
    "Juliana el miércoles = CC Santafe (celda amarilla)")
chk(busca("Gisela", 2) and busca("Gisela", 2)[0]["estado"] == "cc tesoro",
    "Gisela el miércoles = CC Tesoro (celda verde)")
chk(busca("Santiago", 3) and busca("Santiago", 3)[0]["estado"] == "mostrador",
    "Santiago el jueves = Mostrador (celda celeste, alias viejo)")
chk(not any(a["nombre"].lower().startswith(("lunes", "sabado", "domingo")) for a in h["asignaciones"]),
    "No confunde los encabezados de día con nombres")

# =====================================================
# 1c) Soporte por "*", tabla de Almuerzo y límite del cuadro (Leyenda)
# =====================================================
nombres = {a["nombre"] for a in h["asignaciones"]}
chk("Cristian" in nombres, f"'Cristian*' se lee sin el asterisco: {sorted(nombres)}")
chk("Cristian*" not in nombres, "El asterisco no se queda pegado al nombre")
chk(h.get("roles", {}).get("cristian") == "Soporte",
    f"El '*' registra el rol Soporte para Cristian: {h.get('roles')}")

basura = {"12:00 pm", "1:00 pm", "2:00 pm", "6:00 pm", "6:20 pm", "Desde",
          "Hasta", "Almuerzo", "1 Turno", "2 Turno", "3 Turno", "Leyenda:"}
chk(not (nombres & basura),
    f"La leyenda y la tabla de Almuerzo NO contaminan la lista de personas: {nombres & basura}")

chk(h.get("almuerzos") == {1: (12.0, 13.0), 2: (13.0, 14.0), 3: (18.0, 18.0 + 20 / 60)},
    f"Lee la tabla de Almuerzo (Desde/Hasta por turno): {h.get('almuerzos')}")

chk(h.get("vacaciones") == [],
    f"Cuadro sin columna 'Vacaciones' -> lista vacía, no revienta: {h.get('vacaciones')}")

# =====================================================
# 1b) Semana calculada sola (ya no se lee de la hoja)
# =====================================================
# 2026-07-27 es lunes; su sábado es 2026-08-01 (cruza de julio a agosto).
sem_lunes = turnos._semana_actual(datetime(2026, 7, 27, 9, 0))
chk(sem_lunes == "Semana del 27 de Julio al 2 de Agosto de 2026",
    f"Lunes en la semana -> {sem_lunes!r}")

sem_sab_antes = turnos._semana_actual(datetime(2026, 8, 1, 22, 59))
chk(sem_sab_antes == "Semana del 27 de Julio al 2 de Agosto de 2026",
    f"Sábado 10:59pm -> aún semana actual: {sem_sab_antes!r}")

sem_sab_corte = turnos._semana_actual(datetime(2026, 8, 1, 23, 0))
chk(sem_sab_corte == "Semana del 3 al 9 de Agosto de 2026",
    f"Sábado 11:00pm -> ya cambia a la semana siguiente: {sem_sab_corte!r}")

sem_domingo = turnos._semana_actual(datetime(2026, 8, 2, 10, 0))
chk(sem_domingo == "Semana del 3 al 9 de Agosto de 2026",
    f"Domingo -> sigue mostrando la semana siguiente (no vuelve atrás): {sem_domingo!r}")

# =====================================================
# 2) Cobertura según la hora
# =====================================================
LUNES = datetime(2026, 7, 27, 9, 0)      # lunes 9:00am
chk(LUNES.weekday() == 0, "El 27/07/2026 es lunes (base de la prueba)")

c = turnos.calcular_cobertura(h, LUNES)
nombres_cob = {x["nombre"] for x in c["requieren_cobertura"]}
chk("Estefania" in nombres_cob and "Ximena" in nombres_cob,
    f"Lunes 9:00am sin señal -> turno 1 requiere cobertura: {sorted(nombres_cob)}")
chk("Cristian" not in nombres_cob,
    f"Cristian (soporte por '*') nunca se pide cubrir, sin hoja Roles: {sorted(nombres_cob)}")

# Turno 2/3 (Gisela, Yesid) aún no entran a las 9am, pero el turno 1 ya abrió
# (8am): pueden tener chats pendientes de ayer sin revisar, así que TAMBIÉN
# entran a "Requieren cobertura" — con un motivo distinto al de "sin señal",
# y ya NO en "Aún no entran".
chk({"Gisela", "Yesid"} <= nombres_cob,
    f"Turno 2/3 antes de entrar, con el día ya abierto -> pendientes de ayer: {sorted(nombres_cob)}")
chk(not ({"Gisela", "Yesid"} & {x["nombre"] for x in c["por_entrar"]}),
    "Turno 2/3 con pendientes de ayer ya NO está en 'Aún no entran'")
pendientes = [x for x in c["requieren_cobertura"] if x["nombre"] in ("Gisela", "Yesid")]
chk(all(x.get("pendientes_ayer") and "pendientes de ayer" in x["motivo"] for x in pendientes),
    f"El motivo de turno 2/3 antes de entrar es sobre pendientes de ayer: {pendientes}")

# Con "Yo lo cubro" reciente (< 2.5h): pasa a "Aún no entran" tranquilo.
cob_pend_fresca = {turnos.clave("Gisela"): {"soporte": "Mariana", "desde": time.time() - 60 * 60,
                                             "desde_hora": "8:00 AM"}}
c_pf = turnos.calcular_cobertura(h, LUNES, coberturas=cob_pend_fresca)
gisela_pf = [x for x in c_pf["por_entrar"] if x["nombre"] == "Gisela"]
chk(bool(gisela_pf) and gisela_pf[0].get("cubierto_por") == "Mariana"
    and gisela_pf[0].get("estado_etq") == "Pendientes de ayer ya revisados",
    f"Pendientes de ayer con 'Yo lo cubro' de hace 1h: tranquilo en 'Aún no entran': {gisela_pf}")
chk("Gisela" not in {x["nombre"] for x in c_pf["requieren_cobertura"]},
    "Con pendientes ya revisados (vigente), Gisela no está en Requieren cobertura")

# Con "Yo lo cubro" vencido (> 2.5h): vuelve a pedir que alguien revise.
cob_pend_vencida = {turnos.clave("Gisela"): {"soporte": "Mariana", "desde": time.time() - 160 * 60,
                                              "desde_hora": "6:20 AM"}}
c_pv = turnos.calcular_cobertura(h, LUNES, coberturas=cob_pend_vencida)
gisela_pv = [x for x in c_pv["requieren_cobertura"] if x["nombre"] == "Gisela"]
chk(bool(gisela_pv) and gisela_pv[0].get("cubierto_por") is None and gisela_pv[0].get("pendientes_ayer"),
    f"Pendientes de ayer con revisión de hace 160 min (> 2.5h): vuelve a pedir revisión: {gisela_pv}")

# Turno 1 nunca lleva la marca de "pendientes de ayer" (es quien abre el día).
chk(not any(x.get("pendientes_ayer") for x in c["requieren_cobertura"] if x["turno"] == 1),
    "Turno 1 nunca se marca como 'pendientes de ayer'")

turno1_cob = [x for x in c["requieren_cobertura"] if x["turno"] == 1]
chk(bool(turno1_cob) and all(x["motivo"].startswith("sin señal") for x in turno1_cob),
    "El motivo de turno 1 sigue indicando que no hay señal desde el inicio del turno")

# Con presencia reciente de Estefania
pres = {turnos.clave("Estefania"): {"ts": time.time() - 120}}
c2 = turnos.calcular_cobertura(h, LUNES, presencia=pres)
chk("Estefania" in {x["nombre"] for x in c2["en_linea"]},
    "Estefania vista hace 2 min -> aparece En línea")
chk("Estefania" not in {x["nombre"] for x in c2["requieren_cobertura"]},
    "Estefania ya no aparece como pendiente de cobertura")

# Señal vieja (45 min) -> vuelve a requerir cobertura
pres_vieja = {turnos.clave("Estefania"): {"ts": time.time() - 45 * 60}}
c3 = turnos.calcular_cobertura(h, LUNES, presencia=pres_vieja)
item = [x for x in c3["requieren_cobertura"] if x["nombre"] == "Estefania"]
chk(bool(item) and "45 min" in item[0]["motivo"],
    f"Señal de hace 45 min -> cobertura con motivo: {item[0]['motivo'] if item else None}")

# Miércoles: Ximena en compensatorio — igual que turno terminado, puede
# tener un cliente en proceso: sin cobertura, pide revisión cada 2.5h.
MIER = datetime(2026, 7, 29, 9, 0)
c4 = turnos.calcular_cobertura(h, MIER)
ximena_roja = [x for x in c4["requieren_cobertura"] if x["nombre"] == "Ximena"]
chk(bool(ximena_roja) and ximena_roja[0].get("no_viene_hoy") is True,
    f"Miércoles: Ximena (Compensatorio) SIN cobertura -> Requieren cobertura: {ximena_roja}")

cob_ximena = {turnos.clave("Ximena"): {"soporte": "Cristian", "desde": time.time() - 30 * 60,
                                        "desde_hora": "8:45 AM"}}
c4b = turnos.calcular_cobertura(h, MIER, coberturas=cob_ximena)
chk("Ximena" in {x["nombre"] for x in c4b["no_se_espera"]},
    "Miércoles: Ximena (Compensatorio) CON cobertura vigente -> 'no se espera' con su etiqueta")
chk("Ximena" not in {x["nombre"] for x in c4b["requieren_cobertura"]},
    "Miércoles: Ximena (Compensatorio) con cobertura vigente ya no está en Requieren cobertura")

# Miércoles 1:00pm: Gisela en Tesoro (turno 2, 11am-7pm) -> ausencia informada
# con sede=True, NO alarma roja y NO "no se espera" (sigue trabajando, solo
# que sus chats quedan sin atender).
MIER_TARDE = datetime(2026, 7, 29, 13, 0)
c4b = turnos.calcular_cobertura(h, MIER_TARDE)
gisela_aus = [x for x in c4b["ausencia_informada"] if x["nombre"] == "Gisela"]
chk(bool(gisela_aus) and gisela_aus[0].get("sede") is True,
    f"Miércoles 1pm: Gisela (Tesoro) -> ausencia informada con sede=True: {gisela_aus}")
chk("Gisela" not in {x["nombre"] for x in c4b["requieren_cobertura"]},
    "Gisela (Tesoro) NO dispara alarma roja")
chk("Gisela" not in {x["nombre"] for x in c4b["no_se_espera"]},
    "Gisela (Tesoro) NO cae en 'no se espera' (sigue trabajando, solo que presencial)")

# Jueves 10:00am: Santiago en Mostrador (turno 1, 8am-4pm) -> mismo caso
JUEVES_MOSTRADOR = datetime(2026, 7, 30, 10, 0)
c4c = turnos.calcular_cobertura(h, JUEVES_MOSTRADOR)
santiago_aus = [x for x in c4c["ausencia_informada"] if x["nombre"] == "Santiago"]
chk(bool(santiago_aus) and santiago_aus[0].get("sede") is True,
    f"Jueves 10am: Santiago (Mostrador) -> ausencia informada con sede=True: {santiago_aus}")

# =====================================================
# Almuerzo automático (Miércoles 12:30pm, turno 1: 12:00-1:00pm)
# =====================================================
MIER_ALMUERZO = datetime(2026, 7, 29, 12, 30)
c4d = turnos.calcular_cobertura(h, MIER_ALMUERZO)
estefania_aus = [x for x in c4d["ausencia_informada"] if x["nombre"] == "Estefania"]
chk(bool(estefania_aus) and estefania_aus[0].get("estado") == "almuerzo",
    f"Miércoles 12:30 (ventana de almuerzo turno 1) -> Estefania en almuerzo automático: {estefania_aus}")
chk("Estefania" not in {x["nombre"] for x in c4d["requieren_cobertura"]},
    "Estefania en almuerzo automático NO dispara alarma roja")

# Si ya marcó "Desconectado", el almuerzo automático NO se lo pisa.
estados_desc = {turnos.clave("Estefania"): {"estado": "desconectado", "ts": time.time()}}
c4e = turnos.calcular_cobertura(h, MIER_ALMUERZO, estados=estados_desc)
estefania_desc = [x for x in c4e["ausencia_informada"] if x["nombre"] == "Estefania"]
chk(bool(estefania_desc) and estefania_desc[0].get("estado") == "desconectado",
    f"Con 'Desconectado' ya marcado, el almuerzo automático no lo reemplaza: {estefania_desc}")

# Antes de la hora: 7:30am nadie del turno 1 debe alertar
TEMPRANO = datetime(2026, 7, 27, 7, 30)
c5 = turnos.calcular_cobertura(h, TEMPRANO)
chk(not c5["requieren_cobertura"],
    "7:30am (antes del turno 1) -> no hay alertas todavía")

# Tolerancia: 8:10am aún está dentro de los 15 min de gracia para turno 1
# (turno 2/3 puede tener pendientes de ayer desde que abrió el día a las
# 8am, así que se acota la revisión a turno 1 para no mezclar los dos casos).
c6 = turnos.calcular_cobertura(h, datetime(2026, 7, 27, 8, 10))
chk(not any(x["turno"] == 1 for x in c6["requieren_cobertura"]),
    "8:10am -> turno 1 dentro de la tolerancia de 15 min")
c7 = turnos.calcular_cobertura(h, datetime(2026, 7, 27, 8, 20))
chk(any(x["turno"] == 1 for x in c7["requieren_cobertura"]), "8:20am -> pasada la tolerancia, ya alerta turno 1")

# Fuera de jornada
c8 = turnos.calcular_cobertura(h, datetime(2026, 7, 27, 23, 0))
chk(not c8["requieren_cobertura"], "11:00pm -> nadie en turno, sin alertas")

# =====================================================
# Turno terminado: mismo mecanismo que "antes de entrar" (pendientes), pero
# del otro lado. Sin cobertura -> alarma roja (puede haber un cliente en
# proceso). Con "Yo lo cubro" vigente (< 2.5h) -> tranquilo en "Hoy no se
# espera". Si esa cobertura vence, vuelve a sonar. Después del cierre del
# día, ya no se rastrea nada.
# =====================================================
LUNES_5PM = datetime(2026, 7, 27, 17, 0)  # Estefania (T1, 8am-4pm) ya terminó
c10 = turnos.calcular_cobertura(h, LUNES_5PM)
est_roja = [x for x in c10["requieren_cobertura"] if x["nombre"] == "Estefania"]
chk(bool(est_roja) and est_roja[0].get("turno_terminado") is True,
    f"5pm sin cobertura: Estefania (T1 terminó) puede tener clientes sin atender -> Requieren cobertura: {est_roja}")
chk("Estefania" not in {x["nombre"] for x in c10["no_se_espera"]},
    "Turno terminado SIN cobertura no está tranquilo en 'Hoy no se espera'")
chk("Estefania" not in {x["nombre"] for x in c10["ausencia_informada"]},
    "Turno terminado SIN cobertura tampoco aparece en Ausencia informada")

cob_fresca = {turnos.clave("Estefania"): {"soporte": "Cristian", "desde": time.time() - 10 * 60,
                                           "desde_hora": "4:50 PM"}}
c10b = turnos.calcular_cobertura(h, LUNES_5PM, coberturas=cob_fresca)
est_cub = [x for x in c10b["no_se_espera"] if x["nombre"] == "Estefania"]
chk(bool(est_cub) and est_cub[0].get("cubierto_por") == "Cristian",
    f"5pm con 'Yo lo cubro' de hace 10 min: en 'Hoy no se espera', mostrando quién cubre: {est_cub}")
chk("Estefania" not in {x["nombre"] for x in c10b["requieren_cobertura"]},
    "Con cobertura vigente (< 2.5h), turno terminado no está en Requieren cobertura")

# Cobertura de 95 min: sigue vigente para el ciclo de 2.5h (150 min), aunque
# ya hubiera vencido para el ciclo corto de "en turno" (90 min) — son ciclos
# distintos a propósito, porque ya no es tan urgente como estar en turno.
cob_95 = {turnos.clave("Estefania"): {"soporte": "Cristian", "desde": time.time() - 95 * 60,
                                       "desde_hora": "3:25 PM"}}
c10c = turnos.calcular_cobertura(h, LUNES_5PM, coberturas=cob_95)
est_95 = [x for x in c10c["no_se_espera"] if x["nombre"] == "Estefania"]
chk(bool(est_95), f"Turno terminado, cobertura de 95 min: sigue vigente para el ciclo de 2.5h: {est_95}")
chk("Estefania" not in {x["nombre"] for x in c10c["requieren_cobertura"]},
    "Con la cobertura de 95 min aún vigente (< 150 min), no vuelve a Requieren cobertura")

# Cobertura de 160 min: ya venció el ciclo de 2.5h -> vuelve a sonar.
cob_vencida = {turnos.clave("Estefania"): {"soporte": "Cristian", "desde": time.time() - 160 * 60,
                                            "desde_hora": "2:00 PM"}}
c10d = turnos.calcular_cobertura(h, LUNES_5PM, coberturas=cob_vencida)
est_venc = [x for x in c10d["requieren_cobertura"] if x["nombre"] == "Estefania"]
chk(bool(est_venc) and est_venc[0].get("cubierto_por") is None,
    f"Turno terminado, cobertura de 160 min (> 150): venció, vuelve a Requieren cobertura: {est_venc}")

LUNES_10PM = datetime(2026, 7, 27, 22, 0)  # pasado el cierre del día (9pm)
c11 = turnos.calcular_cobertura(h, LUNES_10PM)
en_alguna = any(x.get("nombre") == "Estefania"
                for k in ("requieren_cobertura", "ausencia_informada", "en_linea", "por_entrar", "no_se_espera")
                for x in c11.get(k, []))
chk(not en_alguna, "10pm (pasado el cierre) -> Estefania ya no aparece en ninguna lista")

# Lo mismo pero EN TURNO (caso de siempre, no "terminado"): sin cobertura,
# alarma roja; con cobertura vigente, pasa a ausencia informada.
cob_fresca_yessika = {turnos.clave("Yessika"): {"soporte": "Mariana", "desde": time.time() - 5 * 60,
                                                 "desde_hora": "9:55 AM"}}
c12 = turnos.calcular_cobertura(h, LUNES, coberturas=cob_fresca_yessika)
yes_cub = [x for x in c12["ausencia_informada"] if x["nombre"] == "Yessika"]
chk(bool(yes_cub) and not yes_cub[0].get("turno_terminado"),
    f"En turno, con cobertura vigente: pasa a ausencia informada (no roja): {yes_cub}")
chk("Yessika" not in {x["nombre"] for x in c12["requieren_cobertura"]},
    "En turno, con cobertura vigente: ya no está en Requieren cobertura")

# "Aún no entran" nunca se fuerza a rojo, tenga o no cobertura (ni vencida).
cob_vieja_gisela = {turnos.clave("Gisela"): {"soporte": "Cristian", "desde": time.time() - 200 * 60,
                                              "desde_hora": "6:00 AM"}}
c13 = turnos.calcular_cobertura(h, TEMPRANO, coberturas=cob_vieja_gisela)
gisela_pe = [x for x in c13["por_entrar"] if x["nombre"] == "Gisela"]
chk(bool(gisela_pe) and gisela_pe[0].get("cubierto_por") == "Cristian",
    f"Aún no entra, con cobertura (aunque vieja) -> sigue en por_entrar, se muestra igual: {gisela_pe}")
chk("Gisela" not in {x["nombre"] for x in c13["requieren_cobertura"]},
    "Aún no entra nunca aparece en Requieren cobertura, sin importar la cobertura")

# Roles: soporte y jefe no se cubren
h_roles = dict(h)
h_roles["roles"] = {"estefania": "Soporte", "ximena": "Red social"}
c9 = turnos.calcular_cobertura(h_roles, LUNES)
n9 = {x["nombre"] for x in c9["requieren_cobertura"]}
chk("Estefania" not in n9 and "Ximena" in n9,
    f"Con roles: no se cubre a Soporte, sí a Red social: {sorted(n9)}")

# Personas para el selector
p = turnos.personas_del_horario(h)
chk("Estefania" in p and "Juliana" in p and len(p) == len(set(p)),
    f"Lista de personas sin duplicados ({len(p)}): {p}")

# =====================================================
# Cuadro SIN el rótulo "Leyenda:" (la jefa la reacomodó al lado del turno 1,
# como pasó en producción) — el límite debe caer solo en "Almuerzo".
# =====================================================
FILAS_SIN_LEYENDA = [
    fila(cel(), cel(), cel("Semana del 17 al 23 de Agosto de 2026")),
    fila(cel(), cel(), cel("Lunes 17"), cel("Martes 18"), cel("Miercoles 19"),
         cel("Jueves 20"), cel("Viernes 21"), cel("Sabado 22"), cel("Domingo 23"),
         cel(), cel(), cel("Compensatorio"), cel("", AZUL)),
    fila(cel(), cel("1 Turno 8:00am a 4:00pm, Sábado 8:00am a 3:00pm"), cel(),
         cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"),
         cel(), cel(), cel("CC Tesoro"), cel("", VERDE)),
    fila(cel(), cel(), cel(), cel("Jennifer"), cel("Jennifer"), cel("Jennifer"),
         cel("Jennifer"), cel("Jennifer"), cel("Elvia*"),
         cel(), cel(), cel("Soporte"), cel("*")),
    fila(),
    fila(cel(), cel("2 Turno 11:00am a 7:00pm, Sábado 10:00am a 5:00pm"),
         cel("Estefania"), cel("Estefania"), cel("Estefania"), cel("Estefania"),
         cel("Estefania"), cel("Estefania")),
    fila(),
    fila(cel(), cel("3 Turno 2:00pm a 9:00pm, Sábado 11:00am a 6:00pm"), cel(),
         cel("Cristian*"), cel("Cristian*"), cel("Cristian*"), cel("Cristian*"), cel("Cristian*")),
    fila(),
    # Sin fila "Leyenda:" en ningún lado — solo la tabla de Almuerzo marca el
    # límite. En columnas 14-16 (fuera de col_dia, 2-8), como en la hoja real.
    fila(*([cel()] * 14), cel("Almuerzo"), cel("Desde"), cel("Hasta")),
    fila(*([cel()] * 14), cel("1 Turno"), cel("12:00 pm"), cel("1:00 pm")),
    fila(*([cel()] * 14), cel("2 Turno"), cel("1:00 pm"), cel("2:00 pm")),
    fila(*([cel()] * 14), cel("3 Turno"), cel("6:00 pm"), cel("6:20 pm")),
]
META_SIN_LEYENDA = {"sheets": [{"data": [{"rowData": FILAS_SIN_LEYENDA}]}]}
h_sl = turnos.parsear_horario(META_SIN_LEYENDA)
chk("error" not in h_sl, f"Sin 'Leyenda:' (solo Almuerzo como límite): parsea sin error ({h_sl.get('error', '')})")
nombres_sl = {a["nombre"] for a in h_sl.get("asignaciones", [])}
basura_sl = {"12:00 pm", "1:00 pm", "2:00 pm", "6:00 pm", "6:20 pm", "Almuerzo", "Desde", "Hasta"}
chk(not (nombres_sl & basura_sl),
    f"La tabla de Almuerzo no contamina aunque falte 'Leyenda:': {nombres_sl & basura_sl}")
chk(h_sl.get("roles", {}).get("elvia") == "Soporte" and h_sl.get("roles", {}).get("cristian") == "Soporte",
    f"Roles por '*' detectados igual, con la leyenda al lado del turno 1: {h_sl.get('roles')}")
chk("cc tesoro" in h_sl.get("estados_leyenda", []),
    f"Leyenda detectada aunque esté junto al turno 1, no debajo: {h_sl.get('estados_leyenda')}")

# =====================================================
# Tabla de Almuerzo AL LADO del cuadro (mismas filas que la gente del turno
# 1, no debajo de todo) — bug real de producción: "1 Turno"/"2 Turno"/
# "3 Turno" son las claves de esa tabla, y si quedan en las filas de turno 1
# se confunden con el inicio de un bloque nuevo — el turno 1 se cortaba a una
# sola persona (la de la primera fila) y el resto caía en turno 2/3.
# =====================================================
FILAS_ALMUERZO_JUNTO = [
    fila(cel(), cel(), cel("Semana del 17 al 23 de Agosto de 2026")),
    fila(cel(), cel(), cel("Lunes 17"), cel("Martes 18"), cel("Miercoles 19"),
         cel("Jueves 20"), cel("Viernes 21"), cel("Sabado 22"), cel("Domingo 23"),
         cel(), cel(), cel("Compensatorio"), cel(), cel(), cel(),
         cel("Almuerzo"), cel("Desde"), cel("Hasta"), cel(), cel("Vacaciones")),
    fila(cel(), cel("1 Turno 8:00am a 4:00pm, Sábado 8:00am a 3:00pm"),
         cel(), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"),
         cel(), cel(), cel("CC Tesoro"), cel(), cel(), cel(),
         cel("1 Turno"), cel("12:00 pm"), cel("1:00 pm"), cel(), cel("Jennifer")),
    fila(cel(), cel(), cel(), cel("Jennifer"), cel("Jennifer"), cel("Jennifer"),
         cel("Jennifer"), cel("Jennifer"), cel("Elvia*"),
         cel(), cel(), cel(), cel(), cel(), cel(),
         cel("2 Turno"), cel("1:00 pm"), cel("2:00 pm"), cel(), cel("Roberto")),
    fila(cel(), cel(), cel(), cel("Natalia"), cel("Natalia"), cel("Natalia"),
         cel("Natalia"), cel("Natalia"), cel("Laura"),
         cel(), cel(), cel(), cel(), cel(), cel(),
         cel("3 Turno"), cel("6:00 pm"), cel("6:20 pm")),
    fila(),
    fila(cel(), cel("2 Turno 11:00am a 7:00pm, Sábado 10:00am a 5:00pm"),
         cel("Estefania"), cel("Estefania"), cel("Estefania"), cel("Estefania"),
         cel("Estefania"), cel("Estefania")),
    fila(),
    fila(cel(), cel("3 Turno 2:00pm a 9:00pm, Sábado 11:00am a 6:00pm"), cel(),
         cel("Cristian*"), cel("Cristian*"), cel("Cristian*"), cel("Cristian*"), cel("Cristian*")),
]
META_ALMUERZO_JUNTO = {"sheets": [{"data": [{"rowData": FILAS_ALMUERZO_JUNTO}]}]}
h_aj = turnos.parsear_horario(META_ALMUERZO_JUNTO)
chk("error" not in h_aj, f"Almuerzo al lado del cuadro: parsea sin error ({h_aj.get('error', '')})")
turno1_aj = {a["nombre"] for a in h_aj.get("asignaciones", []) if a["turno"] == 1}
chk({"Gisela", "Jennifer", "Elvia", "Natalia", "Laura"} <= turno1_aj,
    f"Turno 1 no se corta por la tabla de Almuerzo al lado (mismas filas): {sorted(turno1_aj)}")
chk(h_aj.get("almuerzos") == {1: (12.0, 13.0), 2: (13.0, 14.0), 3: (18.0, 18.0 + 20 / 60)},
    f"La tabla de Almuerzo al lado se sigue leyendo bien pese al cambio: {h_aj.get('almuerzos')}")
chk(h_aj.get("vacaciones") == ["Jennifer", "Roberto"],
    f"Lee la columna 'Vacaciones' (nombre por fila, en cualquier columna): {h_aj.get('vacaciones')}")

# =====================================================
# Vacaciones: manda sobre cualquier otra cosa del cuadro (Jennifer SÍ tiene
# turno 1 asignado esta semana) y también funciona para alguien que no tiene
# ninguna fila en el cuadro (Roberto). Informativo en "Hoy no se espera",
# pero pide revisión UNA VEZ AL DÍA en "Requieren cobertura" — se reinicia a
# medianoche, no cada cierto número de minutos.
# =====================================================
MIER_VAC = datetime(2026, 8, 19, 10, 0)   # miércoles, en horas de turno 1

c_jen = turnos.calcular_cobertura(h_aj, MIER_VAC)
jen_roja = [x for x in c_jen["requieren_cobertura"] if x["nombre"] == "Jennifer"]
chk(bool(jen_roja) and jen_roja[0].get("vacaciones") is True,
    f"Jennifer (turno 1 esta semana, pero de vacaciones) -> Requieren cobertura: {jen_roja}")
rob_roja = [x for x in c_jen["requieren_cobertura"] if x["nombre"] == "Roberto"]
chk(bool(rob_roja) and rob_roja[0].get("vacaciones") is True,
    f"Roberto (sin ninguna fila en el cuadro, solo en Vacaciones) -> Requieren cobertura: {rob_roja}")
chk(all(x["turno"] != 1 or x["nombre"] != "Jennifer" for x in c_jen["por_entrar"] + c_jen["ausencia_informada"] + c_jen["en_linea"]),
    "Jennifer de vacaciones no aparece en ninguna lista de turno normal")

# Con "Yo lo cubro" de HOY (aunque haga rato): tranquila el resto del día.
cob_hoy = {turnos.clave("Jennifer"): {"soporte": "Cristian", "desde": MIER_VAC.timestamp() - 3 * 3600,
                                       "desde_hora": "7:00 AM"}}
c_jen2 = turnos.calcular_cobertura(h_aj, MIER_VAC, coberturas=cob_hoy)
jen_ns = [x for x in c_jen2["no_se_espera"] if x["nombre"] == "Jennifer"]
chk(bool(jen_ns) and jen_ns[0].get("cubierto_por") == "Cristian",
    f"Vacaciones con 'Yo lo cubro' de hoy: tranquila en 'Hoy no se espera' el resto del día: {jen_ns}")
chk("Jennifer" not in {x["nombre"] for x in c_jen2["requieren_cobertura"]},
    "Con revisión de hoy ya hecha, Jennifer no está en Requieren cobertura")

# Con "Yo lo cubro" de AYER (aunque sea reciente en minutos): vuelve a sonar
# hoy — el ciclo se reinicia a medianoche, no a las X horas.
AYER_9PM = datetime(2026, 8, 18, 21, 0)
cob_ayer = {turnos.clave("Jennifer"): {"soporte": "Cristian", "desde": AYER_9PM.timestamp(),
                                        "desde_hora": "9:00 PM (ayer)"}}
c_jen3 = turnos.calcular_cobertura(h_aj, MIER_VAC, coberturas=cob_ayer)
jen_roja3 = [x for x in c_jen3["requieren_cobertura"] if x["nombre"] == "Jennifer"]
chk(bool(jen_roja3), f"Vacaciones: la revisión de ayer no cuenta hoy, vuelve a pedir: {jen_roja3}")

# =====================================================
# Auditoría: si la palabra "Almuerzo" cae en una fila que TODAVÍA tiene gente
# del cuadro (en las columnas de los días), esa fila nunca debe cortar el
# cuadro — antes bastaba con que apareciera en cualquier columna de la fila.
# =====================================================
FILAS_ALMUERZO_EN_FILA_CON_GENTE = [
    fila(cel(), cel(), cel("Semana del 17 al 23 de Agosto de 2026")),
    fila(cel(), cel(), cel("Lunes 17"), cel("Martes 18"), cel("Miercoles 19"),
         cel("Jueves 20"), cel("Viernes 21"), cel("Sabado 22"), cel("Domingo 23")),
    fila(cel(), cel("1 Turno 8:00am a 4:00pm, Sábado 8:00am a 3:00pm"),
         cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"),
         *([cel()] * 12), cel("Almuerzo")),   # "Almuerzo" en la MISMA fila que Gisela
    fila(cel(), cel(), cel("Jennifer"), cel("Jennifer"), cel("Jennifer"),
         cel("Jennifer"), cel("Jennifer"), cel("Jennifer")),
    fila(),
    fila(cel(), cel("2 Turno 11:00am a 7:00pm, Sábado 10:00am a 5:00pm"),
         cel("Estefania"), cel("Estefania"), cel("Estefania"), cel("Estefania"),
         cel("Estefania"), cel("Estefania")),
    fila(),
    fila(cel(), cel("3 Turno 2:00pm a 9:00pm, Sábado 11:00am a 6:00pm"), cel(),
         cel("Cristian*"), cel("Cristian*"), cel("Cristian*"), cel("Cristian*"), cel("Cristian*")),
    fila(),
    fila(*([cel()] * 20), cel("Almuerzo"), cel("Desde"), cel("Hasta")),
    fila(*([cel()] * 20), cel("1 Turno"), cel("12:00 pm"), cel("1:00 pm")),
]
META_ALMUERZO_EN_FILA_CON_GENTE = {"sheets": [{"data": [{"rowData": FILAS_ALMUERZO_EN_FILA_CON_GENTE}]}]}
h_afg = turnos.parsear_horario(META_ALMUERZO_EN_FILA_CON_GENTE)
turnos_afg = {a["turno"] for a in h_afg.get("asignaciones", [])}
chk({1, 2, 3} <= turnos_afg,
    f"'Almuerzo' en una fila con gente no corta el cuadro (turnos 2 y 3 se siguen viendo): {sorted(turnos_afg)}")

print("\nRESULTADO:", "[X] HAY FALLOS" if fallos else "[OK] TODO CORRECTO")
sys.exit(1 if fallos else 0)
