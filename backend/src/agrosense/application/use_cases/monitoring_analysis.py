"""Casos de uso del analisis exploratorio por monitoreo (E3) y de la fecha
del monitoreo (E2).

UC-AN1  Calcular el analisis exploratorio de un monitoreo.
UC-M2   Registrar la fecha de un monitoreo.

El MOTOR se inyecta por parametro, igual que los repositorios (ADR-003: sin
puerto donde no hay variacion real; docs/04 §7). Debe ofrecer:

    engine.version                       -> str
    engine.fingerprint(trees, obs)       -> str   (huella de los datos)
    engine.analyze(trees, obs, number)   -> dict  (payload JSON)

Autorizacion: como en todo el proyecto, un proyecto ajeno responde igual que
uno inexistente (PROJECT_NOT_FOUND).
"""
from __future__ import annotations

from datetime import date

from agrosense.application.dtos import AnalysisDTO, MonitoringDTO, ReportData
from agrosense.application.errors import AppError
from agrosense.domain.analysis_rules import validate_monitoring_date


def _owned_project(project_repo, project_id: int, owner_id: str):
    project = project_repo.get_owned(project_id, owner_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", f"El proyecto {project_id} no existe.")
    return project


def _monitoring(project_repo, project_id: int, number: int):
    monitoring = project_repo.get_monitoring(project_id, number)
    if monitoring is None:
        raise AppError(
            "MONITORING_NOT_FOUND",
            f"El proyecto no tiene el monitoreo M{number}. Cargue su Excel primero.",
        )
    return monitoring


def refresh_project_analyses(project_id: int, analysis_repo, engine) -> list[int]:
    """Recalcula el analisis de TODOS los monitoreos del proyecto.

    Todos y no solo los del ultimo archivo: una carga puede corregir valores
    de monitoreos anteriores, y el analisis de Mk depende de Mk-1. Cuesta
    menos de un segundo por monitoreo, por eso corre dentro de la carga
    (ADR-008); si deja de ser asi, pasa a la cola de trabajos (ADR-009).
    """
    trees, observations = analysis_repo.load_dataset(project_id)
    numbers = sorted({o.campaign for o in observations})
    if not numbers:
        return []
    fingerprint = engine.fingerprint(trees, observations)
    snapshots = {n: engine.analyze(trees, observations, n) for n in numbers}
    analysis_repo.save_snapshots(project_id, snapshots, engine.version, fingerprint)
    return numbers


def _to_dto(project_id: int, monitoring, snapshot) -> AnalysisDTO:
    return AnalysisDTO(
        project_id=project_id,
        monitoring=monitoring.number,
        monitoring_date=monitoring.monitoring_date,
        analysis_version=snapshot.analysis_version,
        input_hash=snapshot.input_hash,
        computed_at=snapshot.computed_at,
        payload=snapshot.payload,
    )


def get_monitoring_analysis(
    project_id: int,
    number: int,
    owner_id: str,
    project_repo,
    analysis_repo,
    engine,
) -> AnalysisDTO:
    """El analisis del monitoreo `number`.

    Si no hay snapshot, o lo produjo otra version del calculo, se recalcula
    antes de responder: nunca se sirve un resultado de una definicion vieja.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "MONITORING_NOT_FOUND")
    """
    _owned_project(project_repo, project_id, owner_id)
    monitoring = _monitoring(project_repo, project_id, number)
    snapshot = analysis_repo.get_snapshot(project_id, number)
    if snapshot is None or snapshot.analysis_version != engine.version:
        refresh_project_analyses(project_id, analysis_repo, engine)
        snapshot = analysis_repo.get_snapshot(project_id, number)
    if snapshot is None:
        # El monitoreo existe pero ningun arbol tiene observacion en el
        raise AppError(
            "MONITORING_NOT_FOUND", f"El monitoreo M{number} no tiene observaciones."
        )
    return _to_dto(project_id, monitoring, snapshot)


def get_report_data(
    project_id: int,
    number: int,
    owner_id: str,
    project_repo,
    analysis_repo,
    engine,
) -> ReportData:
    """El analisis de Mk mas los datos crudos de M1..Mk para el reporte .xlsx."""
    project = _owned_project(project_repo, project_id, owner_id)
    analysis = get_monitoring_analysis(
        project_id, number, owner_id, project_repo, analysis_repo, engine
    )
    trees, observations = analysis_repo.load_dataset(project_id)
    return ReportData(
        project_name=project.name,
        project_code=getattr(project, "project_code", None),
        analysis=analysis,
        trees=trees,
        observations=[o for o in observations if o.campaign <= number],
        monitoring_dates=project_repo.monitoring_dates(project_id),
    )


def update_monitoring(
    project_id: int,
    number: int,
    owner_id: str,
    project_repo,
    today: date,
    **fields,
) -> MonitoringDTO:
    """Registra la fecha (y notas) de un monitoreo.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "MONITORING_NOT_FOUND")
        InvalidMonitoringDateError: fecha futura o fuera de orden (→ 422).
    """
    _owned_project(project_repo, project_id, owner_id)
    monitoring = _monitoring(project_repo, project_id, number)
    new_date = fields.get("monitoring_date")
    if new_date is not None:
        validate_monitoring_date(
            number, new_date, project_repo.monitoring_dates(project_id), today
        )
    monitoring = project_repo.update_monitoring(monitoring, **fields)
    return to_monitoring_dto(monitoring)


def to_monitoring_dto(monitoring) -> MonitoringDTO:
    return MonitoringDTO(
        number=monitoring.number,
        monitoring_date=monitoring.monitoring_date,
        field_crew=monitoring.field_crew,
        recorder=monitoring.recorder,
        notes=monitoring.notes,
    )
