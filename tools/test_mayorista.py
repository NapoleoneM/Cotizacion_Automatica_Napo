# Prueba del lector de tarifas mayoristas SIN red: reconstruye la hoja 'Tablas'
# tal como viene del CORE (con sus trampas) y verifica que las tarifas se
# ubiquen por rotulo y no por coordenadas.
#
# Nace del fallo del 06/10/2026: el CORE fusiono Lisa y Diamantada en una fila
# y agrego dos secciones nuevas; como el codigo leia la fila 41 fija, las bolas
# diamantadas quedaron en 0 y el calculo las OMITIA de la cotizacion en
# silencio. Uso: python tools/test_mayorista.py
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.mayorista_logic import (
    _mapear_tarifas, _tarifa, calcular_cotizacion_mayorista, limpiar_peso,
)

fallos = 0


def chk(cond, msg):
    global fallos
    print(("[OK] " if cond else "[X]  ") + msg)
    if not cond:
        fallos += 1


def rejilla(filas_bloque, col=15, fila0=27, trampas=True):
    """Arma una hoja con el bloque MAYORISTAS en (fila0, col).

    Reproduce dos trampas reales de la hoja: otro 'MAYORISTAS' suelto arriba a
    la derecha (sin encabezado debajo) y el bloque JOYERIAS con su propio
    'Tipo | Contado' y otros precios, que es lo que antes se leia por error.
    """
    ancho, alto = col + 6, fila0 + len(filas_bloque) + 4
    g = [["" for _ in range(ancho)] for _ in range(alto)]
    if trampas:
        g[4][col + 14 if col + 14 < ancho else ancho - 1] = "MAYORISTAS"
        g[fila0][6] = "JOYERIAS"
        g[fila0 + 1][6] = "Tipo"
        g[fila0 + 1][7] = "Contado"
        g[fila0 + 2][6] = "NACIONAL"
        g[fila0 + 3][6] = "Corriente"
        g[fila0 + 3][7] = " $410.000"      # precio DISTINTO al de mayoristas
    g[fila0][col] = "MAYORISTAS"
    g[fila0 + 1][col] = "Tipo"
    g[fila0 + 1][col + 1] = "Contado"
    g[fila0 + 1][col + 2] = "F. Electro"
    for n, (rotulo, contado, credito) in enumerate(filas_bloque):
        f = g[fila0 + 2 + n]
        f[col] = rotulo
        if contado:
            f[col + 1] = contado
        if credito:
            f[col + 2] = credito
    return g


# Hoja TAL COMO QUEDO tras el cambio del CORE
HOY = [
    ("NACIONAL", "", ""),
    ("Corriente", " $435.000", " $500.000"),
    ("Especial", " $445.000", " $510.000"),
    ("Fabricaciones", " $455.000", " $520.000"),
    ("ITALIANO", "", ""),
    ("Recargo +1", " $560.000", " $600.000"),
    ("Recargo +2", " $565.000", " $605.000"),
    ("Recargo +3", " $570.000", " $610.000"),
    ("Recargo +4", " $575.000", " $615.000"),
    ("Recargo +5", " $580.000", " $620.000"),
    ("BOLAS", "", ""),
    ("Lisas | Diam.", " $430.000", " $495.000"),
    ("14K ITALIANO", "", ""),
    ("Único", " $350.000", ""),
    ("PLATA 925", "", ""),
    ("Único", " $39.000", ""),
]

m = _mapear_tarifas(rejilla(HOY))
chk(bool(m), "Encuentra el bloque MAYORISTAS pese al rotulo suelto de arriba")
chk(_tarifa(m, "NACIONAL", "CORRIENTE") == 435000,
    f"No se cuela el bloque JOYERIAS (debe dar 435.000) -> {_tarifa(m, 'NACIONAL', 'CORRIENTE')}")
chk(_tarifa(m, "NACIONAL", "FABRICACION") == 455000,
    "'Fabricaciones' (plural en la hoja) resuelve 'Fabricación'")
chk(_tarifa(m, "ITALIANO", "RECARGO +5") == 580000, "Lee el Recargo +5")

# El caso que se rompio: una sola fila sirve para Lisa y para Diamantada
chk(_tarifa(m, "BOLAS", "LISA") == 430000, "Lisa contado = 430.000")
chk(_tarifa(m, "BOLAS", "LISA", credito=True) == 495000, "Lisa credito = 495.000")
chk(_tarifa(m, "BOLAS", "DIAMANTADA", "DIAM") == 430000,
    "Diamantada contado sale de la fila fusionada 'Lisas | Diam.'")
chk(_tarifa(m, "BOLAS", "DIAMANTADA", "DIAM", credito=True) == 495000,
    "Diamantada credito sale de la fila fusionada")

# Las secciones nuevas no estorban ni se confunden con las viejas
chk("14K ITALIANO" in m and "PLATA 925" in m,
    f"Reconoce las secciones nuevas: {sorted(m)}")
chk(_tarifa(m, "ITALIANO", "RECARGO +1") == 560000,
    "'14K ITALIANO' no se confunde con 'ITALIANO'")

# --- Compatibilidad hacia atras: si el CORE vuelve a separar las filas ---
ANTES = [
    ("BOLAS", "", ""),
    ("Lisa", " $430.000", " $495.000"),
    ("Diamantada", " $450.000", " $515.000"),
]
m2 = _mapear_tarifas(rejilla(ANTES))
chk(_tarifa(m2, "BOLAS", "LISA") == 430000, "Formato viejo: Lisa sigue leyendose")
chk(_tarifa(m2, "BOLAS", "DIAMANTADA", "DIAM") == 450000,
    "Formato viejo: Diamantada toma SU propia fila, no la de Lisa")

# --- Si el CORE mueve el bloque de sitio, debe seguir funcionando ---
m3 = _mapear_tarifas(rejilla(HOY, col=22, fila0=12))
chk(_tarifa(m3, "BOLAS", "DIAM") == 430000,
    "El bloque movido de fila y columna se sigue encontrando")

# --- Si el rotulo del bloque no existe, no inventa precios ---
chk(_mapear_tarifas(rejilla(HOY), bloque="NO_EXISTE") == {},
    "Sin el bloque pedido devuelve vacio (y el aviso de faltantes se dispara)")

# =====================================================
# El calculo ya no omite la joya: con tarifa valida, cotiza
# =====================================================
PRECIOS = {
    "Nacional": {"Corriente": 435000, "Especial": 445000, "Fabricación": 455000},
    "Italiano": {f"Recargo +{n}": 555000 + n * 5000 for n in range(1, 6)},
    "Bolas": {"Lisa contado": 430000, "Diamantada contado": 430000},
}


def joya(subtipo, peso="2", tipo="Bolas"):
    return {"nombre": "Bola diamantada", "peso": peso, "cantidad": 1,
            "tipo": tipo, "subtipo": subtipo, "valor_normal": ""}


r = calcular_cotizacion_mayorista([joya("Diamantada contado")], [], PRECIOS,
                                  False, "", "")
chk("exito" in r, f"Cotiza una bola diamantada sin error -> {r.get('error', '')}")
texto = r.get("texto", "")
chk("Bola diamantada" in texto, "La joya aparece en la cotizacion (ya no se omite)")
chk("860.000" in texto, f"2 gr x 430.000 = 860.000 en el texto | {texto[:120]!r}")

# =====================================================
# Una joya sin tarifa ya no se omite en silencio: la cotizacion avisa
# (antes salian cotizaciones vacias o incompletas cuando cambiaba la tabla)
# =====================================================
r0 = calcular_cotizacion_mayorista([joya("Diamantada contado")], [],
                                   {"Bolas": {"Diamantada contado": 0}}, False, "", "")
chk("error" in r0 and "texto" not in r0,
    "Con tarifa en 0 no se arma la cotizacion: se devuelve un aviso")
chk("Bola diamantada" in r0.get("error", "") and "Bolas → Diamantada contado" in r0.get("error", ""),
    f"El aviso dice que joya y que tarifa faltan | {r0.get('error')}")

# Un front viejo en cache que todavia mande "Lisa crédito" tampoco se pierde en silencio
r_vieja = calcular_cotizacion_mayorista([joya("Lisa crédito")], [], PRECIOS, False, "", "")
chk("error" in r_vieja and "Lisa crédito" in r_vieja["error"],
    f"Un subtipo que ya no existe avisa en vez de omitirse | {r_vieja.get('error')}")

# Si una de varias joyas no tiene tarifa, no sale una cotizacion a medias
r_mix = calcular_cotizacion_mayorista(
    [joya("Lisa contado"), {**joya("Corriente", tipo="Nacional"), "nombre": "Cadena"},
     {**joya("Lisa crédito"), "nombre": "Bola rara"}], [], PRECIOS, False, "", "")
chk("error" in r_mix and "Bola rara" in r_mix["error"] and "Cadena" not in r_mix["error"],
    f"Con una sola joya sin tarifa se avisa solo esa | {r_mix.get('error')}")

# =====================================================
# Tabla v.28.10.26: titulo con version y una sola columna de precio
# =====================================================
V2810 = [
    ("NACIONAL", "", ""),
    ("Corriente", " $410.000", ""),
    ("Especial", " $420.000", ""),
    ("Fabricaciones", " $430.000", ""),
    ("ITALIANO", "", ""),
    ("Recargo +1", " $500.000", ""),
    ("Recargo +5", " $520.000", ""),
    ("BOLAS", "", ""),
    ("Lisas | Diam.", " $410.000", ""),
    ("14K ITALIANO", "", ""),
    ("Único", " $420.000", ""),
]
g = rejilla(V2810)
g[27][15] = "MAYORISTAS - v.28.10.26"           # el titulo ahora trae la version
g[28][16] = "Contado No Incluye IVA"            # y una sola columna de precio
g[28][17] = ""
m4 = _mapear_tarifas(g)
chk(_tarifa(m4, "NACIONAL", "CORRIENTE") == 410000,
    f"Encuentra 'MAYORISTAS - v.28.10.26' aunque traiga version -> {_tarifa(m4, 'NACIONAL', 'CORRIENTE')}")
chk(_tarifa(m4, "BOLAS", "DIAM") == 410000, "Bolas sale de la unica columna de contado")
chk(_tarifa(m4, "BOLAS", "LISA", credito=True) == 0,
    "Sin columna de credito, el credito queda en 0: no se inventa un precio")

# El titulo debe EMPEZAR por el nombre del bloque: otro texto no lo engana
g2 = rejilla(V2810)
g2[27][15] = "PRECIOS MAYORISTAS"
chk(_mapear_tarifas(g2) == {}, "'PRECIOS MAYORISTAS' no se toma como el bloque MAYORISTAS")

# Solo cuentan las columnas pegadas a 'Tipo': otra tabla en la misma fila no se mezcla
g3 = rejilla(V2810)
g3[27][15] = "MAYORISTAS - v.28.10.26"
g3[28][16] = "Contado No Incluye IVA"
g3[28][17] = ""
g3[28][19] = "Otra tabla"
m5 = _mapear_tarifas(g3)
chk(_tarifa(m5, "NACIONAL", "CORRIENTE") == 410000 and _tarifa(m5, "NACIONAL", "CORRIENTE", credito=True) == 0,
    "Un encabezado de otra tabla mas a la derecha no se toma como columna de credito")

# Cotizacion completa con la tabla nueva
precios_v2810 = {
    "Nacional": {"Corriente": 410000, "Especial": 420000, "Fabricación": 430000},
    "Italiano": {f"Recargo +{n}": 495000 + n * 5000 for n in range(1, 6)},
    "Bolas": {"Lisa contado": 410000, "Diamantada contado": 410000},
}
r = calcular_cotizacion_mayorista([joya("Diamantada contado")], [], precios_v2810, False, "", "")
chk("820.000" in r.get("texto", ""), f"2 gr x 410.000 = 820.000 con la tabla nueva | {r.get('error', '')}")

print("\nRESULTADO:", "[X] HAY FALLOS" if fallos else "[OK] TODO CORRECTO")
sys.exit(1 if fallos else 0)
