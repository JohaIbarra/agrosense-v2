"""UC1: Crear proyecto de restauracion.

application/ orquesta dominio + repos sin tocar HTTP ni SQL. Devuelve un
DTO propio (ADR-003): el mapeo a la respuesta HTTP es trabajo del adapter.
"""
from __future__ import annotations

from agrosense.application.dtos import ProjectSummary


def create_project(
    repo,
    name: str,
    locality: str | None,
    description: str | None,
) -> ProjectSummary:
    """Registra un nuevo proyecto de restauracion.

    Raises:
        ValueError("DUPLICATE_NAME"): si ya existe un proyecto con ese nombre.
    """
    proj = repo.create(name=name, locality=locality, description=description)
    return ProjectSummary(
        id=proj.id,
        name=proj.name,
        locality=proj.locality,
        description=proj.description,
        created_at=proj.created_at,
        campaigns_count=repo.campaigns_count(proj.id),
    )
