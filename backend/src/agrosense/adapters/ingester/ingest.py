"""Interfaz del modulo ingester (ADR-004).

Orquesta la transformacion ancho -> long y devuelve la campana canonica
con su provenance (version de mapping). Los errores de dominio suben sin
tocar: el caller (CLI, o el adapter de upload) decide como reportarlos.

El tipo devuelto, `CampaignData`, vive en `application/dtos.py`: es el
dato que cruza el boundary, y los adapters dependen de el (hacia adentro),
no al reves.
"""
import pandas as pd

from agrosense.adapters.ingester.column_mapping import MAPPING_VERSION
from agrosense.adapters.ingester.wide_to_long import wide_to_long
from agrosense.application.dtos import CampaignData
from agrosense.domain.errors import (
    CensusGapWarning,
    SuspiciousContractionWarning,
    SuspiciousRevivalWarning,
)

DomainWarning = SuspiciousContractionWarning | SuspiciousRevivalWarning | CensusGapWarning


def ingest_wide(df: pd.DataFrame) -> CampaignData:
    """Ingiere formato ancho de campo. Lanza DomainError ante invariante
    dura (la campana se rechaza completa, sin persistencia parcial)."""
    trees, observations, warnings = wide_to_long(df)
    return CampaignData(
        trees=trees,
        observations=observations,
        warnings=warnings,
        mapping_version=MAPPING_VERSION,
    )
