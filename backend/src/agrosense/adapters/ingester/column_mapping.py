"""Unico lugar del sistema que conoce los nombres REALES del archivo de
campo (typos incluidos: 'Sobrevivemcia M1', 'Diámetro. Copa (m)_M2').

Versionado para provenance (ADR-004): cambiar un alias = nueva version.
Las campanas M1..M4 comparten nombres canonicos; la campana se extrae del
sufijo _M{k} o del nombre exacto de la columna.
"""
import math

MAPPING_VERSION = "2026-09-anexo1"

# (nombre real exacto, canonico, campana o None si es fija por arbol)
_ALIASES: list[tuple[str, str, int | None]] = [
    ("ID_MUEST", "tree_id", None),
    ("ID Parcela", "plot_id", None),
    ("LOCALIDAD", "locality", None),
    ("Especie_M1", "species", None),
    ("Familia", "family", None),
    ("NombCom_M1", "common_name", None),
    ("Gremio ecológico de la especie", "guild", None),
    ("Altura", "elevation_m", None),
    ("Coord_X", "coord_x", None),
    ("Coord_Y", "coord_y", None),
]
for _k in range(1, 5):
    _ALIASES += [
        (f"Altura total (m)_M{_k}", "height_m", _k),
        (f"Diámetro. Copa (m)_M{_k}", "crown_diameter_m", _k),
        (f"Estado Fitosanitario_M{_k}", "phytosanitary", _k),
        (f"Sobrevivencia M{_k}", "alive", _k),
        (f"DAP (CM) M{_k}", "dap_cm", _k),
    ]
_ALIASES += [
    ("Sobrevivemcia M1", "alive", 1),
    ("DAP (CM)", "dap_cm", 1),
    ("DAP M4", "dap_cm", 4),
]


def map_columns(df_columns: list[str]) -> dict[str, str]:
    """Devuelve {nombre_real: canonico} solo para columnas reconocidas."""
    known = {real: canonical for real, canonical, _ in _ALIASES}
    return {c: known[c] for c in df_columns if c in known}


def campaign_columns(df_columns: list[str]) -> dict[str, dict[int, str]]:
    """Devuelve {canonico: {campana: nombre_real}} para columnas por campana."""
    result: dict[str, dict[int, str]] = {}
    for real, canonical, campaign in _ALIASES:
        if campaign is not None and real in df_columns:
            result.setdefault(canonical, {})[campaign] = real
    return result


def fixed_columns(df_columns: list[str]) -> dict[str, str]:
    """Devuelve {canonico: nombre_real} para columnas fijas por arbol."""
    result: dict[str, str] = {}
    for real, canonical, campaign in _ALIASES:
        if campaign is None and real in df_columns:
            result[canonical] = real
    return result


def parse_alive(raw) -> bool | None:
    """'Vivo'->True, 'Muerto'->False, blanco->None. Nunca lanza."""
    if is_blank(raw):
        return None
    s = str(raw).strip()
    if s == "Vivo":
        return True
    if s == "Muerto":
        return False
    return None


def is_blank(v) -> bool:
    """Blanco de campo: None, NaN o string vacio/' '. 0.0 NO es blanco."""
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and v.strip() == ""
