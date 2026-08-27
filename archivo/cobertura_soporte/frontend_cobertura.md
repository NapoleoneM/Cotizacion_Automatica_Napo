# ARCHIVO — el frontend de la cobertura de soporte

Retirado en agosto de 2026 junto con el rol de soporte. Todo lo de aquí salió
de `static/index.html`, `static/app.js` y `static/styles.css`.

---

## 1. `static/index.html`

La sección roja iba **antes** de "Ausencia informada":

```html
      <div class="panel-sec">
        <div class="panel-sec-tit rojo">Requieren cobertura <span id="n-cob"></span></div>
        <div class="panel-lista" id="lista-cobertura"></div>
      </div>
```

Y la vista de Gestión tenía un segundo bloque para soporte:

```html
        <div class="panel-sec-tit" style="margin-top:8px">Asesores — cumplimiento de horario</div>
        <div class="panel-lista" id="gestion-asesores"></div>
        <div class="panel-sec-tit" style="margin-top:8px">Soporte — cobertura y tiempo de respuesta</div>
        <div class="panel-lista" id="gestion-soporte"></div>
```

El título del panel era `Turnos y cobertura`, y el comentario de la sección
`<!-- ============ TURNOS Y COBERTURA ============`.

---

## 2. `static/app.js`

### Roles en vivo y el botón "Yo lo cubro"

```js
// Roles de la última carga (nombre normalizado -> rol), para saber si "Soy:"
// es soporte. Se marca soporte con un "*" al final del nombre en la hoja.
let rolesActual = {};
function normalizarClave(s) {
  return String(s || "").trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}
function esSoporteYo() {
  const rol = rolesActual[normalizarClave(yoNombre())] || "";
  return rol.toLowerCase().includes("soporte");
}

// Botón para que soporte se adjudique la cobertura (o la libere). Evita que dos
// personas entren a la misma cuenta y deja el registro de quién cubrió. Solo
// soporte lo ve — el resto solo ve quién está cubriendo, sin poder tocarlo.
// Evita que un doble-clic (conexión lenta, clic nervioso) mande la misma
// acción dos veces: deshabilita el botón mientras la petición está en curso.
function alClic(b, fn) {
  b.onclick = async () => {
    if (b.disabled) return;
    b.disabled = true;
    try { await fn(); } finally { b.disabled = false; }
  };
}

function botonCubrir(x) {
  const cont = el("div", "panel-cubrir");
  if (x.cubierto_por) {
    cont.append(el("span", "cubre-txt", `cubre ${x.cubierto_por} desde ${x.cubierto_desde || ""}`));
    if (esSoporteYo()) {
      const b = el("button", "panel-mini", "liberar");
      alClic(b, async () => {
        await fetch("/api/turnos/cubrir/cerrar", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ titular: x.nombre }),
        });
        cargarTurnos();
      });
      cont.append(b);
    }
  } else if (esSoporteYo()) {
    const b = el("button", "panel-mini oro", "Yo lo cubro");
    alClic(b, async () => {
      const yo = yoNombre();
      if (!yo) { alert("Primero elige tu nombre en 'Soy:'"); return; }
      await fetch("/api/turnos/cubrir", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ titular: x.nombre, soporte: yo }),
      });
      cargarTurnos();
    });
    cont.append(b);
  }
  return cont;
}
```

`renderPanel(d)` empezaba con:

```js
function renderPanel(d) {
  rolesActual = d.roles || {};
  pedirPermisoNotificacion();
  refrescarSello();
```

### Contadores y pintado de las listas

```js
  const cob = d.requieren_cobertura || [];
  const aus = d.ausencia_informada || [];
  $("#n-cob").textContent = cob.length ? `(${cob.length})` : "";
  $("#n-aus").textContent = aus.length ? `(${aus.length})` : "";
```

```js
  pintarLista($("#lista-cobertura"), cob, x => {
    const d2 = itemBase(x, "rojo");
    // El motivo de "turno terminado" y "pendientes de ayer" ya son frases
    // completas; no repetir la hora de entrada delante (quedaría "empezó
    // 8am · terminó a las 4pm", o "empezó 11am · entra a las 11am...").
    const det = (x.turno_terminado || x.pendientes_ayer || x.no_viene_hoy || x.vacaciones)
      ? x.motivo : `su turno empezó ${x.desde} · ${x.motivo}`;
    d2.append(el("span", "det", det));
    d2.append(botonCubrir(x));
    return d2;
  });
```

En "Ausencia informada" el color distinguía un turno terminado, y llevaba
botón:

```js
    const d2 = itemBase(x, x.sede ? "morado" : x.turno_terminado ? "azul" : "amarillo");
    ...
    d2.append(botonCubrir(x));
```

"Aún no entran" y "Hoy no se espera" también:

```js
  pintarLista($("#lista-porentrar"), d.por_entrar, x => {
    const d2 = itemBase(x, "");
    // Turno 2/3 con pendientes de ayer ya revisados trae una nota aparte;
    // el resto solo dice a qué hora entra.
    const det = x.estado_etq ? `${x.estado_etq} · entra ${x.desde}` : `entra ${x.desde}`;
    d2.append(el("span", "det", det));
    d2.append(botonCubrir(x));   // soporte puede adelantarse, sin esperar la alarma
    return d2;
  });

  pintarLista($("#lista-nospera"), d.no_se_espera, x => {
    const d2 = itemBase(x, "");
    // Todos los casos "tranquilos por ahora" (turno terminado, no viene hoy,
    // vacaciones) muestran cuándo se revisó y el botón para revisar de nuevo
    // antes de que venza — el resto (Aún no entra por horario normal) no.
    if (x.turno_terminado || x.no_viene_hoy || x.vacaciones) {
      d2.append(el("span", "det", x.estado_etq || "Pendientes ya revisados"));
      d2.append(botonCubrir(x));
    }
    return d2;
  });
```

### Aviso sonoro: notificaciones y repique

```js
const MUDO_KEY = "turnos_mudo";
let novVistas = null;          // ids de novedades ya avisadas
let cobVistas = null;          // nombres ya avisados como sin cubrir
let tituloOriginal = document.title;
let parpadeo = null;
let repiqueCobertura = null;   // pitido cada 1 min mientras alguien siga sin cubrir (solo soporte)
```

```js
// Notificación nativa del sistema (funciona con el navegador minimizado, no
// solo en segundo plano). Solo para soporte, y solo tras dar el permiso.
function pedirPermisoNotificacion() {
  if (!esSoporteYo() || !("Notification" in window)) return;
  if (Notification.permission === "default") Notification.requestPermission();
}

function notificarCobertura(nombre) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  try {
    new Notification("⚠️ Requieren cobertura", {
      body: `${nombre} quedó sin cubrir — entra al panel de Turnos.`,
      tag: "cobertura-" + nombre,   // evita apilar varias del mismo nombre
    });
  } catch (e) { /* algunos navegadores bloquean Notification sin foco */ }
}
```

```js
function revisarAvisos(d) {
  const novs = d.novedades || [];
  const cob = d.requieren_cobertura || [];
  const idsNov = new Set(novs.map(n => n.id));
  const nomCob = new Set(cob.map(x => x.nombre));

  // Primera carga: solo se toma nota, sin sonar (evita el pitido al abrir).
  if (novVistas === null) { novVistas = idsNov; cobVistas = nomCob; }
  else {
    const nuevasNov = novs.filter(n => !novVistas.has(n.id));
    const nuevasCob = cob.filter(x => !cobVistas.has(x.nombre));
    const importante = nuevasNov.some(n => n.importante);

    if (importante || nuevasCob.length) {
      sonar(true);
      const quien = importante ? nuevasNov.find(n => n.importante).nombre
                               : nuevasCob[0].nombre;
      avisarEnTitulo(`⚠️ ${quien} — revisar turnos`);
      nuevasCob.forEach(x => notificarCobertura(x.nombre));
    } else if (nuevasNov.length) {
      sonar(false);
    }
    novVistas = idsNov;
    cobVistas = nomCob;
  }

  // Para soporte: mientras alguien siga en "Requieren cobertura", un pitido
  // extra cada minuto — no basta con avisar una sola vez cuando aparece.
  if (esSoporteYo() && cob.length && !estaMudo()) {
    if (!repiqueCobertura) repiqueCobertura = setInterval(() => sonar(true), 60000);
  } else if (repiqueCobertura) {
    clearInterval(repiqueCobertura);
    repiqueCobertura = null;
  }
}
```

### Vista de gestión: veredictos y bloque de soporte

```js
// Umbrales de veredicto — ajustables si con el uso real resultan muy
// estrictos o muy permisivos. Se acumulan sobre el rango mostrado (por
// defecto, la semana en curso), no por día.
const VEREDICTO_ASESOR_MIN = [15, 60];       // minutos sin cobertura confirmada
const VEREDICTO_SOPORTE_MIN = [10, 30];      // minutos de respuesta promedio

function veredicto(minutos, [verde, amarillo]) {
  if (minutos <= verde) return "verde";
  if (minutos <= amarillo) return "amarillo";
  return "rojo";
}
```

```js
    $("#gestion-totales").textContent =
      `${d.desde} a ${d.hasta} · ${t.personas || 0} personas · ` +
      `${t.novedades || 0} novedades · ${t.minutos_sin_cobertura || 0} min sin cobertura` +
      (t.minutos_presencial ? ` · 🏬 ${t.minutos_presencial} min en presencial` : "");

    const personas = d.personas || [];
    const esSoporte = p => (p.rol || "").toLowerCase().includes("soporte");
    const asesores = personas.filter(p => !esSoporte(p))
      .sort((a, b) => b.minutos_sin_cobertura - a.minutos_sin_cobertura);
    const soporte = personas.filter(esSoporte)
      .sort((a, b) => b.min_respuesta_prom - a.min_respuesta_prom);

    pintarLista($("#gestion-asesores"), asesores, p => {
      const v = veredicto(p.minutos_sin_cobertura, VEREDICTO_ASESOR_MIN);
      const d2 = itemBase(p, v);
      const partes = [`entra ~${p.entrada_tipica}`, `${p.dias_con_senal} días con señal`];
      partes.push(p.minutos_sin_cobertura
        ? `${p.minutos_sin_cobertura} min sin cobertura (${p.episodios_sin_cobertura}×)`
        : "sin episodios sin cobertura");
      if (p.total_novedades) partes.push(`${p.total_novedades} novedades`);
      if (p.minutos_presencial) partes.push(`🏬 ${p.minutos_presencial} min presencial`);
      d2.append(el("span", "det", partes.join(" · ")));
      return d2;
    });

    pintarLista($("#gestion-soporte"), soporte, p => {
      // Sin ninguna respuesta registrada no significa que incumplió — puede
      // ser que sencillamente no hubo nada que cubrir en el rango.
      const v = p.veces_respondio ? veredicto(p.min_respuesta_prom, VEREDICTO_SOPORTE_MIN) : "gris";
      const d2 = itemBase(p, v);
      const partes = p.veces_respondio
        ? [`cubrió ${p.veces_respondio}×`, `~${p.min_respuesta_prom} min de respuesta`]
        : ["sin coberturas registradas en el rango"];
      if (p.minutos_cubierto) partes.push(`${p.minutos_cubierto} min cubriendo en total`);
      d2.append(el("span", "det", partes.join(" · ")));
      return d2;
    });
```

La cabecera de la sección del panel decía:

```js
// =====================================================
// PANEL DE TURNOS Y COBERTURA
// Vive fuera de la calculadora. Envía una señal de presencia (para que soporte
// sepa quién está atendiendo) y muestra a quién hay que cubrir según la hora.
// =====================================================
```

y la del aviso sonoro:

```js
// =====================================================
// AVISO SONORO
// El problema original era que soporte no se daba cuenta. Un contador rojo no
// sirve si nadie mira la pantalla, así que suena cuando aparece algo nuevo que
// exige acción: una novedad importante o alguien que se queda sin cubrir.
// =====================================================
```

---

## 3. `static/styles.css`

```css
.panel-sec-tit.rojo { color: #e74c3c; }
.panel-item.rojo { border-left-color: #e74c3c; }

/* "Yo lo cubro" / liberar */
.panel-cubrir { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.cubre-txt { color: var(--verde); font-size: 11px; flex: 1; }

.panel-mini.oro { background: var(--oro); color: var(--oro-texto); border-color: var(--oro);
  font-weight: bold; }
```

El comentario de `.panel-item.gris` era:

```css
/* Sin datos suficientes para un veredicto (ej. soporte sin nada que cubrir) */
```

> Nota: `.panel-item.azul` y `.panel-item .tag.azul` **siguen en uso** (los
> ajustes del día), no hay que tocarlos.
