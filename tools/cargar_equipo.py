"""Carga el equipo real del chat center en el almacén de la app.

Los turnos son los de la **semana del 27 de julio al 2 de agosto** (la vigente
cuando se cargó esto). Rotan cada semana: la jefa los ajusta desde el panel o,
si se usa la hoja 'Horarios' de Sheets, esa manda.

Es idempotente: se puede correr varias veces sin duplicar (actualiza por nombre).

Uso:
    python tools/cargar_equipo.py
    ESTADO_DIR=/ruta/datos python tools/cargar_equipo.py     # otra carpeta
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core import almacen

WEB = "Página web"
REDES = "Red social"
SOPORTE = "Soporte"
JEFA = "Jefa de ventas"
# Vendedoras de la tienda física: no atienden chats, así que el panel nunca
# pide cubrirlas. Están para tenerlas en el equipo y en las métricas.
PRESENCIAL = "Venta presencial"
# Elvia apoya a la jefatura y hace soporte parcial. Se registra con "Soporte"
# dentro del texto para que el panel no la ponga en la lista de "cubrir".
APOYO = "Apoyo jefatura / Soporte"

# (nombre, rol, turno de la semana vigente)
EQUIPO = [
    # --- Turno 1 ---
    ("Estefania", REDES, 1),
    ("Ximena", WEB, 1),
    ("Yesica M", REDES, 1),
    ("Susana", REDES, 1),
    ("Santiago", REDES, 1),
    ("Yessika", REDES, 1),
    ("Elvia", APOYO, 1),
    # --- Turno 2 ---
    ("Gisela", WEB, 2),
    ("Jennifer", WEB, 2),
    ("Angelica", REDES, 2),
    ("Wilmer", REDES, 2),
    ("Juan David", REDES, 2),
    ("Kelly", REDES, 2),
    ("Mariana", SOPORTE, 2),
    # --- Turno 3 ---
    ("Cristian", SOPORTE, 3),
    ("Yesid", REDES, 3),
    ("Juliana", REDES, 3),
    ("Alexander", REDES, 3),
    # --- Jefatura ---
    ("Asbeydi", JEFA, 1),
    # --- Venta presencial (tienda física; no atienden chats) ---
    ("Michelle", PRESENCIAL, 1),
    ("Viviana", PRESENCIAL, 1),
    ("Paula", PRESENCIAL, 2),
    ("Valentina R", PRESENCIAL, 2),
]

if __name__ == "__main__":
    for nombre, rol, turno in EQUIPO:
        almacen.guardar_persona(nombre, rol, turno)
    print(f"Cargadas {len(EQUIPO)} personas en {almacen._BD}\n")
    for p in almacen.equipo():
        print(f"  T{p['turno']}  {p['nombre']:<12} {p['rol']}")
    print("\nLos turnos rotan cada semana: ajustarlos desde el panel (PIN de la jefa).")
