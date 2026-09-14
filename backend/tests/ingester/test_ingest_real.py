from pathlib import Path

import pandas as pd
import pytest

from agrosense.adapters.ingester.ingest import ingest_wide
from agrosense.domain.entities import StatusSemantic

REFERENCE_PATH = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"

pytestmark = pytest.mark.skipif(
    not REFERENCE_PATH.exists(),
    reason="dataset de referencia local ausente (data/raw/anexo1.xlsx)",
)


def read_reference_dataset() -> pd.DataFrame:
    return pd.read_excel(REFERENCE_PATH, sheet_name="Monitoreo_4")


def test_real_annex_ingests():
    """E2E contra el dataset real: 856 arboles, sin errores de dominio duros.

    Evidencia previa del spike (docs/01-discovery.md):
    - 856 filas, 683/652/755/718 alturas en M1-M4
    - 591 vivos los 4, 138 muertos en M4
    - ~13 contracciones >1cm documentadas
    """
    df = read_reference_dataset()
    result = ingest_wide(df)

    assert len(result.trees) == 856
    assert all(o.dap_status in set(StatusSemantic) for o in result.observations)

    by_campaign = {}
    for o in result.observations:
        by_campaign.setdefault(o.campaign, 0)
        by_campaign[o.campaign] += 1
    assert by_campaign[1] > 680  # ~717 censados en M1
    assert by_campaign[4] > 710  # ~855 censados en M4

    deaths_m4 = sum(1 for o in result.observations if o.campaign == 4 and o.alive is False)
    assert deaths_m4 == 138  # mortalidad M4 documentada

    alive_m4 = sum(1 for o in result.observations if o.campaign == 4 and o.alive is True)
    assert alive_m4 == 718  # vivos M4 documentados

    # contracciones: 13 casos >1cm documentados en M1-M2; revives: 6 casos
    # de replanteo (ruling). Tolerancia amplia para periodos M3-M4.
    assert 0 < len(result.warnings) < 60


def test_real_annex_no_dap_zero_as_measured():
    """El hallazgo clave: 714 de 717 DAP M1 son 0.0 = marcador, NO medicion.
    Ningun dap_cm debe colarse como MEDIDO con valor 0."""
    df = read_reference_dataset()
    result = ingest_wide(df)
    for o in result.observations:
        if o.dap_status == StatusSemantic.MEDIDO:
            assert o.dap_cm is not None and o.dap_cm > 0
        else:
            assert o.dap_cm is None
