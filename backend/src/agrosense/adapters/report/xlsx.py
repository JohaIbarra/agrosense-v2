"""Reporte .xlsx del analisis de un monitoreo (E3).

Una hoja por analisis (las 7 del Anexo 1), mas «Resumen» (provenance) y
«Datos crudos». Todo sale del MISMO payload que ve la pagina: este modulo no
calcula ninguna cifra, solo las escribe con el formato que declara cada
columna (entero, decimal con N decimales, porcentaje). Los porcentajes se
escriben en escala 0–100, igual que en la pagina, con el «%» en el encabezado.

La hoja «Datos crudos» usa las cabeceras del formato de campo (`ID_MUEST`,
`Altura total (m)_M1`…): el archivo descargado se puede volver a subir.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from datetime import date

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.series import SeriesLabel
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from agrosense.application.dtos import ReportData
from agrosense.domain.entities import Observation, StatusSemantic, Tree

_SHEET_NAMES = {
    "composicion": "Composición",
    "alturas": "Alturas",
    "copa": "Diámetro de copa",
    "supervivencia": "Supervivencia",
    "estado_fitosanitario": "Estado fitosanitario",
    "edades": "Edades",
    "dap": "DAP",
    "comparacion": "Comparación",
}

_GREEN = "2F6B3A"
_HEADER_FILL = PatternFill("solid", fgColor=_GREEN)
_GROUP_FILL = PatternFill("solid", fgColor="DCE9DE")
_FOOTER_FILL = PatternFill("solid", fgColor="F1F4F1")
_LOW_FILL = PatternFill("solid", fgColor="FFF4D6")
_THIN = Side(style="thin", color="B7C4B9")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_WHITE_BOLD = Font(bold=True, color="FFFFFF")
_BOLD = Font(bold=True)
_TITLE = Font(bold=True, size=14, color=_GREEN)
_SUBTITLE = Font(bold=True, size=11, color=_GREEN)
_MUTED = Font(italic=True, color="5F6B61")

_MAX_WIDTH = 48
_CHART_COL_GAP = 2


def _cell(ws, row: int, column: int, value=None):
    """Escribe una celda. Un texto que empieza por `=` NUNCA es formula.

    openpyxl deduce el tipo del valor: cualquier cadena con `=` delante queda
    marcada como formula y Excel la ejecuta al abrir el archivo. La especie,
    el identificador del arbol y las notas de campo salen del Excel que sube
    el usuario, asi que se fuerza texto. Seguridad, no cosmetica.
    """
    cell = ws.cell(row=row, column=column, value=value)
    if isinstance(value, str) and cell.data_type == "f":
        cell.data_type = "s"
    return cell


def _number_format(col: dict) -> str | None:
    kind = col.get("kind")
    if kind == "int":
        return "#,##0"
    if kind in ("decimal", "percent"):
        decimals = col.get("decimals", 2)
        return "0." + "0" * decimals if decimals else "0"
    return None


class _Widths:
    """Ancho de columna a partir del contenido escrito (acotado)."""

    def __init__(self) -> None:
        self._w: dict[int, int] = {}

    def see(self, col: int, value, wrap_at: int | None = None) -> None:
        text = "" if value is None else str(value)
        n = len(text) if wrap_at is None else min(len(text), wrap_at)
        self._w[col] = max(self._w.get(col, 8), min(n + 2, _MAX_WIDTH))

    def apply(self, ws: Worksheet) -> None:
        for col, width in self._w.items():
            ws.column_dimensions[get_column_letter(col)].width = width


def _write_table(ws: Worksheet, table: dict, row: int, widths: _Widths) -> tuple[int, dict]:
    """Escribe una tabla desde `row`; devuelve la fila siguiente y su ubicacion."""
    cols = table["columns"]
    _cell(ws, row=row, column=1, value=table["title"]).font = _SUBTITLE
    row += 1

    # Encabezado de grupo (p. ej. el diseno sobre «M3 | M4»)
    if any(c.get("group") for c in cols):
        j = 1
        while j <= len(cols):
            group = cols[j - 1].get("group")
            end = j
            while end < len(cols) and group and cols[end].get("group") == group:
                end += 1
            for k in range(j, end + 1):
                cell = _cell(ws, row=row, column=k)
                cell.border = _BORDER
                if group:
                    cell.fill = _GROUP_FILL
            if group:
                cell = _cell(ws, row=row, column=j, value=group)
                cell.font = _BOLD
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                if end > j:
                    ws.merge_cells(start_row=row, start_column=j, end_row=row, end_column=end)
            j = end + 1
        ws.row_dimensions[row].height = 30
        row += 1

    header_row = row
    for j, c in enumerate(cols, start=1):
        cell = _cell(ws, row=row, column=j, value=c["label"])
        cell.fill = _HEADER_FILL
        cell.font = _WHITE_BOLD
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER
        widths.see(j, c["label"], wrap_at=22)
    row += 1

    first_data = row
    for data_row in table["rows"]:
        low = "low_sample" in data_row.get("_flags", [])
        for j, c in enumerate(cols, start=1):
            value = data_row.get(c["key"])
            cell = _cell(ws, row=row, column=j, value=value)
            cell.border = _BORDER
            fmt = _number_format(c)
            if fmt and value is not None:
                cell.number_format = fmt
            if low:
                cell.fill = _LOW_FILL
            widths.see(j, value if c["kind"] == "text" else f"{value}"[:10])
        row += 1
    last_data = row - 1

    for footer in table.get("footer", []):
        for j, c in enumerate(cols, start=1):
            value = footer.get(c["key"])
            cell = _cell(ws, row=row, column=j, value=value)
            cell.font = _BOLD
            cell.fill = _FOOTER_FILL
            cell.border = _BORDER
            fmt = _number_format(c)
            if fmt and value is not None:
                cell.number_format = fmt
            if c["kind"] == "text":
                widths.see(j, value)
        row += 1

    notes = list(table.get("notes", []))
    if any("low_sample" in r.get("_flags", []) for r in table["rows"]):
        notes.append("Filas sombreadas: muestra pequeña, porcentaje poco robusto.")
    for note in notes:
        _cell(ws, row=row, column=1, value=note).font = _MUTED
        row += 1

    location = {
        "header_row": header_row,
        "first_data": first_data,
        "last_data": last_data,
        "columns": {c["key"]: j for j, c in enumerate(cols, start=1)},
        "labels": {
            c["key"]: f"{c['group']} · {c['label']}" if c.get("group") else c["label"] for c in cols
        },
        "width": len(cols),
    }
    return row + 1, location


def _add_chart(ws: Worksheet, chart: dict, loc: dict, anchor: str) -> None:
    if loc["last_data"] < loc["first_data"]:
        return
    bar = BarChart()
    bar.type = "col"
    bar.title = chart["title"]
    bar.y_axis.title = chart.get("y_label") or None
    bar.height = 8
    bar.width = 18
    if chart.get("stacked"):
        bar.grouping = "stacked"
        bar.overlap = 100
    for key in chart["series"]:
        col = loc["columns"][key]
        data = Reference(
            ws, min_col=col, max_col=col, min_row=loc["first_data"], max_row=loc["last_data"]
        )
        bar.add_data(data, titles_from_data=False)
        # Titulo explicito: con columnas agrupadas el encabezado solo dice «M4»
        bar.series[-1].tx = SeriesLabel(v=loc["labels"][key])
    x = loc["columns"][chart["x"]]
    cats = Reference(ws, min_col=x, max_col=x, min_row=loc["first_data"], max_row=loc["last_data"])
    bar.set_categories(cats)
    ws.add_chart(bar, anchor)


def _write_section(wb: Workbook, section: dict) -> None:
    ws = wb.create_sheet(_SHEET_NAMES.get(section["id"], section["title"])[:31])
    widths = _Widths()
    _cell(ws, row=1, column=1, value=section["title"]).font = _TITLE
    _cell(ws, row=2, column=1, value=section.get("description")).font = _MUTED
    row = 4
    for note in section.get("notes", []):
        _cell(ws, row=row, column=1, value=note).font = _MUTED
        row += 2

    locations: dict[str, dict] = {}
    max_width = 1
    for table in section["tables"]:
        row, loc = _write_table(ws, table, row, widths)
        locations[table["id"]] = loc
        max_width = max(max_width, loc["width"])
    widths.apply(ws)

    chart_col = get_column_letter(max_width + _CHART_COL_GAP)
    chart_row = 4
    for chart in section.get("charts", []):
        chart_loc = locations.get(chart["table"])
        if chart_loc is None:
            continue
        _add_chart(ws, chart, chart_loc, f"{chart_col}{chart_row}")
        chart_row += 17
    ws.sheet_view.showGridLines = False


def _write_summary(wb: Workbook, data: ReportData) -> None:
    ws = wb.active
    ws.title = "Resumen"
    a = data.analysis
    ws["A1"] = f"AgroSense — Análisis del monitoreo M{a.monitoring}"
    ws["A1"].font = _TITLE
    info = [
        ("Proyecto", data.project_name),
        ("Código interno", data.project_code),
        ("Monitoreo", f"M{a.monitoring}"),
        ("Fecha del monitoreo", a.monitoring_date),
        (
            "Monitoreo de comparación",
            f"M{a.payload['previous']}" if a.payload.get("previous") else "—",
        ),
        ("Versión del cálculo", a.analysis_version),
        ("Calculado", a.computed_at.replace(tzinfo=None) if a.computed_at else None),
        ("Huella de los datos (SHA-256)", a.input_hash),
    ]
    row = 3
    for label, value in info:
        _cell(ws, row=row, column=1, value=label).font = _BOLD
        cell = _cell(ws, row=row, column=2, value=value)
        if isinstance(value, date):
            cell.number_format = "DD/MM/YYYY" if type(value) is date else "DD/MM/YYYY HH:MM"
        row += 1

    row += 1
    _cell(ws, row=row, column=1, value="Indicadores").font = _SUBTITLE
    row += 1
    for item in a.payload.get("summary", []):
        _cell(ws, row=row, column=1, value=item["label"]).font = _BOLD
        cell = _cell(ws, row=row, column=2, value=item.get("value"))
        fmt = _number_format(item)
        if fmt and item.get("value") is not None:
            cell.number_format = fmt
        if item.get("kind") == "percent":
            _cell(ws, row=row, column=3, value="%")
        elif item.get("unit"):
            _cell(ws, row=row, column=3, value=item["unit"])
        row += 1

    row += 1
    _cell(ws, row=row, column=1, value="Monitoreos del proyecto").font = _SUBTITLE
    row += 1
    for j, h in enumerate(("Monitoreo", "Fecha"), start=1):
        cell = _cell(ws, row=row, column=j, value=h)
        cell.fill, cell.font, cell.border = _HEADER_FILL, _WHITE_BOLD, _BORDER
    row += 1
    for n in a.payload.get("monitorings", []):
        _cell(ws, row=row, column=1, value=f"M{n}").border = _BORDER
        cell = _cell(ws, row=row, column=2, value=data.monitoring_dates.get(n))
        cell.number_format = "DD/MM/YYYY"
        cell.border = _BORDER
        row += 1
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 70
    ws.sheet_view.showGridLines = False


# ── Datos crudos (formato de campo, re-subible) ──────────────────────────────

_FIXED_HEADERS: tuple[tuple[str, str], ...] = (
    ("ID_MUEST", "tree_id"),
    ("LOCALIDAD", "locality"),
    ("Codigo de unidad muestreo", "sampling_unit_code"),
    ("ID Parcela", "plot_id"),
    ("Unidad de monitoreo", "monitoring_unit"),
    ("Diseño floristico", "floristic_design"),
    ("Cobertura vegetal asociada", "associated_cover"),
    ("Cobertura donde se establecio el material vegetal", "establishment_cover"),
    ("Coord_X", "coord_x"),
    ("Coord_Y", "coord_y"),
    ("Altura", "elevation_m"),
    ("Familia", "family"),
    ("Especie_M1", "species"),
    ("NombCom_M1", "common_name"),
    ("Gremio ecológico de la especie", "guild"),
)


def _dap_value(o: Observation) -> float | None:
    if o.dap_status == StatusSemantic.MEDIDO:
        return o.dap_cm
    return 0.0  # el formato de campo marca «bajo umbral» con 0


def _alive_text(alive: bool | None) -> str | None:
    return None if alive is None else ("Vivo" if alive else "Muerto")


def _write_raw(wb: Workbook, trees: Sequence[Tree], observations: Sequence[Observation]) -> None:
    ws = wb.create_sheet("Datos crudos")
    numbers = sorted({o.campaign for o in observations})
    by_tree: dict[str, dict[int, Observation]] = {}
    for o in observations:
        by_tree.setdefault(o.tree_id, {})[o.campaign] = o

    headers = [h for h, _ in _FIXED_HEADERS]
    per_monitoring = []
    for n in numbers:
        per_monitoring += [
            (f"Altura total (m)_M{n}", n, "height", "0.00"),
            (f"Diámetro. Copa (m)_M{n}", n, "crown", "0.00"),
            (f"DAP (CM) M{n}", n, "dap", "0.00"),
            (f"Sobrevivencia M{n}", n, "alive", None),
            (f"Estado Fitosanitario_M{n}", n, "phyto", None),
        ]
    headers += [h for h, *_ in per_monitoring] + ["Observa"]

    widths = _Widths()
    for j, h in enumerate(headers, start=1):
        cell = _cell(ws, row=1, column=j, value=h)
        cell.fill, cell.font, cell.border = _HEADER_FILL, _WHITE_BOLD, _BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        widths.see(j, h, wrap_at=18)
    ws.row_dimensions[1].height = 45

    for i, t in enumerate(sorted(trees, key=lambda t: t.tree_id), start=2):
        obs = by_tree.get(t.tree_id, {})
        values: list = [getattr(t, attr) for _, attr in _FIXED_HEADERS]
        formats: list = [None] * len(values)
        for _, n, what, fmt in per_monitoring:
            obs_n = obs.get(n)
            if obs_n is None:
                values.append(None)
            elif what == "height":
                values.append(obs_n.height_m)
            elif what == "crown":
                values.append(obs_n.crown_diameter_m)
            elif what == "dap":
                values.append(_dap_value(obs_n))
            elif what == "alive":
                values.append(_alive_text(obs_n.alive))
            else:
                values.append(obs_n.phytosanitary)
            formats.append(fmt)
        notes = next(
            (o.field_notes for n, o in sorted(obs.items(), reverse=True) if o.field_notes), None
        )
        values.append(notes)
        formats.append(None)
        for j, (value, fmt) in enumerate(zip(values, formats, strict=True), start=1):
            cell = _cell(ws, row=i, column=j, value=value)
            if fmt and isinstance(value, int | float):
                cell.number_format = fmt
            widths.see(j, value)
    widths.apply(ws)
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(len(trees) + 1, 1)}"


def build_report(data: ReportData) -> bytes:
    """El .xlsx completo del analisis del monitoreo, como bytes."""
    wb = Workbook()
    _write_summary(wb, data)
    for section in data.analysis.payload.get("sections", []):
        _write_section(wb, section)
    _write_raw(wb, data.trees, data.observations)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def report_filename(data: ReportData) -> str:
    """Nombre de descarga: codigo del proyecto + monitoreo, solo ASCII seguro."""
    code = data.project_code or "proyecto"
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in code)
    return f"AgroSense_{safe}_M{data.analysis.monitoring}.xlsx"
