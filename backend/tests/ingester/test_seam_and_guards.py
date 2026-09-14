"""Tests del seam publico de column_mapping + guard de tree_id en la ingesta."""

import pandas as pd
import pytest

from agrosense.adapters.ingester.column_mapping import fixed_columns
from agrosense.adapters.ingester.ingest import ingest_wide


def test_fixed_columns_public_api():
    """El seam publico: {canonico: nombre_real} para columnas fijas por arbol.
    wide_to_long NO debe tocar _ALIASES privado."""
    cols = ["ID_MUEST", "LOCALIDAD", "Especie_M1", "Altura", "Coord_X", "ColumnaRara"]
    fixed = fixed_columns(cols)
    assert fixed["tree_id"] == "ID_MUEST"
    assert fixed["locality"] == "LOCALIDAD"
    assert fixed["elevation_m"] == "Altura"
    assert "ColumnaRara" not in fixed.values()


def test_missing_tree_id_rejected_clearly():
    """tree_id NaN/blank no debe producir 'nan' silencioso: error claro."""
    base = {
        "ID Parcela": 1, "LOCALIDAD": "Guayabal",
        "Especie_M1": "Quercus humboldtii", "Familia": "Fagaceae",
        "Altura": 2700, "Coord_X": 1.0, "Coord_Y": 2.0,
        "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
    }
    df = pd.DataFrame([{**base, "ID_MUEST": float("nan")}])
    with pytest.raises(ValueError, match="tree_id"):
        ingest_wide(df)


def test_missing_species_rejected_clearly():
    base = {
        "ID_MUEST": "T1", "ID Parcela": 1, "LOCALIDAD": "Guayabal",
        "Familia": "Fagaceae", "Altura": 2700, "Coord_X": 1.0, "Coord_Y": 2.0,
        "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
    }
    df = pd.DataFrame([{**base, "Especie_M1": float("nan")}])
    with pytest.raises(ValueError, match="species|especie"):
        ingest_wide(df)
