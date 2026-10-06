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
    "Bolas": {"Lisa contado": 430000, "Lisa crédito": 495000,
              "Diamantada contado": 430000, "Diamantada crédito": 495000},
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

# Con tarifa en 0 la joya se omite: por eso el aviso de faltantes es critico
r0 = calcular_cotizacion_mayorista([joya("Diamantada contado")], [],
                                   {"Bolas": {"Diamantada contado": 0}}, False, "", "")
chk("Bola diamantada" not in r0.get("texto", ""),
    "Con tarifa en 0 la joya SI se omite (motivo del aviso de tarifas faltantes)")

print("\nRESULTADO:", "[X] HAY FALLOS" if fallos else "[OK] TODO CORRECTO")
sys.exit(1 if fallos else 0)
