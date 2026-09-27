"""La migracion de `ai_reports` (E9) deriva del modelo de dominio.

AGENTS.md: "Database schema must be derived from the domain model" y "Every
schema change must use a migration". Aplica las migraciones de Alembic sobre
SQLite en memoria y compara el esquema resultante con `Base.metadata`.
"""
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


def test_migration_creates_ai_reports(migrated_engine):
    tablas = set(inspect(migrated_engine).get_table_names())
    assert "ai_reports" in tablas


def test_migrated_columns_match_the_model(migrated_engine):
    en_db = {c["name"] for c in inspect(migrated_engine).get_columns("ai_reports")}
    en_modelo = {c.name for c in Base.metadata.tables["ai_reports"].columns}
    assert en_db == en_modelo, (
        f"solo en la migracion {sorted(en_db - en_modelo)}; "
        f"solo en el modelo {sorted(en_modelo - en_db)}"
    )


def test_unique_constraint_on_monitoring_id(migrated_engine):
    nombres = {
        u["name"] for u in inspect(migrated_engine).get_unique_constraints("ai_reports")
    }
    assert "uq_ai_report_monitoring" in nombres


def test_foreign_keys_point_to_projects_and_monitorings(migrated_engine):
    referidas = {
        fk["referred_table"] for fk in inspect(migrated_engine).get_foreign_keys("ai_reports")
    }
    assert referidas == {"projects", "monitorings"}


def test_downgrade_removes_only_ai_reports(migrated_engine):
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", "sqlite://")
    with migrated_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "c7e9f2a4b6d8")
        conn.commit()
        tablas = set(inspect(conn).get_table_names())

    assert "ai_reports" not in tablas
    assert {"projects", "monitorings", "reference_models"} <= tablas

    with migrated_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
