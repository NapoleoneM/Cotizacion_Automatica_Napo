"""ARCHIVO — lógica de cobertura de soporte que vivía en core/turnos.py.

Retirada en agosto de 2026: se eliminó el rol de soporte del chat center (todos
pasaron a ser vendedores) y con eso dejó de haber a quién pedirle que cubra a
quién. Esto se guarda por si vuelve a haber personal de soporte.

NO se importa desde ninguna parte. Es una copia de referencia: para reactivarla
hay que volver a pegar estas piezas en `core/turnos.py` y revisar los puntos
que cambiaron alrededor (ver el README de esta carpeta).
"""

# =====================================================
# Constantes que se quitaron de core/turnos.py
# =====================================================

# Minutos de gracia tras el inicio del turno antes de pedir cobertura, y
# tiempo sin señal de la calculadora para considerar a alguien inactivo.
TOLERANCIA_MIN = 15
UMBRAL_INACTIVO_MIN = 30       # este SÍ sigue vivo en core/turnos.py

# Una reclamación de "Yo lo cubro" protege de la alarma roja solo por este
# tiempo — pasado, si la persona sigue sin señal, vuelve a "Requieren
# cobertura" (hay que confirmar la cobertura de nuevo, no vale una sola vez).
VENCIMIENTO_COBERTURA_MIN = 90

# Turno 2/3, antes de que entren: pueden tener chats pendientes de ayer sin
# revisar. Desde que abre el turno 1, cada este tanto sin que soporte
# confirme que ya los revisó, se pide cobertura preventiva (con el mismo
# mecanismo de "Yo lo cubro" y vencimiento, pero un ciclo más largo).
VENCIMIENTO_PENDIENTES_MIN = 150

# Roles que NO requieren cobertura de soporte (soporte cubre a los de redes).
# Ojo con "jefa" y "jefe": el rol real es "Jefa de ventas", así que hay que
# contemplar las dos formas o la jefatura acabaría en la lista de cobertura.
# "presencial": las vendedoras de la tienda no atienden chats, no se cubren.
_ROLES_NO_CUBRIR = ("soporte", "jefe", "jefa", "coordin", "web", "pagina",
                    "página", "presencial")


def _rol_cubrible(rol):
    """Soporte cubre a los vendedores de redes. Si no hay rol definido se asume
    que sí (mejor avisar de más que dejar un chat sin atender)."""
    n = _norm(rol)                                            # noqa: F821
    return not any(x in n for x in _ROLES_NO_CUBRIR)


# =====================================================
# El "*" del cuadro marcaba a soporte
# =====================================================
# Dentro del bucle de nombres de parsear_horario(), donde hoy solo se limpia el
# asterisco, antes se usaba para asignar el rol:
#
#                 # Un "*" al final del nombre marca a soporte: no se le pide
#                 # cobertura (no atiende chats), sin necesitar la hoja Roles.
#                 es_soporte = nombre_bruto.rstrip().endswith("*")
#                 nombre = nombre_bruto.rstrip("* ").strip() if es_soporte else nombre_bruto
#                 if not nombre:
#                     continue
#                 if es_soporte:
#                     roles[_norm(nombre)] = "Soporte"


# =====================================================
# calcular_cobertura() — el reemplazado por calcular_panel()
# =====================================================
def calcular_cobertura(horario, ahora, presencia=None, estados=None,
                       novedades=None, coberturas=None, ajustes=None):
    """Cruza el horario del día con la realidad (señal, estado, novedades) y la
    hora actual. No toca red ni disco, y la ventana de turno se prueba con
    cualquier valor de `ahora` — OJO: los "minutos sin señal" y el vencimiento
    de "Yo lo cubro" (90 min) sí usan el reloj real del proceso (`time.time()`),
    no `ahora`, porque el único llamador real (`app.py`) siempre los pasa
    sincronizados. Una prueba que fije `ahora` lejos de la fecha real, o un
    futuro modo de recálculo histórico con hora simulada, dará esos dos datos
    incoherentes con la ventana de turno — no es un bug hoy, pero es la razón
    por la que las pruebas de este archivo también calculan sus timestamps de
    presencia/cobertura con `time.time()`, no relativos a `ahora`.

    Listas que ve soporte:
      - requieren_cobertura: sin señal y SIN cobertura vigente → alarma roja.
        Tiene cuatro momentos, con distintas velocidades:
          1) Durante su turno (o recién pasada la tolerancia al entrar): el
             más urgente — "Yo lo cubro" dura VENCIMIENTO_COBERTURA_MIN.
          2) Turno 2/3 ANTES de entrar, desde que abre el turno 1: puede
             haber chats de ayer sin revisar.
          3) Cualquier turno DESPUÉS de terminar, o compensatorio/ausencia/
             cambio de horario todo el día: puede haber un cliente en
             proceso sin atender, mientras el día operativo siga.
          4) Vacaciones (columna aparte en la hoja): manda sobre cualquier
             otra cosa que diga el cuadro para esa persona.
        Los momentos 2 y 3 usan "Yo lo cubro" con VENCIMIENTO_PENDIENTES_MIN
        (más largo que el de "en turno", porque es menos urgente). Vacaciones
        es distinto: se revisa UNA VEZ AL DÍA (se reinicia a medianoche, no
        cada cierto número de minutos).
      - ausencia_informada:  en turno con estado (almuerzo…) o novedad; O
        sin señal en turno pero YA con "Yo lo cubro" vigente
        (< VENCIMIENTO_COBERTURA_MIN). Si la cobertura vence y sigue sin
        señal, vuelve a "Requieren cobertura".
      - en_linea:            atendiendo (o quedándose ayudando), señal reciente
      - por_entrar:          aún dentro de la tolerancia — nunca es urgente,
        se puede cubrir de forma preventiva pero no expira ni alarma. Turno
        2/3 con "Yo lo cubro" vigente de pendientes de ayer también cae acá.
      - no_se_espera:        compensatorio / ausencia / cambio de horario /
        turno terminado / vacaciones, todos con "Yo lo cubro" vigente — si
        vence (o, en vacaciones, cuando pasa la medianoche) y sigue sin
        señal, vuelve a "Requieren cobertura" en vez de quedarse tranquilo
        para siempre.
    """
    presencia = presencia or {}
    estados = estados or {}
    novedades = novedades or []
    coberturas = coberturas or {}
    ajustes = ajustes or {}

    roles = horario.get("roles") or {}
    dia_idx = ahora.weekday()                      # 0 = lunes … 6 = domingo
    clave_dia = "sem" if dia_idx <= 4 else ("sab" if dia_idx == 5 else "dom")
    ahora_h = ahora.hour + ahora.minute / 60.0

    # Hora de cierre del día = la más tardía entre los 3 turnos (normalmente
    # el fin del turno 3). Entre el fin del turno propio de alguien y el
    # cierre, sigue apareciendo (como ausencia informada, con "Yo lo cubro")
    # para que quede confirmado que alguien más se hizo cargo de sus chats —
    # de cierre a la apertura del día siguiente no se rastrea nada.
    _turnos_hoy = {**TURNOS, **(horario.get("turnos") or {})}          # noqa: F821
    cierre_dia = max(v.get(clave_dia, v.get("sem", (0.0, 0.0)))[1] for v in _turnos_hoy.values())
    # Hora de apertura del día = inicio del turno 1 — de ahí en adelante puede
    # haber chats de ayer sin revisar esperando a los de turno 2/3.
    apertura_dia = _turnos_hoy.get(1, TURNOS[1]).get(clave_dia, TURNOS[1]["sem"])[0]   # noqa: F821

    vacaciones_set = {_norm(n) for n in horario.get("vacaciones", []) if _norm(n)}      # noqa: F821

    def _procesar_vacacion(item, rol, cob):
        """Vacaciones: informativo (Hoy no se espera), pero pide revisar
        pendientes UNA VEZ AL DÍA — se reinicia a medianoche, no cada cierto
        número de minutos como el resto de "pendientes"."""
        item["vacaciones"] = True
        item["etiqueta"] = "Vacaciones"
        if not _rol_cubrible(rol):
            res["no_se_espera"].append(item)
            return
        vigente_hoy = bool(cob) and datetime.fromtimestamp(cob["desde"]).date() == ahora.date()   # noqa: F821
        if vigente_hoy:
            item["estado_etq"] = "Vacaciones — ya revisado hoy"
            res["no_se_espera"].append(item)
        else:
            item["cubierto_por"] = None
            item["cubierto_desde"] = None
            item["motivo"] = "está de vacaciones — revisar si tiene clientes pendientes de reasignar"
            res["requieren_cobertura"].append(item)

    res = {"requieren_cobertura": [], "ausencia_informada": [], "en_linea": [],
           "por_entrar": [], "no_se_espera": [], "novedades": novedades,
           "ajustes": sorted(ajustes.values(), key=lambda x: x.get("ts", 0)),
           "dia": DIAS[dia_idx], "semana": _semana_actual(ahora),            # noqa: F821
           "hora": ahora.strftime("%I:%M %p")}

    nov_por_clave = {}
    for n in novedades:
        nov_por_clave.setdefault(n.get("clave"), n)

    asignaciones_hoy = _aplicar_ajustes(                                     # noqa: F821
        horario.get("asignaciones", []), ajustes, dia_idx, roles)

    for a in asignaciones_hoy:
        k = _norm(a["nombre"])                                               # noqa: F821
        rol = roles.get(k, "")

        # Vacaciones manda sobre cualquier otra cosa que diga el cuadro para
        # esta persona (turno normal, compensatorio, lo que sea).
        if k in vacaciones_set:
            item = {"nombre": a["nombre"], "turno": a["turno"], "rol": rol,
                    "estado_horario": "vacaciones", "etiqueta": "Vacaciones",
                    "desde": "", "hasta": ""}
            cob = coberturas.get(k)
            if cob:
                item["cubierto_por"] = cob.get("soporte")
                item["cubierto_desde"] = cob.get("desde_hora")
            _procesar_vacacion(item, rol, cob)
            continue

        info = ESTADOS.get(a["estado"], ESTADOS["normal"])                    # noqa: F821
        ventana = (horario.get("turnos", {}).get(a["turno"])
                   or TURNOS.get(a["turno"], TURNOS[1]))                     # noqa: F821
        ini, fin = ventana.get(clave_dia, ventana.get("sem", (8.0, 16.0)))
        # Un ajuste de entrada tardía corre el inicio: antes de esa hora no se
        # alerta, porque su llegada más tarde está autorizada.
        ini_aj = _hora_a_decimal(a.get("entrada_ajustada"))                   # noqa: F821
        if ini_aj is not None:
            ini = ini_aj
        item = {"nombre": a["nombre"], "turno": a["turno"], "rol": rol,
                "estado_horario": a["estado"], "etiqueta": info["etiqueta"],
                "desde": _fmt_hora(ini), "hasta": _fmt_hora(fin)}            # noqa: F821
        if a.get("ajuste"):
            item["ajuste"] = a["ajuste"]
            item["ajuste_nota"] = a.get("ajuste_nota", "")

        cob = coberturas.get(k)
        if cob:
            item["cubierto_por"] = cob.get("soporte")
            item["cubierto_desde"] = cob.get("desde_hora")

        if not info["cubrir"]:
            # Compensatorio/Ausencia/Cambio de horario: no viene hoy, pero
            # puede tener un cliente en proceso sin atender — mismo ciclo de
            # 2.5h que "turno terminado" (ver más abajo), no es informativo
            # puro: si nadie confirma, sí pide revisión.
            item["no_viene_hoy"] = True
            if not _rol_cubrible(rol):
                res["no_se_espera"].append(item)
                continue
            vigente_pend = bool(cob) and (time.time() - cob["desde"]) / 60.0 <= VENCIMIENTO_PENDIENTES_MIN   # noqa: F821
            if vigente_pend:
                item["estado_etq"] = "Pendientes ya revisados"
                res["no_se_espera"].append(item)
            else:
                item["cubierto_por"] = None
                item["cubierto_desde"] = None
                item["motivo"] = f"{info['etiqueta']} hoy, puede tener clientes en proceso sin atender"
                res["requieren_cobertura"].append(item)
            continue

        # Turno 2/3, antes de entrar hoy, con el turno 1 ya abierto: puede
        # tener chats pendientes de ayer sin revisar. A diferencia del resto
        # de "aún no entran" (nunca urgente), esto SÍ pide cobertura cada
        # VENCIMIENTO_PENDIENTES_MIN minutos, con el mismo mecanismo de
        # "Yo lo cubro" y vencimiento que el resto de la alarma roja.
        if a["turno"] in (2, 3) and _rol_cubrible(rol) and apertura_dia <= ahora_h < ini:
            vigente_pend = bool(cob) and (time.time() - cob["desde"]) / 60.0 <= VENCIMIENTO_PENDIENTES_MIN   # noqa: F821
            if vigente_pend:
                item["estado_etq"] = "Pendientes de ayer ya revisados"
                res["por_entrar"].append(item)
            else:
                item["cubierto_por"] = None
                item["cubierto_desde"] = None
                item["pendientes_ayer"] = True
                item["motivo"] = f"entra a las {item['desde']} pero puede tener chats pendientes de ayer sin revisar"
                res["requieren_cobertura"].append(item)
            continue

        # Aún no entra: antes de que se cumpla la tolerancia nunca es urgente
        # (se puede cubrir de forma preventiva con el botón, pero no exige
        # nada todavía — por eso no importa si la cobertura está vencida acá).
        if ahora_h < ini + TOLERANCIA_MIN / 60.0:
            res["por_entrar"].append(item)
            continue

        # Cierre del día: de acá al turno 1 de mañana no se rastrea nada.
        if ahora_h > cierre_dia:
            continue

        dentro_turno = ahora_h <= fin  # False = su turno ya terminó, pero el día sigue

        # Sede presencial: plan conocido de antemano, no depende de señal ni
        # de novedad — sus chats están sin atender todo el turno.
        if dentro_turno and info.get("sede"):
            if _rol_cubrible(rol):
                item["estado"] = a["estado"]
                item["estado_etq"] = info["etiqueta"]
                item["sede"] = True
                res["ausencia_informada"].append(item)
            continue

        pres = presencia.get(k) or {}
        ts = pres.get("ts")
        mins = None if not ts else max(0.0, (time.time() - ts) / 60.0)        # noqa: F821
        item["min_sin_senal"] = None if mins is None else int(mins)
        if pres.get("primera_ts"):
            item["entro"] = datetime.fromtimestamp(pres["primera_ts"]).strftime("%I:%M %p")   # noqa: F821

        est = estados.get(k)
        nov = nov_por_clave.get(k)

        if dentro_turno:
            # Almuerzo automático: dentro de la ventana de su turno se marca
            # solo, sin que el asesor tenga que seleccionarlo — lo único que
            # lo invalida es haber marcado "Desconectado" explícitamente.
            alm_ini, alm_fin = (horario.get("almuerzos", {}).get(a["turno"])
                                or ALMUERZOS.get(a["turno"], (None, None)))   # noqa: F821
            desconectado = bool(est and est["estado"] == "desconectado")
            if alm_ini is not None and alm_ini <= ahora_h < alm_fin and not desconectado:
                est = {"estado": "almuerzo", "ts": _ts_hoy(ahora, alm_ini)}   # noqa: F821

            # 1) Estado explícito que dice que no está atendiendo → ausencia informada
            if est and not ESTADOS_ASESOR.get(est["estado"], {}).get("atiende", True):   # noqa: F821
                item["estado"] = est["estado"]
                item["estado_etq"] = ESTADOS_ASESOR[est["estado"]]["etiqueta"]           # noqa: F821
                item["desde_estado"] = datetime.fromtimestamp(est["ts"]).strftime("%I:%M %p")   # noqa: F821
                if est["estado"] == ESTADO_PRESENCIAL:                                    # noqa: F821
                    item["sede"] = True
                if _rol_cubrible(rol):
                    res["ausencia_informada"].append(item)
                continue

        # 2) Novedad reportada (ausencia, llegada tarde…) → ausencia informada
        if nov and (mins is None or mins > UMBRAL_INACTIVO_MIN):
            item["novedad"] = nov.get("tipo")
            item["nota"] = nov.get("nota", "")
            if nov.get("tipo") == "Apoyo a presencial":
                item["sede"] = True
            if _rol_cubrible(rol):
                res["ausencia_informada"].append(item)
            continue

        # 3) Señal reciente → está trabajando (o se quedó ayudando tras su turno)
        if mins is not None and mins <= UMBRAL_INACTIVO_MIN:
            if est:
                item["estado"] = est["estado"]
                item["estado_etq"] = ESTADOS_ASESOR.get(est["estado"], {}).get("etiqueta", "")   # noqa: F821
            res["en_linea"].append(item)
            continue

        # 4) Sin señal, sin explicación:
        if not _rol_cubrible(rol):
            continue                                # soporte/jefe/web: no se cubre

        if not dentro_turno:
            # Su turno ya terminó, pero el día operativo sigue: puede haber
            # un cliente en proceso sin atender. Mismo mecanismo que "antes
            # de entrar" (ver arriba): cada VENCIMIENTO_PENDIENTES_MIN
            # minutos sin que soporte confirme, se pide revisión de nuevo —
            # un ciclo más largo que el de "en turno" porque ya no es tan
            # urgente, pero tampoco se olvida solo porque el horario terminó.
            item["turno_terminado"] = True
            vigente_pend = bool(cob) and (time.time() - cob["desde"]) / 60.0 <= VENCIMIENTO_PENDIENTES_MIN   # noqa: F821
            if vigente_pend:
                item["estado_etq"] = "Pendientes ya revisados"
                res["no_se_espera"].append(item)
            else:
                item["cubierto_por"] = None
                item["cubierto_desde"] = None
                item["motivo"] = f"su turno terminó a las {item['hasta']} y puede tener clientes en proceso sin atender"
                res["requieren_cobertura"].append(item)
            continue

        # Dentro del turno, sin señal: necesita que alguien confirme la
        # cobertura. Si ya hay una reclamada y vigente (< 90 min desde "Yo lo
        # cubro"), se muestra sin alarma; si nunca la hubo, o ya venció,
        # queda (o vuelve a quedar) en "Requieren cobertura".
        motivo = ("sin señal desde el inicio del turno" if mins is None
                  else f"sin actividad hace {int(mins)} min")

        vigente = bool(cob) and (time.time() - cob["desde"]) / 60.0 <= VENCIMIENTO_COBERTURA_MIN   # noqa: F821
        if vigente:
            item["estado_etq"] = motivo.capitalize()
            res["ausencia_informada"].append(item)
        else:
            item["cubierto_por"] = None    # si había una reclamación, ya venció: se pide de nuevo
            item["cubierto_desde"] = None
            item["motivo"] = motivo
            res["requieren_cobertura"].append(item)

    # Vacaciones sin ninguna fila en el cuadro esta semana (persona que solo
    # vive en esta lista, no tiene turno asignado): igual se procesa.
    nombres_procesados_hoy = {_norm(a["nombre"]) for a in asignaciones_hoy}   # noqa: F821
    for nombre_original in horario.get("vacaciones", []):
        k = _norm(nombre_original)                                           # noqa: F821
        if not k or k in nombres_procesados_hoy:
            continue
        rol = roles.get(k, "")
        item = {"nombre": nombre_original, "turno": 0, "rol": rol,
                "estado_horario": "vacaciones", "etiqueta": "Vacaciones",
                "desde": "", "hasta": ""}
        cob = coberturas.get(k)
        if cob:
            item["cubierto_por"] = cob.get("soporte")
            item["cubierto_desde"] = cob.get("desde_hora")
        _procesar_vacacion(item, rol, cob)

    res["requieren_cobertura"].sort(key=lambda x: (bool(x.get("cubierto_por")), x["turno"], x["nombre"]))
    res["ausencia_informada"].sort(key=lambda x: (bool(x.get("cubierto_por")), x["nombre"]))
    res["en_linea"].sort(key=lambda x: x["nombre"])
    res["por_entrar"].sort(key=lambda x: (x["turno"], x["nombre"]))
    return res
