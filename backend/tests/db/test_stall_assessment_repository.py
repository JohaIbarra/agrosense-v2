"""StallAssessmentRepository: un snapshot por monitoreo, que se reemplaza."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import Base, MonitoringRow, Project, StallAssessmentRow
from agrosense.adapters.db.repository import StallAssessmentRepository


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


@pytest.fixture()
def monitoring(session):
    project = Project(project_code="AGS-2026-1", owner_id="eng-1", name="P1")
    session.add(project)
    session.flush()
    m = MonitoringRow(project_id=project.id, number=3)
    session.add(m)
    session.commit()
    return project.id, m.id


PAYLOAD = {"alert_budget_pct": 20.0, "persistent_min_intervals": 2, "summary": {}, "trees": []}


def test_save_creates_the_row(session, monitoring):
    project_id, monitoring_id = monitoring
    repo = StallAssessmentRepository(session)
    row = repo.save(project_id, monitoring_id, "stall-v1", "a" * 64, "h" * 64, "rules-v1", PAYLOAD)
    assert row.id is not None
    stored = repo.get(monitoring_id)
    assert (
        stored.model_version,
        stored.artifact_sha256,
        stored.input_hash,
        stored.rules_version,
    ) == ("stall-v1", "a" * 64, "h" * 64, "rules-v1")
    assert stored.payload == PAYLOAD
    assert stored.computed_at is not None


def test_save_again_replaces_it(session, monitoring):
    project_id, monitoring_id = monitoring
    repo = StallAssessmentRepository(session)
    repo.save(project_id, monitoring_id, "stall-v1", "a" * 64, "h1" * 32, "rules-v1", PAYLOAD)
    repo.save(project_id, monitoring_id, "stall-v2", "b" * 64, "h2" * 32, "rules-v2", PAYLOAD)
    total = session.scalar(select(func.count()).select_from(StallAssessmentRow))
    assert total == 1
    stored = repo.get(monitoring_id)
    assert (stored.model_version, stored.rules_version) == ("stall-v2", "rules-v2")


def test_get_without_assessment_is_none(session, monitoring):
    _, monitoring_id = monitoring
    assert StallAssessmentRepository(session).get(monitoring_id) is None
