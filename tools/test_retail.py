# Prueba de la cotización Retail, SIN red.
#
# Cubre sobre todo el envío CONTRA ENTREGA, que va por tramos según el valor de
# la joya (tabla de la transportadora) y tiene un tope por encima del cual ese
# medio de pago no se puede usar:
#
#     de 0 a 500.000        30.000 + seguro
#     500.000 a 800.000     40.000 + seguro
#     800.000 a 1.000.000   50.000 + seguro
#     1.000.000 a 1.200.000 70.000 + seguro
#     1.200.000 a 1.500.000 90.000 + seguro
#     más de 1.500.000      no permitido
#
# El seguro es el 1,2% del subtotal en todos los tramos.
# Uso: python tools/test_retail.py
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.cotizacion_logic import calcular_cotizacion

fallos = 0


def chk(cond, msg):
    global fallos
    print(("[OK] " if cond else "[X]  ") + msg)
    if not cond:
        fallos += 1


def cotizar(valor, medio_pago="Contra Entrega", **kw):
    joyas = [{"nombre": "Joya", "cantidad": 1, "valor_unitario": str(valor)}]
    return calcular_cotizacion(joyas, medio_pago,
                               kw.get("aplicar_envio", False),
                               kw.get("tipo_envio", ""),
                               kw.get("envio_manual", ""))


def envio_de(res):
    """La línea del envío que sale en el texto, o None."""
    for linea in res.get("texto", "").split("\n"):
        if linea.startswith("🚚"):
            return linea.strip()
    return None


def total_de(res):
    """El número de la línea TOTAL NETO. No sirve limpiar_numero() acá: esa
    línea trae texto y asteriscos, así que se extraen solo los dígitos."""
    for linea in res.get("texto", "").split("\n"):
        if "TOTAL NETO" in linea:
            return int(re.sub(r"[^\d]", "", linea) or 0)
    return None


# =====================================================
# Contra entrega: los cinco tramos de la tabla
# =====================================================
TRAMOS = [
    (400000, 30000), (500000, 30000),
    (700000, 40000), (800000, 40000),
    (900000, 50000), (1000000, 50000),
    (1100000, 70000), (1200000, 70000),
    (1250000, 90000), (1500000, 90000),
]
for valor, base in TRAMOS:
    r = cotizar(valor)
    linea = envio_de(r) or ""
    chk(f"${base:,}".replace(",", ".") in linea,
        f"{valor:>9,} -> tarifa base {base:,}".replace(",", ".") + f" | {linea}")

# El tramo de 90.000 es el que faltaba: antes, todo lo que pasaba de 1.000.000
# se cobraba a 70.000, incluido el tramo de 1.200.000 a 1.500.000.
r_90 = cotizar(1250000)
chk("$90.000" in (envio_de(r_90) or ""),
    "1.250.000 cobra 90.000 y no 70.000 (tramo que faltaba)")

# El seguro es 1,2% del subtotal, y el envío es base + seguro
r = cotizar(1250000)
chk("15.000" in (envio_de(r) or ""), "Seguro = 1,2% de 1.250.000 = 15.000")
chk("$105.000" in (envio_de(r) or ""), "Envío = 90.000 + 15.000 = 105.000")
chk(total_de(r) == 1250000 + 105000,
    f"Total neto = subtotal + envío = 1.355.000 -> {total_de(r)}")

# =====================================================
# Tope: por encima de 1.500.000 el medio de pago no aplica
# =====================================================
chk("error" not in cotizar(1500000),
    "1.500.000 exacto SÍ se permite (es el tope, inclusive)")
r_tope = cotizar(1500001)
chk("error" in r_tope and "1.500.000" in r_tope["error"],
    f"Por encima del tope se rechaza informando el límite: {r_tope.get('error')}")
chk("texto" not in r_tope,
    "Al rechazar no devuelve una cotización a medias")

# =====================================================
# Contra entrega ignora la sección de envío normal: su tarifa manda
# =====================================================
r_ce = cotizar(400000, aplicar_envio=True, tipo_envio="Nacional")
chk("Contra Entrega" in (envio_de(r_ce) or ""),
    "Con Contra Entrega no se aplica el envío Nacional aunque venga marcado")

# =====================================================
# Los otros medios de pago no se tocaron
# =====================================================
r_tr = cotizar(1000000, medio_pago="Transferencia", aplicar_envio=True,
               tipo_envio="Local (Medellín)")
chk("$17.000" in (envio_de(r_tr) or ""), "Envío local Medellín sigue en 17.000")
chk(total_de(r_tr) == 1017000, f"Transferencia no agrega recargo -> {total_de(r_tr)}")

r_nal = cotizar(1000000, medio_pago="Transferencia", aplicar_envio=True,
                tipo_envio="Nacional")
chk("$26.000" in (envio_de(r_nal) or ""),
    f"Envío nacional = 20.000 + 0,6% (6.000) = 26.000 | {envio_de(r_nal)}")

r_tc = cotizar(1000000, medio_pago="T. Crédito/Débito")
chk(total_de(r_tc) == 1030000, f"Tarjeta agrega 3% -> {total_de(r_tc)}")
chk("error" in cotizar(8000001, medio_pago="T. Crédito/Débito"),
    "Tarjeta se rechaza por encima de 8.000.000")

r_addi = cotizar(1000000, medio_pago="Addi")
chk(total_de(r_addi) == 1060000, f"Addi agrega 6% bajo 2.000.000 -> {total_de(r_addi)}")
r_addi2 = cotizar(3000000, medio_pago="Addi")
chk(total_de(r_addi2) == 3240000, f"Addi agrega 8% entre 2 y 4 millones -> {total_de(r_addi2)}")

# =====================================================
# Casos que deben rechazarse con mensaje, no reventar
# =====================================================
chk("error" in calcular_cotizacion([], "Transferencia", False, "", ""),
    "Sin joyas se rechaza con mensaje")
chk("error" in cotizar(0), "Subtotal en 0 se rechaza con mensaje")

print("\nRESULTADO:", "[X] HAY FALLOS" if fallos else "[OK] TODO CORRECTO")
sys.exit(1 if fallos else 0)
