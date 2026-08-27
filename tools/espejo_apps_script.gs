/**
 * Apps Script que mantiene el documento ESPEJO desde el CORE.
 *
 * NO corre en el servidor: vive en el editor de Apps Script del documento
 * CORE ("Extensiones → Apps Script"). Esta copia está en el repo solo para
 * tenerlo versionado y poder revisarlo junto al código que lo consume; si lo
 * editas allá, pega el cambio acá también.
 *
 * Por qué existe el espejo: el service account que va empaquetado con la
 * calculadora solo tiene acceso a ESTE documento, nunca al CORE. Así una
 * filtración de la credencial no expone las hojas confidenciales.
 *
 * La calculadora lee de aquí:
 *   - "Tablas"        → la tabla de precios que se dibuja en la app, CON su
 *                       formato (colores, negritas, celdas combinadas y
 *                       formato de número). La app usa `formattedValue`, así
 *                       que el formato de número de ESTA hoja es lo que el
 *                       usuario ve.
 *   - "pricing_gramo" → tarifas por gramo (Valor Tienda y datos de bodega).
 */
const CORE_ID   = '1WY_oSWf5QNHdSe1--MPamMUrrHwZ6kYYPHwV06qKkNk';
const ESPEJO_ID = '1S7L7oXZRfMCo6m_QSuzEH2eoIppu91xM_34NIWy5Cnc';

function copiarHojaCompleta(nombreHoja) {
  var origen = SpreadsheetApp.openById(CORE_ID).getSheetByName(nombreHoja);
  if (!origen) throw new Error('No existe la hoja "' + nombreHoja + '" en el CORE');

  var libroDestino = SpreadsheetApp.openById(ESPEJO_ID);
  var anterior = libroDestino.getSheetByName(nombreHoja);

  // Duplica estructura y formato completos (Sheet.copyTo sí permite cruzar
  // de libro, a diferencia de Range.copyTo).
  var nueva = origen.copyTo(libroDestino);

  // Obliga a Google a materializar la copia antes de escribir encima. Sin
  // este flush, el setValues de abajo llegaba a competir con el copyTo y el
  // formato de número se perdía en parte de las celdas — de forma
  // inconsistente, que es lo que hacía difícil de ver el problema: 88 de 151
  // celdas de moneda quedaban sin formato y la app mostraba "630000" donde el
  // CORE dice "$630.000".
  SpreadsheetApp.flush();

  var rango = origen.getDataRange();
  var destino = nueva.getRange(1, 1, rango.getNumRows(), rango.getNumColumns());

  // OJO: al duplicar, las fórmulas quedan pegadas tal cual y Google las
  // evalúa DENTRO del libro espejo. Si una fórmula del core apunta a otra
  // pestaña que no existe aquí, el resultado es #REF!; y peor, si apunta a
  // una que SÍ existe acá (pricing_gramo), recalcularía contra la copia vieja.
  // Por eso los valores se toman del ORIGEN (donde sí resuelven bien) y se
  // pegan encima de las fórmulas ya copiadas.
  destino.setValues(rango.getValues());

  // Y se reponen los formatos de número DESDE EL ORIGEN, en vez de confiar en
  // los que trajo el copyTo. Es lo que garantiza que el espejo muestre
  // "$630.000" y no "630000": la app dibuja el texto que ve la hoja.
  destino.setNumberFormats(rango.getNumberFormats());

  SpreadsheetApp.flush();

  // El borrado y el renombrado van al final a propósito: si algo falla antes,
  // el espejo se queda con la hoja anterior intacta (y una copia suelta que
  // se puede borrar a mano) en vez de quedarse sin la hoja que la app lee.
  if (anterior) libroDestino.deleteSheet(anterior);
  nueva.setName(nombreHoja);
}

/** Comprueba que el espejo quedó con el mismo texto visible que el CORE.
 *  Recorre las celdas y avisa de las que no coinciden — sirve para verificar
 *  después de actualizar, sin tener que comparar a ojo. */
function verificarEspejo(nombreHoja) {
  var origen = SpreadsheetApp.openById(CORE_ID).getSheetByName(nombreHoja);
  var copia = SpreadsheetApp.openById(ESPEJO_ID).getSheetByName(nombreHoja);
  var r = origen.getDataRange();
  var a = origen.getRange(1, 1, r.getNumRows(), r.getNumColumns()).getDisplayValues();
  var b = copia.getRange(1, 1, r.getNumRows(), r.getNumColumns()).getDisplayValues();

  var diferencias = [];
  for (var i = 0; i < a.length; i++) {
    for (var j = 0; j < a[i].length; j++) {
      if (a[i][j] !== b[i][j]) {
        diferencias.push('  fila ' + (i + 1) + ' col ' + (j + 1) +
                         ': CORE "' + a[i][j] + '" vs espejo "' + b[i][j] + '"');
      }
    }
  }
  if (diferencias.length === 0) {
    Logger.log(nombreHoja + ': el espejo coincide con el CORE en todas las celdas.');
  } else {
    Logger.log(nombreHoja + ': ' + diferencias.length + ' celdas distintas');
    Logger.log(diferencias.slice(0, 40).join('\n'));
  }
}

function actualizarEspejo() {
  copiarHojaCompleta('Tablas');
}

function espejarPricingGramo() {
  copiarHojaCompleta('pricing_gramo');
}

function listarHojas() {
  var hojas = SpreadsheetApp.openById(CORE_ID).getSheets();
  Logger.log(hojas.map(function (h) { return h.getName(); }).join(' | '));
}

function actualizarTodo() {
  copiarHojaCompleta('Tablas');
  copiarHojaCompleta('pricing_gramo');
}

/** Actualiza y verifica de una: es la que conviene correr a mano. */
function actualizarYVerificar() {
  actualizarTodo();
  verificarEspejo('Tablas');
  verificarEspejo('pricing_gramo');
}
