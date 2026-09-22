"""E2/E3: la carga fecha el monitoreo y deja el analisis calculado; el
analisis se lee por monitoreo y se recalcula si cambia la version del calculo.

Contra SQLite local (fixture `session`) con los repositorios y el motor
reales: lo que se prueba es la orquestacion completa, no un doble.
"""

from __future__ import annotations

from datetime import date

import pytest

from agrosense.adapters.analysis.engine import ANALYSIS_VERSION, ExploratoryAnalysisEngine
from agrosense.adapters.db.models import MonitoringAnalysisRow
from agrosense.adapters.db.repository import (
    CampaignRepository,
    ProjectAnalysisRepository,
    ProjectRepository,
)
from agrosense.application.dtos import CampaignData
from agrosense.application.errors import AppError
from agrosense.application.use_cases.monitoring_analysis import (
    get_monitoring_analysis,
    get_report_data,
    update_monitoring,
)
from agrosense.application.use_cases.upload_campaign import upload_campaign
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.errors import DomainError
from tests.auth.keys import ENGINEER_A as OWNER

TODAY = date(2026, 9, 22)


def _tree(tid, design="Rehabilitación vegetal"):
    return Tree(
        tree_id=tid,
        species="Senna viarum",
        locality="Guayabal",
        plot_id="1",
        sampling_unit_code="U1",
        floristic_design=design,
        associated_cover="Bosque de galería",
    )


def _obs(tid, m, h, alive=True):
    return Observation(
        tree_id=tid,
        campaign=m,
        height_m=h,
        crown_diameter_m=0.2,
        dap_cm=None,
        dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary="Bueno" if alive else None,
        alive=alive,
        colonization=None,
    )


class _Source:
    """Puerto CampaignSource: devuelve la campana ya construida."""

    def __init__(self, data: CampaignData):
        self._data = data

    def read(self, content: bytes, filename: str) -> CampaignData:
        return self._data


def _engine():
    return ExploratoryAnalysisEngine()


def _upload(session, project_id, data, content=b"x", monitoring_date=None):
    return upload_campaign(
        project_id=project_id,
        filename="m.xlsx",
        content=content,
        project_repo=ProjectRepository(session),
        campaign_repo=CampaignRepository(session),
        source=_Source(data),
        owner_id=OWNER,
        monitoring_date=monitoring_date,
        today=TODAY,
        analysis_repo=ProjectAnalysisRepository(session),
        engine=_engine(),
    )


def _analysis(session, project_id, number, owner=OWNER):
    return get_monitoring_analysis(
        project_id,
        number,
        owner,
        ProjectRepository(session),
        ProjectAnalysisRepository(session),
        _engine(),
    )


@pytest.fixture()
def project(session):
    return ProjectRepository(session).create("Restauracion", owner_id=OWNER)


M1 = CampaignData(
    trees=[_tree("T1"), _tree("T2")], observations=[_obs("T1", 1, 0.3), _obs("T2", 1, 0.4)]
)
M2 = CampaignData(
    trees=[_tree("T1"), _tree("T2")],
    observations=[_obs("T1", 2, 0.5), _obs("T2", 2, None, alive=False)],
)


def test_upload_dates_the_monitoring_and_computes_its_analysis(session, project):
    result = _upload(session, project.id, M1, monitoring_date=date(2025, 3, 1))
    assert result.analyzed == [1]
    assert ProjectRepository(session).get_monitoring(project.id, 1).monitoring_date == date(
        2025, 3, 1
    )

    analysis = _analysis(session, project.id, 1)
    assert analysis.monitoring == 1
    assert analysis.monitoring_date == date(2025, 3, 1)
    assert analysis.analysis_version == ANALYSIS_VERSION
    assert analysis.payload["previous"] is None


def test_second_monitoring_recomputes_both_and_compares(session, project):
    _upload(session, project.id, M1, content=b"m1", monitoring_date=date(2025, 3, 1))
    result = _upload(session, project.id, M2, content=b"m2", monitoring_date=date(2025, 9, 1))
    assert result.analyzed == [1, 2]
    analysis = _analysis(session, project.id, 2)
    assert analysis.payload["previous"] == 1
    summary = {s["key"]: s["value"] for s in analysis.payload["summary"]}
    assert (summary["alive"], summary["dead"]) == (1, 1)


def test_upload_rejects_a_date_out_of_order_before_writing(session, project):
    _upload(session, project.id, M1, content=b"m1", monitoring_date=date(2025, 3, 1))
    with pytest.raises(DomainError) as exc:
        _upload(session, project.id, M2, content=b"m2", monitoring_date=date(2025, 1, 1))
    assert exc.value.code == "INVALID_MONITORING_DATE"
    # Nada del M2 quedo guardado
    assert ProjectRepository(session).get_monitoring(project.id, 2) is None


def test_stale_snapshot_is_recomputed_on_read(session, project):
    _upload(session, project.id, M1)
    row = session.query(MonitoringAnalysisRow).one()
    row.analysis_version = "vieja"
    row.payload = {"obsoleto": True}
    session.commit()
    analysis = _analysis(session, project.id, 1)
    assert analysis.analysis_version == ANALYSIS_VERSION
    assert "sections" in analysis.payload


def test_analysis_of_another_engineers_project_is_not_found(session, project):
    _upload(session, project.id, M1)
    with pytest.raises(AppError) as exc:
        _analysis(session, project.id, 1, owner="otro-ingeniero")
    assert exc.value.code == "PROJECT_NOT_FOUND"


def test_missing_monitoring_is_not_found(session, project):
    _upload(session, project.id, M1)
    with pytest.raises(AppError) as exc:
        _analysis(session, project.id, 3)
    assert exc.value.code == "MONITORING_NOT_FOUND"


def test_update_monitoring_date_validates_order(session, project):
    _upload(session, project.id, M1, content=b"m1", monitoring_date=date(2025, 3, 1))
    _upload(session, project.id, M2, content=b"m2", monitoring_date=date(2025, 9, 1))
    repo = ProjectRepository(session)
    dto = update_monitoring(
        project.id, 1, OWNER, repo, TODAY, monitoring_date=date(2025, 2, 1), notes="Lluvias"
    )
    assert (dto.monitoring_date, dto.notes) == (date(2025, 2, 1), "Lluvias")
    with pytest.raises(DomainError):
        update_monitoring(project.id, 1, OWNER, repo, TODAY, monitoring_date=date(2025, 10, 1))


def test_report_data_carries_raw_data_up_to_the_monitoring(session, project):
    _upload(session, project.id, M1, content=b"m1")
    _upload(session, project.id, M2, content=b"m2")
    data = get_report_data(
        project.id,
        1,
        OWNER,
        ProjectRepository(session),
        ProjectAnalysisRepository(session),
        _engine(),
    )
    assert {o.campaign for o in data.observations} == {1}
    assert len(data.trees) == 2
    assert data.project_name == "Restauracion"
