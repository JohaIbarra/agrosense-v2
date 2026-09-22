"""Endpoints de un monitoreo del proyecto (E2 + E3).

Regla ADR-003: parsear → caso de uso → mapear respuesta. Autorizacion y
reglas (fechas en orden, monitoreo existente) viven en `application/`.

Contratos (todos exigen sesion; proyecto ajeno → 404):
    PATCH /projects/{project_id}/monitorings/{number}
          MonitoringUpdate → 200 MonitoringResponse | 404/422
    GET   /projects/{project_id}/monitorings/{number}/analysis
          → 200 MonitoringAnalysisResponse | 404
    GET   /projects/{project_id}/monitorings/{number}/report.xlsx
          → 200 application/vnd.openxmlformats-officedocument.spreadsheetml.sheet | 404

Los endpoints son `def` (no `async`): calcular el analisis o escribir el
.xlsx es trabajo de CPU bloqueante, y FastAPI solo lo manda al threadpool si
el endpoint es sincrono (leccion de v1, AGENTS.md).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from agrosense.adapters.analysis.engine import ExploratoryAnalysisEngine
from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import (
    MonitoringAnalysisResponse,
    MonitoringResponse,
    MonitoringUpdate,
)
from agrosense.adapters.db.repository import ProjectAnalysisRepository, ProjectRepository
from agrosense.adapters.report.xlsx import build_report, report_filename
from agrosense.application.use_cases.monitoring_analysis import (
    get_monitoring_analysis,
    get_report_data,
    update_monitoring,
)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
NumberPath = Annotated[int, Path(ge=1, le=1000, description="Numero de monitoreo (M1 = 1).")]

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.patch("/projects/{project_id}/monitorings/{number}", response_model=MonitoringResponse)
def update_monitoring_endpoint(
    project_id: int,
    number: NumberPath,
    body: MonitoringUpdate,
    session: SessionDep,
    engineer: CurrentEngineer,
) -> MonitoringResponse:
    """Registra la fecha o las notas de un monitoreo."""
    repo = ProjectRepository(session)
    try:
        dto = update_monitoring(
            project_id,
            number,
            engineer.id,
            repo,
            date.today(),
            **body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    # InvalidMonitoringDateError (DomainError) sube al handler global → 422
    counts = {m.number: n for m, n in repo.get_monitorings(project_id)}
    return MonitoringResponse(
        number=dto.number,
        monitoring_date=dto.monitoring_date,
        field_crew=dto.field_crew,
        recorder=dto.recorder,
        notes=dto.notes,
        observations=counts.get(dto.number, 0),
    )


@router.get(
    "/projects/{project_id}/monitorings/{number}/analysis",
    response_model=MonitoringAnalysisResponse,
)
def get_analysis_endpoint(
    project_id: int,
    number: NumberPath,
    session: SessionDep,
    engineer: CurrentEngineer,
) -> MonitoringAnalysisResponse:
    """Las 7 hojas del Anexo 1 calculadas para el monitoreo `number`."""
    try:
        dto = get_monitoring_analysis(
            project_id,
            number,
            engineer.id,
            ProjectRepository(session),
            ProjectAnalysisRepository(session),
            ExploratoryAnalysisEngine(),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    payload = dto.payload
    return MonitoringAnalysisResponse(
        project_id=dto.project_id,
        monitoring=dto.monitoring,
        monitoring_date=dto.monitoring_date,
        previous=payload.get("previous"),
        monitorings=payload.get("monitorings", []),
        properties=payload.get("properties", []),
        analysis_version=dto.analysis_version,
        input_hash=dto.input_hash,
        computed_at=dto.computed_at,
        summary=payload.get("summary", []),
        sections=payload.get("sections", []),
    )


@router.get(
    "/projects/{project_id}/monitorings/{number}/report.xlsx",
    response_class=Response,
    responses={200: {"content": {XLSX_MEDIA_TYPE: {}}, "description": "Reporte .xlsx"}},
)
def get_report_endpoint(
    project_id: int,
    number: NumberPath,
    session: SessionDep,
    engineer: CurrentEngineer,
) -> Response:
    """Reporte descargable: una hoja por analisis + resumen + datos crudos."""
    try:
        data = get_report_data(
            project_id,
            number,
            engineer.id,
            ProjectRepository(session),
            ProjectAnalysisRepository(session),
            ExploratoryAnalysisEngine(),
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return Response(
        content=build_report(data),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{report_filename(data)}"',
            "Cache-Control": "no-store",
        },
    )
