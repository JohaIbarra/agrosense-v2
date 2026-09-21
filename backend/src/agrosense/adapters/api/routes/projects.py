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
    GET    /projects/{project_id}/monitorings      → 200 list[MonitoringResponse] | 404  (E0)
"""
from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import (
    CampaignResponse,
    MonitoringResponse,
    ObservationResponse,
    ProjectCreate,
    ProjectResponse,
    TreeRowResponse,
    UploadResultResponse,
    WarningItem,
)
from agrosense.adapters.db.repository import CampaignRepository, ProjectRepository
from agrosense.adapters.ingester.excel_source import ExcelCampaignSource
from agrosense.application.dtos import ProjectSummary, UploadResult
from agrosense.application.errors import AppError
from agrosense.application.use_cases.create_project import create_project
from agrosense.application.use_cases.upload_campaign import upload_campaign

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]

# Techo del cuerpo del upload (AGENTS.md: "file uploads are validated").
# El dataset de referencia pesa ~200 KB; 10 MB deja margen de sobra para
# proyectos mayores sin permitir que una sola request agote la RAM del
# free tier. Las guardas de FORMATO (zip, bomba) viven en el adapter que
# entiende el formato, no aqui.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024

# Ancho de la columna `campaign_files.filename`
_FILENAME_MAX = 500


def _read_capped(upload: UploadFile) -> bytes:
    """Lee el cuerpo abortando en cuanto supera el techo.

    Se lee por trozos a proposito: confiar en `Content-Length` deja que el
    cliente mienta, y `await file.read()` sin limite era el hallazgo R4.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = upload.file.read(_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise AppError(
                "FILE_TOO_LARGE",
                f"El archivo supera el limite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_filename(raw: str | None) -> str:
    """Deja el nombre en algo seguro de persistir, sin perder la provenance.

    Quita componentes de ruta y caracteres de control, y lo acota al ancho de
    la columna (en Postgres un nombre mas largo seria un 500 por truncamiento).
    No se escapa HTML: la respuesta es JSON y escapar es trabajo de quien
    renderice.
    """
    name = (raw or "").replace("\\", "/")
    name = os.path.basename(name)
    name = "".join(ch for ch in name if ch.isprintable())
    return name.strip()[:_FILENAME_MAX] or "upload.xlsx"


# ── Mapeo DTO de application/ -> schema del contrato (ADR-003) ─────────────
# El use case no conoce estos schemas; traducir es trabajo del adapter.

def _to_project_response(dto: ProjectSummary) -> ProjectResponse:
    return ProjectResponse(
        id=dto.id,
        name=dto.name,
        locality=dto.locality,
        description=dto.description,
        created_at=dto.created_at,
        campaigns_count=dto.campaigns_count,
    )


def _to_upload_response(dto: UploadResult) -> UploadResultResponse:
    return UploadResultResponse(
        valid=dto.valid,
        campaign_id=dto.campaign_id,
        trees=dto.trees,
        observations=dto.observations,
        deaths=dto.deaths,
        warnings=[
            WarningItem(type=w.type, tree_id=w.tree_id, message=w.message)
            for w in dto.warnings
        ],
        errors=[],
        monitorings=dto.monitorings,
    )


# ── UC1: Crear proyecto ────────────────────────────────────────────────────

@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project_endpoint(body: ProjectCreate, session: SessionDep) -> ProjectResponse:
    repo = ProjectRepository(session)
    try:
        dto = create_project(
            repo=repo,
            name=body.name,
            locality=body.locality,
            description=body.description,
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return _to_project_response(dto)


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
def upload_campaign_endpoint(
    project_id: int,
    file: UploadFile,
    session: SessionDep,
) -> UploadResultResponse:
    """Sube una campaña de monitoreo.

    Es `def` y no `async def` a propósito (hallazgo R3): el parseo y las
    escrituras son bloqueantes y duran decenas de segundos. FastAPI solo
    despacha al threadpool los endpoints síncronos; como corrutina, este
    trabajo congelaba el event loop y el worker dejaba de atender cualquier
    otra request. Es la tercera lección de v1 en AGENTS.md.
    """
    proj_repo = ProjectRepository(session)
    camp_repo = CampaignRepository(session)
    try:
        content = _read_capped(file)
        dto = upload_campaign(
            project_id=project_id,
            filename=_safe_filename(file.filename),
            content=content,
            project_repo=proj_repo,
            campaign_repo=camp_repo,
            source=ExcelCampaignSource(),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    # DomainError sube al handler global registrado en app.py → 422
    return _to_upload_response(dto)


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
            plot_id=t.plot_id,
            sampling_unit_code=t.sampling_unit_code,
            monitoring_unit=t.monitoring_unit,
            floristic_design=t.floristic_design,
            associated_cover=t.associated_cover,
            establishment_cover=t.establishment_cover,
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


# ── Monitoreos del proyecto (E0) ───────────────────────────────────────────

@router.get("/projects/{project_id}/monitorings", response_model=list[MonitoringResponse])
def list_monitorings_endpoint(project_id: int, session: SessionDep) -> list[MonitoringResponse]:
    repo = ProjectRepository(session)
    if repo.get(project_id) is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND", "message": f"Proyecto {project_id} no existe"},
        )
    return [
        MonitoringResponse(
            number=m.number,
            monitoring_date=m.monitoring_date,
            field_crew=m.field_crew,
            recorder=m.recorder,
            observations=n,
        )
        for m, n in repo.get_monitorings(project_id)
    ]
