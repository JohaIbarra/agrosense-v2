"""UC2: Cargar campana de monitoreo a un proyecto.

Flujo:
    1. Verificar que el proyecto exista (antes de leer nada).
    2. Calcular sha256 del archivo crudo (provenance, AGENTS.md).
    3. Delegar el parseo al puerto CampaignSource -> CampaignData.
    4. Persistir via campaign_repo (transaccional, sin persistencia parcial).
    5. Mapear los warnings de dominio al DTO de aplicacion.

Esta capa no sabe de Excel, HTTP ni SQL: recibe el parser como puerto y
los repos por parametro. El caller mapea ValueError y DomainError al
protocolo que corresponda.
"""
from __future__ import annotations

import hashlib

from agrosense.application.dtos import UploadResult, WarningDTO
from agrosense.application.ports import CampaignSource
from agrosense.domain.errors import (
    CensusGapWarning,
    SuspiciousContractionWarning,
    SuspiciousRevivalWarning,
)

# Vocabulario estable del contrato (schemas.WarningItem.type)
_WARNING_TYPES: tuple[tuple[type[Exception], str], ...] = (
    (SuspiciousContractionWarning, "contraction"),
    (SuspiciousRevivalWarning, "revival"),
    (CensusGapWarning, "census_gap"),
)


def _map_warning(w: Exception) -> WarningDTO:
    """Convierte un warning de dominio al DTO del contrato."""
    for warning_cls, type_name in _WARNING_TYPES:
        if isinstance(w, warning_cls):
            return WarningDTO(
                type=type_name,
                tree_id=getattr(w, "tree_id", ""),
                message=str(w),
            )
    # Tipo desconocido: no se silencia y no se filtra el internals al usuario
    raise ValueError(f"Tipo de warning no reconocido: {type(w).__name__}")


def upload_campaign(
    project_id: int,
    filename: str,
    content: bytes,
    project_repo,
    campaign_repo,
    source: CampaignSource,
) -> UploadResult:
    """Sube y valida una campana de monitoreo a un proyecto existente.

    Raises:
        ValueError("PROJECT_NOT_FOUND"): si el project_id no existe.
        ValueError("INVALID_FILE"): si el source no puede leer el archivo.
        ValueError("DUPLICATE_FILE"): si ese archivo ya fue ingresado.
        DomainError: si un invariante de dominio falla (el caller lo mapea).
    """
    # 1. Proyecto primero: no se parsea un archivo que no tiene donde ir
    if project_repo.get(project_id) is None:
        raise ValueError("PROJECT_NOT_FOUND")

    # 2. Hash del archivo CRUDO, antes de parsear
    sha256 = hashlib.sha256(content).hexdigest()

    # 3. El puerto decide como leerlo (DomainError sube sin envolver)
    data = source.read(content, filename)

    # 4. Persistencia transaccional
    stats = campaign_repo.save_ingest(
        project_id=project_id,
        result=data,
        filename=filename,
        sha256=sha256,
    )

    # 5. Warnings -> DTO
    return UploadResult(
        valid=True,
        campaign_id=stats["campaign_id"],
        trees=stats["trees"],
        observations=stats["observations"],
        deaths=stats["deaths"],
        warnings=[_map_warning(w) for w in data.warnings],
    )
