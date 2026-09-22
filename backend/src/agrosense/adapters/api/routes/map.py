"""Endpoint del mapa del predio (E6).

Contrato (exige sesion; proyecto ajeno → 404):
    GET /projects/{project_id}/map → 200 ProjectMapResponse | 401 | 404 | 422

Es `def` y no `async def`: proyectar 856 puntos y armar el payload es trabajo
de CPU: sincrono, FastAPI lo manda al threadpool y no congela el event loop.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import ImageryLayerResponse, ProjectMapResponse
from agrosense.adapters.db.repository import (
    ImageryRepository,
    ProjectAnalysisRepository,
    ProjectRepository,
)
from agrosense.adapters.geo import MapBuilder
from agrosense.application.use_cases.project_imagery import list_imagery_layers
from agrosense.application.use_cases.project_map import get_project_map

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/projects/{project_id}/map", response_model=ProjectMapResponse)
def get_project_map_endpoint(
    project_id: int,
    session: SessionDep,
    engineer: CurrentEngineer,
) -> ProjectMapResponse:
    """Arboles, parcelas y encuadre del proyecto, en coordenadas WGS84."""
    try:
        project_repo = ProjectRepository(session)
        dto = get_project_map(
            project_id,
            engineer.id,
            project_repo,
            ProjectAnalysisRepository(session),
            MapBuilder(),
        )
        # Las capas viajan en la MISMA respuesta: el mapa se pide una vez
        capas = list_imagery_layers(
            project_id, engineer.id, project_repo, ImageryRepository(session)
        )
    except ValueError as exc:
        # UnsupportedSridError hereda de ValueError: un proyecto con un srid
        # que PROJ no conoce es un dato invalido, no un fallo del servidor.
        raise_for_value_error(exc)
    return ProjectMapResponse(
        project_id=dto.project_id,
        imagery=[ImageryLayerResponse(**vars(c)) for c in capas],
        **dto.payload,
    )
