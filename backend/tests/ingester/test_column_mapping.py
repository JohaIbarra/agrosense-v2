
from agrosense.adapters.ingester.column_mapping import (
    MAPPING_VERSION,
    is_blank,
    map_columns,
    parse_alive,
)


def test_maps_real_annex_columns():
    cols = [
        "ID_MUEST", "ID Parcela", "LOCALIDAD", "Especie_M1", "Familia", "NombCom_M1",
        "Gremio ecológico de la especie",
        "Altura", "Coord_X", "Coord_Y",
        "Altura total (m)_M1", "Altura total (m)_M2", "Altura total (m)_M3",
        "Altura total (m)_M4",
        "Diámetro. Copa (m)_M1", "Diámetro. Copa (m)_M2", "Diámetro. Copa (m)_M3",
        "Diámetro. Copa (m)_M4",
        "DAP (CM)", "DAP (CM) M3", "DAP M4",
        "Sobrevivemcia M1", "Sobrevivencia M2", "Sobrevivencia M3", "Sobrevivencia M4",
        "Estado Fitosanitario_M1", "Estado Fitosanitario_M2",
        "Estado Fitosanitario_M3", "Estado Fitosanitario_M4",
        "ColumnaRara", "OtraDesconocida",
    ]
    mapping = map_columns(cols)
    assert mapping["ID_MUEST"] == "tree_id"
    assert mapping["LOCALIDAD"] == "locality"
    assert mapping["Altura total (m)_M3"] == "height_m"
    assert mapping["Diámetro. Copa (m)_M2"] == "crown_diameter_m"
    assert mapping["DAP (CM) M3"] == "dap_cm"
    assert mapping["Sobrevivemcia M1"] == "alive"
    assert mapping["DAP (CM)"] == "dap_cm"
    assert mapping["DAP M4"] == "dap_cm"
    assert mapping["Estado Fitosanitario_M2"] == "phytosanitary"
    assert mapping["Gremio ecológico de la especie"] == "guild"
    assert mapping["Altura"] == "elevation_m"
    assert mapping["Especie_M1"] == "species"
    assert "ColumnaRara" not in mapping
    assert "OtraDesconocida" not in mapping


def test_campaigns_exposed():
    """El ingester necesita saber a que campana pertenece cada columna M{k}."""
    from agrosense.adapters.ingester.column_mapping import campaign_columns

    cols = campaign_columns(["Altura total (m)_M2", "Sobrevivemcia M1",
                             "Estado Fitosanitario_M4", "DAP (CM) M3"])
    # canonical -> {campaign: nombre_real}
    assert cols["height_m"] == {2: "Altura total (m)_M2"}
    assert cols["alive"][1] == "Sobrevivemcia M1"
    assert cols["phytosanitary"][4] == "Estado Fitosanitario_M4"
    assert cols["dap_cm"][3] == "DAP (CM) M3"


def test_mapping_version_stable():
    assert MAPPING_VERSION == "2026-09-anexo1"


def test_parse_alive_semantics():
    assert parse_alive("Vivo") is True
    assert parse_alive("Muerto") is False
    assert parse_alive(" ") is None
    assert parse_alive("NaN") is None
    assert parse_alive(float("nan")) is None
    assert parse_alive(None) is None
    assert parse_alive("") is None


def test_is_blank_helper():
    from agrosense.adapters.ingester.column_mapping import is_blank

    assert is_blank(None) is True
    assert is_blank(float("nan")) is True
    assert is_blank("") is True
    assert is_blank("   ") is True
    assert is_blank("Vivo") is False
    assert is_blank(0.0) is False


def test_nan_is_not_blank_zero():
    """0.0 es un valor REAL (marcador bajo_umbral), no un blanco."""
    assert is_blank(0.0) is False
