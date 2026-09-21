"""Perfil del ingeniero autenticado y catalogos del dominio (E1, ADR-006).

    GET /api/v1/me        → 200 EngineerResponse | 401
    PUT /api/v1/me        → 200 EngineerResponse | 401 | 422
    GET /api/v1/catalogs  → 200 CatalogsResponse | 401

Los catalogos existen para que el frontend NO duplique los vocabularios del
dominio (AGENTS.md): el formulario de proyecto ofrece exactamente los valores
que `domain/project.py` acepta.

El perfil se crea solo en la primera peticion autenticada; estas rutas lo
leen y lo completan (nombre, matricula profesional, organizacion).
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.schemas import CatalogsResponse, EngineerResponse, EngineerUpdate
from agrosense.adapters.db.repository import EngineerRepository
from agrosense.application.use_cases.engineers import update_profile
from agrosense.domain.project import (
    DEFAULT_SRID,
    INTERVENTION_TYPES,
    LEGAL_FRAMEWORKS,
    PROJECT_STATUSES,
)

router = APIRouter(prefix="/api/v1", tags=["perfil"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/me", response_model=EngineerResponse)
def get_me(engineer: CurrentEngineer) -> EngineerResponse:
    return EngineerResponse(**asdict(engineer))


@router.put("/me", response_model=EngineerResponse)
def update_me(
    body: EngineerUpdate, session: SessionDep, engineer: CurrentEngineer
) -> EngineerResponse:
    dto = update_profile(
        EngineerRepository(session), engineer.id, **body.model_dump(exclude_unset=True)
    )
    return EngineerResponse(**asdict(dto))


@router.get("/catalogs", response_model=CatalogsResponse)
def get_catalogs(engineer: CurrentEngineer) -> CatalogsResponse:
    return CatalogsResponse(
        intervention_types=list(INTERVENTION_TYPES),
        legal_frameworks=list(LEGAL_FRAMEWORKS),
        project_statuses=list(PROJECT_STATUSES),
        default_srid=DEFAULT_SRID,
    )
