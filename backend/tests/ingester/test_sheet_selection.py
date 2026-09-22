"""E2: el Excel del ingeniero no tiene por que llamar a su hoja `Monitoreo_4`.

El archivo del M1 se llamara `Monitoreo_1`, `Datos` o `Hoja1`; y el Anexo 1
trae ademas siete hojas de resumen que NO son datos. La hoja de campo se
reconoce por su contenido (columnas de identidad del arbol), no por su nombre.
"""

import io

import pytest
from openpyxl import Workbook

from agrosense.adapters.ingester.excel_source import ExcelCampaignSource
from agrosense.application.errors import AppError

HEADERS = [
    "LOCALIDAD",
    "Codigo de unidad muestreo",
    "ID Parcela",
    "ID_MUEST",
    "Especie_M1",
    "Altura total (m)_M1",
    "Sobrevivemcia M1",
    "Estado Fitosanitario_M1",
]
ROWS = [
    ["Guayabal", "U1", 1, "G_1_1", "Senna viarum", 0.3, "Vivo", "Bueno"],
    ["Guayabal", "U1", 1, "G_1_2", "Inga punctata", 0.25, "Vivo", "Regular"],
]


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_reads_a_single_monitoring_file_with_any_sheet_name():
    data = ExcelCampaignSource().read(_xlsx({"Monitoreo_1": [HEADERS, *ROWS]}), "m1.xlsx")
    assert [t.tree_id for t in data.trees] == ["G_1_1", "G_1_2"]
    assert data.monitorings == [1]


def test_skips_summary_sheets_and_finds_the_field_sheet():
    content = _xlsx(
        {
            "Composición": [["Especie", "Total"], ["Senna viarum", 1]],
            "Alturas": [["Promedio de Altura total (m)_M4"]],
            "Datos campo": [HEADERS, *ROWS],
        }
    )
    data = ExcelCampaignSource().read(content, "m1.xlsx")
    assert len(data.trees) == 2


def test_prefers_monitoreo_4_when_present():
    otra = [HEADERS, ["X", "U9", 9, "OTRO_1", "Senna viarum", 0.3, "Vivo", "Bueno"]]
    content = _xlsx({"Copia": otra, "Monitoreo_4": [HEADERS, *ROWS]})
    data = ExcelCampaignSource().read(content, "m4.xlsx")
    assert [t.tree_id for t in data.trees] == ["G_1_1", "G_1_2"]


def test_workbook_without_a_field_sheet_is_rejected_with_an_actionable_message():
    content = _xlsx({"Composición": [["Especie", "Total"], ["Senna viarum", 1]]})
    with pytest.raises(AppError) as exc:
        ExcelCampaignSource().read(content, "resumen.xlsx")
    assert exc.value.code == "INVALID_FILE"
    assert "ID_MUEST" in exc.value.message
