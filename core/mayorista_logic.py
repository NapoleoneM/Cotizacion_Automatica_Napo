import re
import gspread

from core.app_config import log

# Documento ESPEJO de precios ("Precio de tablas publica"): réplica de la hoja
# Tablas del CORE, refrescada cada 5 min por un Apps Script del lado de Google.
# La app NUNCA debe apuntar al documento CORE — el service account empaquetado
# solo tiene acceso a este espejo, así una filtración de credenciales no expone
# las hojas confidenciales. (Migrado el 2026-06-25.)
_SPREADSHEET_ID = "1S7L7oXZRfMCo6m_QSuzEH2eoIppu91xM_34NIWy5Cnc"
_SHEET_GID = 988798885
# Solo lectura — el service account no necesita permisos de escritura
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# --- NORMALIZADORES ---
def limpiar_numero_mayorista(texto):
    """Limpia dinero: elimina $, puntos, comas y espacios."""
    if not texto: return 0
    t = re.sub(r'[$.,\s]', '', str(texto))
    try: return int(t)
    except ValueError: return 0

def limpiar_peso(texto):
    """Limpia peso: acepta 1.5, 1,5, 1.5gr y lo convierte a float."""
    if not texto: return 0.0
    t = re.sub(r'[^\d,\.]', '', str(texto))
    t = t.replace(',', '.')
    try: return float(t)
    except ValueError: return 0.0

def generar_tachado(texto):
    """Genera efecto de tachado usando Unicode (compatible con WhatsApp/Instagram)"""
    return ''.join([c + '̶' for c in str(texto)])

# --- GOOGLE SHEETS PARSER ---
def obtener_precios_sheets(ruta_credenciales):
    """
    Lee los precios desde Google Sheets usando Service Account.
    El acceso es autenticado — la hoja debe estar compartida con el service account.
    Retorna un diccionario con las tarifas por gramo.
    """
    if not ruta_credenciales:
        return {"error": "Falta la ruta al archivo de credenciales."}

    try:
        gc = gspread.service_account(filename=ruta_credenciales, scopes=_SCOPES)
        try:
            # Evita que la app espere indefinidamente con internet inestable
            gc.http_client.set_timeout(20)
        except AttributeError:
            pass
        spreadsheet = gc.open_by_key(_SPREADSHEET_ID)
        worksheet = spreadsheet.get_worksheet_by_id(_SHEET_GID)
        reader = worksheet.get_all_values()

        def get_val(row, col):
            try:
                return limpiar_numero_mayorista(reader[row][col])
            except IndexError:
                return 0

        precios = {
            "Nacional": {
                "Corriente": get_val(30, 16),
                "Especial": get_val(31, 16),
                "Fabricación": get_val(32, 16)
            },
            "Italiano": {
                "Recargo +1": get_val(34, 16),
                "Recargo +2": get_val(35, 16),
                "Recargo +3": get_val(36, 16),
                "Recargo +4": get_val(37, 16)
            },
            "Bolas": {
                "Lisa contado": get_val(39, 16),
                "Lisa crédito": get_val(39, 17),
                "Diamantada contado": get_val(40, 16),
                "Diamantada crédito": get_val(40, 17)
            }
        }
        # Si una tarifa llega en 0 es porque el Sheet cambió de estructura o la
        # celda está vacía: se avisa para no cotizar con precios incompletos.
        faltantes = [
            f"{tipo} → {subtipo}"
            for tipo, subtipos in precios.items()
            for subtipo, valor in subtipos.items()
            if valor <= 0
        ]
        if faltantes:
            log.warning("Tarifas en 0 o no encontradas en Sheets: %s", faltantes)
        return {"exito": True, "datos": precios, "tarifas_faltantes": faltantes}
    except FileNotFoundError:
        return {"error": "No se encontró el archivo de credenciales.\nVerifique que 'credentials/credenciales.json' exista."}
    except Exception as e:
        log.warning("Fallo al conectar con Google Sheets", exc_info=True)
        return {"error": f"Error al conectar con Sheets: Verifique internet, credenciales y permisos.\nDetalle: {str(e)}"}

# --- LÓGICA DE CÁLCULO ---
def calcular_cotizacion_mayorista(joyas, otros, precios, aplicar_envio, tipo_envio, envio_manual):
    """Motor de cálculo para Mayoristas con formato Whatsapp/Instagram."""
    joyas_validas = [
        j for j in joyas
        if j['tipo'] != "Tipo Oro" and j['subtipo'] != "Subtipo" and j['subtipo'] != "Seleccione..."
    ]

    if not joyas_validas and not otros:
        return {"exito": True, "texto": ""}

    subtotal = 0
    texto = "🦁 *COTIZACIÓN MAYORISTA*\n\n"

    # Procesar solo Joyas Válidas
    for j in joyas_validas:
        peso = limpiar_peso(j['peso'])
        cant = max(1, int(j['cantidad']))
        val_normal = limpiar_numero_mayorista(j['valor_normal'])

        try:
            precio_gramo = precios[j['tipo']][j['subtipo']]
            if precio_gramo == 0: continue
        except KeyError:
            continue

        # Lógica de costos
        precio_unitario_mayorista = round(precio_gramo * peso)
        total_item = precio_unitario_mayorista * cant
        subtotal += total_item

        texto += f"{j['nombre']} {peso} gr\n"

        if val_normal > 0:
            tachado = generar_tachado(f"${val_normal:,}".replace(',', '.'))
            texto += f"{tachado} → ${precio_unitario_mayorista:,}\n".replace(',', '.')
        else:
            texto += f"${precio_unitario_mayorista:,}\n".replace(',', '.')

        if cant > 1:
            texto += f"Cantidad: {cant}\nTotal: ${total_item:,}\n".replace(',', '.')

        texto += "\n"

    # Procesar "Otros"
    if otros:
        texto += "*Otros artículos*\n"
        for o in otros:
            cant = max(1, int(o['cantidad']))
            val_uni = limpiar_numero_mayorista(o['valor_unitario'])
            tot_o = cant * val_uni
            subtotal += tot_o

            texto += f"{o['nombre']}\n"
            if cant > 1:
                texto += f"${val_uni:,}\nCantidad: {cant}\nTotal: ${tot_o:,}\n\n".replace(',', '.')
            else:
                texto += f"${val_uni:,}\n\n".replace(',', '.')

    texto = texto.strip() + "\n\n"

    # Envío
    envio = 0
    detalle_envio = ""
    if aplicar_envio:
        if tipo_envio == "Nacional":
            seguro_may = round(subtotal * 0.006)
            envio = 20000 + seguro_may
            detalle_envio = f"Envío Nacional $20.000 + Seguro 0.6% ({seguro_may:,}): ${envio:,}".replace(',', '.')
        elif tipo_envio == "Internacional":
            envio = limpiar_numero_mayorista(envio_manual)
            detalle_envio = f"Envío Internacional: ${envio:,}".replace(',', '.')

        if envio > 0:
            texto += f"🚚 {detalle_envio}\n"

    total_neto = subtotal + envio

    texto += f"━━━━━━━━━━━━━━━━━━\n"
    texto += f"*TOTAL NETO: ${total_neto:,}*".replace(',', '.')

    if total_neto > 15000000:
        texto += "\n\n⚠️ ALERTA: Este pedido debe facturarse en dos envíos (Supera los $15.000.000)."

    return {"exito": True, "texto": texto}
