"""AIReportRepository: guarda y reemplaza el borrador de un monitoreo (E9).

Un borrador por monitoreo: publicar de nuevo REEMPLAZA el anterior, igual
que `ProjectAnalysisRepository.save_snapshots` reemplaza el snapshot
(ADR-008) -- nunca se acumulan versiones de un borrador.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import AIReportRow, Base, MonitoringRow, Project
from agrosense.adapters.db.repository import AIReportRepository


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    yield s
    s.close()


@pytest.fixture()
def monitoring(session):
    project = Project(project_code="AGS-2026-1", owner_id="eng-1", name="P1")
    session.add(project)
    session.flush()
    m = MonitoringRow(project_id=project.id, number=1)
    session.add(m)
    session.commit()
    return project.id, m.id


def test_save_creates_the_row(session, monitoring):
    project_id, monitoring_id = monitoring
    repo = AIReportRepository(session)
    row = repo.save(
        project_id, monitoring_id, "qwen2.5:3b", "test-v1", "v1:hash1",
        "Borrador generado por IA...", [],
    )
    assert row.id is not None
    assert repo.get(monitoring_id).content == "Borrador generado por IA..."


def test_save_again_replaces_it(session, monitoring):
    project_id, monitoring_id = monitoring
    repo = AIReportRepository(session)
    repo.save(project_id, monitoring_id, "qwen2.5:3b", "test-v1", "v1:hash1", "primero", [])
    repo.save(
        project_id, monitoring_id, "qwen2.5:3b", "test-v1", "v1:hash2", "segundo", ["4.9x"]
    )

    row = repo.get(monitoring_id)
    assert row.content == "segundo"
    assert row.input_hash == "v1:hash2"
    assert row.unverified_numbers == ["4.9x"]

    todas = session.query(AIReportRow).all()
    assert len(todas) == 1, "regenerar reemplaza, no acumula filas"


def test_get_returns_none_when_no_report_yet(session, monitoring):
    _, monitoring_id = monitoring
    assert AIReportRepository(session).get(monitoring_id) is None
