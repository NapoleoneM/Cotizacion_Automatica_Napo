import re
import gspread

from core.app_config import log

# Documento ESPEJO de precios ("Precio de tablas publica"): réplica de la hoja
# Tablas del CORE, refrescada por un Apps Script del lado de Google.
# La app NUNCA debe apuntar al documento CORE — el service account empaquetado
# solo tiene acceso a este espejo, así una filtración de credenciales no expone
# las hojas confidenciales. (Migrado el 2026-06-25.)
_SPREADSHEET_ID = "1S7L7oXZRfMCo6m_QSuzEH2eoIppu91xM_34NIWy5Cnc"
# Por NOMBRE, no por gid: el Apps Script recrea la pestaña con copyTo() en
# cada actualización, y eso le asigna un gid interno nuevo cada vez aunque
# el nombre se mantenga igual.
_HOJA_TABLAS = "Tablas"
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
# Las tarifas se ubican por su ROTULO, no por coordenadas. Antes iban con fila
# y columna fijas (ej. fila 41 = Diamantada) y cualquier cambio en el CORE las
# desalineaba en silencio: la joya quedaba con precio 0 y el calculo la OMITIA
# de la cotizacion sin avisar. Paso el 06/10/2026, cuando el CORE fusiono Lisa
# y Diamantada en una sola fila ("Lisas | Diam.") y agrego las secciones 14K
# ITALIANO y PLATA 925: la fila 41 dejo de ser Diamantada y paso a ser un
# encabezado sin numeros.
#
# Ahora se puede mover, agregar o quitar filas y secciones en la hoja sin tocar
# este archivo. Lo unico que debe mantenerse es el TEXTO de los rotulos.

def _norm(texto):
    """'Fabricaciones ' -> 'FABRICACIONES': compara rotulos sin depender de
    tildes, mayusculas ni espacios de sobra."""
    import unicodedata
    sin_tildes = unicodedata.normalize("NFKD", str(texto or ""))
    limpio = "".join(c for c in sin_tildes if not unicodedata.combining(c))
    return " ".join(limpio.upper().split())


def _mapear_tarifas(filas, bloque="MAYORISTAS"):
    """Recorre la hoja y devuelve {SECCION: {ROTULO: (contado, credito)}}.

    La hoja trae VARIOS bloques lado a lado (Cliente, Joyerias, Mayoristas,
    Neoros...) y todos usan el mismo encabezado 'Tipo | Contado', asi que hay
    que anclarse al rotulo del bloque pedido. Ojo: ese texto puede aparecer mas
    de una vez en la hoja (hay un 'MAYORISTAS' suelto arriba a la derecha), por
    eso se prueban TODOS los candidatos y se usa el primero que tenga un 'Tipo'
    debajo en su misma columna: ese es el bloque de verdad.

    Desde esa fila hacia abajo, una fila con rotulo y sin numeros es un
    encabezado de seccion; una con numeros es una tarifa de la seccion vigente.
    """
    candidatos = [
        (i, j)
        for i, fila in enumerate(filas)
        for j, celda in enumerate(fila)
        if _norm(celda) == bloque
    ]

    for fila_bloque, col_rotulo in candidatos:
        col_contado = col_credito = fila_inicio = None
        for i in range(fila_bloque + 1, len(filas)):
            fila = filas[i]
            if col_rotulo >= len(fila) or _norm(fila[col_rotulo]) != "TIPO":
                continue
            valores = [k for k in range(col_rotulo + 1, len(fila)) if _norm(fila[k])]
            if valores:
                fila_inicio = i + 1
                col_contado = valores[0]
                col_credito = valores[1] if len(valores) > 1 else valores[0]
            break
        if fila_inicio is None:
            continue                  # este rotulo no era el bloque: probar el siguiente

        mapa, seccion = {}, ""
        for fila in filas[fila_inicio:]:
            def celda(c):
                return fila[c] if c < len(fila) else ""

            rotulo = _norm(celda(col_rotulo))
            if not rotulo:
                continue
            contado = limpiar_numero_mayorista(celda(col_contado))
            credito = limpiar_numero_mayorista(celda(col_credito))
            if contado <= 0 and credito <= 0:
                seccion = rotulo      # fila sin numeros = encabezado de seccion
                continue
            if seccion:
                mapa.setdefault(seccion, {})[rotulo] = (contado, credito)
        if mapa:
            return mapa
    return {}


def _tarifa(mapa, seccion, *claves, credito=False):
    """Primer rotulo de la seccion que empiece por alguna de las claves, o que
    las contenga. Lo segundo es lo que permite que 'Lisas | Diam.' sirva tanto
    para Lisa como para Diamantada ahora que el CORE las unio en una fila."""
    filas = mapa.get(seccion, {})
    for clave in claves:
        for rotulo, valores in filas.items():
            if rotulo.startswith(clave):
                return valores[1 if credito else 0]
    for clave in claves:
        for rotulo, valores in filas.items():
            if clave in rotulo:
                return valores[1 if credito else 0]
    return 0


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
        worksheet = spreadsheet.worksheet(_HOJA_TABLAS)
        mapa = _mapear_tarifas(worksheet.get_all_values())

        # Nacional e Italiano cotizan solo con la columna de contado: es como
        # funciono siempre y no se toca para no mover montos ya pactados.
        precios = {
            "Nacional": {
                "Corriente": _tarifa(mapa, "NACIONAL", "CORRIENTE"),
                "Especial": _tarifa(mapa, "NACIONAL", "ESPECIAL"),
                # El CORE escribe "Fabricaciones" (plural): startswith lo cubre
                "Fabricación": _tarifa(mapa, "NACIONAL", "FABRICACION"),
            },
            "Italiano": {
                f"Recargo +{n}": _tarifa(mapa, "ITALIANO", f"RECARGO +{n}")
                for n in range(1, 6)
            },
            # Bolas es el unico que usa las dos columnas. Se aceptan tanto las
            # filas separadas (Lisa / Diamantada) como la fila unica que las
            # agrupa: si un rotulo nombra a las dos, sirve para ambas.
            "Bolas": {
                "Lisa contado": _tarifa(mapa, "BOLAS", "LISA"),
                "Lisa crédito": _tarifa(mapa, "BOLAS", "LISA", credito=True),
                "Diamantada contado": _tarifa(mapa, "BOLAS", "DIAMANTADA", "DIAM"),
                "Diamantada crédito": _tarifa(mapa, "BOLAS", "DIAMANTADA", "DIAM",
                                              credito=True),
            },
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
