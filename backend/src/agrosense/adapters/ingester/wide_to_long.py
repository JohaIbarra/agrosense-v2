"""Transformacion ancho -> list[Tree] + list[Observation] (ADR-004).

Una fila del ancho = un arbol con hasta 4 observaciones (una por campana
con columnas M{k}). Solo TRADUCE semantica de campo a entidades de dominio:
- campana totalmente en blanco -> sin Observation (sin_censo)
- DAP>0 -> MEDIDO; DAP 0/blanco con arbol censado -> BAJO_UMBRAL_DAP
- ' '/'NaN'/NaN -> None (blanco de campo)
Las invariantes de SERIE las valida rules.py por arbol.
"""
import pandas as pd

from agrosense.adapters.ingester.column_mapping import (
    campaign_columns,
    is_blank,
    parse_alive,
)
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.errors import SpeciesMismatchError, SuspiciousContractionWarning
from agrosense.domain.rules import validate_tree_observations

CAMPAIGNS = (1, 2, 3, 4)


def _to_float(v) -> float | None:
    return None if is_blank(v) else float(v)


def _to_str(v) -> str | None:
    if is_blank(v):
        return None
    s = str(v).strip()
    return s or None


def wide_to_long(
    df: pd.DataFrame,
) -> tuple[list[Tree], list[Observation], list[SuspiciousContractionWarning]]:
    columns = list(df.columns)

    fixed_map: dict[str, str] = {}
    for real, canonical, campaign in _iter_aliases():
        if campaign is None and real in columns:
            fixed_map[canonical] = real

    per_campaign = campaign_columns(columns)

    trees: list[Tree] = []
    observations: list[Observation] = []
    all_warnings: list[SuspiciousContractionWarning] = []
    species_by_tree: dict[str, str] = {}

    for _, row in df.iterrows():
        tree_id = str(row[fixed_map["tree_id"]]).strip()
        species = str(row[fixed_map["species"]]).strip()

        if tree_id in species_by_tree and species_by_tree[tree_id] != species:
            raise SpeciesMismatchError(tree_id, species, species_by_tree[tree_id])
        species_by_tree[tree_id] = species

        tree = Tree(
            tree_id=tree_id,
            species=species,
            family=_to_str(row[fixed_map["family"]]) if "family" in fixed_map else None,
            common_name=(
                _to_str(row[fixed_map["common_name"]]) if "common_name" in fixed_map else None
            ),
            guild=_to_str(row[fixed_map["guild"]]) if "guild" in fixed_map else None,
            plot_id=(
                _to_str(row[fixed_map["plot_id"]]) if "plot_id" in fixed_map else None
            ),
            locality=(
                _to_str(row[fixed_map["locality"]]) if "locality" in fixed_map else None
            ),
            coord_x=(
                _to_float(row[fixed_map["coord_x"]]) if "coord_x" in fixed_map else None
            ),
            coord_y=(
                _to_float(row[fixed_map["coord_y"]]) if "coord_y" in fixed_map else None
            ),
            elevation_m=(
                _to_float(row[fixed_map["elevation_m"]])
                if "elevation_m" in fixed_map
                else None
            ),
        )
        trees.append(tree)

        tree_obs: list[Observation] = []
        for campaign in CAMPAIGNS:
            raw = {
                canonical: (
                    row[cols[campaign]]
                    if canonical in per_campaign and campaign in per_campaign[canonical]
                    else None
                )
                for canonical, cols in per_campaign.items()
            }
            if all(is_blank(v) for v in raw.values()):
                continue

            dap_raw = _to_float(raw.get("dap_cm"))
            dap_measured = dap_raw is not None and dap_raw > 0

            tree_obs.append(
                Observation(
                    tree_id=tree_id,
                    campaign=campaign,
                    height_m=_to_float(raw.get("height_m")),
                    crown_diameter_m=_to_float(raw.get("crown_diameter_m")),
                    dap_cm=dap_raw if dap_measured else None,
                    dap_status=(
                        StatusSemantic.MEDIDO if dap_measured else StatusSemantic.BAJO_UMBRAL_DAP
                    ),
                    phytosanitary=_to_str(raw.get("phytosanitary")),
                    alive=parse_alive(raw.get("alive")),
                    colonization=None,
                )
            )

        all_warnings.extend(validate_tree_observations(tree, tree_obs))
        observations.extend(tree_obs)

    return trees, observations, all_warnings


def _iter_aliases():
    from agrosense.adapters.ingester import column_mapping as _cm

    return _cm._ALIASES
