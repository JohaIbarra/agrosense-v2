"""UC2: Cargar campaña de monitoreo (archivo Excel) a un proyecto.

Flujo:
    1. Verificar que el proyecto exista.
    2. Calcular sha256 del archivo (provenance).
    3. Leer el Excel con pandas (solo la hoja Monitoreo_4).
    4. Transformar ancho → long + validar invariantes de dominio (ingest_wide).
    5. Persistir vía campaign_repo (transaccional — sin persistencia parcial).
    6. Mapear warnings del ingester al schema WarningItem del contrato.
    7. Devolver UploadResultResponse.

El caller (API route) mapea ValueError y DomainError a respuestas HTTP.
Esta capa no importa fastapi ni sqlalchemy.
"""
from __future__ import annotations

import hashlib
import io

import pandas as pd

from agrosense.adapters.api.schemas import UploadResultResponse, WarningItem
from agrosense.adapters.ingester.ingest import ingest_wide
from agrosense.domain.errors import (
    CensusGapWarning,
    SuspiciousContractionWarning,
    SuspiciousRevivalWarning,
)

# Hoja del dataset de campo (ADR-004 + AGENTS.md)
_SHEET_NAME = "Monitoreo_4"


def _map_warning(w) -> WarningItem:
    """Convierte los 3 tipos de DomainWarning al WarningItem del contrato."""
    if isinstance(w, SuspiciousContractionWarning):
        return WarningItem(
            type="contraction",
            tree_id=w.tree_id,
            message=str(w),
        )
    if isinstance(w, SuspiciousRevivalWarning):
        return WarningItem(
            type="revival",
            tree_id=w.tree_id,
            message=str(w),
        )
    if isinstance(w, CensusGapWarning):
        return WarningItem(
            type="census_gap",
            tree_id=w.tree_id,
            message=str(w),
        )
    # Tipo de warning desconocido — no silenciar, no exponer internals
    raise ValueError(f"Tipo de warning no reconocido: {type(w).__name__}")


def upload_campaign(
    project_id: int,
    filename: str,
    content: bytes,
    project_repo,
    campaign_repo,
) -> UploadResultResponse:
    """Sube y valida una campaña de monitoreo a un proyecto existente.

    Raises:
        ValueError("PROJECT_NOT_FOUND"): si el project_id no existe.
        ValueError("INVALID_FILE"): si los bytes no son un Excel legible.
        ValueError("DUPLICATE_FILE"): si ese archivo ya fue ingresado.
        DomainError: si algún invariante de dominio falla (el caller HTTP lo mapea a 422).
    """
    # 1. Verificar proyecto
    project = project_repo.get(project_id)
    if project is None:
        raise ValueError("PROJECT_NOT_FOUND")

    # 2. sha256 de provenance (antes de parsear — el hash es del archivo crudo)
    sha256 = hashlib.sha256(content).hexdigest()

    # 3. Leer Excel
    try:
        df = pd.read_excel(io.BytesIO(content), sheet_name=_SHEET_NAME)
    except Exception as exc:
        raise ValueError(f"INVALID_FILE: no se pudo leer '{filename}' como Excel: {exc}") from exc

    # 4. Transformar + validar invariantes de dominio (DomainError sube sin wrap)
    result = ingest_wide(df)

    # 5. Persistir (transaccional — ValueError("DUPLICATE_FILE") si sha256 ya existe)
    stats = campaign_repo.save_ingest(
        project_id=project_id,
        result=result,
        filename=filename,
        sha256=sha256,
    )

    # 6. Mapear warnings
    warning_items = [_map_warning(w) for w in result.warnings]

    # 7. Respuesta
    return UploadResultResponse(
        valid=True,
        campaign_id=stats["campaign_id"],
        trees=stats["trees"],
        observations=stats["observations"],
        deaths=stats["deaths"],
        warnings=warning_items,
        errors=[],
    )
