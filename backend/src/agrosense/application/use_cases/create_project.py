"""Casos de uso de proyectos (UC1 + E1: multi-proyecto por ingeniero).

La AUTORIZACION vive aqui, no en la route: "un ingeniero solo ve y modifica
sus proyectos" es una regla de negocio. Un proyecto ajeno se trata igual que
uno inexistente (PROJECT_NOT_FOUND → 404) para no revelar que existe.

application/ orquesta dominio + repos sin tocar HTTP ni SQL. Devuelve DTOs
propios (ADR-003): el mapeo a la respuesta HTTP es trabajo del adapter.
"""
from __future__ import annotations

from agrosense.application.dtos import ProjectSummary
from agrosense.application.errors import AppError
from agrosense.domain.project import ProjectSpec

# Campos editables del proyecto (todo ProjectSpec). El codigo interno, el
# propietario y la fecha de creacion NO se editan.
EDITABLE_FIELDS = tuple(ProjectSpec.model_fields)

# Campos que el proyecto siempre tiene: no se pueden borrar con null.
REQUIRED_FIELDS = ("name", "status", "coordinate_srid")


def to_summary(proj, campaigns_count: int) -> ProjectSummary:
    """Proyecto persistido -> DTO. Lee atributos por nombre (ORM o doble)."""
    return ProjectSummary(
        id=proj.id,
        name=proj.name,
        locality=proj.locality,
        description=proj.description,
        created_at=proj.created_at,
        campaigns_count=campaigns_count,
        **{
            f: getattr(proj, f, None)
            for f in ("project_code", *EDITABLE_FIELDS)
            if f not in ("name", "locality", "description") and getattr(proj, f, None) is not None
        },
    )


def create_project(repo, owner_id: str, **fields) -> ProjectSummary:
    """Registra un proyecto del ingeniero autenticado.

    Raises:
        InvalidProjectError: si los campos rompen una regla del dominio (→ 422).
        AppError("DUPLICATE_NAME"): si el ingeniero ya tiene uno con ese nombre.
    """
    spec = ProjectSpec(**fields)
    proj = repo.create(owner_id=owner_id, **spec.model_dump())
    return to_summary(proj, repo.campaigns_count(proj.id))


def list_projects(repo, owner_id: str) -> list[ProjectSummary]:
    return [to_summary(p, repo.campaigns_count(p.id)) for p in repo.list_for_owner(owner_id)]


def get_owned_project(repo, owner_id: str, project_id: int):
    """El proyecto del ingeniero, o PROJECT_NOT_FOUND si no existe o es ajeno."""
    proj = repo.get_owned(project_id, owner_id)
    if proj is None:
        raise AppError("PROJECT_NOT_FOUND", f"Proyecto {project_id} no existe.")
    return proj


def get_project(repo, owner_id: str, project_id: int) -> ProjectSummary:
    proj = get_owned_project(repo, owner_id, project_id)
    return to_summary(proj, repo.campaigns_count(proj.id))


def update_project(repo, owner_id: str, project_id: int, **changes) -> ProjectSummary:
    """Edita los campos del proyecto. Valida el resultado COMPLETO contra el dominio.

    Validar solo los campos que llegan dejaria pasar, por ejemplo, una fecha de
    fin anterior a la de inicio ya guardada.
    """
    proj = get_owned_project(repo, owner_id, project_id)
    actual = {f: getattr(proj, f) for f in EDITABLE_FIELDS}
    desconocidos = set(changes) - set(EDITABLE_FIELDS)
    if desconocidos:
        raise AppError(
            "BAD_REQUEST", f"Campos no editables: {', '.join(sorted(desconocidos))}."
        )
    # Vaciar un campo opcional es valido (null lo borra); vaciar uno obligatorio
    # no. Sin esta comprobacion el error salia como un 400 generico que no
    # decia que campo era.
    vaciados = sorted(f for f in REQUIRED_FIELDS if f in changes and changes[f] is None)
    if vaciados:
        raise AppError(
            "BAD_REQUEST",
            f"Estos campos no pueden quedar vacios: {', '.join(vaciados)}.",
        )
    spec = ProjectSpec(**{**actual, **changes})
    nuevos = {k: v for k, v in spec.model_dump().items() if k in changes}
    repo.update(proj, **nuevos)
    return to_summary(proj, repo.campaigns_count(proj.id))
