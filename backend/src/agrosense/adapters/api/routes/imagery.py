"""Capas de imagen de un proyecto (E6b).

Contratos (todos exigen sesion; proyecto ajeno → 404):
    GET    /projects/{project_id}/imagery        → 200 [ImageryLayerResponse]
    POST   /projects/{project_id}/imagery        → 201 ImageryLayerResponse
                                                   | 409 | 422
    DELETE /projects/{project_id}/imagery/{id}   → 204 | 404

AgroSense guarda DONDE esta la ortofoto, no la ortofoto (ADR-009).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import ImageryLayerCreate, ImageryLayerResponse
from agrosense.adapters.db.repository import ImageryRepository, ProjectRepository
from agrosense.application.use_cases.project_imagery import (
    add_imagery_layer,
    list_imagery_layers,
    remove_imagery_layer,
)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/projects/{project_id}/imagery", response_model=list[ImageryLayerResponse])
def list_imagery_endpoint(
    project_id: int, session: SessionDep, engineer: CurrentEngineer
) -> list[ImageryLayerResponse]:
    """Las capas de imagen registradas en el proyecto."""
    try:
        capas = list_imagery_layers(
            project_id, engineer.id, ProjectRepository(session), ImageryRepository(session)
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return [ImageryLayerResponse(**vars(c)) for c in capas]


@router.post(
    "/projects/{project_id}/imagery",
    response_model=ImageryLayerResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_imagery_endpoint(
    project_id: int,
    body: ImageryLayerCreate,
    session: SessionDep,
    engineer: CurrentEngineer,
) -> ImageryLayerResponse:
    """Registra la ortofoto del proyecto como plantilla de teselas."""
    try:
        capa = add_imagery_layer(
            project_id,
            engineer.id,
            ProjectRepository(session),
            ImageryRepository(session),
            **body.model_dump(),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    # InvalidImageryLayerError (DomainError) sube al handler global → 422
    return ImageryLayerResponse(**vars(capa))


@router.delete(
    "/projects/{project_id}/imagery/{layer_id}", status_code=status.HTTP_204_NO_CONTENT
)
def remove_imagery_endpoint(
    project_id: int, layer_id: int, session: SessionDep, engineer: CurrentEngineer
) -> Response:
    """Quita una capa del proyecto (la imagen sigue donde estaba)."""
    try:
        remove_imagery_layer(
            project_id,
            layer_id,
            engineer.id,
            ProjectRepository(session),
            ImageryRepository(session),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
