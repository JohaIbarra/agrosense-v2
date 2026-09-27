"""La migracion del referente versionado (E5) deriva del modelo de dominio.

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

REFERENCE_TABLES = (
    "reference_models",
    "reference_species_effects",
    "reference_plot_effects",
    "variance_components",
)


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


def test_migration_creates_the_reference_tables(migrated_engine):
    tablas = set(inspect(migrated_engine).get_table_names())
    faltan = set(REFERENCE_TABLES) - tablas
    assert not faltan, f"la migracion no creo: {sorted(faltan)}"
    assert "species_analytics" not in tablas
    assert "plot_analytics" not in tablas


@pytest.mark.parametrize("table", REFERENCE_TABLES)
def test_migrated_columns_match_the_model(migrated_engine, table):
    en_db = {c["name"] for c in inspect(migrated_engine).get_columns(table)}
    en_modelo = {c.name for c in Base.metadata.tables[table].columns}
    assert en_db == en_modelo, (
        f"{table}: solo en la migracion {sorted(en_db - en_modelo)}; "
        f"solo en el modelo {sorted(en_modelo - en_db)}"
    )


@pytest.mark.parametrize(
    ("table", "pk"),
    [
        ("reference_models", ["id"]),
        ("reference_species_effects", ["reference_model_id", "species_name"]),
        ("reference_plot_effects", ["reference_model_id", "plot_code"]),
        ("variance_components", ["id"]),
    ],
)
def test_primary_keys(migrated_engine, table, pk):
    real = sorted(inspect(migrated_engine).get_pk_constraint(table)["constrained_columns"])
    assert real == sorted(pk)


def test_reference_models_version_is_unique(migrated_engine):
    """I-3: dos versiones no pueden compartir `version` (uq_reference_models_version)."""
    nombres = {
        u["name"] for u in inspect(migrated_engine).get_unique_constraints("reference_models")
    }
    assert "uq_reference_models_version" in nombres


def test_reference_models_single_active_index_exists(migrated_engine):
    """I-3: a lo sumo UNA fila con `is_active` en toda la tabla, forzado por
    un indice unico parcial (WHERE is_active) — no solo por disciplina de la
    aplicacion."""
    indices = {
        i["name"]: i for i in inspect(migrated_engine).get_indexes("reference_models")
    }
    assert "uq_reference_models_single_active" in indices
    assert indices["uq_reference_models_single_active"]["unique"]


def test_variance_components_is_unique_per_version_model_and_grouping(migrated_engine):
    nombres = {
        u["name"] for u in inspect(migrated_engine).get_unique_constraints(
            "variance_components"
        )
    }
    assert "uq_variance_model_grouping" in nombres


@pytest.mark.parametrize(
    "table", ["reference_species_effects", "reference_plot_effects", "variance_components"]
)
def test_effect_tables_reference_a_model_version(migrated_engine, table):
    fks = inspect(migrated_engine).get_foreign_keys(table)
    assert any(fk["referred_table"] == "reference_models" for fk in fks), (
        f"{table} deberia tener una FK hacia reference_models (provenance, E5)"
    )


@pytest.mark.parametrize("table", REFERENCE_TABLES)
def test_reference_tables_have_no_project_foreign_key(migrated_engine, table):
    """Decision de diseno explicita: el referente no cuelga de un proyecto.

    Los efectos se estimaron sobre el dataset completo del programa. Si
    alguien anade una FK a `projects` sin ADR, este test lo para (regresion
    del `test_analytics_tables_have_no_project_foreign_key` de Slice 5).
    """
    fks = inspect(migrated_engine).get_foreign_keys(table)
    assert not any(fk["referred_table"] == "projects" for fk in fks), (
        f"{table} tiene una FK hacia projects; el referente es independiente "
        f"del grafo de proyectos (ver models.ReferenceModel)"
    )


def test_downgrade_removes_only_the_reference_tables(migrated_engine):
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", "sqlite://")
    with migrated_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "a2c4e6f8b1d3")
        conn.commit()
        tablas = set(inspect(conn).get_table_names())

    # `variance_components` NO desaparece: existe en ambos lados de esta
    # migracion (antes sin version, despues con `reference_model_id`), asi
    # que no entra en el chequeo de "solo tablas nuevas del referente".
    assert not (
        {"reference_models", "reference_species_effects", "reference_plot_effects"} & tablas
    )
    assert {"species_analytics", "plot_analytics"} <= tablas
    # El downgrade debe ser simetrico con b1c4a7f20e51: variance_components
    # tambien vuelve a existir, en su forma vieja (sin reference_model_id).
    assert "variance_components" in tablas
    with migrated_engine.connect() as conn:
        columnas_vc = {c["name"] for c in inspect(conn).get_columns("variance_components")}
        assert "reference_model_id" not in columnas_vc
        constraints_vc = {
            u["name"] for u in inspect(conn).get_unique_constraints("variance_components")
        }
        assert "uq_variance_model_grouping" in constraints_vc
    assert {"projects", "trees", "observations"} <= tablas

    with migrated_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
