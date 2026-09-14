"""Interfaz del modulo ingester (ADR-004).

Orquesta la transformacion y expone un resultado unico con provenance
(version de mapping). Los errores de dominio suben sin tocar: el caller
(CLI hoy, API en el siguiente slice) decide como reportarlos.
"""
from dataclasses import dataclass, field

import pandas as pd

from agrosense.adapters.ingester.column_mapping import MAPPING_VERSION
from agrosense.adapters.ingester.wide_to_long import wide_to_long
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.errors import SuspiciousContractionWarning


@dataclass
class IngestResult:
    trees: list[Tree]
    observations: list[Observation]
    warnings: list[SuspiciousContractionWarning] = field(default_factory=list)
    mapping_version: str = MAPPING_VERSION


def ingest_wide(df: pd.DataFrame) -> IngestResult:
    """Ingiere formato ancho de campo. Lanza DomainError ante invariante
    dura (la campana se rechaza completa, sin persistencia parcial)."""
    trees, observations, warnings = wide_to_long(df)
    return IngestResult(
        trees=trees,
        observations=observations,
        warnings=warnings,
        mapping_version=MAPPING_VERSION,
    )
