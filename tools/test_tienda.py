# Prueba del precio de tienda y de los datos de bodega, SIN red.
#
# Los números esperados están calculados a mano desde las fórmulas reales del
# documento "Ferney - Catálogo Napoleone Medellín" (leídas el 27/08/2026):
#
#   Inputs!L  (Costo)      = REDONDEAR.MAS(tarifas_gramo!F * peso; -2)
#   Inputs!M  (Valor CO.)  = REDONDEAR.MAS(tarifas_gramo!G * peso; -3)
#   EFFILoad!S (Costo)         = Inputs!L
#   EFFILoad!T (Precio mínimo) = REDONDEAR(S * 1,05; 0)
#   EFFILoad!AB (Tarifa 1)     = Inputs!M / 1,19        (SIN redondear)
#   EFFILoad!AC (Tarifa 2)     = x_mayor_cop  * peso, al millar  -> solo Pulsera
#   EFFILoad!AD (Tarifa 3)     = Inputs!M                          Tejida con
#   EFFILoad!AE (Tarifa 4)     = joyerias_cop * peso, al millar  -> costo manual
#   EFFILoad!AF (Tarifa 5)     = REDONDEAR.MAS(shopi_gr_usd * peso; 0), en USD
#
# Si alguna de esas fórmulas cambia en la hoja, esta prueba es la que avisa.
# Uso: python tools/test_tienda.py
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.tienda_logic import calcular_precio_tienda

fallos = 0


def chk(cond, msg):
    global fallos
    print(("[OK] " if cond else "[X]  ") + msg)
    if not cond:
        fallos += 1


# Réplica de dos filas de pricing_gramo (columnas C, D, E, F, G)
TARIFAS = [
    {"calidad": "Nacional Corriente", "peso_min": 2.0, "peso_max": 4.0,
     "valor_gr": 532000, "costo_gr": 345000, "usd_gr": 202,
     "joyerias_gr": 405000, "mayor_gr": 425000},
    {"calidad": "Recargo +1", "peso_min": 0.05, "peso_max": 3.0,
     "valor_gr": 630000, "costo_gr": 390000, "usd_gr": 239,
     "joyerias_gr": 532000, "mayor_gr": 560000},
    # Fila sin costo por gramo: el precio de tienda debe seguir saliendo igual
    {"calidad": "Sin costo", "peso_min": 0.0, "peso_max": 100.0,
     "valor_gr": 500000, "costo_gr": 0},
    # Banda ancha, solo para barrer todos los pesos en la prueba del redondeo
    {"calidad": "Barrido", "peso_min": 0.0, "peso_max": 100.0,
     "valor_gr": 532000, "costo_gr": 345000, "usd_gr": 202},
]

# =====================================================
# Precio de tienda (lo que ya existía): no debe cambiar
# =====================================================
r = calcular_precio_tienda("2,5", "Nacional Corriente", TARIFAS)
chk(r.get("precio") == 1330000,
    f"532.000/gr x 2,5 gr, al millar hacia arriba = 1.330.000 -> {r.get('precio')}")
chk(r.get("rango") == "2 a 4 gr", f"Informa la banda de peso usada: {r.get('rango')}")
chk("bodega" not in r, "Sin con_bodega, la respuesta NO trae datos de bodega")

# El redondeo es hacia arriba al millar, no al más cercano.
r_red = calcular_precio_tienda("1,001", "Recargo +1", TARIFAS)
chk(r_red.get("precio") == 631000,
    f"630.000 x 1,001 = 630.630 -> sube a 631.000, no baja a 631 mil por cercanía: {r_red.get('precio')}")

# El peso acepta coma o punto, y el límite de banda es (min, max]
chk(calcular_precio_tienda("2.5", "Nacional Corriente", TARIFAS).get("precio") == 1330000,
    "El peso con punto decimal da el mismo resultado que con coma")
chk("error" in calcular_precio_tienda("2", "Nacional Corriente", TARIFAS),
    "Peso 2 gr NO entra en la banda 2-4 (el mínimo es exclusivo)")
chk(calcular_precio_tienda("4", "Nacional Corriente", TARIFAS).get("precio") == 2128000,
    "Peso 4 gr SÍ entra en la banda 2-4 (el máximo es inclusivo)")
chk("error" in calcular_precio_tienda("0", "Nacional Corriente", TARIFAS),
    "Peso 0 se rechaza con un mensaje, no calcula")
chk("error" in calcular_precio_tienda("2,5", "Calidad inventada", TARIFAS),
    "Una calidad que no está en las tarifas se rechaza")

# =====================================================
# Datos de bodega (con_bodega=True)
# =====================================================
b = calcular_precio_tienda("2,5", "Nacional Corriente", TARIFAS, con_bodega=True)
chk(b.get("precio") == 1330000, "Con con_bodega, el precio de tienda es EXACTAMENTE el mismo")
d = b.get("bodega") or {}
chk(d.get("costo") == 862500,
    f"Costo = 345.000 x 2,5 = 862.500, a la centena hacia arriba -> {d.get('costo')}")
chk(d.get("precio_minimo") == 905625,
    f"Precio mínimo = 862.500 x 1,05 = 905.625 -> {d.get('precio_minimo')}")
chk(d.get("valor_co") == b.get("precio"),
    f"Valor CO. es el mismo precio de tienda, no se recalcula -> {d.get('valor_co')}")
chk(d.get("tarifa_1") == 1117647.06,
    f"Tarifa 1 = 1.330.000 / 1,19 = 1117647,06 (sin IVA, con decimales) -> {d.get('tarifa_1')}")
chk(d.get("costo_gr") == 345000,
    f"Informa el costo por gramo usado, para poder auditar la cifra: {d.get('costo_gr')}")

# =====================================================
# Las cinco tarifas de EFFI, con la fila real que el usuario cargo a mano:
# 3,1 gr de Nacional Corriente -> Costo 1.069.500, minimo 1.122.975,
# Tarifa 1 1386554,62, Tarifa 3 1.650.000, Tarifa 5 627. Tarifas 2 y 4 vacias.
# =====================================================
t = calcular_precio_tienda("3,1", "Nacional Corriente", TARIFAS, con_bodega=True)
chk(t["precio"] == 1650000, f"Valor CO de 3,1 gr = 1.650.000 -> {t['precio']}")
tb = t["bodega"]
for clave, esperado in (("costo", 1069500), ("precio_minimo", 1122975),
                        ("tarifa_1", 1386554.62), ("tarifa_3", 1650000),
                        ("tarifa_5", 627)):
    chk(tb.get(clave) == esperado,
        f"{clave} coincide con la hoja: {esperado} -> {tb.get(clave)}")
chk(tb.get("tarifa_2") is None and tb.get("tarifa_4") is None,
    f"Tarifas 2 y 4 vienen en None (piden Pulsera Tejida + costo manual): "
    f"{tb.get('tarifa_2')}, {tb.get('tarifa_4')}")
chk(tb.get("tarifa_3") == t["precio"],
    "Tarifa 3 es el mismo Valor CO, no un calculo aparte")

# Tarifa 1 es la unica que la hoja NO redondea: se entrega con dos decimales.
chk(isinstance(tb["tarifa_1"], float) and round(tb["tarifa_1"], 2) == tb["tarifa_1"],
    f"Tarifa 1 llega con dos decimales, no redondeada al entero: {tb['tarifa_1']}")
chk(tb["tarifa_1"] != round(tb["tarifa_1"]),
    "Tarifa 1 conserva su parte decimal (antes se redondeaba a 1.386.555)")

# Tarifa 5 va en dolares y sube al entero: ceil(239 * 1,5) = ceil(358,5) = 359
t5 = calcular_precio_tienda("1,5", "Recargo +1", TARIFAS, con_bodega=True)["bodega"]
chk(t5["tarifa_5"] == 359, f"Tarifa 5 = ceil(239 x 1,5) = 359 -> {t5['tarifa_5']}")
chk(t5["usd_gr"] == 239, f"Informa el precio/gramo en USD usado: {t5['usd_gr']}")

# Sin la columna de USD en la hoja, la Tarifa 5 se omite en vez de dar 0
sin_usd = calcular_precio_tienda("2,5", "Barrido", TARIFAS, con_bodega=True)["bodega"]
chk(sin_usd["tarifa_5"] is not None, "Con usd_gr, la Tarifa 5 se calcula")
TARIFAS_SIN_USD = [dict(TARIFAS[3], calidad="SinUSD", usd_gr=0)]
b_su = calcular_precio_tienda("2,5", "SinUSD", TARIFAS_SIN_USD, con_bodega=True)["bodega"]
chk(b_su["tarifa_5"] is None,
    f"Sin usd_gr en la hoja, la Tarifa 5 va en None y no en 0: {b_su['tarifa_5']}")

# El costo redondea hacia arriba a la CENTENA (distinto del precio, al millar)
b2 = calcular_precio_tienda("1,001", "Recargo +1", TARIFAS, con_bodega=True)
chk(b2["bodega"]["costo"] == 390400,
    f"390.000 x 1,001 = 390.390 -> sube a 390.400 (centena), no a 391.000: {b2['bodega']['costo']}")

# BUG CORREGIDO: con float, 345.000 x 1,1 da 379500.00000000006 y math.ceil lo
# empujaba un escalón completo (379.600) aunque 379.500 ya sea centena exacta.
# Cuando el producto cae justo en un múltiplo de 100, el costo es ese número.
for peso_txt, esperado in (("1,1", 379500), ("1,12", 386400), ("0,14", 48300),
                           ("2", 690000), ("3,2", 1104000)):
    got = calcular_precio_tienda(peso_txt, "Barrido", TARIFAS,
                                 con_bodega=True)["bodega"]["costo"]
    chk(got == esperado,
        f"345.000 x {peso_txt} = {esperado} exacto, no un escalón más arriba -> {got}")

# El mismo peso, comprobado contra aritmética exacta en todo el rango útil
from decimal import Decimal, ROUND_CEILING  # noqa: E402
desvios = []
for centesimas in range(1, 2001):
    peso = Decimal(centesimas) / 100
    exacto = int(((Decimal(345000) * peso) / 100).to_integral_value(rounding=ROUND_CEILING)) * 100
    got = calcular_precio_tienda(str(peso).replace(".", ","), "Barrido",
                                 TARIFAS, con_bodega=True)["bodega"]["costo"]
    if got != exacto:
        desvios.append((str(peso), got, exacto))
chk(not desvios,
    f"0,01 a 20 gr: el costo coincide con la aritmética exacta en los 2.000 pesos ({desvios[:3]})")

# Si la hoja no trajo el costo por gramo, el precio de tienda igual funciona
b3 = calcular_precio_tienda("2", "Sin costo", TARIFAS, con_bodega=True)
chk(b3.get("precio") == 1000000, f"Sin costo/gr, el precio de tienda sale igual: {b3.get('precio')}")
chk("bodega" not in b3,
    "Sin costo/gr no se inventan datos de bodega: se omite el bloque")

print("\nRESULTADO:", "[X] HAY FALLOS" if fallos else "[OK] TODO CORRECTO")
sys.exit(1 if fallos else 0)
