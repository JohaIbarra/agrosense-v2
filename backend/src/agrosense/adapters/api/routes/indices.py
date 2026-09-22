"""Indices espectrales por predio (E10a).

Contratos (exigen sesion; proyecto ajeno → 404):
    GET  /projects/{project_id}/indices/{index}
         → 200 ProjectIndexResponse   (lo guardado; no sale a la red)
    POST /projects/{project_id}/indices/{index}/refresh
         → 200 IndexRefreshResponse | 422 | 503

Separar leer de refrescar es deliberado: abrir la pantalla debe ser
instantaneo y no depender de un tercero; salir a buscar imagenes nuevas es
una accion que el ingeniero pide a proposito y que puede tardar.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import IndexRefreshResponse, ProjectIndexResponse
from agrosense.adapters.db.repository import (
    ProjectAnalysisRepository,
    ProjectRepository,
    SatelliteIndexRepository,
)
from agrosense.adapters.geo import PropertyOutlineBuilder
from agrosense.adapters.satellite.planetary_computer import PlanetaryComputerIndexSource
from agrosense.application.use_cases.project_index import (
    DEFAULT_MAX_SCENES,
    MAX_SCENES_LIMIT,
    get_project_index,
    refresh_project_index,
)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]

# Ventana por defecto de una consulta nueva: un ano hacia atras, que es lo que
# hace falta para ver una temporada seca y una lluviosa.
DEFAULT_WINDOW_DAYS = 365


def _payload(dto, resumen: dict | None = None) -> dict:
    return {
        "project_id": dto.project_id,
        "index": dto.index,
        "properties": dto.properties,
        "last_refreshed_at": dto.last_refreshed_at,
        "readings": [vars(r) for r in dto.readings],
        **({"summary": resumen} if resumen is not None else {}),
    }


@router.get(
    "/projects/{project_id}/indices/{index}", response_model=ProjectIndexResponse
)
def get_index_endpoint(
    project_id: int, index: str, session: SessionDep, engineer: CurrentEngineer
) -> ProjectIndexResponse:
    """La serie guardada del índice, sin consultar al proveedor."""
    try:
        dto = get_project_index(
            project_id,
            engineer.id,
            index,
            ProjectRepository(session),
            SatelliteIndexRepository(session),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return ProjectIndexResponse(**_payload(dto))


@router.post(
    "/projects/{project_id}/indices/{index}/refresh", response_model=IndexRefreshResponse
)
def refresh_index_endpoint(
    project_id: int,
    index: str,
    session: SessionDep,
    engineer: CurrentEngineer,
    start: Annotated[date | None, Query(description="Inicio de la ventana.")] = None,
    end: Annotated[date | None, Query(description="Fin de la ventana.")] = None,
    max_scenes: Annotated[
        int, Query(ge=1, le=MAX_SCENES_LIMIT, description="Tope de escenas a medir.")
    ] = DEFAULT_MAX_SCENES,
) -> IndexRefreshResponse:
    """Busca imágenes nuevas y mide el índice en cada predio del proyecto."""
    hoy = date.today()
    hasta = end or hoy
    desde = start or (hasta - timedelta(days=DEFAULT_WINDOW_DAYS))
    try:
        dto, resumen = refresh_project_index(
            project_id,
            engineer.id,
            index,
            desde,
            hasta,
            hoy,
            ProjectRepository(session),
            ProjectAnalysisRepository(session),
            SatelliteIndexRepository(session),
            PlanetaryComputerIndexSource(),
            PropertyOutlineBuilder(),
            max_scenes=max_scenes,
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return IndexRefreshResponse(**_payload(dto, resumen))
