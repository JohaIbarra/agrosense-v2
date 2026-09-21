"""Endpoints de proyectos (slice 2 + E0 + E1).

Regla ADR-003: las routes parsean → llaman application/ → mapean respuesta.
Cero logica de negocio aqui: la autorizacion (un ingeniero solo ve lo suyo)
vive en los casos de uso.

AUTH (E1, ADR-006): todas las rutas exigen un token de Supabase Auth
(`Authorization: Bearer …`) → 401 si falta o no es valido. Un proyecto de
otro ingeniero responde 404, igual que uno inexistente.

Contratos:
    GET    /projects                               → 200 list[ProjectResponse]  (E1)
    POST   /projects                               → 201 ProjectResponse | 409/422
    GET    /projects/{project_id}                  → 200 ProjectResponse | 404
    PATCH  /projects/{project_id}                  → 200 ProjectResponse | 404/409/422  (E1)
    POST   /projects/{project_id}/campaigns        → 201 UploadResultResponse | 400/404/409/422
    GET    /projects/{project_id}/campaigns        → 200 list[CampaignResponse] | 404
    GET    /projects/{project_id}/trees            → 200 list[TreeRowResponse] | 404
    GET    /projects/{project_id}/trees/{tree_row_id}/observations
                                                   → 200 list[ObservationResponse] | 404
    GET    /projects/{project_id}/monitorings      → 200 list[MonitoringResponse] | 404  (E0)
"""
from __future__ import annotations

import os
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import (
    CampaignResponse,
    MonitoringResponse,
    ObservationResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    TreeRowResponse,
    UploadResultResponse,
    WarningItem,
)
from agrosense.adapters.db.repository import CampaignRepository, ProjectRepository
from agrosense.adapters.ingester.excel_source import ExcelCampaignSource
from agrosense.application.dtos import EngineerDTO, ProjectSummary, UploadResult
from agrosense.application.errors import AppError
from agrosense.application.use_cases.create_project import (
    create_project,
    get_owned_project,
    get_project,
    list_projects,
    update_project,
)
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
    return ProjectResponse(**asdict(dto))


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


def _owned(repo: ProjectRepository, engineer: EngineerDTO, project_id: int):
    """El proyecto del ingeniero, o 404 con la forma del contrato."""
    try:
        return get_owned_project(repo, engineer.id, project_id)
    except ValueError as exc:
        raise_for_value_error(exc)


# ── Proyectos del ingeniero (UC1 + E1) ─────────────────────────────────────

@router.get("/projects", response_model=list[ProjectResponse])
def list_projects_endpoint(
    session: SessionDep, engineer: CurrentEngineer
) -> list[ProjectResponse]:
    """Los proyectos del ingeniero autenticado, y solo esos."""
    return [_to_project_response(p) for p in list_projects(ProjectRepository(session), engineer.id)]


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project_endpoint(
    body: ProjectCreate, session: SessionDep, engineer: CurrentEngineer
) -> ProjectResponse:
    try:
        dto = create_project(
            ProjectRepository(session), engineer.id, **body.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    # InvalidProjectError (DomainError) sube al handler global → 422
    return _to_project_response(dto)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project_endpoint(
    project_id: int, session: SessionDep, engineer: CurrentEngineer
) -> ProjectResponse:
    try:
        dto = get_project(ProjectRepository(session), engineer.id, project_id)
    except ValueError as exc:
        raise_for_value_error(exc)
    return _to_project_response(dto)


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
def update_project_endpoint(
    project_id: int, body: ProjectUpdate, session: SessionDep, engineer: CurrentEngineer
) -> ProjectResponse:
    """Edita solo los campos presentes en el cuerpo."""
    try:
        dto = update_project(
            ProjectRepository(session),
            engineer.id,
            project_id,
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return _to_project_response(dto)


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
    engineer: CurrentEngineer,
) -> UploadResultResponse:
    """Sube una campaña de monitoreo a un proyecto del ingeniero.

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
            owner_id=engineer.id,
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    # DomainError sube al handler global registrado en app.py → 422
    return _to_upload_response(dto)


# ── Listar campañas ────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/campaigns", response_model=list[CampaignResponse])
def list_campaigns_endpoint(
    project_id: int, session: SessionDep, engineer: CurrentEngineer
) -> list[CampaignResponse]:
    repo = ProjectRepository(session)
    _owned(repo, engineer, project_id)
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
        for c in repo.get_campaigns(project_id)
    ]


# ── Listar árboles (paginado) ──────────────────────────────────────────────

@router.get("/projects/{project_id}/trees", response_model=list[TreeRowResponse])
def list_trees_endpoint(
    project_id: int,
    session: SessionDep,
    engineer: CurrentEngineer,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TreeRowResponse]:
    repo = ProjectRepository(session)
    _owned(repo, engineer, project_id)
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
        for t in repo.get_trees(project_id, limit=limit, offset=offset)
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
    engineer: CurrentEngineer,
) -> list[ObservationResponse]:
    repo = ProjectRepository(session)
    _owned(repo, engineer, project_id)
    if repo.get_tree_row(project_id, tree_row_id) is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "TREE_NOT_FOUND",
                "message": f"Árbol {tree_row_id} no encontrado en proyecto {project_id}",
            },
        )
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
        for o in repo.get_observations(tree_row_id)
    ]


# ── Monitoreos del proyecto (E0) ───────────────────────────────────────────

@router.get("/projects/{project_id}/monitorings", response_model=list[MonitoringResponse])
def list_monitorings_endpoint(
    project_id: int, session: SessionDep, engineer: CurrentEngineer
) -> list[MonitoringResponse]:
    repo = ProjectRepository(session)
    _owned(repo, engineer, project_id)
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
