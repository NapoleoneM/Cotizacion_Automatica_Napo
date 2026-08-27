"""Cálculo del precio de tienda (valor de página) por peso y calidad de oro.

Replica el caso "Pesado" de la fórmula de Sheets: busca en la hoja
pricing_gramo la fila cuya calidad coincide y cuya banda de peso (peso_min <
peso <= peso_max) contiene el peso ingresado, y calcula valor_gr * peso
redondeado hacia arriba al millar — igual que REDONDEAR.MAS(...; -3).

pricing_gramo vive en el documento CORE; se espeja a este mismo documento
espejo (mismo _SPREADSHEET_ID que mayorista_logic) para no darle acceso al
CORE al service account de la app.

Los auxiliares de bodega necesitan además las cifras con las que cargan los
productos a EFFI. Salen de la MISMA fila de pricing_gramo, así que no hay que
consultar el documento del catálogo: ver `detalle_bodega()`.
"""
import re
import math
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

import gspread

from core.app_config import log
from core.mayorista_logic import _SPREADSHEET_ID, limpiar_peso

_HOJA_TARIFAS_GRAMO = "pricing_gramo"
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def obtener_tarifas_gramo(ruta_credenciales):
    """Lee la hoja tarifas_gramo del espejo: calidad + banda de peso -> valor/gr."""
    if not ruta_credenciales:
        return {"error": "Falta la ruta al archivo de credenciales."}
    try:
        gc = gspread.service_account(filename=ruta_credenciales, scopes=_SCOPES)
        try:
            gc.http_client.set_timeout(20)
        except AttributeError:
            pass
        spreadsheet = gc.open_by_key(_SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(_HOJA_TARIFAS_GRAMO)
        filas = worksheet.get_all_values()[1:]  # sin encabezado (fila 1)

        tarifas = []
        for fila in filas:
            try:
                calidad = fila[2].strip()  # columna C
                if not calidad:
                    continue
                peso_min = float(fila[3].replace(",", "."))  # columna D
                peso_max = float(fila[4].replace(",", "."))  # columna E
                valor_gr = int(re.sub(r"[$.,\s]", "", fila[6]))  # columna G (shopi_gr_cop)
            except (IndexError, ValueError):
                continue
            # Columnas que solo usan los auxiliares de bodega. Si alguna
            # falta se guarda en 0 y ese dato se omite del detalle — el precio
            # de tienda no depende de ellas y debe seguir saliendo igual.
            def col(i):
                try:
                    return int(re.sub(r"[$.,\s]", "", fila[i]))
                except (IndexError, ValueError):
                    return 0
            tarifas.append({
                "calidad": calidad, "peso_min": peso_min, "peso_max": peso_max,
                "valor_gr": valor_gr,          # G shopi_gr_cop
                "costo_gr": col(5),            # F costo
                "usd_gr": col(7),              # H shopi_gr_usd  -> Tarifa 5
                "joyerias_gr": col(9),         # J joyerias_cop  -> Tarifa 4
                "mayor_gr": col(10),           # K x_mayor_cop   -> Tarifa 2
            })

        if not tarifas:
            log.warning("La hoja pricing_gramo llegó vacía o con formato inesperado")
            return {"error": "Tarifas de tienda no disponibles."}
        calidades = sorted({t["calidad"] for t in tarifas})
        return {"exito": True, "tarifas": tarifas, "calidades": calidades}
    except gspread.exceptions.WorksheetNotFound:
        log.warning("La hoja pricing_gramo no existe en el documento espejo")
        return {"error": "Tarifas de tienda no disponibles."}
    except FileNotFoundError:
        log.warning("No se encontró el archivo de credenciales para pricing_gramo")
        return {"error": "Tarifas de tienda no disponibles."}
    except Exception:
        # El detalle (puede traer IDs/emails de la API de Google) solo al log.
        log.warning("Fallo al leer pricing_gramo", exc_info=True)
        return {"error": "Tarifas de tienda no disponibles."}


def _fmt_peso(n):
    """1.0 -> '1', 1.5 -> '1.5' — para mostrar el rango sin ceros de más."""
    return str(int(n)) if n == int(n) else str(n)


# IVA colombiano: la Tarifa 1 de EFFI se carga sin impuesto, y el Valor CO ya
# lo trae incluido (=Inputs!M/1,19 en la hoja EFFILoad).
_IVA = Decimal("1.19")
# Margen mínimo de venta sobre el costo (=ROUND(S*1,05;0) en EFFILoad).
_MARGEN_MINIMO = Decimal("1.05")


def _techo(valor, escalon):
    """Redondeo hacia arriba al escalón dado (REDONDEAR.MAS de Sheets), con
    aritmética exacta.

    Hay que hacerlo con Decimal: en float, 345.000 * 1,1 da
    379500.00000000006, y ese resto invisible empuja el redondeo un escalón
    completo hacia arriba (379.600 en vez de 379.500, que ya era una centena
    exacta). Con el escalón de 1.000 del precio de tienda el resto no alcanza
    a cruzar el corte, pero con el de 100 del costo sí — pasaba en 1 de cada
    22 pesos aproximadamente.
    """
    return int((valor / escalon).to_integral_value(rounding=ROUND_CEILING)) * escalon


def detalle_bodega(peso, tarifa, precio_tienda):
    """Las cifras con las que los auxiliares cargan un producto a EFFI, todas
    derivadas de la misma fila de pricing_gramo que el precio de tienda:

      - costo         = REDONDEAR.MAS(costo_gr * peso; -2)   (Inputs!L = EFFILoad!S)
      - precio_minimo = REDONDEAR(costo * 1,05; 0)           (EFFILoad!T)
      - valor_co      = el precio de tienda, sin recalcular  (Inputs!M)
      - tarifa_1      = valor_co / 1,19, CON decimales       (EFFILoad!AB)
      - tarifa_2      = no aplica acá (ver abajo)            (EFFILoad!AC)
      - tarifa_3      = valor_co, el mismo número            (EFFILoad!AD)
      - tarifa_4      = no aplica acá (ver abajo)            (EFFILoad!AE)
      - tarifa_5      = REDONDEAR.MAS(usd_gr * peso; 0), en USD (EFFILoad!AF)

    Tarifa 1 es la única que NO se redondea en la hoja (`=Inputs!M2/1,19`, sin
    ROUND), así que se entrega con dos decimales como se ve allá.

    Las tarifas 2 y 4 quedan vacías a propósito: en el modelo "Pesado" sus
    fórmulas exigen que la categoría sea "Pulsera Tejida" Y que haya costo
    manual, y esta pestaña no pide ninguna de las dos cosas. Se devuelven en
    None para que la app las muestre como "no aplica" en vez de omitirlas — el
    auxiliar necesita saber que esas dos columnas de EFFI van vacías.

    Vale solo para el modelo de precio "Pesado" (peso y calidad, sin costo
    manual ni segundo set), que es justo lo que pide esta pestaña.
    Devuelve None si la hoja no trajo el costo por gramo.
    """
    costo_gr = tarifa.get("costo_gr") or 0
    if costo_gr <= 0:
        return None
    # Decimal(str(peso)) y no Decimal(peso): así el 1,1 que escribió la
    # persona es exactamente 1,1 y no el float más cercano.
    peso_d = Decimal(str(peso))
    costo = _techo(Decimal(costo_gr) * peso_d, 100)
    minimo = (Decimal(costo) * _MARGEN_MINIMO).to_integral_value(rounding=ROUND_HALF_UP)
    tarifa_1 = (Decimal(precio_tienda) / _IVA).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    usd_gr = tarifa.get("usd_gr") or 0
    return {
        "costo": costo,
        "costo_gr": costo_gr,
        "precio_minimo": int(minimo),
        "valor_co": precio_tienda,
        "tarifa_1": float(tarifa_1),
        "tarifa_2": None,
        "tarifa_3": precio_tienda,
        "tarifa_4": None,
        "tarifa_5": _techo(Decimal(usd_gr) * peso_d, 1) if usd_gr > 0 else None,
        "usd_gr": usd_gr,
    }


def calcular_precio_tienda(peso_texto, calidad, tarifas, con_bodega=False):
    """Busca la banda de peso+calidad y redondea hacia arriba al millar.

    Con `con_bodega` agrega la clave 'bodega' con las cifras de EFFI (ver
    `detalle_bodega`). El precio de tienda se calcula igual en ambos casos.
    """
    peso = limpiar_peso(peso_texto)
    if peso <= 0:
        return {"error": "Ingrese un peso válido."}
    for t in tarifas or []:
        if t["calidad"] == calidad and peso > t["peso_min"] and peso <= t["peso_max"]:
            # Se deja con math.ceil (no con _techo) porque es la fórmula de
            # negocio que ya está en producción y no se toca: con el escalón de
            # 1.000 el resto del float no alcanza a cruzar el corte — barrido
            # de 20.000 pesos x 6 tarifas, 0 diferencias contra Decimal.
            precio = math.ceil((t["valor_gr"] * peso) / 1000) * 1000
            res = {
                "exito": True,
                "precio": precio,
                "valor_gr": t["valor_gr"],
                "rango": f"{_fmt_peso(t['peso_min'])} a {_fmt_peso(t['peso_max'])} gr",
            }
            if con_bodega:
                detalle = detalle_bodega(peso, t, precio)
                if detalle:
                    res["bodega"] = detalle
            return res
    return {"error": "No se encontró una tarifa para esa calidad y peso."}
