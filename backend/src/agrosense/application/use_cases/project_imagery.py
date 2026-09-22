"""UC-MP2: Registrar la ortofoto de un proyecto (E6b).

El ingeniero pega la direccion de las teselas de su ortofoto y el mapa la
dibuja debajo de los arboles. AgroSense no guarda la imagen: guarda donde
esta (ADR-009).

Autorizacion: como en todo el proyecto, un proyecto ajeno responde igual que
uno inexistente. Y una capa se identifica SIEMPRE dentro de su proyecto: el
id suelto no da acceso.
"""
from __future__ import annotations

from agrosense.application.dtos import ImageryLayerDTO
from agrosense.application.errors import AppError
from agrosense.domain.imagery_rules import (
    InvalidImageryLayerError,
    normalize_opacity,
    validate_tile_template,
)


def _owned_project(project_repo, project_id: int, owner_id: str):
    project = project_repo.get_owned(project_id, owner_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", f"El proyecto {project_id} no existe.")
    return project


def _to_dto(row) -> ImageryLayerDTO:
    return ImageryLayerDTO(
        id=row.id,
        name=row.name,
        tile_template=row.tile_template,
        attribution=row.attribution,
        min_zoom=row.min_zoom,
        max_zoom=row.max_zoom,
        opacity=row.opacity,
    )


def list_imagery_layers(
    project_id: int, owner_id: str, project_repo, imagery_repo
) -> list[ImageryLayerDTO]:
    """Las capas de imagen del proyecto, en el orden en que se registraron."""
    _owned_project(project_repo, project_id, owner_id)
    return [_to_dto(r) for r in imagery_repo.list_for_project(project_id)]


def add_imagery_layer(
    project_id: int,
    owner_id: str,
    project_repo,
    imagery_repo,
    *,
    name: str,
    tile_template: str,
    attribution: str | None = None,
    min_zoom: int | None = None,
    max_zoom: int | None = None,
    opacity: float | None = None,
) -> ImageryLayerDTO:
    """Registra una capa.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "DUPLICATE_IMAGERY_LAYER")
        InvalidImageryLayerError: plantilla u opacidad invalidas (→ 422).
    """
    _owned_project(project_repo, project_id, owner_id)
    limpio = (name or "").strip()
    if not limpio:
        raise InvalidImageryLayerError("Póngale un nombre a la capa.")
    plantilla = validate_tile_template(tile_template)
    transparencia = normalize_opacity(opacity)
    if imagery_repo.name_taken(project_id, limpio):
        raise AppError(
            "DUPLICATE_IMAGERY_LAYER",
            f"El proyecto ya tiene una capa llamada «{limpio}».",
        )
    row = imagery_repo.create(
        project_id,
        name=limpio,
        tile_template=plantilla,
        attribution=(attribution or "").strip() or None,
        min_zoom=min_zoom,
        max_zoom=max_zoom,
        opacity=transparencia,
    )
    return _to_dto(row)


def remove_imagery_layer(
    project_id: int, layer_id: int, owner_id: str, project_repo, imagery_repo
) -> None:
    """Quita una capa del proyecto.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "IMAGERY_LAYER_NOT_FOUND")
    """
    _owned_project(project_repo, project_id, owner_id)
    layer = imagery_repo.get(project_id, layer_id)
    if layer is None:
        raise AppError("IMAGERY_LAYER_NOT_FOUND", "Esa capa de imagen no existe.")
    imagery_repo.delete(layer)
