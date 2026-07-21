"""Lectura de la hoja "Tablas" de Google Sheets con su formato visual.

A diferencia de mayorista_logic (que extrae celdas puntuales), aquí se descarga
el rango completo con colores, negritas, celdas combinadas y tamaños para
reproducir la tabla tal como se ve en Sheets dentro de la aplicación.
Esta hoja es de visualización pública; la credencial es de solo lectura.
"""
import gspread

from core.app_config import log
# Mismo documento espejo que alimenta los precios mayoristas — el ID vive en
# un solo lugar para que un cambio de documento no deje fuentes mezcladas.
from core.mayorista_logic import _SPREADSHEET_ID, _SHEET_GID

_RANGO = "A1:AH50"  # hasta AH para incluir la tabla NEOROS (antes se cortaba en AE)
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _color_hex(color, defecto):
    """Convierte el color de la API ({'red':0-1,...}) a '#rrggbb'.

    Ojo: la API omite los canales en 0 — un negro puro llega como {} —
    así que cuando el dict existe los canales faltantes valen 0, y solo
    si no hay dict se usa el color por defecto.
    """
    if color is None:
        return defecto
    r = round(color.get("red", 0) * 255)
    g = round(color.get("green", 0) * 255)
    b = round(color.get("blue", 0) * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def parsear_grid(meta):
    """Convierte la respuesta de la API (includeGridData) en una estructura
    simple lista para dibujar: tamaños en px, celdas con estilo y merges."""
    hoja = next(
        s for s in meta["sheets"] if s["properties"]["sheetId"] == _SHEET_GID
    )
    data = hoja["data"][0]
    filas = data.get("rowData", [])
    row_px = [m.get("pixelSize", 21) for m in data.get("rowMetadata", [])]
    col_px = [m.get("pixelSize", 100) for m in data.get("columnMetadata", [])]

    # Merges: ancla -> (rowspan, colspan); el resto de celdas cubiertas se omite
    spans = {}
    cubiertas = set()
    for m in hoja.get("merges", []):
        r0, c0 = m["startRowIndex"], m["startColumnIndex"]
        rs = m["endRowIndex"] - r0
        cs = m["endColumnIndex"] - c0
        spans[(r0, c0)] = (rs, cs)
        for r in range(r0, m["endRowIndex"]):
            for c in range(c0, m["endColumnIndex"]):
                if (r, c) != (r0, c0):
                    cubiertas.add((r, c))

    celdas = []
    max_fila = max_col = 0
    for r, fila in enumerate(filas):
        for c, celda in enumerate(fila.get("values", [])):
            if (r, c) in cubiertas:
                continue
            texto = (celda.get("formattedValue") or "").strip()
            fmt = celda.get("effectiveFormat", {})
            bg = _color_hex(fmt.get("backgroundColor"), "#FFFFFF")
            if not texto and bg == "#FFFFFF":
                continue
            tf = fmt.get("textFormat", {})
            rs, cs = spans.get((r, c), (1, 1))
            celdas.append({
                "r": r, "c": c, "rs": rs, "cs": cs,
                "texto": texto,
                "bg": bg,
                "fg": _color_hex(tf.get("foregroundColor"), "#000000"),
                "bold": bool(tf.get("bold")),
                "tam": tf.get("fontSize", 10),
                "align": fmt.get("horizontalAlignment", "CENTER"),
            })
            max_fila = max(max_fila, r + rs)
            max_col = max(max_col, c + cs)

    return {
        "filas": max_fila,
        "cols": max_col,
        "row_px": row_px[:max_fila],
        "col_px": col_px[:max_col],
        "celdas": celdas,
    }


def obtener_tabla_precios(ruta_credenciales):
    """Descarga la hoja Tablas con formato. Retorna {'exito', 'tabla'} o {'error'}."""
    if not ruta_credenciales:
        return {"error": "Falta la ruta al archivo de credenciales."}
    try:
        gc = gspread.service_account(filename=ruta_credenciales, scopes=_SCOPES)
        try:
            gc.http_client.set_timeout(25)
        except AttributeError:
            pass
        spreadsheet = gc.open_by_key(_SPREADSHEET_ID)
        worksheet = spreadsheet.get_worksheet_by_id(_SHEET_GID)
        meta = spreadsheet.fetch_sheet_metadata(params={
            "includeGridData": "true",
            "ranges": f"'{worksheet.title}'!{_RANGO}",
        })
        tabla = parsear_grid(meta)
        if not tabla["celdas"]:
            return {"error": "La hoja Tablas llegó vacía. Verifique el documento."}
        return {"exito": True, "tabla": tabla}
    except FileNotFoundError:
        return {"error": "No se encontró el archivo de credenciales.\nVerifique que 'credentials/credenciales.json' exista."}
    except Exception as e:
        log.warning("Fallo al descargar la tabla de precios", exc_info=True)
        return {"error": f"No se pudo descargar la tabla: Verifique internet y permisos.\nDetalle: {str(e)}"}
