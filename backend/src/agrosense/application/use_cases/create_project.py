"""UC1: Crear proyecto de restauración.

application/ orquesta dominio + repos sin tocar HTTP ni SQL directamente.
El caller (API route) es responsable de mapear errores al protocolo HTTP.
"""
from agrosense.adapters.api.schemas import ProjectResponse


def create_project(
    repo,
    name: str,
    locality: str | None,
    description: str | None,
) -> ProjectResponse:
    """Registra un nuevo proyecto de restauración.

    Raises:
        ValueError("DUPLICATE_NAME"): si ya existe un proyecto con ese nombre.
    """
    proj = repo.create(name=name, locality=locality, description=description)
    return ProjectResponse(
        id=proj.id,
        name=proj.name,
        locality=proj.locality,
        description=proj.description,
        created_at=proj.created_at,
        campaigns_count=repo.campaigns_count(proj.id),
    )
