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
MORA = {"red": 0.55, "green": 0.49, "blue": 0.76}        # Reparte Chats
GRIS = {"red": 0.72, "green": 0.72, "blue": 0.72}        # Cambio de Horario
AMAR = {"red": 1.0, "green": 1.0, "blue": 0.0}           # Santafe
VERDE = {"red": 0.20, "green": 0.65, "blue": 0.32}       # Tesoro
CELESTE = {"red": 0.60, "green": 0.80, "blue": 0.95}     # Mostrador


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
         cel("Ximena"), cel("Ximena"), cel("Cristian", MORA)),
    fila(cel(), cel("Santiago"), cel("Santiago"), cel("Santiago"), cel("Santiago", CELESTE),
         cel("Santiago"), cel("Santiago"), cel()),
    fila(cel(), cel("Yessika"), cel("Yessika", ROSA), cel("Yessika"), cel("Yessika"),
         cel("Yessika"), cel("Yessika"), cel("Yessika")),
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
    # --- Leyenda (texto + color a la derecha) ---
    fila(*([cel()] * 20 + [cel("Reparte Chats"), cel("", MORA)])),
    fila(*([cel()] * 20 + [cel("Compensatorio"), cel("", AZUL)])),
    fila(*([cel()] * 20 + [cel("Ausencia"), cel("", ROSA)])),
    fila(*([cel()] * 20 + [cel("Cambio de Horario"), cel("", GRIS)])),
    fila(*([cel()] * 20 + [cel("Santafe"), cel("", AMAR)])),
    fila(*([cel()] * 20 + [cel("Tesoro"), cel("", VERDE)])),
    fila(*([cel()] * 20 + [cel("Mostrador"), cel("", CELESTE)])),
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
chk(busca("Juliana", 2) and busca("Juliana", 2)[0]["estado"] == "santafe",
    "Juliana el miércoles = Santafé (celda amarilla)")
chk(busca("Gisela", 2) and busca("Gisela", 2)[0]["estado"] == "tesoro",
    "Gisela el miércoles = Tesoro (celda verde)")
chk(busca("Santiago", 3) and busca("Santiago", 3)[0]["estado"] == "mostrador",
    "Santiago el jueves = Mostrador (celda celeste)")
chk(not any(a["nombre"].lower().startswith(("lunes", "sabado", "domingo")) for a in h["asignaciones"]),
    "No confunde los encabezados de día con nombres")

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
chk({x["nombre"] for x in c["por_entrar"]} >= {"Gisela", "Yesid"},
    f"Turnos 2 y 3 aún no entran (no se alerta): {sorted(x['nombre'] for x in c['por_entrar'])}")
chk(all(x["motivo"].startswith("sin señal") for x in c["requieren_cobertura"]),
    "El motivo indica que no hay señal desde el inicio del turno")

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

# Miércoles: Ximena en compensatorio no se espera
MIER = datetime(2026, 7, 29, 9, 0)
c4 = turnos.calcular_cobertura(h, MIER)
chk("Ximena" not in {x["nombre"] for x in c4["requieren_cobertura"]},
    "Miércoles: Ximena (Compensatorio) NO se pide cubrir")
chk("Ximena" in {x["nombre"] for x in c4["no_se_espera"]},
    "Miércoles: Ximena aparece en 'no se espera' con su etiqueta")

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

# Antes de la hora: 7:30am nadie del turno 1 debe alertar
TEMPRANO = datetime(2026, 7, 27, 7, 30)
c5 = turnos.calcular_cobertura(h, TEMPRANO)
chk(not c5["requieren_cobertura"],
    "7:30am (antes del turno 1) -> no hay alertas todavía")

# Tolerancia: 8:10am aún está dentro de los 15 min de gracia
c6 = turnos.calcular_cobertura(h, datetime(2026, 7, 27, 8, 10))
chk(not c6["requieren_cobertura"], "8:10am -> dentro de la tolerancia de 15 min")
c7 = turnos.calcular_cobertura(h, datetime(2026, 7, 27, 8, 20))
chk(bool(c7["requieren_cobertura"]), "8:20am -> pasada la tolerancia, ya alerta")

# Fuera de jornada
c8 = turnos.calcular_cobertura(h, datetime(2026, 7, 27, 23, 0))
chk(not c8["requieren_cobertura"], "11:00pm -> nadie en turno, sin alertas")

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

print("\nRESULTADO:", "[X] HAY FALLOS" if fallos else "[OK] TODO CORRECTO")
sys.exit(1 if fallos else 0)
