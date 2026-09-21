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
from agrosense.application.errors import AppError
from agrosense.application.ports import CampaignSource
from agrosense.domain.errors import (
    CensusGapWarning,
    EventMismatchWarning,
    LargeContractionNoted,
    ProjectLabelMismatchWarning,
    SuspiciousRevivalWarning,
    UnrecognizedColumnsWarning,
)

# Vocabulario estable del contrato (schemas.WarningItem.type)
_WARNING_TYPES: tuple[tuple[type[Exception], str], ...] = (
    (LargeContractionNoted, "contraction"),
    (SuspiciousRevivalWarning, "revival"),
    (CensusGapWarning, "census_gap"),
    # E0 — avisos de archivo (tree_id = "")
    (EventMismatchWarning, "event_mismatch"),
    (ProjectLabelMismatchWarning, "project_mismatch"),
    (UnrecognizedColumnsWarning, "unknown_columns"),
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
    # Tipo desconocido: es un bug nuestro, no un error del usuario. RuntimeError
    # para que no se confunda con un fallo de operacion y salga como 500.
    raise RuntimeError(f"Tipo de warning no reconocido: {type(w).__name__}")


def upload_campaign(
    project_id: int,
    filename: str,
    content: bytes,
    project_repo,
    campaign_repo,
    source: CampaignSource,
    owner_id: str,
) -> UploadResult:
    """Sube y valida una campana de monitoreo a un proyecto existente.

    Raises:
        AppError("PROJECT_NOT_FOUND"): si el proyecto no existe o no es del ingeniero.
        AppError("INVALID_FILE"): si el source no puede leer el archivo.
        AppError("DUPLICATE_FILE"): si ese archivo ya fue ingresado.
        DomainError: si un invariante de dominio falla (el caller lo mapea).
    """
    # 1. Proyecto primero, y del ingeniero que llama (E1): no se parsea un
    #    archivo que no tiene donde ir. Uno ajeno responde igual que uno
    #    inexistente, para no revelar que existe.
    if project_repo.get_owned(project_id, owner_id) is None:
        raise AppError("PROJECT_NOT_FOUND", f"El proyecto {project_id} no existe.")

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

    # 5. Warnings -> DTO. Los del archivo los produce la lectura; los que
    #    dependen de cargas anteriores (proyecto distinto) solo los puede
    #    detectar la persistencia.
    warnings = list(data.warnings) + list(stats.get("extra_warnings", []))
    return UploadResult(
        valid=True,
        campaign_id=stats["campaign_id"],
        trees=stats["trees"],
        observations=stats["observations"],
        deaths=stats["deaths"],
        warnings=[_map_warning(w) for w in warnings],
        monitorings=list(stats.get("monitorings", data.monitorings)),
    )
