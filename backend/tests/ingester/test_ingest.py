import pandas as pd
import pytest

from agrosense.adapters.ingester.column_mapping import MAPPING_VERSION
from agrosense.adapters.ingester.ingest import ingest_wide
from agrosense.domain.entities import StatusSemantic


def make_wide_df(rows: list[dict]) -> pd.DataFrame:
    base = {
        "ID_MUEST": "T1",
        "ID Parcela": 1,
        "LOCALIDAD": "Guayabal",
        "Especie_M1": "Quercus humboldtii",
        "Familia": "Fagaceae",
        "NombCom_M1": "Roble",
        "Gremio ecológico de la especie": "Tardía",
        "Altura": 2700,
        "Coord_X": 4735725.0,
        "Coord_Y": 2199477.0,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def test_wide_to_long_basic():
    df = make_wide_df([
        {
            "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo", "DAP (CM)": 0.0,
            "Estado Fitosanitario_M1": "Bueno",
            "Altura total (m)_M2": 0.3, "Sobrevivencia M2": "Vivo",
            "Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo",
            "Altura total (m)_M4": 0.5, "Sobrevivencia M4": "Vivo",
        }
    ])
    result = ingest_wide(df)
    assert len(result.trees) == 1
    assert len(result.observations) == 4
    obs_by_campaign = {o.campaign: o for o in result.observations}
    assert obs_by_campaign[2].height_m == pytest.approx(0.3)
    assert obs_by_campaign[1].alive is True
    assert obs_by_campaign[1].dap_status == StatusSemantic.BAJO_UMBRAL_DAP
    assert obs_by_campaign[1].dap_cm is None
    assert result.mapping_version == MAPPING_VERSION
    tree = result.trees[0]
    assert tree.species == "Quercus humboldtii"
    assert tree.elevation_m == 2700
    assert tree.guild == "Tardía"


def test_dap_measured_when_positive():
    df = make_wide_df([
        {
            "Altura total (m)_M3": 1.5, "Sobrevivencia M3": "Vivo",
            "DAP (CM) M3": 2.0,
            "Altura total (m)_M4": 1.8, "Sobrevivencia M4": "Vivo", "DAP M4": 2.4,
        }
    ])
    result = ingest_wide(df)
    by_campaign = {o.campaign: o for o in result.observations}
    assert by_campaign[3].dap_status == StatusSemantic.MEDIDO
    assert by_campaign[3].dap_cm == pytest.approx(2.0)
    assert by_campaign[4].dap_cm == pytest.approx(2.4)


def test_sin_censo_campaign_excluded():
    df = make_wide_df([
        {
            "Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo",
            "Altura total (m)_M4": 0.5, "Sobrevivencia M4": "Vivo",
        }
    ])
    result = ingest_wide(df)
    campaigns = {o.campaign for o in result.observations}
    assert campaigns == {3, 4}


def test_space_string_counts_as_sin_censo():
    """' ' en Estado Fitosanitario_M2 (22 casos reales) es blanco, no dato."""
    df = make_wide_df([
        {
            "Altura total (m)_M2": 0.3, "Sobrevivencia M2": "Vivo",
            "Estado Fitosanitario_M2": " ",
            "Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo",
        }
    ])
    result = ingest_wide(df)
    by_campaign = {o.campaign: o for o in result.observations}
    assert by_campaign[2].phytosanitary is None


def test_censused_without_height_keeps_observation():
    """Arbol censado (vive) pero sin altura medida ese periodo."""
    df = make_wide_df([
        {
            "Sobrevivemcia M1": "Vivo",
            "Altura total (m)_M2": 0.3, "Sobrevivencia M2": "Vivo",
        }
    ])
    result = ingest_wide(df)
    by_campaign = {o.campaign: o for o in result.observations}
    assert 1 in by_campaign
    assert by_campaign[1].height_m is None
    assert by_campaign[1].alive is True


def test_dead_tree_valid():
    df = make_wide_df([
        {
            "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
            "Altura total (m)_M2": 0.25, "Sobrevivencia M2": "Muerto",
            "Altura total (m)_M3": 0.25, "Sobrevivencia M3": "Muerto",
            "Altura total (m)_M4": 0.25, "Sobrevivencia M4": "Muerto",
        }
    ])
    result = ingest_wide(df)
    assert len(result.observations) == 4


def test_dead_revives_warns_with_context():
    """Ruling replanteo: revive = warning, la ingesta continua."""
    df = make_wide_df([
        {
            "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Muerto",
            "Altura total (m)_M2": 0.3, "Sobrevivencia M2": "Vivo",
            "Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo",
            "Altura total (m)_M4": 0.5, "Sobrevivencia M4": "Vivo",
        }
    ])
    result = ingest_wide(df)
    assert len(result.observations) == 4
    assert len(result.warnings) == 1
    assert "T1" in str(result.warnings[0])


def test_contraction_warns_but_ingests():
    df = make_wide_df([
        {
            "Altura total (m)_M1": 0.30, "Sobrevivemcia M1": "Vivo",
            "Altura total (m)_M2": 0.20, "Sobrevivencia M2": "Vivo",
            "Altura total (m)_M3": 0.30, "Sobrevivencia M3": "Vivo",
            "Altura total (m)_M4": 0.35, "Sobrevivencia M4": "Vivo",
        }
    ])
    result = ingest_wide(df)
    assert len(result.warnings) == 1
    assert len(result.observations) == 4


def test_multiple_trees():
    df = make_wide_df([
        {
            "ID_MUEST": "T1", "Especie_M1": "Quercus humboldtii",
            "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
            "Altura total (m)_M2": 0.3, "Sobrevivencia M2": "Vivo",
        },
        {
            "ID_MUEST": "T2", "Especie_M1": "Montanoa quadrangularis",
            "Altura total (m)_M1": 0.4, "Sobrevivemcia M1": "Vivo",
            "Altura total (m)_M2": 0.5, "Sobrevivencia M2": "Vivo",
        },
    ])
    result = ingest_wide(df)
    assert len(result.trees) == 2
    assert len(result.observations) == 4
    species = {t.tree_id: t.species for t in result.trees}
    assert species["T2"] == "Montanoa quadrangularis"


def test_unmapped_columns_ignored():
    df = make_wide_df([
        {
            "ColumnaNueva": "valor", "OtraColumna": 123,
            "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
        }
    ])
    result = ingest_wide(df)
    assert len(result.observations) == 1
