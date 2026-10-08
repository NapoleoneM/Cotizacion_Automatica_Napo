import re

def limpiar_numero(texto):
    """Elimina $, puntos, comas, espacios y convierte a entero."""
    if not texto: 
        return 0
    texto_limpio = re.sub(r'[$.,\s]', '', str(texto))
    try:
        return int(texto_limpio)
    except ValueError:
        return 0

# Tachado con el caracter Unicode U+0336 (raya sobre cada caracter). Es el
# mismo que usa mayorista_logic.generar_tachado: se ve tachado tanto en
# WhatsApp como en Instagram, a diferencia del ~texto~ que solo entiende
# WhatsApp. Se duplica aqui para no hacer depender retail de gspread.
def tachar(texto):
    return "".join(c + "\u0336" for c in str(texto))


# PROMOCION DE ENVIO — medida TEMPORAL: campana de ~1 mes desde el 08/10/2026.
# Con la casilla "Obsequiar envio" se descuentan $20.000 de la tarifa del envio
# que toque, sea cual sea (Contra Entrega e Internacional incluidos). Si la
# tarifa es menor (Medellin, $17.000) el envio queda gratis: nunca baja de $0.
# Que la casilla se marque sola desde $600.000 en joyas se decide en
# static/app.js; aqui solo se respeta lo que llega.
#
# Historia: el 08/10 empezo regalando la tarifa COMPLETA solo en Medellin,
# Area Metropolitana y Nacional. Ese mismo dia paso a esta regla general de
# $20.000 fijos, con Contra Entrega incluido.
DESCUENTO_ENVIO = 20000


def _tarifa_con_descuento(tarifa, aplicar):
    """(lo que se cobra, texto de la tarifa para el mensaje).

    Sin descuento el texto es el de siempre ("$17.000"). Con descuento la
    tarifa sale tachada y al lado lo que paga el cliente, para que vea el
    regalo: "[$50.000 tachado] $30.000 ¡Te regalamos $20.000!", o la tarifa
    tachada con "¡GRATIS!" si el descuento la cubre toda.
    """
    normal = f"${tarifa:,}".replace(',', '.')
    descuento = min(DESCUENTO_ENVIO, tarifa) if aplicar else 0
    if descuento <= 0:
        return tarifa, normal
    cobrado = tarifa - descuento
    if cobrado == 0:
        return 0, f"{tachar(normal)} ¡GRATIS!"
    regalo = f"${descuento:,}".replace(',', '.')
    return cobrado, f"{tachar(normal)} ${cobrado:,} ¡Te regalamos {regalo}!".replace(',', '.')


def calcular_cotizacion(joyas, medio_pago, aplicar_envio, tipo_envio, envio_manual,
                        obsequiar_envio=False):
    """Procesa los datos y retorna el texto formateado o un error."""
    if not joyas:
        return {"error": "Debe agregar al menos una joya para calcular."}

    # 1. Calcular subtotal
    subtotal = 0
    detalle_joyas = []
    
    for j in joyas:
        cant = int(j.get('cantidad', 1))
        if cant < 1: cant = 1
        
        val_uni = limpiar_numero(j.get('valor_unitario', 0))
        if val_uni < 0: val_uni = 0
        
        tot_j = cant * val_uni
        subtotal += tot_j
        detalle_joyas.append({
            'nombre': j.get('nombre', 'Joya sin nombre'),
            'cantidad': cant,
            'valor_unitario': val_uni,
            'total': tot_j
        })

    if subtotal == 0:
        return {"error": "El subtotal no puede ser $0. Revise los valores ingresados."}

    envio = 0
    detalle_envio = ""
    
    # 2. Calcular envío
    if medio_pago == "Contra Entrega":
        if subtotal > 1500000:
            return {"error": "Este medio de pago no está disponible para este monto (Máx $1.500.000)."}
        
        # Tarifa por tramo del valor de la joya (tabla de la transportadora).
        # Los límites van con el +1 que ya traía el código desde el principio;
        # no se tocan para no cambiar el resultado de una cotización existente.
        if subtotal <= 500001: tarifa_base = 30000
        elif subtotal <= 800001: tarifa_base = 40000
        elif subtotal <= 1000001: tarifa_base = 50000
        elif subtotal <= 1200001: tarifa_base = 70000
        else: tarifa_base = 90000

        # ------------------------------------------------------------------
        # DIRECTIVA DEL 08/10/2026: Contra Entrega YA NO cobra el seguro del
        # 1,2%. Se cobra solo la tarifa del tramo (menos la promocion, si
        # aplica). Va para TODAS las cotizaciones contra entrega, no solo las
        # de la promocion.
        #
        # LOGICA ANTERIOR (se deja escrita por si se vuelve a cobrar):
        #   El seguro era el 1,2% del SUBTOTAL de las joyas (sin el envio),
        #   igual en todos los tramos, y se sumaba a la tarifa:
        #
        #     seguro_ce = round(subtotal * 0.012)
        #     envio = tarifa_base + seguro_ce
        #     detalle_envio = f"Envío Contra Entrega ${tarifa_base:,} + Seguro 1.2% ({seguro_ce:,}): ${envio:,}".replace(',', '.')
        #
        #   En el mensaje salia asi (compra de $820.000):
        #     🚚 Envío Contra Entrega $50.000 + Seguro 1.2% (9.840): $59.840
        # ------------------------------------------------------------------
        envio, tarifa_txt = _tarifa_con_descuento(tarifa_base, obsequiar_envio)
        detalle_envio = f"Envío Contra Entrega: {tarifa_txt}"
    
    else:
        if aplicar_envio:
            # Con la promocion se descuentan $20.000 de la tarifa (ver
            # _tarifa_con_descuento). El seguro de Nacional se sigue cobrando.
            # Sin promocion el texto queda EXACTAMENTE como estaba.
            if tipo_envio == "Local (Medellín)":
                envio, tarifa_txt = _tarifa_con_descuento(17000, obsequiar_envio)
                detalle_envio = f"Envío Local Medellín: {tarifa_txt}"
            elif tipo_envio == "Local (Área Metropolitana)":
                envio, tarifa_txt = _tarifa_con_descuento(22000, obsequiar_envio)
                detalle_envio = f"Envío Área Metropolitana: {tarifa_txt}"
            elif tipo_envio == "Nacional":
                seguro_nal = round(subtotal * 0.006)
                tarifa, tarifa_txt = _tarifa_con_descuento(20000, obsequiar_envio)
                envio = tarifa + seguro_nal
                # --- CAMBIO: Se agregó "0.6%" al texto del seguro Nacional
                detalle_envio = f"Envío Nacional {tarifa_txt} + Seguro 0.6% ({seguro_nal:,}): ${envio:,}".replace(',', '.')
            elif tipo_envio == "Internacional":
                envio, tarifa_txt = _tarifa_con_descuento(limpiar_numero(envio_manual), obsequiar_envio)
                detalle_envio = f"Envío Internacional: {tarifa_txt}"

    # 3. Calcular Total Base
    total_base = subtotal + envio

    # 4. Calcular Recargos y 5. Total Final
    recargo = 0
    detalle_recargo = ""
    total_final = total_base

    # ------------------------------------------------------------------
    # DIRECTIVA DEL 06/10/2026: en RETAIL ningun medio de pago lleva recargo.
    # Addi, Sistecredito y T. Credito/Debito quedan EXACTAMENTE igual que
    # Transferencia: total = subtotal + envio. Al no entrar en ningun 'if' se
    # quedan con recargo = 0, y como el texto solo imprime "Total base" y la
    # linea del recargo cuando recargo > 0, el mensaje sale limpio.
    #
    # Lo que SI se conserva:
    #   - El tope de $8.000.000 de la tarjeta. No es un recargo sino un LIMITE
    #     del medio de pago: por encima de ese monto no se puede cobrar con
    #     tarjeta, se cobre comision o no.
    #   - Contra Entrega: sus tarifas de envio por tramo y su tope de $1.500.000.
    #
    # La maquinaria de recargos (recargo / detalle_recargo / total_final) se
    # deja en pie a proposito: para volver a cobrar basta con reponer el bloque
    # que corresponda, sin tocar nada mas.
    #
    # LOGICA ANTERIOR (se deja escrita por si se vuelven a cobrar recargos):
    #
    #   ADDI -> recargo por escalones sobre el TOTAL BASE (subtotal + envio),
    #   sin tope de monto:
    #       total_base <  2.000.000  ->  6%
    #       total_base <  4.000.000  ->  8%
    #       total_base <  6.000.000  -> 10%
    #       total_base >= 6.000.000  -> 12%
    #
    #     if medio_pago == "Addi":
    #         if total_base < 2000000: pct, pct_str = 0.06, "6%"
    #         elif total_base < 4000000: pct, pct_str = 0.08, "8%"
    #         elif total_base < 6000000: pct, pct_str = 0.10, "10%"
    #         else: pct, pct_str = 0.12, "12%"
    #         recargo = round(total_base * pct)
    #         total_final = total_base + recargo
    #         detalle_recargo = f"Recargo {pct_str} ({recargo:,})".replace(',', '.')
    #
    #   SISTECREDITO -> tuvo DOS etapas:
    #     1) Hasta agosto de 2026 iba con los MISMOS escalones de Addi; la
    #        condicion de arriba decia: if medio_pago in ["Addi", "Sistecredito"].
    #     2) Desde septiembre de 2026 paso a un 3% plano, sin escalones y sin
    #        tope de monto, compartiendo rama con la tarjeta.
    #
    #   T. CREDITO/DEBITO -> 3% plano sobre el TOTAL BASE (subtotal + envio).
    #   Su linea decia "Recargo Tarjeta 3%" (las otras no repetian el medio de
    #   pago porque el titulo del mensaje ya lo nombra).
    #
    #   Las dos ultimas compartian este bloque:
    #
    #     elif medio_pago in ["T. Credito/Debito", "Sistecredito"]:
    #         if medio_pago == "T. Credito/Debito" and subtotal > 8000000:
    #             return {"error": "Este medio de pago ya no es valido para este monto (Max $8.000.000)."}
    #         recargo = round(total_base * 0.03)
    #         total_final = total_base + recargo
    #         etiqueta = "Tarjeta " if medio_pago == "T. Credito/Debito" else ""
    #         detalle_recargo = f"Recargo {etiqueta}3% ({recargo:,})".replace(',', '.')
    #
    #   El tope de $8.000.000 fue SIEMPRE solo de la tarjeta, y se mide contra
    #   el SUBTOTAL (sin envio): ni Addi ni Sistecredito tuvieron limite.
    # ------------------------------------------------------------------

    # La tarjeta ya no cobra recargo, pero se sigue rechazando por encima de
    # $8.000.000: es un limite del medio de pago, no una tarifa.
    if medio_pago == "T. Crédito/Débito" and subtotal > 8000000:
        return {"error": "Este medio de pago ya no es válido para este monto (Máx $8.000.000)."}

    # 6. Construcción del texto de salida
    texto = f"🦁 *{medio_pago.upper()}*\n\n"
    
    for j in detalle_joyas:
        texto += f"{j['nombre']}\n"
        if j['cantidad'] > 1:
            texto += f"${j['valor_unitario']:,}\nCantidad: {j['cantidad']}\nTotal: ${j['total']:,}\n\n".replace(',', '.')
        else:
            texto += f"${j['valor_unitario']:,}\n\n".replace(',', '.')

    texto = texto.strip() + "\n\n"

    # --- CAMBIOS DE FORMATO FINAL ---
    if envio > 0 or detalle_envio:
        texto += f"🚚 {detalle_envio}\n\n"  # <-- Salto de línea extra

    if recargo > 0:
        texto += f"Total base: ${total_base:,}\n\n".replace(',', '.')  # <-- Salto de línea extra
        texto += f"{detalle_recargo}\n"  # <-- Se quitó el emoji de engranaje y se dio salto extra

    texto += f"━━━━━━━━━━━━━━━━━━\n"
    texto += f"*TOTAL NETO: ${total_final:,}*".replace(',', '.')

    return {"exito": True, "texto": texto}