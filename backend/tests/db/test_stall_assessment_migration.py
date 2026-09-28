"""La migracion de `stall_assessments` (E7) deriva del modelo de dominio."""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import Base

BACKEND = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def migrated_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", "sqlite://")
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
    yield engine
    engine.dispose()


def test_migration_creates_stall_assessments(migrated_engine):
    assert "stall_assessments" in set(inspect(migrated_engine).get_table_names())


def test_migrated_columns_match_the_model(migrated_engine):
    en_db = {c["name"] for c in inspect(migrated_engine).get_columns("stall_assessments")}
    en_modelo = {c.name for c in Base.metadata.tables["stall_assessments"].columns}
    assert en_db == en_modelo


def test_one_assessment_per_monitoring(migrated_engine):
    nombres = {
        u["name"] for u in inspect(migrated_engine).get_unique_constraints("stall_assessments")
    }
    assert "uq_stall_assessment_monitoring" in nombres
