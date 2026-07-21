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

def calcular_cotizacion(joyas, medio_pago, aplicar_envio, tipo_envio, envio_manual):
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
        
        seguro_ce = round(subtotal * 0.012)
        if subtotal <= 500001: tarifa_base = 30000
        elif subtotal <= 800001: tarifa_base = 40000
        elif subtotal <= 1000001: tarifa_base = 50000
        else: tarifa_base = 70000

        envio = tarifa_base + seguro_ce
        # --- CAMBIO: Se agregó "1.2%" al texto del seguro Contra Entrega
        detalle_envio = f"Envío Contra Entrega ${tarifa_base:,} + Seguro 1.2% ({seguro_ce:,}): ${envio:,}".replace(',', '.')
    
    else:
        if aplicar_envio:
            if tipo_envio == "Local (Medellín)":
                envio = 17000
                detalle_envio = f"Envío Local Medellín: ${envio:,}".replace(',', '.')
            elif tipo_envio == "Local (Área Metropolitana)":
                envio = 22000
                detalle_envio = f"Envío Área Metropolitana: ${envio:,}".replace(',', '.')
            elif tipo_envio == "Nacional":
                seguro_nal = round(subtotal * 0.006)
                envio = 20000 + seguro_nal
                # --- CAMBIO: Se agregó "0.6%" al texto del seguro Nacional
                detalle_envio = f"Envío Nacional $20.000 + Seguro 0.6% ({seguro_nal:,}): ${envio:,}".replace(',', '.')
            elif tipo_envio == "Internacional":
                envio = limpiar_numero(envio_manual)
                detalle_envio = f"Envío Internacional: ${envio:,}".replace(',', '.')

    # 3. Calcular Total Base
    total_base = subtotal + envio

    # 4. Calcular Recargos y 5. Total Final
    recargo = 0
    detalle_recargo = ""
    total_final = total_base

    if medio_pago in ["Addi", "Sistecredito"]:
        if total_base < 2000000: pct, pct_str = 0.06, "6%"
        elif total_base < 4000000: pct, pct_str = 0.08, "8%"
        elif total_base < 6000000: pct, pct_str = 0.10, "10%"
        else: pct, pct_str = 0.12, "12%"

        recargo = round(total_base * pct)
        total_final = total_base + recargo
        
        detalle_recargo = f"Recargo {pct_str} ({recargo:,})".replace(',', '.')

    elif medio_pago == "T. Crédito/Débito":
        if subtotal > 8000000:
            return {"error": "Este medio de pago ya no es válido para este monto (Máx $8.000.000)."}
            
        recargo = round(total_base * 0.03)
        total_final = total_base + recargo
        detalle_recargo = f"Recargo Tarjeta 3% ({recargo:,})".replace(',', '.')

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