"""Interfaz del modulo ingester (ADR-004).

Orquesta la transformacion ancho -> long y devuelve la campana canonica
con su provenance (version de mapping). Los errores de dominio suben sin
tocar: el caller (CLI, o el adapter de upload) decide como reportarlos.

El tipo devuelto, `CampaignData`, vive en `application/dtos.py`: es el
dato que cruza el boundary, y los adapters dependen de el (hacia adentro),
no al reves.
"""
import pandas as pd

from agrosense.adapters.ingester.column_mapping import (
    MAPPING_VERSION,
    parse_event_number,
    unclassified_columns,
)
from agrosense.adapters.ingester.wide_to_long import read_file_metadata, wide_to_long
from agrosense.application.dtos import CampaignData
from agrosense.domain.errors import (
    CensusGapWarning,
    EventMismatchWarning,
    LargeContractionNoted,
    SuspiciousRevivalWarning,
    UnrecognizedColumnsWarning,
)

DomainWarning = LargeContractionNoted | SuspiciousRevivalWarning | CensusGapWarning


def ingest_wide(df: pd.DataFrame) -> CampaignData:
    """Ingiere formato ancho de campo. Lanza DomainError ante invariante
    dura (la campana se rechaza completa, sin persistencia parcial)."""
    trees, observations, warnings = wide_to_long(df)
    metadata = read_file_metadata(df)
    data = CampaignData(
        trees=trees,
        observations=observations,
        warnings=list(warnings),
        mapping_version=MAPPING_VERSION,
        file_metadata=metadata,
    )

    # `Evento` solo verifica: la fuente de verdad son las columnas con datos
    declared = parse_event_number(metadata.event)
    if declared is not None and data.monitorings and declared != data.monitorings[-1]:
        data.warnings.append(EventMismatchWarning(declared, data.monitorings[-1]))

    # Una columna que no se sabe interpretar se reporta; no se pierde en silencio
    desconocidas = [str(c) for c in unclassified_columns(list(df.columns))]
    if desconocidas:
        data.warnings.append(UnrecognizedColumnsWarning(desconocidas))
    return data
