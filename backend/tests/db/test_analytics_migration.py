"""La migracion del slice 5 deriva del modelo de dominio, no al reves.

AGENTS.md: "Database schema must be derived from the domain model" y "Every
schema change must use a migration". Este test aplica las migraciones de
Alembic sobre SQLite en memoria y compara el esquema resultante con
`Base.metadata`. Sin el, un `mapped_column` nuevo se olvida en la migracion y
el fallo aparece recien en Supabase.

Lo que SQLite no puede probar (tipos de Postgres, timezone real) sigue en
`tests/smoke/test_supabase_smoke.py`, marcado `supabase`.
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

ANALYTICS_TABLES = ("species_analytics", "plot_analytics", "variance_components")


@pytest.fixture(scope="module")
def migrated_engine():
    """Engine con TODAS las migraciones aplicadas (no `create_all`).

    La diferencia importa: `create_all` construye el esquema desde los
    modelos, asi que nunca detectaria una migracion incompleta.
    """
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


def test_migration_creates_the_analytics_tables(migrated_engine):
    tablas = set(inspect(migrated_engine).get_table_names())
    faltan = set(ANALYTICS_TABLES) - tablas
    assert not faltan, f"la migracion no creo: {sorted(faltan)}"


@pytest.mark.parametrize("table", ANALYTICS_TABLES)
def test_migrated_columns_match_the_model(migrated_engine, table):
    """Cada columna del modelo existe en la tabla migrada, y al reves."""
    en_db = {c["name"] for c in inspect(migrated_engine).get_columns(table)}
    en_modelo = {c.name for c in Base.metadata.tables[table].columns}
    assert en_db == en_modelo, (
        f"{table}: solo en la migracion {sorted(en_db - en_modelo)}; "
        f"solo en el modelo {sorted(en_modelo - en_db)}"
    )


@pytest.mark.parametrize(
    ("table", "pk"),
    [
        ("species_analytics", ["species_name"]),
        ("plot_analytics", ["plot_code"]),
        ("variance_components", ["id"]),
    ],
)
def test_primary_keys(migrated_engine, table, pk):
    real = inspect(migrated_engine).get_pk_constraint(table)["constrained_columns"]
    assert real == pk


def test_variance_components_is_unique_per_model_and_grouping(migrated_engine):
    """Sin esta constraint, dos cargas seguidas duplicarian los ICC.

    `replace_all` borra antes de insertar, pero la constraint es la que hace
    que el invariante no dependa de que el script se porte bien.
    """
    nombres = {
        u["name"] for u in inspect(migrated_engine).get_unique_constraints(
            "variance_components"
        )
    }
    assert "uq_variance_model_grouping" in nombres


def test_analytics_tables_have_no_project_foreign_key(migrated_engine):
    """Decision de diseno explicita: la analitica no cuelga de un proyecto.

    Los efectos se estimaron sobre el dataset completo del programa. Si
    alguien anade una FK a `projects` sin ADR, este test lo para.
    """
    inspector = inspect(migrated_engine)
    for table in ANALYTICS_TABLES:
        assert inspector.get_foreign_keys(table) == [], (
            f"{table} tiene FKs; la analitica es independiente del grafo de "
            f"proyectos (ver models.SpeciesAnalytics)"
        )


def test_downgrade_removes_only_the_analytics_tables(migrated_engine):
    """El downgrade del slice 5 no puede tocar las tablas del slice 2."""
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", "sqlite://")
    with migrated_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "-1")
        conn.commit()
        tablas = set(inspect(conn).get_table_names())

    assert not (set(ANALYTICS_TABLES) & tablas)
    assert {"projects", "trees", "observations", "campaign_files"} <= tablas

    # Volver a subir para no dejar el engine del modulo a medias.
    with migrated_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
