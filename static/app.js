// Calculadora Napo — Web. Toda la presentación; los cálculos los hace el servidor
// reutilizando la misma lógica Python del escritorio (resultados idénticos).
"use strict";
const $ = (s, ctx = document) => ctx.querySelector(s);
const $$ = (s, ctx = document) => [...ctx.querySelectorAll(s)];
const DEBOUNCE = 300;

// ---------- Tema ----------
function aplicarTema(t) {
  document.documentElement.dataset.tema = t;
  $$("#toggle-tema button").forEach(b => b.classList.toggle("activo", b.dataset.tema === t));
  const src = t === "light" ? "/img/logo_negro.png" : "/img/logo_blanco.png";
  $("#logo").src = src;
  const gl = $("#gate-logo"); if (gl) gl.src = src;
  localStorage.setItem("tema", t);
  if (tablaCargada) dibujarTabla(tablaCargada);  // repintar con colores del tema
  if (typeof refrescarSello === "function") refrescarSello();
}
$("#toggle-tema").addEventListener("click", e => {
  if (e.target.dataset.tema) aplicarTema(e.target.dataset.tema);
});

// ---------- Tabs ----------
$("#tabs").addEventListener("click", e => {
  const v = e.target.dataset.vista;
  if (!v) return;
  $$(".tab").forEach(t => t.classList.toggle("activa", t.dataset.vista === v));
  $$(".vista").forEach(s => s.classList.toggle("activa", s.id === "vista-" + v));
  if (v === "tabla" && !tablaCargada) cargarTabla();
});

// ---------- Utilidades ----------
function fmtMiles(v) {
  const d = String(v).replace(/\D/g, "").slice(0, 12);
  return d ? Number(d).toLocaleString("es-CO").replace(/,/g, ".") : "";
}
function ligarDinero(input, alCambiar) {
  input.addEventListener("input", () => {
    const pos = input.selectionStart, largo = input.value.length;
    input.value = fmtMiles(input.value);
    input.selectionStart = input.selectionEnd = Math.max(0, input.value.length - (largo - pos));
    alCambiar();
  });
}
function limpiarNombre(txt) {
  let lineas = String(txt || "").split(/\r?\n/).map(s => s.trim())
    .filter(s => s && s.toLowerCase() !== "compartir");
  let n = lineas.join(" ").trim();
  if (n.toLowerCase().startsWith("compartir ")) n = n.slice(10).trim();
  return n;
}
function ligarNombre(input, alCambiar) {
  input.addEventListener("input", alCambiar);
  input.addEventListener("paste", () => setTimeout(() => {
    const limpio = limpiarNombre(input.value);
    if (limpio !== input.value) { input.value = limpio; alCambiar(); }
  }, 1));
}
function contador(alCambiar) {
  const wrap = document.createElement("div"); wrap.className = "contador";
  let n = 1;
  const menos = document.createElement("button"); menos.textContent = "−";
  const span = document.createElement("span"); span.textContent = "1";
  const mas = document.createElement("button"); mas.textContent = "+";
  menos.onclick = () => { if (n > 1) { n--; span.textContent = n; alCambiar(); } };
  mas.onclick = () => { n++; span.textContent = n; alCambiar(); };
  wrap.append(menos, span, mas);
  wrap.getVal = () => n;
  return wrap;
}
function botonX(onclick) {
  const b = document.createElement("button"); b.className = "btn-x"; b.textContent = "✕";
  b.title = "Eliminar"; b.onclick = onclick; return b;
}
function debounce(fn) { let t; return () => { clearTimeout(t); t = setTimeout(fn, DEBOUNCE); }; }

// =====================================================
// RETAIL
// =====================================================
const filasRetail = [];
const calcRetailDeb = debounce(calcularRetail);

function nuevaFilaRetail() {
  const div = document.createElement("div"); div.className = "fila";
  const idx = document.createElement("span"); idx.className = "idx";
  const nombre = document.createElement("input"); nombre.className = "nombre"; nombre.placeholder = "Nombre de la joya";
  const cont = contador(calcRetailDeb);
  const valor = document.createElement("input"); valor.className = "dinero"; valor.placeholder = "Valor unitario"; valor.inputMode = "numeric";
  const linea = document.createElement("div"); linea.className = "fila-linea";
  const x = botonX(() => { div.remove(); filasRetail.splice(filasRetail.indexOf(obj), 1); reindexar(filasRetail); calcularRetail(); });
  linea.append(idx, nombre, cont, valor, x);
  div.append(linea);
  ligarNombre(nombre, calcRetailDeb); ligarDinero(valor, calcRetailDeb);
  const obj = { div, idx, get: () => ({ nombre: nombre.value || "Joya", cantidad: cont.getVal(), valor_unitario: valor.value }),
                vacia: () => !nombre.value.trim() && !valor.value.trim() };
  filasRetail.push(obj);
  $("#filas-retail").append(div);
  reindexar(filasRetail); nombre.focus();
}
function reindexar(arr, etq = "Joya") { arr.forEach((o, i) => o.idx.textContent = `${etq} ${i + 1}`); }

$("#add-retail").onclick = nuevaFilaRetail;
$("#ret-envio-chk").onchange = toggleEnvioRet;
$("#ret-envio-tipo").onchange = () => { toggleEnvioRet(); };
$("#ret-pago").onchange = () => {
  if ($("#ret-pago").value === "Contra Entrega") {
    $("#ret-envio-chk").checked = false; $("#ret-envio-chk").disabled = true;
  } else $("#ret-envio-chk").disabled = false;
  toggleEnvioRet();
};
$("#calc-retail").onclick = calcularRetail;

function toggleEnvioRet() {
  const on = $("#ret-envio-chk").checked;
  $("#ret-envio-tipo").disabled = !on;
  const intl = on && $("#ret-envio-tipo").value === "Internacional";
  $("#ret-envio-manual").style.display = intl ? "" : "none";
  calcRetailDeb();
}

async function calcularRetail() {
  if (filasRetail.every(f => f.vacia())) {
    $("#res-retail").textContent = "💡 Ingrese el nombre y el valor de cada joya.\n\nLa cotización se genera automáticamente mientras escribe.";
    return;
  }
  const body = {
    joyas: filasRetail.filter(f => !f.vacia()).map(f => f.get()),
    medio_pago: $("#ret-pago").value,
    aplicar_envio: $("#ret-envio-chk").checked,
    tipo_envio: $("#ret-envio-tipo").value,
    envio_manual: $("#ret-envio-manual").value,
  };
  const r = await fetch("/api/retail", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json();
  $("#res-retail").textContent = d.error ? "⚠️ " + d.error : d.texto;
}
if (typeof ligarNombre !== "undefined") ligarNombre;  // no-op guard

// =====================================================
// MAYORISTA
// =====================================================
const SUBTIPOS = {
  "Nacional": ["Corriente", "Especial", "Fabricación"],
  "Italiano": ["Recargo +1", "Recargo +2", "Recargo +3", "Recargo +4"],
  "Bolas": ["Lisa contado", "Lisa crédito", "Diamantada contado", "Diamantada crédito"],
};
const filasMay = [], filasOtros = [];
const calcMayDeb = debounce(calcularMayorista);

function nuevaFilaMay() {
  const div = document.createElement("div"); div.className = "fila";
  const l1 = document.createElement("div"); l1.className = "fila-linea";
  const idx = document.createElement("span"); idx.className = "idx";
  const nombre = document.createElement("input"); nombre.className = "nombre"; nombre.placeholder = "Nombre de la joya";
  const cont = contador(calcMayDeb);
  const x = botonX(() => { div.remove(); filasMay.splice(filasMay.indexOf(obj), 1); reindexar(filasMay); calcularMayorista(); });
  l1.append(idx, nombre, cont, x);
  const l2 = document.createElement("div"); l2.className = "fila-linea";
  const peso = document.createElement("input"); peso.className = "peso"; peso.placeholder = "Peso (gr)"; peso.inputMode = "decimal";
  const tipo = document.createElement("select");
  ["Tipo Oro", "Nacional", "Italiano", "Bolas"].forEach(t => tipo.add(new Option(t, t)));
  const sub = document.createElement("select"); sub.add(new Option("Subtipo", "Subtipo"));
  const valor = document.createElement("input"); valor.className = "dinero"; valor.placeholder = "Valor original"; valor.inputMode = "numeric";
  tipo.onchange = () => {
    sub.innerHTML = ""; (SUBTIPOS[tipo.value] || ["Seleccione..."]).forEach(s => sub.add(new Option(s, s)));
    calcMayDeb();
  };
  l2.append(peso, tipo, sub, valor);
  div.append(l1, l2);
  ligarNombre(nombre, calcMayDeb); ligarDinero(valor, calcMayDeb);
  peso.addEventListener("input", () => { peso.value = peso.value.replace(/[^\d.,]/g, ""); calcMayDeb(); });
  const obj = { div, idx, get: () => ({
    nombre: nombre.value || "Joya", cantidad: cont.getVal(), peso: peso.value,
    tipo: tipo.value, subtipo: sub.value, valor_normal: valor.value }) };
  filasMay.push(obj);
  $("#filas-mayorista").append(div);
  reindexar(filasMay); nombre.focus();
}
function nuevaFilaOtro() {
  const div = document.createElement("div"); div.className = "fila";
  const idx = document.createElement("span"); idx.className = "idx";
  const nombre = document.createElement("input"); nombre.className = "nombre"; nombre.placeholder = "Nombre del artículo";
  const cont = contador(calcMayDeb);
  const valor = document.createElement("input"); valor.className = "dinero"; valor.placeholder = "Valor unitario"; valor.inputMode = "numeric";
  const x = botonX(() => { div.remove(); filasOtros.splice(filasOtros.indexOf(obj), 1); reindexar(filasOtros, "Otro"); calcularMayorista(); });
  const linea = document.createElement("div"); linea.className = "fila-linea";
  linea.append(idx, nombre, cont, valor, x); div.append(linea);
  ligarNombre(nombre, calcMayDeb); ligarDinero(valor, calcMayDeb);
  const obj = { div, idx, get: () => ({ nombre: nombre.value || "Extra", cantidad: cont.getVal(), valor_unitario: valor.value }) };
  filasOtros.push(obj);
  $("#filas-otros").append(div);
  reindexar(filasOtros, "Otro"); nombre.focus();
}
$("#add-mayorista").onclick = nuevaFilaMay;
$("#add-otro").onclick = nuevaFilaOtro;
$("#calc-mayorista").onclick = calcularMayorista;
$("#may-envio-chk").onchange = toggleEnvioMay;
$("#may-envio-tipo").onchange = toggleEnvioMay;
$("#actualizar-precios").onclick = actualizarPrecios;

function toggleEnvioMay() {
  const on = $("#may-envio-chk").checked;
  $("#may-envio-tipo").disabled = !on;
  const intl = on && $("#may-envio-tipo").value === "Internacional";
  $("#may-envio-manual").style.display = intl ? "" : "none";
  calcMayDeb();
}

async function calcularMayorista() {
  const body = {
    joyas: filasMay.map(f => f.get()),
    otros: filasOtros.map(f => f.get()).filter(o => o.valor_unitario.trim() || o.nombre !== "Extra"),
    aplicar_envio: $("#may-envio-chk").checked,
    tipo_envio: $("#may-envio-tipo").value,
    envio_manual: $("#may-envio-manual").value,
  };
  const r = await fetch("/api/mayorista", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json();
  $("#aviso-incompletas").textContent = d.incompletas ? `⚠️ ${d.incompletas} joya(s) sin tipo/subtipo/peso — no incluidas` : "";
  if (d.error) $("#res-mayorista").textContent = "⚠️ " + d.error;
  else if (!d.texto) $("#res-mayorista").textContent = "💡 Agregue joyas con peso, tipo y subtipo de oro.";
  else $("#res-mayorista").textContent = d.texto;
}

async function actualizarPrecios() {
  const btns = $$("#actualizar-precios, #actualizar-tienda");
  btns.forEach(b => { b.disabled = true; b.textContent = "Conectando…"; });
  $("#estado-precios").textContent = "⏳ Conectando con Google Sheets…";
  $("#estado-tienda").textContent = "⏳ Conectando con Google Sheets…";
  try {
    const d = await (await fetch("/api/actualizar-precios", { method: "POST" })).json();
    if (d.error) {
      $("#estado-precios").textContent = "❌ " + d.error;
      $("#estado-tienda").textContent = "❌ " + d.error;
    } else {
      $("#estado-precios").textContent = `Precios actualizados: ${d.hora}`;
      $("#estado-tienda").textContent = `Precios actualizados: ${d.hora}`;
      const falt = d.tarifas_faltantes || [];
      $("#aviso-tarifas").style.display = falt.length ? "" : "none";
      $("#aviso-tarifas").textContent = falt.length ? "⚠️ Tarifas sin valor en el Sheet: " + falt.join(", ") : "";
      poblarCalidadesTienda(d.calidades_tienda || []);
      calcularMayorista();
    }
  } finally { btns.forEach(b => { b.disabled = false; b.textContent = "Actualizar precios"; }); }
}

// =====================================================
// VALOR TIENDA
// =====================================================
const calcTiendaDeb = debounce(calcularTienda);

$("#actualizar-tienda").onclick = actualizarPrecios;
$("#tienda-peso").addEventListener("input", () => {
  $("#tienda-peso").value = $("#tienda-peso").value.replace(/[^\d.,]/g, "");
  calcTiendaDeb();
});
$("#tienda-calidad").onchange = calcTiendaDeb;

function poblarCalidadesTienda(calidades) {
  const sel = $("#tienda-calidad");
  const actual = sel.value;
  sel.innerHTML = "";
  if (!calidades.length) { sel.add(new Option("Sin datos", "")); return; }
  calidades.forEach(c => sel.add(new Option(c, c)));
  if (calidades.includes(actual)) sel.value = actual;
  calcTiendaDeb();
}

function fmtPesos(n) { return `$${n.toLocaleString("es-CO").replace(/,/g, ".")}`; }

async function calcularTienda() {
  const peso = $("#tienda-peso").value.trim();
  const calidad = $("#tienda-calidad").value;
  const criterio = $("#criterio-tienda");
  if (!peso || !calidad) {
    $("#res-tienda").textContent = "Ingrese peso y tipo de material.";
    criterio.style.display = "none";
    return;
  }
  const r = await fetch("/api/precio-tienda", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ peso, calidad }),
  });
  const d = await r.json();
  if (d.error) {
    $("#res-tienda").textContent = "⚠️ " + d.error;
    criterio.style.display = "none";
    return;
  }
  $("#res-tienda").textContent = fmtPesos(d.precio);
  criterio.style.display = "";
  criterio.textContent = `Precio por gramo: ${fmtPesos(d.valor_gr)} — ${calidad}, rango ${d.rango}`;
}

// =====================================================
// TABLA DE PRECIOS (canvas)
// =====================================================
let tablaCargada = null;
$("#actualizar-tabla").onclick = cargarTabla;

async function cargarTabla() {
  $("#estado-tabla").textContent = "⏳ Descargando tabla…";
  const d = await (await fetch("/api/tabla")).json();
  if (d.error) { $("#estado-tabla").textContent = "❌ " + d.error; return; }
  tablaCargada = d.bloques;
  dibujarTabla(d.bloques);
  $("#estado-tabla").textContent = "✅ Tabla actualizada · los precios cambian con el oro.";
}

function adaptarColor(bg, fg, oscuro) {
  if (!oscuro) return [bg, fg, bg === "#000000" ? "#000000" : "#D9D9D9"];
  const r = parseInt(bg.slice(1, 3), 16), g = parseInt(bg.slice(3, 5), 16), b = parseInt(bg.slice(5, 7), 16);
  if (r >= 235 && g >= 235 && b >= 235) return ["#232323", "#E6E6E6", "#3A3A3A"];
  if (r <= 20 && g <= 20 && b <= 20) return ["#000000", fg, "#000000"];
  return [bg, fg, "#3A3A3A"];
}

function dibujarTabla(bloques) {
  const oscuro = document.documentElement.dataset.tema === "dark";
  const cv = $("#canvas-tabla"), ctx = cv.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  let anchoMax = 0, altoMax = 0;
  bloques.forEach(b => {
    const w = b.col_px.reduce((a, x) => a + x, 0), h = b.row_px.reduce((a, x) => a + x, 0);
    anchoMax = Math.max(anchoMax, b.x0 + w); altoMax = Math.max(altoMax, b.y0 + h);
  });
  cv.width = (anchoMax + 8) * dpr; cv.height = (altoMax + 8) * dpr;
  cv.style.width = (anchoMax + 8) + "px"; cv.style.height = (altoMax + 8) + "px";
  ctx.scale(dpr, dpr);
  ctx.fillStyle = oscuro ? "#232323" : "#FFFFFF";
  ctx.fillRect(0, 0, anchoMax + 8, altoMax + 8);
  ctx.textBaseline = "middle";

  bloques.forEach(b => {
    const xs = [b.x0]; b.col_px.forEach(w => xs.push(xs[xs.length - 1] + w));
    const ys = [b.y0]; b.row_px.forEach(h => ys.push(ys[ys.length - 1] + h));
    const nc = b.col_px.length, nr = b.row_px.length;
    b.cells.forEach(c => {
      const x0 = xs[c.c], y0 = ys[c.r];
      const x1 = xs[Math.min(c.c + c.cs, nc)], y1 = ys[Math.min(c.r + c.rs, nr)];
      const [bg, fg, borde] = adaptarColor(c.bg, c.fg, oscuro);
      ctx.fillStyle = bg; ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      ctx.strokeStyle = borde; ctx.lineWidth = 1; ctx.strokeRect(x0 + .5, y0 + .5, x1 - x0 - 1, y1 - y0 - 1);
      if (!c.texto) return;
      ctx.fillStyle = fg;
      ctx.font = `${c.bold ? "bold " : ""}${Math.max(9, (c.tam || 10))}px ${getComputedStyle(document.body).fontFamily}`;
      ctx.textAlign = c.align === "LEFT" ? "left" : c.align === "RIGHT" ? "right" : "center";
      const tx = c.align === "LEFT" ? x0 + 5 : c.align === "RIGHT" ? x1 - 5 : (x0 + x1) / 2;
      ctx.save(); ctx.beginPath(); ctx.rect(x0, y0, x1 - x0, y1 - y0); ctx.clip();
      ctx.fillText(c.texto, tx, (y0 + y1) / 2); ctx.restore();
    });
  });
}

// =====================================================
// COPIAR AL PORTAPAPELES
// =====================================================
$$(".btn-copiar").forEach(btn => {
  btn.addEventListener("click", async () => {
    const el = $("#" + btn.dataset.target);
    const texto = (el.innerText ?? el.textContent ?? "").trim();
    if (!texto) return;
    try {
      await navigator.clipboard.writeText(texto);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = texto; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.append(ta); ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    const original = btn.textContent;
    btn.textContent = "¡Copiado!";
    setTimeout(() => { btn.textContent = original; }, 1500);
  });
});

// =====================================================
// CRÉDITOS OCULTOS (doble clic en el título)
// =====================================================
$("#titulo-app").addEventListener("dblclick", () => {
  const c = $("#creditos"); c.hidden = !c.hidden;
});

// =====================================================
// ACCESO POR PIN
// =====================================================
// Interceptor: cualquier respuesta 401 de un endpoint de datos (p. ej. tras
// reiniciarse el servidor y caducar la sesión) vuelve a mostrar la pantalla
// de PIN, sin importar desde qué parte de la app se disparó la petición.
const _fetch = window.fetch.bind(window);
window.fetch = async (url, opts) => {
  const resp = await _fetch(url, opts);
  const u = String(url);
  if (resp.status === 401 && !u.includes("/api/acceso") && !u.includes("/api/sesion")) {
    mostrarGate();
  }
  return resp;
};

const gate = $("#gate");
let gateTimer = null;

function mostrarGate() {
  gate.hidden = false;
  $("#gate-cargando").hidden = true;
  $("#gate-form").hidden = false;
  const pin = $("#gate-pin");
  pin.disabled = false; $("#gate-ok").disabled = false;
  pin.value = ""; pin.focus();
}
function ocultarGate() { clearInterval(gateTimer); gate.hidden = true; }

async function comprobarSesion() {
  try {
    const d = await _fetch("/api/sesion").then(r => r.json());
    if (d.autorizado) { ocultarGate(); iniciarApp(); aplicarRol(d.rol || ""); }
    else mostrarGate();
  } catch { mostrarGate(); }
}

async function enviarPin() {
  const pin = $("#gate-pin");
  const msg = $("#gate-msg");
  if (pin.disabled) return;
  const valor = pin.value.trim();
  if (valor.length < 4) { msg.textContent = "Ingrese los 4 dígitos."; return; }
  $("#gate-ok").disabled = true;
  try {
    const r = await _fetch("/api/acceso", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin: valor }),
    });
    const d = await r.json();
    if (r.ok && d.ok) { msg.textContent = ""; ocultarGate(); iniciarApp(); aplicarRol(d.rol || ""); return; }
    pin.value = "";
    if (d.espera && d.espera > 0) cuentaRegresiva(d.espera, d.error === "bloqueado");
    else { msg.textContent = "PIN incorrecto. Intente de nuevo."; $("#gate-ok").disabled = false; pin.focus(); }
  } catch {
    msg.textContent = "Error de conexión. Reintente.";
    $("#gate-ok").disabled = false;
  }
}

function cuentaRegresiva(seg, bloqueado) {
  const msg = $("#gate-msg"), pin = $("#gate-pin");
  $("#gate-ok").disabled = true; pin.disabled = true;
  clearInterval(gateTimer);
  let restante = seg;
  const pintar = () => {
    msg.textContent = (bloqueado ? "Demasiados intentos. " : "PIN incorrecto. ") + `Espere ${restante}s.`;
  };
  pintar();
  gateTimer = setInterval(() => {
    if (--restante <= 0) {
      clearInterval(gateTimer);
      msg.textContent = ""; pin.disabled = false; $("#gate-ok").disabled = false; pin.focus();
    } else pintar();
  }, 1000);
}

$("#gate-ok").onclick = enviarPin;
$("#gate-pin").addEventListener("input", () => {
  const pin = $("#gate-pin");
  pin.value = pin.value.replace(/\D/g, "");
  if (pin.value.length === 4) enviarPin();  // auto-enviar al completar 4 dígitos
});
$("#gate-pin").addEventListener("keydown", e => { if (e.key === "Enter") enviarPin(); });

// =====================================================
// PANEL DE TURNOS Y COBERTURA
// Vive fuera de la calculadora. Envía una señal de presencia (para que soporte
// sepa quién está atendiendo) y muestra a quién hay que cubrir según la hora.
// =====================================================
const YO_KEY = "turnos_yo";
// 8s: se siente "en vivo" sin necesitar websockets — lo que lee viene de la
// base de datos local (novedades, presencia, equipo), no de Sheets, así que
// no hay costo de cuota por refrescar seguido.
const REFRESCO_PANEL_MS = 8000;
const LATIDO_MS = 180000;          // cada cuánto se envía la señal de presencia
let panelTimer = null, latidoTimer = null;

function yoNombre() { return localStorage.getItem(YO_KEY) || ""; }

// La calculadora queda bloqueada hasta que la persona elija "Soy:" y "Estoy:".
// "Soy:" se recuerda entre sesiones (localStorage); "Estoy:" se vuelve a pedir
// en cada carga fresca de la página, para que el estado reflejado sea el de
// ahora, no el de la última vez que se abrió el navegador.
let estoyConfirmado = false;
function identificado() { return esJefa || (!!yoNombre() && estoyConfirmado); }
function actualizarBloqueo() {
  const ok = identificado();
  $("#app-principal").classList.toggle("bloqueado", !ok);
  $("#app-bloqueo").hidden = ok;
}

function el(tag, cls, txt) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
}

function pintarLista(cont, items, hacerItem) {
  cont.innerHTML = "";
  if (!items || !items.length) {
    cont.append(el("div", "panel-vacio", "— nadie —"));
    return;
  }
  items.forEach(x => cont.append(hacerItem(x)));
}

function itemBase(x, color) {
  const d = el("div", "panel-item " + color);
  d.append(el("span", "nom", x.nombre));
  if (x.turno) d.append(el("span", "tag", "T" + x.turno));
  if (x.etiqueta) d.append(el("span", "tag", x.etiqueta));
  // Marca de ajuste: explica por qué el panel dice algo distinto al cuadro
  if (x.ajuste) d.append(el("span", "tag azul", "✎ " + x.ajuste));
  return d;
}

// Muestra el campo que pide cada tipo de ajuste (turno, hora, o ninguno)
function pintarCamposAjuste() {
  const o = $("#aj-tipo").selectedOptions[0];
  const pide = o ? (o.dataset.pide || "") : "";
  $("#aj-turno").hidden = pide !== "turno";
  $("#aj-hora").hidden = pide !== "hora";
}

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

function renderPanel(d) {
  rolesActual = d.roles || {};
  pedirPermisoNotificacion();
  refrescarSello();
  revisarAvisos(d);
  $("#panel-semana").textContent =
    d.semana + (d.fuente === "equipo" ? " · usando equipo de la app" : "");

  if (!d.configurado) {
    const av = $("#panel-aviso");
    av.hidden = false;
    av.textContent = "⚠️ " + (d.aviso || "Horario de turnos no configurado todavía.");
  } else {
    $("#panel-aviso").hidden = true;
  }

  const cob = d.requieren_cobertura || [];
  const aus = d.ausencia_informada || [];
  $("#n-cob").textContent = cob.length ? `(${cob.length})` : "";
  $("#n-aus").textContent = aus.length ? `(${aus.length})` : "";
  $("#n-linea").textContent = (d.en_linea || []).length ? `(${d.en_linea.length})` : "";

  // Estados posibles en el selector "Estoy:" — se compara la firma para que,
  // si la jefa cambia la lista, quien ya tenía el panel abierto la vea sin
  // tener que recargar la página (antes solo se llenaba una vez, la primera).
  const selEst = $("#mi-estado");
  const firmaEst = (d.estados_posibles || []).map(e => e.clave).join("|");
  if (selEst.dataset.firma !== firmaEst) {
    const valorEst = selEst.value;
    selEst.innerHTML = "";
    selEst.add(new Option("— elige tu estado —", ""));
    (d.estados_posibles || []).forEach(e => selEst.add(new Option(e.etiqueta, e.clave)));
    selEst.value = valorEst;
    selEst.dataset.firma = firmaEst;
  }
  $("#fila-mi-estado").hidden = !yoNombre();
  actualizarBloqueo();

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

  pintarLista($("#lista-ausencia"), aus, x => {
    // Sede presencial (zona presencial, Santa Fe, El Tesoro, Mostrador…): la
    // persona está trabajando, pero sus chats quedaron sin atender por
    // prioridad de cliente presencial — se resalta distinto de una ausencia.
    const d2 = itemBase(x, x.sede ? "morado" : x.turno_terminado ? "azul" : "amarillo");
    let det = x.estado_etq
      ? `${x.estado_etq}${x.desde_estado ? " desde " + x.desde_estado : ` · turno ${x.desde}-${x.hasta}`}`
      : "";
    if (x.novedad) det = `${x.novedad}${x.nota ? " · " + x.nota : ""}`;
    if (x.sede) det = "🏬 " + det + " · sus chats quedan libres";
    d2.append(el("span", "det", det));
    d2.append(botonCubrir(x));
    return d2;
  });

  // Ajustes de hoy: lo que rige por encima del plan de la semana
  const ajs = d.ajustes || [];
  $("#n-ajustes").textContent = ajs.length ? `(${ajs.length})` : "";
  pintarLista($("#lista-ajustes"), ajs, x => {
    const it = el("div", "panel-item azul");
    const quitar = el("button", "panel-quitar", "✕");
    quitar.title = "Deshacer el ajuste";
    quitar.onclick = async () => {
      await fetch("/api/turnos/ajuste/quitar", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nombre: x.nombre, tipo: x.tipo }),
      });
      cargarTurnos();
    };
    it.append(quitar);
    it.append(el("span", "nom", x.nombre));
    it.append(el("span", "tag", x.etiqueta));
    const partes = [];
    if (x.turno) partes.push("turno " + x.turno);
    if (x.hora) partes.push("entra " + x.hora);
    if (x.nota) partes.push(x.nota);
    if (x.autor) partes.push("por " + x.autor);
    it.append(el("span", "det", partes.join(" · ")));
    return it;
  });

  // Tipos de ajuste en el formulario (misma comparación de firma que arriba)
  const selTipo = $("#aj-tipo");
  const firmaAjTipo = (d.tipos_ajuste || []).map(t => t.clave).join("|");
  if (selTipo.dataset.firma !== firmaAjTipo) {
    const valorAjTipo = selTipo.value;
    selTipo.innerHTML = "";
    (d.tipos_ajuste || []).forEach(t => {
      const o = new Option(t.etiqueta, t.clave);
      o.dataset.pide = t.pide || "";
      selTipo.add(o);
    });
    selTipo.value = valorAjTipo;
    selTipo.dataset.firma = firmaAjTipo;
    pintarCamposAjuste();
  }

  // Tipos de novedad en el formulario
  const selNov = $("#nov-tipo");
  const firmaNov = (d.tipos_novedad || []).join("|");
  if (selNov.dataset.firma !== firmaNov) {
    const valorNov = selNov.value;
    selNov.innerHTML = "";
    (d.tipos_novedad || []).forEach(t => selNov.add(new Option(t, t)));
    selNov.value = valorNov;
    selNov.dataset.firma = firmaNov;
  }

  pintarLista($("#lista-novedades"), d.novedades, x => {
    const d2 = el("div", "panel-item amarillo");
    const quitar = el("button", "panel-quitar", "✕");
    quitar.title = "Quitar novedad";
    quitar.onclick = () => quitarNovedad(x.nombre, x.tipo);
    d2.append(quitar);
    d2.append(el("span", "nom", x.nombre));
    d2.append(el("span", "tag", x.tipo));
    let det = x.hora || "";
    if (x.nota) det += " · " + x.nota;
    if (x.reportado_por) det += " · reportó " + x.reportado_por;
    d2.append(el("span", "det", det));
    return d2;
  });

  pintarLista($("#lista-linea"), d.en_linea, x => {
    const d2 = itemBase(x, "verde");
    const m = x.min_sin_senal;
    d2.append(el("span", "det", m === null || m === undefined
      ? "activa" : (m <= 1 ? "activa ahora" : `activa hace ${m} min`)));
    return d2;
  });

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

  // Selectores de personas (conservando lo ya elegido). Se compara la lista
  // completa (no solo la cantidad) para no perder altas/bajas cuando el total
  // coincide por casualidad con el de antes.
  const personas = d.personas || [];
  const firmaPersonas = personas.join("|");
  [["#panel-yo-sel", yoNombre(), "— elige tu nombre —"],
   ["#nov-nombre", $("#nov-nombre").value || yoNombre(), "— ¿de quién? —"],
   ["#aj-nombre", $("#aj-nombre").value, "— ¿a quién? —"]
  ].forEach(([sel, valor, ph]) => {
    const s = $(sel);
    if (s.dataset.firma === firmaPersonas && s.options.length > 1) {
      s.value = valor || "";
      return;
    }
    s.innerHTML = "";
    s.add(new Option(ph, ""));
    personas.forEach(p => s.add(new Option(p, p)));
    s.value = valor || "";
    s.dataset.firma = firmaPersonas;
  });
}

async function cargarTurnos() {
  try {
    const r = await fetch("/api/turnos/estado");
    if (!r.ok) return;
    renderPanel(await r.json());
  } catch (e) { /* sin conexión: se reintenta en el próximo ciclo */ }
}

async function enviarPresencia() {
  const nombre = yoNombre();
  if (!nombre) return;
  try {
    await fetch("/api/turnos/presencia", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre }),
    });
  } catch (e) { /* se reintenta con el próximo latido */ }
}

async function quitarNovedad(nombre, tipo) {
  await fetch("/api/turnos/novedad/quitar", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nombre, tipo }),
  });
  cargarTurnos();
}

// =====================================================
// AVISO SONORO
// El problema original era que soporte no se daba cuenta. Un contador rojo no
// sirve si nadie mira la pantalla, así que suena cuando aparece algo nuevo que
// exige acción: una novedad importante o alguien que se queda sin cubrir.
// =====================================================
const MUDO_KEY = "turnos_mudo";
let novVistas = null;          // ids de novedades ya avisadas
let cobVistas = null;          // nombres ya avisados como sin cubrir
let tituloOriginal = document.title;
let parpadeo = null;
let repiqueCobertura = null;   // pitido cada 1 min mientras alguien siga sin cubrir (solo soporte)

function estaMudo() { return localStorage.getItem(MUDO_KEY) === "1"; }

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

function sonar(doble) {
  if (estaMudo()) return;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    const tonos = doble ? [880, 1175] : [880];   // dos notas si es importante
    tonos.forEach((hz, i) => {
      const t0 = ctx.currentTime + i * 0.18;
      const osc = ctx.createOscillator(), vol = ctx.createGain();
      osc.type = "sine"; osc.frequency.value = hz;
      vol.gain.setValueAtTime(0.0001, t0);
      vol.gain.exponentialRampToValueAtTime(0.25, t0 + 0.02);
      vol.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.16);
      osc.connect(vol); vol.connect(ctx.destination);
      osc.start(t0); osc.stop(t0 + 0.18);
    });
    setTimeout(() => ctx.close(), 900);
  } catch (e) { /* si el navegador lo bloquea, queda el aviso visual */ }
}

// Con la pestaña en segundo plano el pitido puede pasar desapercibido: el
// título parpadea hasta que el usuario vuelve.
function avisarEnTitulo(texto) {
  clearInterval(parpadeo);
  let on = false;
  parpadeo = setInterval(() => {
    document.title = on ? tituloOriginal : texto;
    on = !on;
  }, 1000);
  const parar = () => {
    if (document.hidden) return;
    clearInterval(parpadeo); parpadeo = null;
    document.title = tituloOriginal;
    document.removeEventListener("visibilitychange", parar);
  };
  document.addEventListener("visibilitychange", parar);
  if (!document.hidden) setTimeout(parar, 8000);
}

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

// --- Sello de fecha y hora del servidor (imagen, no texto editable) ---
function refrescarSello() {
  const img = $("#panel-sello");
  if (!img) return;
  const tema = document.documentElement.dataset.tema === "light" ? "light" : "dark";
  img.src = `/api/reloj.png?t=${tema}&_=${Date.now()}`;   // _ evita la caché
}

// --- Equipo: la jefa registra a su gente (sin depender de la hoja de Sheets) ---
async function cargarEquipo() {
  if (!esJefa) return;
  try {
    const r = await fetch("/api/equipo/gestion");
    if (!r.ok) return;
    const d = await r.json();
    const selRol = $("#per-rol");
    if (selRol.options.length === 0) {
      (d.roles || []).forEach(x => selRol.add(new Option(x, x)));
    }
    pintarLista($("#lista-equipo"), d.personas, p => {
      const it = el("div", "panel-item" + (p.activa ? "" : " inactiva"));
      // El área es muy rotativa: quitar solo desactiva (el historial se
      // conserva) y se puede volver a activar con el mismo botón.
      const quitar = el("button", "panel-quitar", p.activa ? "✕" : "↺");
      quitar.title = p.activa ? "Quitar del equipo" : "Volver a activar";
      quitar.onclick = async () => {
        const ruta = p.activa ? "/api/equipo/quitar" : "/api/equipo/guardar";
        const cuerpo = p.activa
          ? { nombre: p.nombre }
          : { nombre: p.nombre, rol: p.rol, turno: p.turno, activa: true };
        await fetch(ruta, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(cuerpo),
        });
        cargarEquipo(); cargarTurnos();
      };
      it.append(quitar);
      it.append(el("span", "nom", p.nombre));
      it.append(el("span", "tag", "T" + p.turno));
      it.append(el("span", "det", p.rol + (p.activa ? "" : " · inactiva")));
      it.onclick = e => {                       // clic para editar
        if (e.target === quitar) return;
        $("#per-nombre").value = p.nombre;
        $("#per-rol").value = p.rol;
        $("#per-turno").value = String(p.turno);
      };
      return it;
    });
  } catch (e) { /* reintenta al abrir de nuevo */ }
}

async function guardarPersona() {
  const nombre = $("#per-nombre").value.trim();
  if (!nombre) { $("#per-nombre").focus(); return; }
  const r = await fetch("/api/equipo/guardar", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      nombre, rol: $("#per-rol").value,
      turno: Number($("#per-turno").value), activa: true,
    }),
  });
  if (r.ok) {
    $("#per-nombre").value = "";
    cargarEquipo();
    cargarTurnos();          // el horario se rearma con el equipo nuevo
  }
}

// --- Vista de gestión: solo aparece con el PIN de la jefa de ventas ---
let esJefa = false;

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

async function cargarGestion() {
  if (!esJefa) return;
  try {
    const r = await fetch("/api/gestion/resumen");
    if (!r.ok) return;
    const d = await r.json();
    const t = d.totales || {};
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
  } catch (e) { /* se reintenta al pulsar Actualizar */ }
}

function aplicarRol(rol) {
  esJefa = rol === "jefa";
  $("#sec-gestion").hidden = !esJefa;
  $("#sec-equipo").hidden = !esJefa;
  if (esJefa) { cargarGestion(); cargarEquipo(); }
  actualizarBloqueo();   // la jefa no necesita Soy:/Estoy: para usar la calculadora
}

function iniciarPanelTurnos() {
  $("#panel-yo-sel").onchange = e => {
    const v = e.target.value;
    if (v) localStorage.setItem(YO_KEY, v); else localStorage.removeItem(YO_KEY);
    $("#nov-nombre").value = v;
    $("#fila-mi-estado").hidden = !v;
    if (!v) estoyConfirmado = false;      // cambió de identidad: hay que reconfirmar "Estoy:"
    actualizarBloqueo();
    enviarPresencia().then(cargarTurnos);
  };

  // "Estoy:" — el asesor dice en qué está, así soporte no lo confunde con una
  // ausencia sin explicación. También es lo que desbloquea la calculadora.
  $("#mi-estado").onchange = async e => {
    const nombre = yoNombre();
    if (!nombre || !e.target.value) return;
    estoyConfirmado = true;
    actualizarBloqueo();
    await fetch("/api/turnos/estado-asesor", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre, estado: e.target.value }),
    });
    cargarTurnos();
  };

  $("#btn-gestion-refrescar").onclick = cargarGestion;
  $("#per-guardar").onclick = guardarPersona;
  $("#per-nombre").addEventListener("keydown", e => { if (e.key === "Enter") guardarPersona(); });

  // Silenciar / reactivar el aviso sonoro (queda guardado en el navegador)
  const pintarMudo = () => {
    const b = $("#btn-mudo");
    b.textContent = estaMudo() ? "🔕" : "🔔";
    b.title = estaMudo() ? "Aviso sonoro silenciado" : "Silenciar el aviso sonoro";
  };
  $("#btn-mudo").onclick = () => {
    localStorage.setItem(MUDO_KEY, estaMudo() ? "0" : "1");
    pintarMudo();
    if (!estaMudo()) sonar(false);        // prueba de sonido al reactivar
  };
  pintarMudo();

  // Salir: sin esto, quien entró con un PIN no podía cambiar de rol en 7 días.
  $("#btn-salir").onclick = async () => {
    await fetch("/api/salir", { method: "POST" });
    localStorage.removeItem(YO_KEY);
    location.reload();
  };

  // --- Ajustes del día ---
  $("#btn-abrir-ajuste").onclick = () => {
    const f = $("#form-ajuste");
    f.hidden = !f.hidden;
    if (!f.hidden) pintarCamposAjuste();
  };
  $("#aj-tipo").onchange = pintarCamposAjuste;
  $("#aj-cancelar").onclick = () => {
    $("#form-ajuste").hidden = true;
    $("#aj-nota").value = ""; $("#aj-hora").value = "";
  };
  alClic($("#aj-guardar"), async () => {
    const nombre = $("#aj-nombre").value;
    if (!nombre) { $("#aj-nombre").focus(); return; }
    const o = $("#aj-tipo").selectedOptions[0];
    const pide = o ? (o.dataset.pide || "") : "";
    const cuerpo = {
      nombre, tipo: $("#aj-tipo").value, nota: $("#aj-nota").value,
      autor: yoNombre(),
    };
    if (pide === "turno") cuerpo.turno = Number($("#aj-turno").value);
    if (pide === "hora") {
      const h = $("#aj-hora").value.trim();
      if (!/^\d{1,2}:\d{2}$/.test(h)) { $("#aj-hora").focus(); return; }
      cuerpo.hora = h;
    }
    const r = await fetch("/api/turnos/ajuste", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    const d = await r.json();
    if (d.error) { alert(d.error); return; }
    $("#aj-nota").value = ""; $("#aj-hora").value = "";
    $("#form-ajuste").hidden = true;
    cargarTurnos();
  });

  $("#btn-abrir-novedad").onclick = () => {
    const f = $("#form-novedad");
    f.hidden = !f.hidden;
    if (!f.hidden && !$("#nov-nombre").value) $("#nov-nombre").value = yoNombre();
  };
  $("#nov-cancelar").onclick = () => { $("#form-novedad").hidden = true; $("#nov-nota").value = ""; };
  alClic($("#nov-guardar"), async () => {
    const nombre = $("#nov-nombre").value;
    if (!nombre) { $("#nov-nombre").focus(); return; }
    await fetch("/api/turnos/novedad", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nombre, tipo: $("#nov-tipo").value, nota: $("#nov-nota").value,
        reportado_por: yoNombre(),
      }),
    });
    $("#nov-nota").value = "";
    $("#form-novedad").hidden = true;
    cargarTurnos();
  });

  // Presencia automática: al abrir la calculadora y luego cada pocos minutos.
  enviarPresencia();
  cargarTurnos();
  clearInterval(panelTimer); clearInterval(latidoTimer);
  panelTimer = setInterval(cargarTurnos, REFRESCO_PANEL_MS);
  latidoTimer = setInterval(enviarPresencia, LATIDO_MS);

  // Al volver a la pestaña, refrescar de inmediato.
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) { enviarPresencia(); cargarTurnos(); }
  });

  // Al cerrar la pestaña o el navegador, marcar "Desconectado". sendBeacon
  // (no fetch) porque el navegador puede matar una petición normal antes de
  // que termine durante el cierre; sendBeacon está pensado justo para esto.
  window.addEventListener("pagehide", () => {
    const nombre = yoNombre();
    if (!nombre) return;
    const body = new Blob([JSON.stringify({ nombre, estado: "desconectado" })],
                           { type: "application/json" });
    navigator.sendBeacon("/api/turnos/estado-asesor", body);
  });
}

// =====================================================
// INICIO
// =====================================================
let appIniciada = false;

function iniciarApp() {
  if (!appIniciada) {
    appIniciada = true;
    nuevaFilaRetail(); calcularRetail();
    nuevaFilaMay();
    iniciarPanelTurnos();
  }
  cargarEstadoPrecios();
}

async function cargarEstadoPrecios() {
  const r = await fetch("/api/estado-precios");
  if (!r.ok) return;  // el interceptor ya mostró la pantalla de PIN
  const e = await r.json();
  if (e.cargado) {
    $("#estado-precios").textContent = `Precios actualizados: ${e.hora}`;
    $("#estado-tienda").textContent = `Precios actualizados: ${e.hora}`;
    const falt = e.tarifas_faltantes || [];
    if (falt.length) { $("#aviso-tarifas").style.display = ""; $("#aviso-tarifas").textContent = "⚠️ Tarifas sin valor: " + falt.join(", "); }
    poblarCalidadesTienda(e.calidades_tienda || []);
    calcularMayorista();
  } else {
    $("#estado-precios").textContent = "⚠️ Precios no cargados. Presione 'Actualizar precios'.";
    $("#estado-tienda").textContent = "⚠️ Precios no cargados. Presione 'Actualizar precios'.";
  }
}

aplicarTema(localStorage.getItem("tema") || "dark");
comprobarSesion();
