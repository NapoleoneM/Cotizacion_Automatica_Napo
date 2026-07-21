"""Cálculo del precio de tienda (valor de página) por peso y calidad de oro.

Replica el caso "Pesado" de la fórmula de Sheets: busca en la hoja
pricing_gramo la fila cuya calidad coincide y cuya banda de peso (peso_min <
peso <= peso_max) contiene el peso ingresado, y calcula valor_gr * peso
redondeado hacia arriba al millar — igual que REDONDEAR.MAS(...; -3).

pricing_gramo vive en el documento CORE; se espeja a este mismo documento
espejo (mismo _SPREADSHEET_ID que mayorista_logic) para no darle acceso al
CORE al service account de la app.
"""
import re
import math
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
                valor_gr = int(re.sub(r"[$.,\s]", "", fila[6]))  # columna G
            except (IndexError, ValueError):
                continue
            tarifas.append({"calidad": calidad, "peso_min": peso_min, "peso_max": peso_max, "valor_gr": valor_gr})

        if not tarifas:
            return {"error": "La hoja 'tarifas_gramo' llegó vacía o con formato inesperado."}
        calidades = sorted({t["calidad"] for t in tarifas})
        return {"exito": True, "tarifas": tarifas, "calidades": calidades}
    except gspread.exceptions.WorksheetNotFound:
        return {"error": "No se encontró la hoja 'tarifas_gramo' en el documento espejo."}
    except FileNotFoundError:
        return {"error": "No se encontró el archivo de credenciales."}
    except Exception as e:
        log.warning("Fallo al leer tarifas_gramo", exc_info=True)
        return {"error": f"Error al conectar con Sheets: {str(e)}"}


def calcular_precio_tienda(peso_texto, calidad, tarifas):
    """Busca la banda de peso+calidad y redondea hacia arriba al millar."""
    peso = limpiar_peso(peso_texto)
    if peso <= 0:
        return {"error": "Ingrese un peso válido."}
    for t in tarifas or []:
        if t["calidad"] == calidad and peso > t["peso_min"] and peso <= t["peso_max"]:
            precio = math.ceil((t["valor_gr"] * peso) / 1000) * 1000
            return {"exito": True, "precio": precio}
    return {"error": "No se encontró una tarifa para esa calidad y peso."}
