# Prueba del lector de horarios y del panel informativo SIN red: construye una
# réplica del cuadro semanal real (bloques por turno, días en columnas y
# estados por color) y verifica el parseo y las listas del panel por hora.
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
    # El "*" al final del nombre marcaba a soporte; ese rol ya no existe, pero
    # se sigue quitando para no duplicar a la persona.
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
    # --- Turno 3 (auditoría de calidad) ---
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

LISTAS = ("ausencia_informada", "en_linea", "por_entrar", "no_se_espera")

fallos = 0


def chk(cond, msg):
    global fallos
    print(("[OK] " if cond else "[X]  ") + msg)
    if not cond:
        fallos += 1


def donde(panel, nombre):
    """En qué listas del panel aparece esa persona."""
    return {k for k in LISTAS if any(x["nombre"] == nombre for x in panel.get(k, []))}


def uno(panel, lista, nombre):
    """El item de esa persona en esa lista, o None."""
    for x in panel.get(lista, []):
        if x["nombre"] == nombre:
            return x
    return None


# =====================================================
# 1) Parseo
# =====================================================
h = turnos.parsear_horario(META)
chk("error" not in h, f"Parsea sin error ({h.get('error','')})")
chk(set(h.get("turnos", {})) == {1, 2, 3}, f"Detecta 3 turnos: {sorted(h.get('turnos', {}))}")
chk(h["turnos"][1]["sem"] == (8.0, 16.0), f"Turno 1 L-V 8:00-16:00 -> {h['turnos'][1]['sem']}")
chk(h["turnos"][1]["sab"] == (8.0, 15.0), f"Turno 1 sábado 8:00-15:00 -> {h['turnos'][1]['sab']}")
chk(h["turnos"][3]["sem"] == (10.0, 18.0),
    f"Turno 3 usa el respaldo del código (texto ambiguo, sin am/pm) -> {h['turnos'][3]['sem']}")

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
# 1c) El "*", tabla de Almuerzo y límite del cuadro (Leyenda)
# =====================================================
nombres = {a["nombre"] for a in h["asignaciones"]}
chk("Cristian" in nombres, f"'Cristian*' se lee sin el asterisco: {sorted(nombres)}")
chk("Cristian*" not in nombres, "El asterisco no se queda pegado al nombre")
chk(not h.get("roles"),
    f"El '*' ya NO asigna el rol Soporte (ese rol dejó de existir): {h.get('roles')}")

basura = {"12:00 pm", "1:00 pm", "2:00 pm", "6:00 pm", "6:20 pm", "Desde",
          "Hasta", "Almuerzo", "1 Turno", "2 Turno", "3 Turno", "Leyenda:"}
chk(not (nombres & basura),
    f"La leyenda y la tabla de Almuerzo NO contaminan la lista de personas: {nombres & basura}")

chk(h.get("almuerzos") == {1: (12.0, 13.0), 2: (13.0, 14.0), 3: (18.0, 18.0 + 20 / 60)},
    f"Lee la tabla de Almuerzo (Desde/Hasta por turno): {h.get('almuerzos')}")

chk(h.get("vacaciones") == [],
    f"Cuadro sin columna 'Vacaciones' -> lista vacía, no revienta: {h.get('vacaciones')}")

# =====================================================
# 1d) Rótulo del turno sin número, y con horas incoherentes
# Caso real de la hoja: "Turno 10:00pm a 6:00pm, Sábado 9:00am a 4:00pm" — sin
# número (el 10 es la hora, no el turno) y con un pm donde iba am.
# =====================================================
FILAS_ROTULO_RARO = [
    fila(cel(), cel("Lunes 24"), cel("Martes 25"), cel("Miercoles 26"),
         cel("Jueves 27"), cel("Viernes 28"), cel("Sabado 29"), cel("Domingo 30")),
    fila(cel("1 Turno 8:00am a 4:00pm, Sábado 8:00am a 3:00pm"),
         cel("Estefania"), cel("Estefania"), cel("Estefania"), cel("Estefania"),
         cel("Estefania"), cel("Estefania"), cel()),
    fila(),
    fila(cel("2 Turno 11:00am a 7:00pm, Sábado 10:00am a 5:00pm"),
         cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"),
         cel("Gisela"), cel("Gisela"), cel()),
    fila(),
    fila(cel("Turno 10:00pm a 6:00pm, Sábado 9:00am a 4:00pm"),
         cel("Laura"), cel("Laura"), cel("Laura"), cel("Laura"),
         cel("Laura"), cel("Laura"), cel()),
]
h_rr = turnos.parsear_horario({"sheets": [{"data": [{"rowData": FILAS_ROTULO_RARO}]}]})
chk("error" not in h_rr, f"Rótulo sin número: parsea sin error ({h_rr.get('error','')})")
chk(set(h_rr.get("turnos", {})) == {1, 2, 3},
    f"Un rótulo sin número toma el número por su posición (3er bloque = 3): {sorted(h_rr.get('turnos', {}))}")
laura = {a["turno"] for a in h_rr["asignaciones"] if a["nombre"] == "Laura"}
chk(laura == {3}, f"Laura queda en el turno 3, no en un 'turno 10' inventado: {laura}")
chk(h_rr["turnos"][3]["sem"] == (10.0, 18.0),
    f"'10:00pm a 6:00pm' es incoherente: se ignora y manda el respaldo -> {h_rr['turnos'][3]['sem']}")
chk(h_rr["turnos"][3]["sab"] == (9.0, 16.0),
    f"El sábado del mismo rótulo sí es coherente y se usa -> {h_rr['turnos'][3]['sab']}")
chk(turnos._numero_del_turno("Turno: 3 de 10:00am a 6:00pm", 9) == 3,
    "Un número escrito después de 'Turno:' sí cuenta si no es una hora")

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
# 2) Panel informativo según la hora
# Ya no hay "Requieren cobertura": quien está en su turno y no da señal no
# aparece en ninguna lista (queda en el historial, para Gestión).
# =====================================================
LUNES = datetime(2026, 7, 27, 9, 0)      # lunes 9:00am
chk(LUNES.weekday() == 0, "El 27/07/2026 es lunes (base de la prueba)")

c = turnos.calcular_panel(h, LUNES)
chk("requieren_cobertura" not in c,
    f"El panel ya no devuelve 'requieren_cobertura': {sorted(c)}")
chk(donde(c, "Estefania") == set(),
    f"Lunes 9am, en turno y sin señal -> no aparece en ninguna lista: {donde(c, 'Estefania')}")
chk(donde(c, "Gisela") == {"por_entrar"},
    f"Turno 2 antes de entrar (11am) -> solo 'Aún no entran': {donde(c, 'Gisela')}")
chk(donde(c, "Yesid") == {"por_entrar"},
    f"Turno 3 antes de entrar (10am) -> solo 'Aún no entran': {donde(c, 'Yesid')}")

# Con presencia reciente de Estefania
pres = {turnos.clave("Estefania"): {"ts": time.time() - 120}}
c2 = turnos.calcular_panel(h, LUNES, presencia=pres)
chk(donde(c2, "Estefania") == {"en_linea"},
    "Estefania vista hace 2 min -> aparece solo En línea")

# Señal vieja (45 min) -> ya no cuenta como en línea, y no hay nada que decir
pres_vieja = {turnos.clave("Estefania"): {"ts": time.time() - 45 * 60}}
c3 = turnos.calcular_panel(h, LUNES, presencia=pres_vieja)
chk(donde(c3, "Estefania") == set(),
    f"Señal de hace 45 min -> sale de En línea y no va a ninguna otra lista: {donde(c3, 'Estefania')}")

# Novedad reportada: eso sí es una explicación
novs = [{"id": 1, "clave": turnos.clave("Estefania"), "nombre": "Estefania",
         "tipo": "Cita médica", "nota": "vuelve al mediodía", "importante": False}]
c3b = turnos.calcular_panel(h, LUNES, novedades=novs)
est_nov = uno(c3b, "ausencia_informada", "Estefania")
chk(bool(est_nov) and est_nov.get("novedad") == "Cita médica",
    f"Con novedad reportada -> Ausencia informada: {est_nov}")

# Miércoles: Ximena en compensatorio -> hoy no se espera, sin más
MIER = datetime(2026, 7, 29, 9, 0)
c4 = turnos.calcular_panel(h, MIER)
ximena = uno(c4, "no_se_espera", "Ximena")
chk(bool(ximena) and ximena.get("no_viene_hoy") is True,
    f"Miércoles: Ximena (Compensatorio) -> 'Hoy no se espera': {ximena}")
chk(donde(c4, "Ximena") == {"no_se_espera"},
    f"Ximena en compensatorio no aparece en ninguna otra lista: {donde(c4, 'Ximena')}")

# Miércoles 1:00pm: Gisela en Tesoro (turno 2, 11am-7pm) -> ausencia informada
# con sede=True (sigue trabajando, solo que sus chats quedan sin atender).
MIER_TARDE = datetime(2026, 7, 29, 13, 0)
c4b = turnos.calcular_panel(h, MIER_TARDE)
gisela_aus = uno(c4b, "ausencia_informada", "Gisela")
chk(bool(gisela_aus) and gisela_aus.get("sede") is True,
    f"Miércoles 1pm: Gisela (Tesoro) -> ausencia informada con sede=True: {gisela_aus}")
chk(donde(c4b, "Gisela") == {"ausencia_informada"},
    "Gisela (Tesoro) NO cae en 'no se espera' (sigue trabajando, solo que presencial)")

# Jueves 10:00am: Santiago en Mostrador (turno 1, 8am-4pm) -> mismo caso
JUEVES_MOSTRADOR = datetime(2026, 7, 30, 10, 0)
c4c = turnos.calcular_panel(h, JUEVES_MOSTRADOR)
santiago_aus = uno(c4c, "ausencia_informada", "Santiago")
chk(bool(santiago_aus) and santiago_aus.get("sede") is True,
    f"Jueves 10am: Santiago (Mostrador) -> ausencia informada con sede=True: {santiago_aus}")

# =====================================================
# Almuerzo automático (Miércoles 12:30pm, turno 1: 12:00-1:00pm)
# =====================================================
MIER_ALMUERZO = datetime(2026, 7, 29, 12, 30)
c4d = turnos.calcular_panel(h, MIER_ALMUERZO)
estefania_aus = uno(c4d, "ausencia_informada", "Estefania")
chk(bool(estefania_aus) and estefania_aus.get("estado") == "almuerzo",
    f"Miércoles 12:30 (ventana de almuerzo turno 1) -> almuerzo automático: {estefania_aus}")

# Si ya marcó "Desconectado", el almuerzo automático NO se lo pisa.
estados_desc = {turnos.clave("Estefania"): {"estado": "desconectado", "ts": time.time()}}
c4e = turnos.calcular_panel(h, MIER_ALMUERZO, estados=estados_desc)
estefania_desc = uno(c4e, "ausencia_informada", "Estefania")
chk(bool(estefania_desc) and estefania_desc.get("estado") == "desconectado",
    f"Con 'Desconectado' ya marcado, el almuerzo automático no lo reemplaza: {estefania_desc}")

# Antes de la hora: 7:30am todo el turno 1 está solo en "Aún no entran"
TEMPRANO = datetime(2026, 7, 27, 7, 30)
c5 = turnos.calcular_panel(h, TEMPRANO)
chk(donde(c5, "Estefania") == {"por_entrar"},
    f"7:30am (antes del turno 1) -> solo 'Aún no entran': {donde(c5, 'Estefania')}")

# En cuanto pasa la hora de entrada ya no está "por entrar" (sin tolerancia:
# no hay alarma que amortiguar, así que la lista sigue el horario tal cual).
c6 = turnos.calcular_panel(h, datetime(2026, 7, 27, 8, 10))
chk(donde(c6, "Estefania") == set(),
    f"8:10am -> ya entró su turno, sale de 'Aún no entran': {donde(c6, 'Estefania')}")

# =====================================================
# Turno terminado, y cierre del día
# =====================================================
LUNES_6PM = datetime(2026, 7, 27, 18, 0)  # Estefania (T1, 8am-4pm) ya terminó
c10 = turnos.calcular_panel(h, LUNES_6PM)
est_fin = uno(c10, "no_se_espera", "Estefania")
chk(bool(est_fin) and est_fin.get("turno_terminado") is True,
    f"6pm: Estefania (T1 terminó) -> 'Hoy no se espera' con turno_terminado: {est_fin}")

# Si se quedó ayudando después de su turno, sigue contando como En línea.
pres_tarde = {turnos.clave("Estefania"): {"ts": time.time() - 60}}
c10b = turnos.calcular_panel(h, LUNES_6PM, presencia=pres_tarde)
chk(donde(c10b, "Estefania") == {"en_linea"},
    "Con señal reciente después de su turno, se queda En línea (no en 'no se espera')")

# El cierre del día es el fin más tardío entre los turnos. Con el turno 3 en
# 10am-6pm y el 2 en 11am-7pm, un día de semana cierra a las 7pm.
LUNES_11PM = datetime(2026, 7, 27, 23, 0)  # pasado el cierre del día
c11 = turnos.calcular_panel(h, LUNES_11PM)
chk(donde(c11, "Estefania") == set(),
    "11pm sin señal (pasado el cierre) -> no aparece en ninguna lista")

# BUG CORREGIDO: la comprobación del cierre estaba ANTES de mirar la presencia,
# así que a las 7:01pm el panel quedaba COMPLETAMENTE en blanco aunque hubiera
# gente conectada. Quien da señal se sigue viendo: se quedó trabajando.
pres_noche = {turnos.clave("Estefania"): {"ts": time.time(), "primera_ts": time.time()}}
for hora in (19, 20, 23):
    c_n = turnos.calcular_panel(h, datetime(2026, 7, 27, hora, 30), presencia=pres_noche)
    chk(donde(c_n, "Estefania") == {"en_linea"},
        f"{hora}:30, pasado el cierre pero con señal reciente -> sigue En línea: {donde(c_n, 'Estefania')}")
c_vacio = turnos.calcular_panel(h, datetime(2026, 7, 27, 19, 30))
chk(sum(len(c_vacio[k]) for k in LISTAS) == 0,
    "Pasado el cierre y sin nadie con señal, el panel sí queda vacío (no se inventa nada)")

# El almuerzo del turno 3 no tiene respaldo en el código: cuando ese bloque
# pasó a ser la auditoría (10am-6pm), su almuerzo viejo (6:00-6:20pm) quedaba
# justo al terminar la jornada, así que se encendía en el peor momento.
chk(3 not in turnos.ALMUERZOS,
    f"El turno 3 no tiene almuerzo de respaldo: lo tiene que traer la hoja: {turnos.ALMUERZOS}")
h_sin_alm = dict(h, almuerzos={1: (12.0, 13.0), 2: (13.0, 14.0)})
pres_yesid = {turnos.clave("Yesid"): {"ts": time.time(), "primera_ts": time.time()}}
sin_almuerzo = all(
    not [x for x in turnos.calcular_panel(
            h_sin_alm, datetime(2026, 7, 27, hh, mm), presencia=pres_yesid)["ausencia_informada"]
         if x["nombre"] == "Yesid"]
    for hh, mm in ((11, 0), (13, 0), (17, 0), (18, 0)))
chk(sin_almuerzo,
    "Sin la fila '3 Turno' en la hoja, el turno 3 nunca se marca en almuerzo solo")

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
         cel("Jennifer"), cel("Jennifer"), cel("Elvia*")),
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
chk({"Elvia", "Cristian"} <= nombres_sl and not ({"Elvia*", "Cristian*"} & nombres_sl),
    f"Los nombres con '*' se leen limpios, con la leyenda al lado del turno 1: {sorted(nombres_sl)}")
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
         cel("Almuerzo"), cel("Desde"), cel("Hasta"), cel(), cel("Vacaciones"),
         cel(), cel("auxiliares de bodega")),
    fila(cel(), cel("1 Turno 8:00am a 4:00pm, Sábado 8:00am a 3:00pm"),
         cel(), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"), cel("Gisela"),
         cel(), cel(), cel("CC Tesoro"), cel(), cel(), cel(),
         cel("1 Turno"), cel("12:00 pm"), cel("1:00 pm"), cel(), cel("Jennifer"),
         cel(), cel("Ferney")),
    fila(cel(), cel(), cel(), cel("Jennifer"), cel("Jennifer"), cel("Jennifer"),
         cel("Jennifer"), cel("Jennifer"), cel("Elvia*"),
         cel(), cel(), cel(), cel(), cel(), cel(),
         cel("2 Turno"), cel("1:00 pm"), cel("2:00 pm"), cel(), cel("Roberto"),
         cel(), cel("Jhian")),
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
# Columna "Auxiliares de bodega": gente que usa la calculadora pero NO tiene
# turno en el cuadro (no atienden chats). Va al selector "Soy:" y habilita los
# datos de bodega en "Valor Tienda", pero no aparece en las listas del panel.
# =====================================================
chk(h_aj.get("auxiliares") == ["Ferney", "Jhian"],
    f"Lee la columna 'auxiliares de bodega' igual que Vacaciones: {h_aj.get('auxiliares')}")
personas_aj = turnos.personas_del_horario(h_aj)
chk("Ferney" in personas_aj and "Jhian" in personas_aj,
    f"Los auxiliares entran al selector 'Soy:': {personas_aj}")
chk(len(personas_aj) == len(set(personas_aj)),
    "El selector no duplica a nadie al sumar los auxiliares")
chk(turnos.es_auxiliar_bodega(h_aj, "ferney") and turnos.es_auxiliar_bodega(h_aj, "Jhian"),
    "es_auxiliar_bodega reconoce el nombre sin importar mayúsculas")
chk(not turnos.es_auxiliar_bodega(h_aj, "Gisela") and not turnos.es_auxiliar_bodega(h_aj, ""),
    "es_auxiliar_bodega dice no a una vendedora y a un nombre vacío")
c_aux = turnos.calcular_panel(h_aj, datetime(2026, 8, 19, 10, 0))  # miércoles, en turno 1
chk(donde(c_aux, "Ferney") == set(),
    f"Un auxiliar no aparece en ninguna lista del panel (no tiene turno): {donde(c_aux, 'Ferney')}")
chk(h_aj.get("auxiliares") and not (set(h_aj["auxiliares"]) & {a["nombre"] for a in h_aj["asignaciones"]}),
    "Los auxiliares no se cuelan como asignaciones de ningún turno")

# =====================================================
# Vacaciones: manda sobre cualquier otra cosa del cuadro (Jennifer SÍ tiene
# turno 1 asignado esta semana) y también funciona para alguien que no tiene
# ninguna fila en el cuadro (Roberto).
# =====================================================
MIER_VAC = datetime(2026, 8, 19, 10, 0)   # miércoles, en horas de turno 1
c_vac = turnos.calcular_panel(h_aj, MIER_VAC)
jen = uno(c_vac, "no_se_espera", "Jennifer")
chk(bool(jen) and jen.get("vacaciones") is True,
    f"Jennifer (turno 1 esta semana, pero de vacaciones) -> 'Hoy no se espera': {jen}")
rob = uno(c_vac, "no_se_espera", "Roberto")
chk(bool(rob) and rob.get("vacaciones") is True,
    f"Roberto (sin fila en el cuadro, solo en Vacaciones) -> 'Hoy no se espera': {rob}")
chk(donde(c_vac, "Jennifer") == {"no_se_espera"},
    f"Jennifer de vacaciones no aparece en ninguna lista de turno normal: {donde(c_vac, 'Jennifer')}")

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
