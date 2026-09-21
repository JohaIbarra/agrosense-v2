"""Transformacion ancho -> list[Tree] + list[Observation] (ADR-004).

Una fila del ancho = un arbol con una observacion por cada monitoreo cuyas
columnas M{k} traen datos. Los monitoreos se DETECTAN en las columnas del
archivo, sin techo: un Excel de un solo monitoreo o uno acumulado (M1-M4, o
mas) se leen igual (decision D1 de E0). Solo TRADUCE semantica de campo a
entidades de dominio:
- campana totalmente en blanco -> sin Observation (sin_censo)
- DAP>0 -> MEDIDO; DAP 0/blanco con arbol censado -> BAJO_UMBRAL_DAP
- ' '/'NaN'/NaN -> None (blanco de campo)
Las invariantes de SERIE las valida rules.py por arbol.
"""
import pandas as pd

from agrosense.adapters.ingester.column_mapping import (
    campaign_columns,
    file_columns,
    fixed_columns,
    is_blank,
    parse_alive,
)
from agrosense.application.dtos import FileMetadata
from agrosense.application.errors import AppError
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.errors import (
    CensusGapWarning,
    LargeContractionNoted,
    SpeciesMismatchError,
    SuspiciousRevivalWarning,
)
from agrosense.domain.rules import validate_tree_observations


def _to_float(v) -> float | None:
    return None if is_blank(v) else float(v)


def _to_str(v) -> str | None:
    if is_blank(v):
        return None
    s = str(v).strip()
    return s or None


DomainWarning = LargeContractionNoted | SuspiciousRevivalWarning | CensusGapWarning

# Atributos de parcela que el arbol transporta desde el archivo (E0)
_PLOT_FIELDS = (
    "sampling_unit_code",
    "monitoring_unit",
    "floristic_design",
    "associated_cover",
    "establishment_cover",
)


def read_file_metadata(df: pd.DataFrame) -> FileMetadata:
    """Lee las columnas que describen el archivo completo.

    En el formato de campo vienen repetidas en cada fila. Si aparecen valores
    distintos se conservan todos, unidos, en lugar de quedarse con uno al azar:
    es un archivo raro y el ingeniero debe poder verlo.
    """
    cols = file_columns(list(df.columns))
    values: dict[str, str | None] = {}
    for canonical, real in cols.items():
        distintos = []
        for v in df[real]:
            texto = _to_str(v)
            if texto is not None and texto not in distintos:
                distintos.append(texto)
        values[canonical] = "; ".join(distintos) if distintos else None
    return FileMetadata(**values)


def wide_to_long(df: pd.DataFrame) -> tuple[list[Tree], list[Observation], list[DomainWarning]]:
    columns = list(df.columns)

    fixed_map = fixed_columns(columns)
    if "tree_id" not in fixed_map or "species" not in fixed_map:
        raise AppError(
            "INVALID_FILE",
            "El archivo no tiene las columnas de identidad del arbol "
            f"(ID_MUEST / Especie_M1). Columnas encontradas: {columns[:10]}...",
        )

    per_campaign = campaign_columns(columns)
    # Monitoreos presentes en las COLUMNAS; que traigan datos se decide fila a fila
    campaigns = sorted({k for by_campaign in per_campaign.values() for k in by_campaign})

    trees: list[Tree] = []
    observations: list[Observation] = []
    all_warnings: list[
        LargeContractionNoted | SuspiciousRevivalWarning | CensusGapWarning
    ] = []
    species_by_tree: dict[str, str] = {}

    for _, row in df.iterrows():
        raw_tree_id = row[fixed_map["tree_id"]]
        if is_blank(raw_tree_id):
            raise AppError(
                "INVALID_FILE",
                f"Fila con tree_id vacio (ID_MUEST en blanco); "
                f"no se puede identificar al arbol. Fila: {row.name}",
            )
        tree_id = str(raw_tree_id).strip()

        raw_species = row[fixed_map["species"]]
        if is_blank(raw_species):
            raise AppError(
                "INVALID_FILE",
                f"Arbol {tree_id} sin especie registrada; la identidad del "
                f"arbol requiere especie",
            )
        species = str(raw_species).strip()

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
            **{
                f: (_to_str(row[fixed_map[f]]) if f in fixed_map else None)
                for f in _PLOT_FIELDS
            },
        )
        trees.append(tree)

        tree_obs: list[Observation] = []
        for campaign in campaigns:
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

        # `Observa` no tiene sufijo de monitoreo: es la nota de la visita mas
        # reciente del archivo, asi que va a la ultima observacion del arbol.
        notes = _to_str(row[fixed_map["field_notes"]]) if "field_notes" in fixed_map else None
        if notes and tree_obs:
            tree_obs[-1] = tree_obs[-1].model_copy(update={"field_notes": notes})

        all_warnings.extend(validate_tree_observations(tree, tree_obs))
        observations.extend(tree_obs)

    return trees, observations, all_warnings
