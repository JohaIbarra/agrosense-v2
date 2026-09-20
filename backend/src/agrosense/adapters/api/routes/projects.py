"""Endpoints del slice 2 (UC1/UC2 + reads).

Regla ADR-003: las routes parsean → llaman application/ → mapean respuesta.
Cero logica de negocio aqui.

Contratos:
    POST   /projects                               → 201 ProjectResponse
    GET    /projects/{project_id}                  → 200 ProjectResponse | 404
    POST   /projects/{project_id}/campaigns        → 201 UploadResultResponse | 400/404/409/422
    GET    /projects/{project_id}/campaigns        → 200 list[CampaignResponse] | 404
    GET    /projects/{project_id}/trees            → 200 list[TreeRowResponse] | 404
    GET    /projects/{project_id}/trees/{tree_row_id}/observations
                                                   → 200 list[ObservationResponse] | 404
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import (
    CampaignResponse,
    ObservationResponse,
    ProjectCreate,
    ProjectResponse,
    TreeRowResponse,
    UploadResultResponse,
)
from agrosense.adapters.db.repository import CampaignRepository, ProjectRepository
from agrosense.application.use_cases.create_project import create_project
from agrosense.application.use_cases.upload_campaign import upload_campaign

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


# ── UC1: Crear proyecto ────────────────────────────────────────────────────

@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project_endpoint(body: ProjectCreate, session: SessionDep) -> ProjectResponse:
    repo = ProjectRepository(session)
    try:
        return create_project(
            repo=repo,
            name=body.name,
            locality=body.locality,
            description=body.description,
        )
    except ValueError as exc:
        raise_for_value_error(exc)


# ── Leer proyecto ──────────────────────────────────────────────────────────

@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project_endpoint(project_id: int, session: SessionDep) -> ProjectResponse:
    repo = ProjectRepository(session)
    proj = repo.get(project_id)
    if proj is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": f"Proyecto {project_id} no existe"},
        )
    return ProjectResponse(
        id=proj.id,
        name=proj.name,
        locality=proj.locality,
        description=proj.description,
        created_at=proj.created_at,
        campaigns_count=repo.campaigns_count(proj.id),
    )


# ── UC2: Cargar campaña ────────────────────────────────────────────────────

@router.post(
    "/projects/{project_id}/campaigns",
    response_model=UploadResultResponse,
    status_code=201,
)
async def upload_campaign_endpoint(
    project_id: int,
    file: UploadFile,
    session: SessionDep,
) -> UploadResultResponse:
    content = await file.read()
    proj_repo = ProjectRepository(session)
    camp_repo = CampaignRepository(session)
    try:
        return upload_campaign(
            project_id=project_id,
            filename=file.filename or "upload.xlsx",
            content=content,
            project_repo=proj_repo,
            campaign_repo=camp_repo,
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    # DomainError sube al handler global registrado en app.py → 422


# ── Listar campañas ────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/campaigns", response_model=list[CampaignResponse])
def list_campaigns_endpoint(
    project_id: int, session: SessionDep
) -> list[CampaignResponse]:
    repo = ProjectRepository(session)
    if repo.get(project_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": f"Proyecto {project_id} no existe"},
        )
    campaigns = repo.get_campaigns(project_id)
    return [
        CampaignResponse(
            id=c.id,
            project_id=c.project_id,
            filename=c.filename,
            mapping_version=c.mapping_version,
            ingested_at=c.ingested_at,
            trees=c.trees,
            observations=c.observations,
            deaths=c.deaths,
        )
        for c in campaigns
    ]


# ── Listar árboles (paginado) ──────────────────────────────────────────────

@router.get("/projects/{project_id}/trees", response_model=list[TreeRowResponse])
def list_trees_endpoint(
    project_id: int,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TreeRowResponse]:
    repo = ProjectRepository(session)
    if repo.get(project_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": f"Proyecto {project_id} no existe"},
        )
    trees = repo.get_trees(project_id, limit=limit, offset=offset)
    return [
        TreeRowResponse(
            id=t.id,
            tree_id=t.tree_id,
            species=t.species,
            family=t.family,
            common_name=t.common_name,
            guild=t.guild,
            locality=t.locality,
            elevation_m=t.elevation_m,
        )
        for t in trees
    ]


# ── Observaciones de un árbol ──────────────────────────────────────────────

@router.get(
    "/projects/{project_id}/trees/{tree_row_id}/observations",
    response_model=list[ObservationResponse],
)
def list_observations_endpoint(
    project_id: int,
    tree_row_id: int,
    session: SessionDep,
) -> list[ObservationResponse]:
    repo = ProjectRepository(session)
    tree = repo.get_tree_row(project_id, tree_row_id)
    if tree is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "TREE_NOT_FOUND",
                "message": f"Árbol {tree_row_id} no encontrado en proyecto {project_id}",
            },
        )
    obs_rows = repo.get_observations(tree_row_id)
    return [
        ObservationResponse(
            campaign=o.campaign,
            height_m=o.height_m,
            crown_diameter_m=o.crown_diameter_m,
            dap_cm=o.dap_cm,
            dap_status=o.dap_status,
            phytosanitary=o.phytosanitary,
            alive=o.alive,
            colonization=o.colonization,
        )
        for o in obs_rows
    ]
