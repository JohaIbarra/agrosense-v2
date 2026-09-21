from collections import Counter
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
    - 13 contracciones documentadas en M1->M2 (1-20 cm); 7 superan los
      5 cm de MAX_CONTRACTION_M y se anotan
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

    # Desglose real con MAX_CONTRACTION_M = 0.05 (2026-09-21):
    #   7 contracciones anotadas (0.07-0.20 m) + 6 revives + 1 hueco de censo.
    # Las otras 6 contracciones del dataset (1-5 cm) quedan por debajo del
    # umbral a proposito: anotarlas empujaba a la cuadrilla a monotonizar la
    # altura (ver LargeContractionNoted). La cota superior queda holgada
    # porque M5 traera casos nuevos.
    counts = Counter(type(w).__name__ for w in result.warnings)
    assert counts["LargeContractionNoted"] == 7
    assert counts["SuspiciousRevivalWarning"] == 6
    assert counts["CensusGapWarning"] == 1
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
