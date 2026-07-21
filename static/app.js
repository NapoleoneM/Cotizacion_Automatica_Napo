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
  $("#logo").src = t === "light" ? "/img/logo_negro.png" : "/img/logo_blanco.png";
  localStorage.setItem("tema", t);
  if (tablaCargada) dibujarTabla(tablaCargada);  // repintar con colores del tema
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
    $("#res-tienda").textContent = "Ingrese peso y calidad.";
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
// INICIO
// =====================================================
aplicarTema(localStorage.getItem("tema") || "dark");
nuevaFilaRetail(); calcularRetail();
nuevaFilaMay();
(async () => {
  const e = await (await fetch("/api/estado-precios")).json();
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
})();
