"""UC-IA1/UC-IA2: generar y leer el borrador de informe con IA (E9).

Contra SQLite local con los repositorios y el motor reales: lo que se
prueba es la orquestacion (snapshot -> figuras -> LLM -> guardia ->
guardar), con un LLMClient de mentira -- nunca se sale a la red (AGENTS.md,
Testing).
"""
from __future__ import annotations

import copy
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


def test_changing_another_monitoring_project_wide_hash_does_not_make_this_one_stale(
    session, project
):
    """Regresion (fix wave 2026-09-27, item 3): antes `input_hash` se ataba
    al fingerprint de TODO el dataset del proyecto, asi que subir M5 (o
    cualquier cambio que mueva ese fingerprint) marcaba "stale" M1-M4 aunque
    sus propias cifras (`build_report_figures`) no hubieran cambiado en
    nada. Ahora se ata solo a esas cifras.
    """
    _upload(session, project.id, M1)
    project_repo, analysis_repo, report_repo, engine = _repos(session)
    generate_ai_report(
        project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine,
        FakeLLMClient("primero"),
    )

    # Simula que el fingerprint del PROYECTO cambio (p. ej. otra carga que
    # afecto a otro monitoreo), sin tocar el payload de M1.
    snapshot = analysis_repo.get_snapshot(project.id, 1)
    analysis_repo.save_snapshots(
        project.id, {1: snapshot.payload}, snapshot.analysis_version, "hash-de-proyecto-distinto",
    )

    leido = get_ai_report(project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine)
    assert leido.stale is False


def test_changing_this_monitoring_figures_makes_the_saved_draft_stale(session, project):
    """Contraparte del test anterior: si las cifras que SI ve el LLM
    cambian, el borrador debe quedar stale."""
    _upload(session, project.id, M1)
    project_repo, analysis_repo, report_repo, engine = _repos(session)
    generate_ai_report(
        project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine,
        FakeLLMClient("primero"),
    )

    snapshot = analysis_repo.get_snapshot(project.id, 1)
    payload_cambiado = copy.deepcopy(snapshot.payload)
    primero = payload_cambiado["summary"][0]
    primero["value"] = (primero.get("value") or 0) + 1
    analysis_repo.save_snapshots(
        project.id, {1: payload_cambiado}, snapshot.analysis_version, snapshot.input_hash,
    )

    leido = get_ai_report(project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine)
    assert leido.stale is True


class _RecordingReportRepo:
    """Envuelve el repo real y anota el ORDEN en que se llama a cada metodo,
    para probar que `release()` corre antes que `llm.generate()` (fix wave
    2026-09-27, item 4)."""

    def __init__(self, inner, calls: list[str]):
        self._inner = inner
        self._calls = calls

    def get(self, monitoring_id):
        return self._inner.get(monitoring_id)

    def release(self):
        self._calls.append("release")
        self._inner.release()

    def save(self, *args, **kwargs):
        self._calls.append("save")
        return self._inner.save(*args, **kwargs)


class _RecordingLLMClient(FakeLLMClient):
    def __init__(self, response, calls: list[str]):
        super().__init__(response)
        self._calls = calls

    def generate(self, prompt: str, system: str) -> str:
        self._calls.append("generate")
        return super().generate(prompt, system)


def test_release_runs_before_the_llm_call(session, project):
    """Regresion (fix wave 2026-09-27, item 4): la conexion de BD no debe
    seguir reservada en transaccion durante la llamada al LLM (hasta 180 s).
    """
    _upload(session, project.id, M1)
    project_repo, analysis_repo, real_report_repo, engine = _repos(session)
    calls: list[str] = []
    report_repo = _RecordingReportRepo(real_report_repo, calls)
    llm = _RecordingLLMClient(
        "Borrador generado por IA: revise las cifras antes de usarlo.\n\nListo.", calls
    )

    generate_ai_report(project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine, llm)

    assert "release" in calls and "generate" in calls
    assert calls.index("release") < calls.index("generate")


def test_the_prompt_never_carries_raw_tree_data(session, project):
    """Regresion (fix wave 2026-09-27, item 8): el prompt solo lleva las
    cifras de `build_report_figures`, nunca codigos de arbol ni especies."""
    _upload(session, project.id, M1)
    project_repo, analysis_repo, report_repo, engine = _repos(session)
    llm = FakeLLMClient("Borrador generado por IA: revise las cifras antes de usarlo.\n\nListo.")

    generate_ai_report(project.id, 1, OWNER, project_repo, analysis_repo, report_repo, engine, llm)

    prompt, system = llm.calls[0]
    for dato_crudo in ("T1", "T2", "Senna viarum"):
        assert dato_crudo not in prompt
        assert dato_crudo not in system
