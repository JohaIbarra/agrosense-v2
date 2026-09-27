"""UC-IA1/UC-IA2: generar y leer el borrador de informe con IA (E9).

Contra SQLite local con los repositorios y el motor reales: lo que se
prueba es la orquestacion (snapshot -> figuras -> LLM -> guardia ->
guardar), con un LLMClient de mentira -- nunca se sale a la red (AGENTS.md,
Testing).
"""
from __future__ import annotations

from datetime import date

import pytest

from agrosense.adapters.analysis.engine import ExploratoryAnalysisEngine
from agrosense.adapters.db.repository import (
    AIReportRepository,
    CampaignRepository,
    ProjectAnalysisRepository,
    ProjectRepository,
)
from agrosense.application.dtos import CampaignData
from agrosense.application.errors import AppError
from agrosense.application.use_cases.ai_report import (
    PROMPT_VERSION,
    generate_ai_report,
    get_ai_report,
)
from agrosense.application.use_cases.upload_campaign import upload_campaign
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from tests.auth.keys import ENGINEER_A as OWNER

TODAY = date(2026, 9, 22)


def _tree(tid):
    return Tree(
        tree_id=tid, species="Senna viarum", locality="Guayabal", plot_id="1",
        sampling_unit_code="U1", floristic_design="Rehabilitación vegetal",
        associated_cover="Bosque de galería",
    )


def _obs(tid, m, h, alive=True):
    return Observation(
        tree_id=tid, campaign=m, height_m=h, crown_diameter_m=0.2, dap_cm=None,
        dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary="Bueno" if alive else None, alive=alive, colonization=None,
    )


class _Source:
    """Puerto CampaignSource: devuelve la campana ya construida."""

    def __init__(self, data: CampaignData):
        self._data = data

    def read(self, content: bytes, filename: str) -> CampaignData:
        return self._data


class FakeLLMClient:
    model_name = "fake-llm-test"

    def __init__(self, response: str):
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt: str, system: str) -> str:
        self.calls.append((prompt, system))
        return self._response


M1 = CampaignData(
    trees=[_tree("T1"), _tree("T2")], observations=[_obs("T1", 1, 0.3), _obs("T2", 1, 0.4)]
)


def _upload(session, project_id, data, content=b"m1", monitoring_date=date(2025, 3, 1)):
    return upload_campaign(
        project_id=project_id, filename="m.xlsx", content=content,
        project_repo=ProjectRepository(session), campaign_repo=CampaignRepository(session),
        source=_Source(data), owner_id=OWNER, monitoring_date=monitoring_date, today=TODAY,
        analysis_repo=ProjectAnalysisRepository(session), engine=ExploratoryAnalysisEngine(),
    )


@pytest.fixture()
def project(session):
    return ProjectRepository(session).create("Restauracion", owner_id=OWNER)


def _repos(session):
    return (
        ProjectRepository(session), ProjectAnalysisRepository(session),
        AIReportRepository(session), ExploratoryAnalysisEngine(),
    )


def test_generate_saves_the_draft_and_reads_it_back(session, project):
    _upload(session, project.id, M1)
    project_repo, analysis_repo, report_repo, engine = _repos(session)
    llm = FakeLLMClient(
        "Borrador generado por IA: revise las cifras antes de usarlo.\n\nHay 2 árboles."
    )

    dto = generate_ai_report(
        project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine, llm
    )
    assert dto.model_name == "fake-llm-test"
    assert dto.prompt_version == PROMPT_VERSION
    assert dto.stale is False

    leido = get_ai_report(project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine)
    assert leido.content == dto.content
    assert leido.stale is False


def test_reading_before_generating_is_not_found(session, project):
    _upload(session, project.id, M1)
    project_repo, analysis_repo, report_repo, engine = _repos(session)
    with pytest.raises(AppError) as exc:
        get_ai_report(project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine)
    assert exc.value.code == "AI_REPORT_NOT_FOUND"


def test_a_number_the_model_invented_is_flagged_as_unverified(session, project):
    _upload(session, project.id, M1)
    project_repo, analysis_repo, report_repo, engine = _repos(session)
    llm = FakeLLMClient(
        "Borrador generado por IA: revise las cifras antes de usarlo.\n\n"
        "Sobrevivieron el 150%."
    )

    dto = generate_ai_report(
        project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine, llm
    )
    assert "150%" in dto.unverified_numbers


def test_regenerating_replaces_the_previous_draft(session, project):
    _upload(session, project.id, M1)
    project_repo, analysis_repo, report_repo, engine = _repos(session)
    generate_ai_report(
        project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine,
        FakeLLMClient("primero"),
    )
    dto = generate_ai_report(
        project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine,
        FakeLLMClient("segundo"),
    )
    assert dto.content == "segundo"

    leido = get_ai_report(project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine)
    assert leido.content == "segundo"


def test_a_recalculated_snapshot_makes_the_saved_draft_stale(session, project):
    _upload(session, project.id, M1)
    project_repo, analysis_repo, report_repo, engine = _repos(session)
    generate_ai_report(
        project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine,
        FakeLLMClient("primero"),
    )

    # Simula que el analisis se recalculo con datos distintos (nuevo input_hash),
    # sin pasar por una reingesta real.
    snapshot = analysis_repo.get_snapshot(project.id, 1)
    analysis_repo.save_snapshots(
        project.id, {1: snapshot.payload}, snapshot.analysis_version, "hash-distinto",
    )

    leido = get_ai_report(project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine)
    assert leido.stale is True
