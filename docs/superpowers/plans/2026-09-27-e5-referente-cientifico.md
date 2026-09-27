# E5 — Referente científico + contraste — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar la épica E5 del roadmap de AgroSense v2: versionar el Referente científico (los modelos mixtos ya ajustados del antiguo Slice 5) con provenance real, renombrar su contrato de `/api/v1/analytics` a `/api/v1/reference`, y añadir la feature de valor nueva (UC-AN3): contrastar las especies plantadas de un proyecto contra ese referente.

**Architecture:** Slice 1 es un refactor de provenance — añade `reference_models` (versión, `is_active`) y hace que `reference_species_effects` / `reference_plot_effects` / `variance_components` cuelguen de una versión en vez de borrarse en cada carga. Slice 2 es una feature de lectura nueva: cruza `trees.species` (por proyecto) contra la versión activa del referente y arma un DTO explicado, sin domain nuevo (la interpretación de OR ya vive en `application/use_cases/read_analytics.py` y se reutiliza, no se duplica).

**Tech Stack:** FastAPI + SQLAlchemy + Alembic (backend, Python), React + TypeScript + Vitest (frontend), pytest + `TestClient` para integración, SQLite en memoria para tests.

**Spec:** `docs/04-vision-producto.md` (secciones 3, 4, 6.7, 8, 9 — E5), `AGENTS.md`, `docs/obsidian-agrosense/01-Proyecto/Roadmap.md`.

## Global Constraints

- La lógica de negocio (qué significa un OR, qué IC es concluyente, cómo se frasea un contraste) vive en `application/`, nunca en rutas ni en el frontend (AGENTS.md: "Business rules must not be duplicated in the frontend").
- Todo cambio de esquema va por una migración de Alembic; nunca se toca el esquema a mano (AGENTS.md).
- TDD: cada tarea empieza por un test que falla.
- Cada dato de un modelo debe ser trazable a su `reference_model_id` (AGENTS.md, Data provenance).
- Cada slice es demostrable de punta a punta (DB → API → frontend) por sí solo.
- Este NO es un slice de ML: no hay entrenamiento nuevo ni aplica el ML eval gate (`tests/architecture/test_ml_eval_gate.py` no se toca). Los CSV de `backend/data/processed/` siguen siendo la fuente de verdad; este trabajo traduce y versiona, no reestima.
- Alcance del renombre (explícito para que un revisor no espere más de lo que hay): se renombran las **tablas**, las **clases ORM** que las mapean 1:1, el **archivo y prefijo de la ruta** (`routes/analytics.py` → `routes/reference.py`, `/api/v1/analytics` → `/api/v1/reference`) y el **repositorio** que las lee. Los DTOs de `application/dtos.py`, los schemas Pydantic y los tipos TypeScript (`SpeciesAnalyticsDTO`, `SpeciesAnalyticsResponse`, `SpeciesAnalytics`, etc.) **no** se renombran en este plan: no son la ruta URL que confundía (doc §4), y renombrarlos también infla el diff sin necesidad. Si en el futuro se justifica, es una tarea aparte.

---

## Slice 1 — Referente versionado (provenance + rename del contrato)

### Task 1: Migración y modelos ORM del referente versionado

**Files:**
- Create: `backend/alembic/versions/c7e9f2a4b6d8_e5_reference_models_versioned.py`
- Modify: `backend/src/agrosense/adapters/db/models.py:510-609` (bloque "Slice 5: analitica")
- Test: `backend/tests/db/test_reference_migration.py` (reemplaza a `backend/tests/db/test_analytics_migration.py`)

**Interfaces:**
- Produces: ORM classes `ReferenceModel` (tabla `reference_models`: `id`, `version`, `source_dataset`, `method`, `n_observations`, `computed_at`, `is_active`), `ReferenceSpeciesEffect` (tabla `reference_species_effects`, PK compuesta `(reference_model_id, species_name)`), `ReferencePlotEffect` (tabla `reference_plot_effects`, PK compuesta `(reference_model_id, plot_code)`), `VarianceComponent` (tabla `variance_components`, ahora con `reference_model_id` y `UniqueConstraint('reference_model_id', 'model', 'grouping')`). Todas con los mismos campos de negocio que `SpeciesAnalytics` / `PlotAnalytics` tenían antes, más `reference_model_id`.
- Consumes: nada de tareas previas.

**Por qué se dropean y recrean las tablas en vez de `ALTER`:** no hay datos de producción que preservar (`docs/obsidian-agrosense/01-Proyecto/Roadmap.md`: "Deploy — BLOQUEADO"), y la forma de la PK cambia de columna simple a compuesta porque ahora conviven varias versiones del referente en la misma tabla. Migrar con `ALTER`/`batch_alter_table` para terminar recreando la tabla de todos modos sería más código para el mismo resultado.

- [ ] **Step 1: Escribir el test de migración que falla**

Reemplaza el contenido completo de `backend/tests/db/test_analytics_migration.py` (bórralo) por `backend/tests/db/test_reference_migration.py`:

```python
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


def test_downgrade_removes_only_the_reference_tables(migrated_engine):
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", "sqlite://")
    with migrated_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.downgrade(cfg, "a2c4e6f8b1d3")
        conn.commit()
        tablas = set(inspect(conn).get_table_names())

    assert not (set(REFERENCE_TABLES) & tablas)
    assert {"species_analytics", "plot_analytics"} <= tablas
    assert {"projects", "trees", "observations"} <= tablas

    with migrated_engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
```

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd backend && pytest tests/db/test_reference_migration.py -v`
Expected: FAIL (`KeyError` sobre `reference_models` en `Base.metadata.tables`, la clase ORM todavía no existe; la migración tampoco).

- [ ] **Step 3: Renombrar y versionar las clases ORM en `models.py`**

En `backend/src/agrosense/adapters/db/models.py`, reemplaza el bloque completo desde el comentario `# ── Slice 5: analitica (efectos de los modelos mixtos) ─────` (línea ~374) hasta el final de `class VarianceComponent` (línea ~609) por:

```python
# ── E5: referente cientifico versionado (efectos de los modelos mixtos) ────
#
# `reference_models` es la version: cada fila es UNA corrida completa de los
# modelos mixtos (lme4::glmer binomial). Las tres tablas de efectos cuelgan
# de una version por `reference_model_id`, y su PK ahora es compuesta
# (version, nivel): asi conviven varias versiones sin pisarse.
#
# `is_active` marca cual version sirve la API hoy. Publicar una version
# nueva NO borra las anteriores (antes de E5 una recarga borraba la version
# vieja sin rastro, doc 04-vision-producto.md §6.7) — quedan en la base,
# consultables por su `reference_model_id`, fuera de lectura por defecto.
#
# Sin FK hacia `projects`: los efectos se estimaron sobre el dataset de
# referencia completo (856 arboles, 30 especies), que es conceptualmente
# "la evidencia del programa", no de un proyecto. Ver models.SpeciesAnalytics
# original y ADR pendiente si esto deja de ser cierto.


class ReferenceModel(Base):
    """Una corrida versionada de los modelos mixtos de estancamiento/mortalidad."""

    __tablename__ = "reference_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(300), nullable=False)
    method: Mapped[str] = mapped_column(String(100), nullable=False)
    n_observations: Mapped[int | None] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ReferenceSpeciesEffect(Base):
    """Efecto aleatorio por especie de UNA version del referente.

    `effect_*` es el log-odds; `or_* = exp(effect_*)`; `or_*_lo/hi` son los
    extremos del IC 95% YA exponenciados (`exp(efecto +- 1.96*se)`).
    `sig_*` es True cuando el IC 95% en log-odds no cruza 0.
    """

    __tablename__ = "reference_species_effects"

    reference_model_id: Mapped[int] = mapped_column(
        ForeignKey("reference_models.id", ondelete="CASCADE"), primary_key=True
    )
    species_name: Mapped[str] = mapped_column(String(300), primary_key=True)

    # Estancamiento
    effect_stall: Mapped[float | None] = mapped_column(Float)
    se_stall: Mapped[float | None] = mapped_column(Float)
    or_stall: Mapped[float | None] = mapped_column(Float)
    or_stall_lo: Mapped[float | None] = mapped_column(Float)
    or_stall_hi: Mapped[float | None] = mapped_column(Float)
    sig_stall: Mapped[bool | None] = mapped_column(Boolean)

    # Mortalidad
    effect_mort: Mapped[float | None] = mapped_column(Float)
    se_mort: Mapped[float | None] = mapped_column(Float)
    or_mort: Mapped[float | None] = mapped_column(Float)
    or_mort_lo: Mapped[float | None] = mapped_column(Float)
    or_mort_hi: Mapped[float | None] = mapped_column(Float)
    sig_mort: Mapped[bool | None] = mapped_column(Boolean)

    # Metadatos
    n_observations: Mapped[int | None] = mapped_column(Integer)
    n_trees: Mapped[int | None] = mapped_column(Integer)
    gremio: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_analytics_updated, nullable=False
    )


class ReferencePlotEffect(Base):
    """Efecto aleatorio por parcela (`Codigo de unidad muestreo`) de UNA version."""

    __tablename__ = "reference_plot_effects"

    reference_model_id: Mapped[int] = mapped_column(
        ForeignKey("reference_models.id", ondelete="CASCADE"), primary_key=True
    )
    plot_code: Mapped[str] = mapped_column(String(100), primary_key=True)
    localidad: Mapped[str | None] = mapped_column(String(200))

    effect_stall: Mapped[float | None] = mapped_column(Float)
    se_stall: Mapped[float | None] = mapped_column(Float)
    or_stall: Mapped[float | None] = mapped_column(Float)

    effect_mort: Mapped[float | None] = mapped_column(Float)
    se_mort: Mapped[float | None] = mapped_column(Float)
    or_mort: Mapped[float | None] = mapped_column(Float)

    n_trees: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_analytics_updated, nullable=False
    )


class VarianceComponent(Base):
    """Descomposicion de varianza de UNA version (una fila por modelo x nivel)."""

    __tablename__ = "variance_components"
    __table_args__ = (
        UniqueConstraint(
            "reference_model_id", "model", "grouping", name="uq_variance_model_grouping"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference_model_id: Mapped[int] = mapped_column(
        ForeignKey("reference_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(20), nullable=False)  # stall | mortality
    grouping: Mapped[str] = mapped_column(String(20), nullable=False)  # especie | parcela
    variance: Mapped[float] = mapped_column(Float, nullable=False)
    sd: Mapped[float] = mapped_column(Float, nullable=False)
    icc: Mapped[float] = mapped_column(Float, nullable=False)
    n_levels: Mapped[int | None] = mapped_column(Integer)
    n_observations: Mapped[int | None] = mapped_column(Integer)
    n_events: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_analytics_updated, nullable=False
    )
```

(`_analytics_updated`, `_utcnow`, `Base`, `Boolean`, `String`, `Float`, `Integer`, `DateTime`, `ForeignKey`, `UniqueConstraint`, `Mapped`, `mapped_column` ya están importados/definidos más arriba en el archivo — no cambian.)

- [ ] **Step 4: Escribir la migración**

Cabecera del head actual: `alembic/versions/a2c4e6f8b1d3_e10a_satellite_index_values.py` tiene `revision = 'a2c4e6f8b1d3'`. La nueva migración cuelga de ahí.

```python
"""E5: referente cientifico versionado (reference_models + efectos por version)

docs/superpowers/plans/2026-09-27-e5-referente-cientifico.md, docs/04-vision-producto.md §6.7.

Reemplaza `species_analytics` / `plot_analytics` (Slice 5, sin version) por
`reference_species_effects` / `reference_plot_effects`, y anade
`reference_model_id` a `variance_components`. Las tres tablas de efectos
ahora cuelgan de `reference_models`, que registra CADA corrida de los
modelos mixtos con su `is_active`.

Se dropean y recrean en vez de ALTER: no hay datos de produccion que
preservar (deploy bloqueado, ver Roadmap) y la PK cambia de columna simple a
compuesta (version, nivel) porque ahora conviven varias versiones.

Revision ID: c7e9f2a4b6d8
Revises: a2c4e6f8b1d3
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c7e9f2a4b6d8'
down_revision: str | None = 'a2c4e6f8b1d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'reference_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('source_dataset', sa.String(length=300), nullable=False),
        sa.Column('method', sa.String(length=100), nullable=False),
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.drop_table('species_analytics')
    op.drop_table('plot_analytics')
    op.drop_table('variance_components')

    op.create_table(
        'reference_species_effects',
        sa.Column('reference_model_id', sa.Integer(), nullable=False),
        sa.Column('species_name', sa.String(length=300), nullable=False),
        sa.Column('effect_stall', sa.Float(), nullable=True),
        sa.Column('se_stall', sa.Float(), nullable=True),
        sa.Column('or_stall', sa.Float(), nullable=True),
        sa.Column('or_stall_lo', sa.Float(), nullable=True),
        sa.Column('or_stall_hi', sa.Float(), nullable=True),
        sa.Column('sig_stall', sa.Boolean(), nullable=True),
        sa.Column('effect_mort', sa.Float(), nullable=True),
        sa.Column('se_mort', sa.Float(), nullable=True),
        sa.Column('or_mort', sa.Float(), nullable=True),
        sa.Column('or_mort_lo', sa.Float(), nullable=True),
        sa.Column('or_mort_hi', sa.Float(), nullable=True),
        sa.Column('sig_mort', sa.Boolean(), nullable=True),
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('n_trees', sa.Integer(), nullable=True),
        sa.Column('gremio', sa.String(length=100), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('reference_model_id', 'species_name'),
        sa.ForeignKeyConstraint(
            ['reference_model_id'], ['reference_models.id'], ondelete='CASCADE'
        ),
    )
    op.create_index(
        'ix_reference_species_effects_or_stall', 'reference_species_effects', ['or_stall']
    )
    op.create_index(
        'ix_reference_species_effects_or_mort', 'reference_species_effects', ['or_mort']
    )
    op.create_index(
        'ix_reference_species_effects_gremio', 'reference_species_effects', ['gremio']
    )

    op.create_table(
        'reference_plot_effects',
        sa.Column('reference_model_id', sa.Integer(), nullable=False),
        sa.Column('plot_code', sa.String(length=100), nullable=False),
        sa.Column('localidad', sa.String(length=200), nullable=True),
        sa.Column('effect_stall', sa.Float(), nullable=True),
        sa.Column('se_stall', sa.Float(), nullable=True),
        sa.Column('or_stall', sa.Float(), nullable=True),
        sa.Column('effect_mort', sa.Float(), nullable=True),
        sa.Column('se_mort', sa.Float(), nullable=True),
        sa.Column('or_mort', sa.Float(), nullable=True),
        sa.Column('n_trees', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('reference_model_id', 'plot_code'),
        sa.ForeignKeyConstraint(
            ['reference_model_id'], ['reference_models.id'], ondelete='CASCADE'
        ),
    )
    op.create_index(
        'ix_reference_plot_effects_localidad', 'reference_plot_effects', ['localidad']
    )

    op.create_table(
        'variance_components',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference_model_id', sa.Integer(), nullable=False),
        sa.Column('model', sa.String(length=20), nullable=False),
        sa.Column('grouping', sa.String(length=20), nullable=False),
        sa.Column('variance', sa.Float(), nullable=False),
        sa.Column('sd', sa.Float(), nullable=False),
        sa.Column('icc', sa.Float(), nullable=False),
        sa.Column('n_levels', sa.Integer(), nullable=True),
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('n_events', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'reference_model_id', 'model', 'grouping', name='uq_variance_model_grouping'
        ),
        sa.ForeignKeyConstraint(
            ['reference_model_id'], ['reference_models.id'], ondelete='CASCADE'
        ),
    )
    op.create_index(
        'ix_variance_components_reference_model_id', 'variance_components', ['reference_model_id']
    )


def downgrade() -> None:
    op.drop_table('variance_components')
    op.drop_index(
        'ix_reference_plot_effects_localidad', table_name='reference_plot_effects'
    )
    op.drop_table('reference_plot_effects')
    op.drop_index(
        'ix_reference_species_effects_gremio', table_name='reference_species_effects'
    )
    op.drop_index(
        'ix_reference_species_effects_or_mort', table_name='reference_species_effects'
    )
    op.drop_index(
        'ix_reference_species_effects_or_stall', table_name='reference_species_effects'
    )
    op.drop_table('reference_species_effects')
    op.drop_table('reference_models')

    # Recrea las tablas del Slice 5 tal como las dejo b1c4a7f20e51, para que
    # el downgrade sea simetrico de verdad.
    op.create_table(
        'species_analytics',
        sa.Column('species_name', sa.String(length=300), nullable=False),
        sa.Column('effect_stall', sa.Float(), nullable=True),
        sa.Column('se_stall', sa.Float(), nullable=True),
        sa.Column('or_stall', sa.Float(), nullable=True),
        sa.Column('or_stall_lo', sa.Float(), nullable=True),
        sa.Column('or_stall_hi', sa.Float(), nullable=True),
        sa.Column('sig_stall', sa.Boolean(), nullable=True),
        sa.Column('effect_mort', sa.Float(), nullable=True),
        sa.Column('se_mort', sa.Float(), nullable=True),
        sa.Column('or_mort', sa.Float(), nullable=True),
        sa.Column('or_mort_lo', sa.Float(), nullable=True),
        sa.Column('or_mort_hi', sa.Float(), nullable=True),
        sa.Column('sig_mort', sa.Boolean(), nullable=True),
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('n_trees', sa.Integer(), nullable=True),
        sa.Column('gremio', sa.String(length=100), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('species_name'),
    )
    op.create_table(
        'plot_analytics',
        sa.Column('plot_code', sa.String(length=100), nullable=False),
        sa.Column('localidad', sa.String(length=200), nullable=True),
        sa.Column('effect_stall', sa.Float(), nullable=True),
        sa.Column('se_stall', sa.Float(), nullable=True),
        sa.Column('or_stall', sa.Float(), nullable=True),
        sa.Column('effect_mort', sa.Float(), nullable=True),
        sa.Column('se_mort', sa.Float(), nullable=True),
        sa.Column('or_mort', sa.Float(), nullable=True),
        sa.Column('n_trees', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('plot_code'),
    )
```

- [ ] **Step 5: Ejecutar el test para verlo pasar**

Run: `cd backend && pytest tests/db/test_reference_migration.py -v`
Expected: PASS (9 tests: creación, columnas, PKs, unique constraint, FKs x3, downgrade).

- [ ] **Step 6: Commit**

```bash
git add backend/src/agrosense/adapters/db/models.py backend/alembic/versions/c7e9f2a4b6d8_e5_reference_models_versioned.py backend/tests/db/test_reference_migration.py
git rm backend/tests/db/test_analytics_migration.py
git commit -m "feat(e5): reference_models versionado + rename de tablas del referente"
```

---

### Task 2: `ReferenceRepository` con publicación versionada (no borra el historial)

**Files:**
- Modify: `backend/src/agrosense/adapters/db/repository.py:646-716` (clase `AnalyticsRepository`)
- Test: `backend/tests/db/test_reference_repository.py` (nuevo)

**Interfaces:**
- Consumes: `ReferenceModel`, `ReferenceSpeciesEffect`, `ReferencePlotEffect`, `VarianceComponent` (Task 1).
- Produces: clase `ReferenceRepository` con `active_model() -> ReferenceModel | None`, `list_species(gremio=None) -> list[ReferenceSpeciesEffect]`, `get_species(name) -> ReferenceSpeciesEffect | None`, `list_plots(localidad=None) -> list[ReferencePlotEffect]`, `list_variance() -> list[VarianceComponent]`, `publish_version(model, species, plots, variance) -> ReferenceModel`. Estos 4 métodos de lectura son los que usa `AnalyticsReader` (el `Protocol` de `read_analytics.py`, sin cambios de nombre).

- [ ] **Step 1: Escribir el test que falla**

Crea `backend/tests/db/test_reference_repository.py`:

```python
"""ReferenceRepository: publicar una version nueva no borra la anterior (E5).

Antes de E5, `AnalyticsRepository.replace_all` borraba las tres tablas en
cada carga (docs/04-vision-producto.md §6.7: "una recarga borra la anterior
sin rastro"). Esto prueba que ya no es asi.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import (
    Base,
    ReferenceModel,
    ReferencePlotEffect,
    ReferenceSpeciesEffect,
    VarianceComponent,
)
from agrosense.adapters.db.repository import ReferenceRepository


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


def _model(version: str) -> ReferenceModel:
    return ReferenceModel(
        version=version, source_dataset="data/raw/anexo1.xlsx",
        method="lme4::glmer binomial", n_observations=100,
    )


def test_publish_first_version_activates_it(session):
    repo = ReferenceRepository(session)
    m = repo.publish_version(
        _model("v1"),
        [ReferenceSpeciesEffect(species_name="Lafoensia speciosa", or_stall=4.94)],
        [], [],
    )
    assert m.is_active is True
    assert repo.active_model().version == "v1"
    assert len(repo.list_species()) == 1


def test_publish_second_version_deactivates_the_first_but_keeps_its_rows(session):
    repo = ReferenceRepository(session)
    v1 = repo.publish_version(
        _model("v1"),
        [ReferenceSpeciesEffect(species_name="Lafoensia speciosa", or_stall=4.94)],
        [], [],
    )
    v2 = repo.publish_version(
        _model("v2"),
        [ReferenceSpeciesEffect(species_name="Lafoensia speciosa", or_stall=5.10)],
        [], [],
    )

    session.refresh(v1)
    assert v1.is_active is False
    assert v2.is_active is True
    assert repo.active_model().version == "v2"

    # Solo la version activa se lee por defecto...
    activos = repo.list_species()
    assert len(activos) == 1
    assert activos[0].or_stall == pytest.approx(5.10)

    # ...pero la fila de v1 sigue en la base, no se borro.
    todas = session.query(ReferenceSpeciesEffect).all()
    assert len(todas) == 2


def test_get_species_reads_only_the_active_version(session):
    repo = ReferenceRepository(session)
    repo.publish_version(
        _model("v1"), [ReferenceSpeciesEffect(species_name="X", or_stall=1.0)], [], [],
    )
    repo.publish_version(
        _model("v2"), [ReferenceSpeciesEffect(species_name="X", or_stall=2.0)], [], [],
    )
    assert repo.get_species("X").or_stall == pytest.approx(2.0)


def test_no_active_model_yet_reads_are_empty_not_an_error(session):
    repo = ReferenceRepository(session)
    assert repo.active_model() is None
    assert repo.list_species() == []
    assert repo.list_plots() == []
    assert repo.list_variance() == []
    assert repo.get_species("X") is None


def test_publish_is_all_or_nothing(session):
    """Si una fila de efectos no cuadra con el esquema, la version no queda a medias."""
    repo = ReferenceRepository(session)
    bad_plot = ReferencePlotEffect(plot_code="P1")
    bad_plot.effect_stall = "no-es-un-float"  # fuerza el fallo al hacer flush
    with pytest.raises(Exception):
        repo.publish_version(_model("v1"), [], [bad_plot], [])
    assert repo.active_model() is None
```

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd backend && pytest tests/db/test_reference_repository.py -v`
Expected: FAIL (`ImportError: cannot import name 'ReferenceRepository'`).

- [ ] **Step 3: Implementar `ReferenceRepository`**

En `backend/src/agrosense/adapters/db/repository.py`, actualiza el import (línea ~20):

```python
from agrosense.adapters.db.models import (
    CampaignFile,
    Engineer,
    ImageryLayerRow,
    MonitoringAnalysisRow,
    MonitoringRow,
    ObservationRow,
    PlotRow,
    Project,
    PropertyRow,
    ReferenceModel,
    ReferencePlotEffect,
    ReferenceSpeciesEffect,
    SatelliteIndexValueRow,
    TreeRow,
    VarianceComponent,
)
```

Reemplaza la clase `AnalyticsRepository` completa (líneas 646-716) por:

```python
class ReferenceRepository:
    """Lectura y publicacion versionada del Referente cientifico (E5).

    Publicar SIEMPRE anade una version nueva; nunca borra una anterior. Las
    lecturas (`list_species`, `get_species`, `list_plots`, `list_variance`)
    filtran por la version activa: la API nunca mezcla efectos de dos
    corridas distintas del modelo mixto.
    """

    def __init__(self, session: Session):
        self._s = session

    # ── Lectura ────────────────────────────────────────────────────────────

    def active_model(self) -> ReferenceModel | None:
        return self._s.scalar(select(ReferenceModel).where(ReferenceModel.is_active.is_(True)))

    def list_models(self) -> list[ReferenceModel]:
        return list(
            self._s.scalars(
                select(ReferenceModel).order_by(ReferenceModel.computed_at.desc())
            ).all()
        )

    def list_species(self, gremio: str | None = None) -> list[ReferenceSpeciesEffect]:
        active = self.active_model()
        if active is None:
            return []
        stmt = select(ReferenceSpeciesEffect).where(
            ReferenceSpeciesEffect.reference_model_id == active.id
        )
        if gremio is not None:
            stmt = stmt.where(ReferenceSpeciesEffect.gremio == gremio)
        return list(
            self._s.scalars(stmt.order_by(ReferenceSpeciesEffect.species_name)).all()
        )

    def get_species(self, name: str) -> ReferenceSpeciesEffect | None:
        active = self.active_model()
        if active is None:
            return None
        return self._s.get(ReferenceSpeciesEffect, (active.id, name))

    def list_plots(self, localidad: str | None = None) -> list[ReferencePlotEffect]:
        active = self.active_model()
        if active is None:
            return []
        stmt = select(ReferencePlotEffect).where(
            ReferencePlotEffect.reference_model_id == active.id
        )
        if localidad is not None:
            stmt = stmt.where(ReferencePlotEffect.localidad == localidad)
        return list(self._s.scalars(stmt.order_by(ReferencePlotEffect.plot_code)).all())

    def list_variance(self) -> list[VarianceComponent]:
        active = self.active_model()
        if active is None:
            return []
        return list(
            self._s.scalars(
                select(VarianceComponent)
                .where(VarianceComponent.reference_model_id == active.id)
                .order_by(VarianceComponent.model, VarianceComponent.grouping)
            ).all()
        )

    # ── Publicacion (UC-R2, solo desde scripts/load_analytics.py) ──────────

    def publish_version(
        self,
        model: ReferenceModel,
        species: list[ReferenceSpeciesEffect],
        plots: list[ReferencePlotEffect],
        variance: list[VarianceComponent],
    ) -> ReferenceModel:
        """Publica una version nueva del referente (ADR-004: todo o nada).

        Desactiva la version activa (si hay) e inserta la nueva, ya activa,
        con sus tres tablas de efectos estampadas con su `reference_model_id`.
        La version anterior NO se borra: sigue en la base para trazabilidad,
        solo deja de ser la que leen `list_species` / `get_species` / etc.
        """
        try:
            previous = self.active_model()
            if previous is not None:
                previous.is_active = False
            model.is_active = True
            self._s.add(model)
            self._s.flush()  # asigna model.id antes de estampar las filas

            for row in species:
                row.reference_model_id = model.id
            for row in plots:
                row.reference_model_id = model.id
            for row in variance:
                row.reference_model_id = model.id

            self._s.add_all(species)
            self._s.add_all(plots)
            self._s.add_all(variance)
            self._s.commit()
        except Exception:
            self._s.rollback()
            raise
        return model
```

- [ ] **Step 4: Ejecutar el test para verlo pasar**

Run: `cd backend && pytest tests/db/test_reference_repository.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/adapters/db/repository.py backend/tests/db/test_reference_repository.py
git commit -m "feat(e5): ReferenceRepository publica versiones sin borrar el historial"
```

---

### Task 3: `scripts/load_analytics.py` publica una versión del referente

**Files:**
- Modify: `backend/scripts/load_analytics.py` (completo)
- Modify: `backend/tests/analytics/conftest.py:38-79` (fixture `analytics_client`, que importa este script)

**Interfaces:**
- Consumes: `ReferenceRepository.publish_version` (Task 2), `build_bundle` (sin cambios, `adapters/analytics/effects_loader.py`).
- Produces: `to_orm(bundle) -> tuple[list[ReferenceSpeciesEffect], list[ReferencePlotEffect], list[VarianceComponent]]` (mismo nombre, tipos nuevos), `build_reference_model(bundle, version, source_dataset) -> ReferenceModel`.

- [ ] **Step 1: Escribir el test que falla**

Añade a `backend/tests/analytics/test_effects_loader.py` (o crea si no existe una sección de `to_orm`; si el archivo ya prueba `build_bundle`, añade al final):

```python
def test_to_orm_produces_versioned_rows_without_a_reference_model_id_yet():
    """`to_orm` no estampa `reference_model_id`: eso lo hace `publish_version`
    (Task 2), que es quien conoce el id recien asignado."""
    import sys
    from pathlib import Path

    SCRIPTS = Path(__file__).parents[2] / "scripts"
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import load_analytics

    from agrosense.adapters.analytics.effects_loader import build_bundle

    processed = Path(__file__).parents[2] / "data" / "processed"
    if not (processed / "efectos_aleatorios.csv").exists():
        import pytest
        pytest.skip("CSV de los modelos mixtos ausentes")

    bundle = build_bundle(processed)
    species, plots, variance = load_analytics.to_orm(bundle)
    assert len(species) == len(bundle.species)
    assert all(row.reference_model_id is None for row in species)

    model = load_analytics.build_reference_model(bundle, version="test-v1")
    assert model.source_dataset == "data/raw/anexo1.xlsx"
    assert model.method == "lme4::glmer binomial"
    assert model.n_observations == len(bundle.species) or model.n_observations > 0
    assert model.is_active is False  # lo activa publish_version, no el builder
```

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd backend && pytest tests/analytics/test_effects_loader.py -v -k to_orm_produces_versioned`
Expected: FAIL (`AttributeError: module 'load_analytics' has no attribute 'build_reference_model'`, y `to_orm` sigue devolviendo `SpeciesAnalytics`).

- [ ] **Step 3: Reescribir `load_analytics.py`**

Reemplaza el archivo completo:

```python
"""Carga y publicacion versionada del Referente cientifico (E5).

Lee los efectos de los modelos mixtos ya ajustados (`data/processed/*.csv`) y
PUBLICA una version nueva: crea una fila en `reference_models` y sus tres
tablas de efectos, y desactiva la version anterior sin borrarla (E5,
docs/04-vision-producto.md §6.7 — antes de esto, `replace_all` borraba la
version previa sin rastro).

Uso:
    python scripts/load_analytics.py                    # publica en DATABASE_URL
    python scripts/load_analytics.py --dry-run          # no escribe, solo reporta
    python scripts/load_analytics.py --version v2       # etiqueta explicita
    python scripts/load_analytics.py --processed-dir otra/ruta

Requiere que la migracion `c7e9f2a4b6d8` este aplicada (`alembic upgrade head`).

Este script NO re-estima nada. Los modelos mixtos (`lme4::glmer` binomial) ya
se corrieron sobre `data/raw/anexo1.xlsx`; los CSV son la fuente de verdad y
este script solo los traduce a filas y las publica como una version.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agrosense.adapters.analytics.effects_loader import (  # noqa: E402
    AnalyticsBundle,
    build_bundle,
)
from agrosense.adapters.db.models import (  # noqa: E402
    ReferenceModel,
    ReferencePlotEffect,
    ReferenceSpeciesEffect,
    VarianceComponent,
)
from agrosense.adapters.db.repository import ReferenceRepository  # noqa: E402
from agrosense.adapters.db.session import get_session_factory  # noqa: E402

DEFAULT_PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"
SOURCE_DATASET = "data/raw/anexo1.xlsx"
METHOD = "lme4::glmer binomial"


def to_orm(bundle: AnalyticsBundle) -> tuple[
    list[ReferenceSpeciesEffect], list[ReferencePlotEffect], list[VarianceComponent]
]:
    """Traduce las filas del loader a instancias del ORM, sin version todavia.

    `reference_model_id` lo asigna `ReferenceRepository.publish_version`,
    que es quien conoce el id recien insertado de `reference_models`.
    """
    species = [
        ReferenceSpeciesEffect(
            species_name=r.species_name,
            effect_stall=r.effect_stall, se_stall=r.se_stall,
            or_stall=r.or_stall, or_stall_lo=r.or_stall_lo, or_stall_hi=r.or_stall_hi,
            sig_stall=r.sig_stall,
            effect_mort=r.effect_mort, se_mort=r.se_mort,
            or_mort=r.or_mort, or_mort_lo=r.or_mort_lo, or_mort_hi=r.or_mort_hi,
            sig_mort=r.sig_mort,
            n_observations=r.n_observations, n_trees=r.n_trees, gremio=r.gremio,
        )
        for r in bundle.species
    ]
    plots = [
        ReferencePlotEffect(
            plot_code=r.plot_code, localidad=r.localidad,
            effect_stall=r.effect_stall, se_stall=r.se_stall, or_stall=r.or_stall,
            effect_mort=r.effect_mort, se_mort=r.se_mort, or_mort=r.or_mort,
            n_trees=r.n_trees,
        )
        for r in bundle.plots
    ]
    variance = [
        VarianceComponent(
            model=r.model, grouping=r.grouping, variance=r.variance, sd=r.sd, icc=r.icc,
            n_levels=r.n_levels, n_observations=r.n_observations, n_events=r.n_events,
        )
        for r in bundle.variance
    ]
    return species, plots, variance


def build_reference_model(bundle: AnalyticsBundle, version: str | None = None) -> ReferenceModel:
    """La fila de `reference_models` para esta corrida.

    `version` por defecto es un timestamp UTC: no hay un numero de version
    humano todavia, y un timestamp es unico y ordenable sin coordinacion.
    """
    return ReferenceModel(
        version=version or datetime.now(UTC).strftime("%Y%m%d%H%M%S"),
        source_dataset=SOURCE_DATASET,
        method=METHOD,
        n_observations=sum(s.n_observations or 0 for s in bundle.species) or None,
        is_active=False,  # lo activa ReferenceRepository.publish_version
    )


def report(bundle: AnalyticsBundle, version: str) -> None:
    sig_stall = [s for s in bundle.species if s.sig_stall]
    sig_mort = [s for s in bundle.species if s.sig_mort]

    print(f"Version a publicar: {version}")
    print(f"Especies:  {len(bundle.species)}")
    print(f"Parcelas:  {len(bundle.plots)}")
    print(f"Varianza:  {len(bundle.variance)} filas")
    print()
    print(f"Especies con IC significativo (estancamiento): {len(sig_stall)}")
    for s in sorted(sig_stall, key=lambda x: -(x.or_stall or 0)):
        signo = "mas" if (s.or_stall or 1) > 1 else "menos"
        print(
            f"  {s.species_name:<28} OR {s.or_stall:5.2f} "
            f"[{s.or_stall_lo:.2f}, {s.or_stall_hi:.2f}]  se estanca {signo}"
        )
    print()
    print(f"Especies con IC significativo (mortalidad): {len(sig_mort)}")
    for s in sig_mort:
        print(
            f"  {s.species_name:<28} OR {s.or_mort:5.2f} "
            f"[{s.or_mort_lo:.2f}, {s.or_mort_hi:.2f}]"
        )
    print()
    for v in bundle.variance:
        print(
            f"  {v.model:<10} {v.grouping:<8} var={v.variance:.3f} "
            f"ICC={v.icc:.3f}  ({v.n_events}/{v.n_observations} eventos)"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--version", default=None, help="Etiqueta de la version (por defecto, timestamp UTC)."
    )
    args = parser.parse_args(argv)

    try:
        bundle = build_bundle(args.processed_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    model = build_reference_model(bundle, version=args.version)
    report(bundle, model.version)

    if args.dry_run:
        print("\n--dry-run: no se publico nada.")
        return 0

    try:
        session = get_session_factory()()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        species, plots, variance = to_orm(bundle)
        published = ReferenceRepository(session).publish_version(model, species, plots, variance)
    finally:
        session.close()

    print(
        f"\nPublicado reference_models.id={published.id} (version={published.version}): "
        f"{len(species)} especies, {len(plots)} parcelas, {len(variance)} componentes."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Ejecutar el test para verlo pasar**

Run: `cd backend && pytest tests/analytics/test_effects_loader.py -v`
Expected: PASS.

- [ ] **Step 5: Actualizar `tests/analytics/conftest.py` para usar `publish_version`**

En `backend/tests/analytics/conftest.py`, dentro de `analytics_client` (líneas 38-79), reemplaza:

```python
    from agrosense.adapters.api.app import create_app
    from agrosense.adapters.api.deps import get_session, get_token_verifier
    from agrosense.adapters.db.models import Base
    from agrosense.adapters.db.repository import AnalyticsRepository

    from agrosense.adapters.analytics.effects_loader import build_bundle  # isort: skip
```

por:

```python
    from agrosense.adapters.api.app import create_app
    from agrosense.adapters.api.deps import get_session, get_token_verifier
    from agrosense.adapters.db.models import Base
    from agrosense.adapters.db.repository import ReferenceRepository

    from agrosense.adapters.analytics.effects_loader import build_bundle  # isort: skip
```

y reemplaza:

```python
    load_analytics = _load_analytics_module()
    bundle = build_bundle(PROCESSED)
    seed = TestingSession()
    try:
        AnalyticsRepository(seed).replace_all(*load_analytics.to_orm(bundle))
    finally:
        seed.close()
```

por:

```python
    load_analytics = _load_analytics_module()
    bundle = build_bundle(PROCESSED)
    seed = TestingSession()
    try:
        model = load_analytics.build_reference_model(bundle, version="test")
        species, plots, variance = load_analytics.to_orm(bundle)
        ReferenceRepository(seed).publish_version(model, species, plots, variance)
    finally:
        seed.close()
```

- [ ] **Step 6: Ejecutar toda la suite de analítica para verla pasar**

Run: `cd backend && pytest tests/analytics/ -v`
Expected: PASS (las pruebas de contrato siguen apuntando a `/api/v1/analytics` hasta el Task 5 — está bien, todavía no lo hemos movido).

- [ ] **Step 7: Commit**

```bash
git add backend/scripts/load_analytics.py backend/tests/analytics/conftest.py backend/tests/analytics/test_effects_loader.py
git commit -m "feat(e5): load_analytics.py publica una version del referente (UC-R2)"
```

---

### Task 4: Rutas — `routes/reference.py`, prefijo `/api/v1/reference`

**Files:**
- Create: `backend/src/agrosense/adapters/api/routes/reference.py` (contenido de `routes/analytics.py`, adaptado)
- Delete: `backend/src/agrosense/adapters/api/routes/analytics.py`
- Modify: `backend/src/agrosense/adapters/api/app.py:34-41`
- Modify: `backend/src/agrosense/adapters/api/errors.py:38` (código `ANALYTICS_NOT_LOADED` → `REFERENCE_NOT_LOADED`)

**Interfaces:**
- Consumes: `ReferenceRepository` (Task 2), `read_analytics.py` sin cambios (el `Protocol AnalyticsReader` ya solo pide `list_species`/`get_species`/`list_plots`/`list_variance`, que `ReferenceRepository` implementa con esos mismos nombres).
- Produces: `router` en `routes/reference.py` con prefijo `/api/v1/reference`, mismos 6 endpoints.

- [ ] **Step 1: Actualizar el test de contrato para que apunte al nuevo prefijo (y falle)**

Reemplaza `backend/tests/analytics/test_analytics_api.py` por `backend/tests/analytics/test_reference_api.py`, sustituyendo cada aparición de `/api/v1/analytics` por `/api/v1/reference` (mismo contenido, `sed`-style; el archivo completo queda igual salvo el prefijo). Por ejemplo, las primeras líneas quedan:

```python
"""Contrato de `/api/v1/reference/*` contra la analitica real cargada."""
from __future__ import annotations

import math

import pytest


def test_list_species_returns_all_thirty(analytics_client):
    r = analytics_client.get("/api/v1/reference/species")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 30
    assert {s["species"] for s in body} != {""}
```

(Repite la sustitución `/api/v1/analytics` → `/api/v1/reference` en las demás ~15 funciones del archivo; el resto de cada test —aserciones, nombres de especie, status codes— no cambia.)

Borra el archivo viejo:

```bash
git rm backend/tests/analytics/test_analytics_api.py
```

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd backend && pytest tests/analytics/test_reference_api.py -v`
Expected: FAIL con 404 en cada request (la ruta sigue viva en `/api/v1/analytics`).

- [ ] **Step 3: Crear `routes/reference.py`**

Copia `backend/src/agrosense/adapters/api/routes/analytics.py` a `backend/src/agrosense/adapters/api/routes/reference.py` y aplica estos cambios puntuales:

```python
"""Endpoints del Referente cientifico (E5).

Regla ADR-003: las routes parsean -> llaman application/ -> mapean respuesta.
Cero logica de negocio aqui: la interpretacion de un OR y el criterio de
significancia viven en `application/use_cases/read_analytics.py`.

Contratos (todos de solo lectura; la publicacion la hace
`scripts/load_analytics.py`, UC-R2):

    GET /api/v1/reference/species                  -> 200 list[SpeciesAnalyticsResponse]
    GET /api/v1/reference/species/top-risk-stall   -> 200 list[...]
    GET /api/v1/reference/species/top-protective   -> 200 list[...]
    GET /api/v1/reference/species/{name}           -> 200 SpeciesAnalyticsResponse | 404
    GET /api/v1/reference/plots                    -> 200 list[PlotAnalyticsResponse]
    GET /api/v1/reference/variance-decomposition   -> 200 list[ModelVarianceResponse]

Orden de declaracion: las rutas fijas `top-risk-stall` y `top-protective` van
ANTES de `/{name}`. Al reves, FastAPI resolveria `/species/top-risk-stall`
contra el parametro y devolveria un 404 buscando la especie "top-risk-stall".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import get_current_engineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import (
    ModelVarianceResponse,
    PlotAnalyticsResponse,
    RiskResponse,
    SpeciesAnalyticsResponse,
    VarianceComponentResponse,
)
from agrosense.adapters.db.repository import ReferenceRepository
from agrosense.application.dtos import (
    ModelVarianceDTO,
    PlotAnalyticsDTO,
    RiskDTO,
    SpeciesAnalyticsDTO,
)
from agrosense.application.use_cases.read_analytics import (
    get_species_analytics,
    list_plot_analytics,
    list_species_analytics,
    top_protective,
    top_risk_stall,
    variance_decomposition,
)

router = APIRouter(
    prefix="/api/v1/reference",
    tags=["reference"],
    dependencies=[Depends(get_current_engineer)],
)

SessionDep = Annotated[Session, Depends(get_session)]

MAX_TOP = 30


def _repo(session: Session) -> ReferenceRepository:
    return ReferenceRepository(session)


# ── el resto del archivo (mapeos _to_risk/_to_species/_to_plot/_to_variance
# y los 6 endpoints) queda IGUAL que en analytics.py: no usan el nombre de
# la clase del repositorio en ningun otro punto. ──────────────────────────
```

(El cuerpo de `_to_risk`, `_to_species`, `_to_plot`, `_to_variance` y los seis `@router.get(...)` se copian tal cual de `analytics.py` — solo cambiaron el docstring del módulo, el import de `ReferenceRepository` y el `prefix` del router.)

En el endpoint `variance_decomposition_endpoint`, cambia el código de error:

```python
    if not (dtos := variance_decomposition(_repo(session))):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "REFERENCE_NOT_LOADED",
                "message": "El referente no esta publicado. Ejecute "
                "scripts/load_analytics.py.",
            },
        )
```

Borra el archivo viejo:

```bash
git rm backend/src/agrosense/adapters/api/routes/analytics.py
```

- [ ] **Step 4: Actualizar `app.py`**

En `backend/src/agrosense/adapters/api/app.py:34-41`, reemplaza:

```python
    # Rutas del slice 5 (analitica de los modelos mixtos, solo lectura).
    # Llevan prefijo /api/v1 mientras que las del slice 2 no: es deuda
    # conocida del contrato, anotada en docs/deuda-tecnica.md. Versionar las
    # existentes rompe al consumidor del slice 2, asi que se unifica cuando
    # haya un cambio de contrato que lo justifique, no de paso.
    from agrosense.adapters.api.routes.analytics import router as analytics_router

    app.include_router(analytics_router)
```

por:

```python
    # E5: Referente cientifico (efectos de los modelos mixtos, solo lectura).
    # Lleva prefijo /api/v1 mientras que las rutas de proyecto no: es deuda
    # conocida del contrato, anotada en docs/deuda-tecnica.md. Versionar las
    # existentes rompe al consumidor de esas rutas, asi que se unifica cuando
    # haya un cambio de contrato que lo justifique, no de paso.
    from agrosense.adapters.api.routes.reference import router as reference_router

    app.include_router(reference_router)
```

- [ ] **Step 5: Renombrar el código de error en `errors.py`**

En `backend/src/agrosense/adapters/api/errors.py:38`, cambia:

```python
    "ANALYTICS_NOT_LOADED": 404,
```

por:

```python
    "REFERENCE_NOT_LOADED": 404,
```

- [ ] **Step 6: Ejecutar el test para verlo pasar**

Run: `cd backend && pytest tests/analytics/ -v`
Expected: PASS (todos los tests de `test_reference_api.py`, incluyendo `empty_analytics_client` para el 404 de `REFERENCE_NOT_LOADED` si existe un test parametrizado para eso — si no existe, añádelo):

```python
def test_variance_not_published_is_404_with_the_right_code(empty_analytics_client):
    r = empty_analytics_client.get("/api/v1/reference/variance-decomposition")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "REFERENCE_NOT_LOADED"
```

- [ ] **Step 7: Commit**

```bash
git add backend/src/agrosense/adapters/api/routes/reference.py backend/src/agrosense/adapters/api/app.py backend/src/agrosense/adapters/api/errors.py backend/tests/analytics/test_reference_api.py
git commit -m "feat(e5): renombra /api/v1/analytics a /api/v1/reference"
```

---

### Task 5: Actualizar el smoke test de analítica

**Files:**
- Modify: `backend/tests/smoke/test_analytics_smoke.py` → renombrar a `backend/tests/smoke/test_reference_smoke.py`

**Interfaces:**
- Consumes: contrato `/api/v1/reference/*` (Task 4).

- [ ] **Step 1: Leer el smoke test actual**

Run: `cd backend && cat tests/smoke/test_analytics_smoke.py` — identifica cada URL `/api/v1/analytics/...` y cada import de `AnalyticsRepository` si los hay.

- [ ] **Step 2: Renombrar y actualizar**

```bash
git mv backend/tests/smoke/test_analytics_smoke.py backend/tests/smoke/test_reference_smoke.py
```

Edita `backend/tests/smoke/test_reference_smoke.py` sustituyendo toda ocurrencia de `/api/v1/analytics` por `/api/v1/reference`, y cualquier `AnalyticsRepository` por `ReferenceRepository` (mismos métodos de lectura, mismo uso).

- [ ] **Step 3: Ejecutar el smoke test (marcado `supabase`, requiere `DATABASE_URL`; si no hay conexión disponible, se salta)**

Run: `cd backend && pytest tests/smoke/test_reference_smoke.py -v -m supabase`
Expected: PASS, o SKIPPED si no hay `DATABASE_URL` configurada en el entorno — en ese caso, verifícalo leyendo el archivo para confirmar que no queda ninguna referencia a `/api/v1/analytics` ni a `AnalyticsRepository`:

Run: `cd backend && grep -rn "api/v1/analytics\|AnalyticsRepository" tests/smoke/test_reference_smoke.py`
Expected: sin resultados.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/smoke/test_reference_smoke.py
git commit -m "test(e5): smoke test de analitica apunta a /api/v1/reference"
```

---

### Task 6: Frontend — el cliente apunta a `/api/v1/reference`

**Files:**
- Modify: `frontend/src/api/client.ts:1-18`
- Modify: `frontend/src/api/client.test.ts:36,51` (y cualquier otra URL literal `/api/v1/analytics`)

**Interfaces:**
- Consumes: contrato `/api/v1/reference/*` (Task 4). Ningún tipo de `types.ts` cambia (mismo shape de respuesta).

- [ ] **Step 1: Actualizar `client.test.ts` para que falle**

En `frontend/src/api/client.test.ts`, cambia las URLs esperadas:

```ts
    expect(spy.mock.calls[0][0]).toBe("/api/v1/reference/species?sort=stall_risk");
```

```ts
      "/api/v1/reference/species/Lafoensia%20speciosa",
```

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd frontend && npx vitest run src/api/client.test.ts`
Expected: FAIL (el cliente sigue pidiendo `/api/v1/analytics/...`).

- [ ] **Step 3: Actualizar `client.ts`**

En `frontend/src/api/client.ts:2,18`, cambia:

```ts
/**
 * Acceso a datos del Referente cientifico (`/api/v1/reference`).
 *
 * El transporte (URL, token de sesion, errores) vive en `http.ts`.
 */
```

y:

```ts
const BASE = "/api/v1/reference";
```

(El resto del archivo —`fetchSpecies`, `fetchSpeciesDetail`, `fetchTopRiskStall`, `fetchTopProtective`, `fetchPlots`, `fetchVarianceDecomposition`— no cambia: todos construyen la URL a partir de `BASE`.)

- [ ] **Step 4: Ejecutar el test para verlo pasar**

Run: `cd frontend && npx vitest run src/api/client.test.ts`
Expected: PASS.

- [ ] **Step 5: Actualizar el comentario de cabecera en `types.ts`**

En `frontend/src/api/types.ts:2`, cambia:

```ts
 * Tipos del contrato de `/api/v1/reference/*`.
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/client.test.ts frontend/src/api/types.ts
git commit -m "feat(e5): el cliente del referente apunta a /api/v1/reference"
```

---

### Task 7: Gate de verificación — Slice 1

**Files:** ninguno (solo comandos).

- [ ] **Step 1: Backend — suite completa**

Run: `cd backend && pytest -q`
Expected: 0 failed. Presta atención a `tests/architecture/test_layer_dependencies.py` (el rename no debe introducir un import hacia afuera de su capa) y a `tests/db/` completo.

- [ ] **Step 2: Backend — lint y tipos**

Run: `cd backend && ruff check . && mypy src/agrosense` (usa los comandos exactos que ya use el proyecto; revisa `pyproject.toml` si difieren).
Expected: sin errores.

- [ ] **Step 3: Frontend — suite completa**

Run: `cd frontend && npx vitest run`
Expected: 0 failed.

- [ ] **Step 4: Frontend — build**

Run: `cd frontend && npm run build`
Expected: build exitoso (confirma que ningún import roto de `client.ts`/`types.ts` quedó suelto).

- [ ] **Step 5: Grep de residuos del nombre viejo**

Run: `grep -rn "api/v1/analytics\|AnalyticsRepository\|species_analytics\|plot_analytics" backend/src backend/tests backend/scripts frontend/src`
Expected: sin resultados (o solo en comentarios históricos de ADRs/docs que documentan el pasado — no en código ni tests).

- [ ] **Step 6: Confirmar manualmente**

Levanta el backend y pide `GET /api/v1/reference/species` con un token válido: debe responder 200 con las 30 especies. Pide `GET /api/v1/analytics/species`: debe responder 404 (la ruta ya no existe).

---

## Slice 2 — UC-AN3: Contraste de especies del proyecto con el referente

### Task 8: Repositorio — especies plantadas de un proyecto

**Files:**
- Modify: `backend/src/agrosense/adapters/db/repository.py` (nueva clase, al final del archivo)
- Test: `backend/tests/db/test_project_species_repository.py` (nuevo)

**Interfaces:**
- Produces: `ProjectSpeciesRepository.list_species(project_id: int) -> list[tuple[str, int]]` (especie, árboles distintos), ordenado por nombre de especie.

- [ ] **Step 1: Escribir el test que falla**

Crea `backend/tests/db/test_project_species_repository.py`:

```python
"""ProjectSpeciesRepository: especies plantadas de un proyecto (E5, UC-AN3)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import Base, Project, TreeRow
from agrosense.adapters.db.repository import ProjectSpeciesRepository


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


def _project(session, owner="eng-1") -> Project:
    p = Project(name="P1", owner_id=owner, project_code="AGS-2026-0001")
    session.add(p)
    session.commit()
    return p


def test_lists_distinct_species_with_tree_count(session):
    p = _project(session)
    session.add_all([
        TreeRow(project_id=p.id, tree_id="T1", species="Lafoensia speciosa"),
        TreeRow(project_id=p.id, tree_id="T2", species="Lafoensia speciosa"),
        TreeRow(project_id=p.id, tree_id="T3", species="Inga punctata"),
    ])
    session.commit()

    rows = ProjectSpeciesRepository(session).list_species(p.id)

    assert rows == [("Inga punctata", 1), ("Lafoensia speciosa", 2)]


def test_only_this_projects_trees_count(session):
    p1 = _project(session, owner="eng-1")
    p2 = _project(session, owner="eng-2")
    session.add_all([
        TreeRow(project_id=p1.id, tree_id="T1", species="Especie A"),
        TreeRow(project_id=p2.id, tree_id="T1", species="Especie B"),
    ])
    session.commit()

    rows = ProjectSpeciesRepository(session).list_species(p1.id)
    assert rows == [("Especie A", 1)]


def test_project_without_trees_is_empty(session):
    p = _project(session)
    assert ProjectSpeciesRepository(session).list_species(p.id) == []
```

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd backend && pytest tests/db/test_project_species_repository.py -v`
Expected: FAIL (`ImportError: cannot import name 'ProjectSpeciesRepository'`).

- [ ] **Step 3: Implementar el repositorio**

Al final de `backend/src/agrosense/adapters/db/repository.py`, añade:

```python
class ProjectSpeciesRepository:
    """Especies plantadas de un proyecto, para el contraste con el referente
    cientifico (E5, UC-AN3)."""

    def __init__(self, session: Session):
        self._s = session

    def list_species(self, project_id: int) -> list[tuple[str, int]]:
        """(especie, arboles distintos) del proyecto, especie ascendente."""
        stmt = (
            select(TreeRow.species, func.count(TreeRow.id))
            .where(TreeRow.project_id == project_id)
            .group_by(TreeRow.species)
            .order_by(TreeRow.species)
        )
        return [(species, int(count)) for species, count in self._s.execute(stmt).all()]
```

- [ ] **Step 4: Ejecutar el test para verlo pasar**

Run: `cd backend && pytest tests/db/test_project_species_repository.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/adapters/db/repository.py backend/tests/db/test_project_species_repository.py
git commit -m "feat(e5): ProjectSpeciesRepository lista especies plantadas por proyecto"
```

---

### Task 9: Caso de uso — contrastar especies del proyecto con el referente (UC-AN3)

**Files:**
- Modify: `backend/src/agrosense/application/use_cases/read_analytics.py` (promueve dos helpers privados a públicos)
- Modify: `backend/src/agrosense/application/dtos.py` (nuevo DTO)
- Create: `backend/src/agrosense/application/use_cases/contrast_species.py`
- Test: `backend/tests/application/test_contrast_species.py` (nuevo)

**Interfaces:**
- Consumes: `ProjectSpeciesRepository.list_species` (Task 8), `ReferenceRepository.get_species` (Task 2), `MODEL_STALL`/`MODEL_MORTALITY` (ya existen en `read_analytics.py`).
- Produces: `SpeciesContrastDTO` (dataclass), `contrast_project_species(project_id, project_repo, reference_repo) -> list[SpeciesContrastDTO]`.

- [ ] **Step 1: Escribir el test que falla**

Crea `backend/tests/application/test_contrast_species.py`:

```python
"""UC-AN3: contrastar las especies plantadas de un proyecto con el referente."""
from __future__ import annotations

from dataclasses import dataclass

from agrosense.application.use_cases.contrast_species import contrast_project_species


@dataclass
class _FakeEffect:
    species_name: str
    effect_stall: float | None = None
    se_stall: float | None = None
    or_stall: float | None = None
    or_stall_lo: float | None = None
    or_stall_hi: float | None = None
    sig_stall: bool | None = None
    effect_mort: float | None = None
    se_mort: float | None = None
    or_mort: float | None = None
    or_mort_lo: float | None = None
    or_mort_hi: float | None = None
    sig_mort: bool | None = None
    gremio: str | None = None


class _FakeProjectRepo:
    def __init__(self, species: list[tuple[str, int]]):
        self._species = species

    def list_species(self, project_id: int) -> list[tuple[str, int]]:
        return self._species


class _FakeReferenceRepo:
    def __init__(self, rows: dict[str, _FakeEffect]):
        self._rows = rows

    def get_species(self, name: str):
        return self._rows.get(name)


def test_species_with_significant_reference_effect_gets_a_narrative():
    project_repo = _FakeProjectRepo([("Lafoensia speciosa", 12)])
    reference_repo = _FakeReferenceRepo({
        "Lafoensia speciosa": _FakeEffect(
            species_name="Lafoensia speciosa",
            effect_stall=1.598, se_stall=0.3, or_stall=4.94,
            or_stall_lo=2.71, or_stall_hi=9.02, sig_stall=True,
            effect_mort=0.0, se_mort=0.5, or_mort=1.0,
            or_mort_lo=0.4, or_mort_hi=2.5, sig_mort=False,
            gremio="Tardia",
        ),
    })

    out = contrast_project_species(1, project_repo, reference_repo)

    assert len(out) == 1
    dto = out[0]
    assert dto.species == "Lafoensia speciosa"
    assert dto.n_trees_in_project == 12
    assert dto.has_reference is True
    assert dto.gremio == "Tardia"
    assert dto.stall_risk.significant is True
    assert dto.stall_risk.odds_ratio == 4.94
    assert "12" in dto.narrative
    assert "Lafoensia speciosa" in dto.narrative


def test_species_absent_from_the_reference_is_marked_not_an_error():
    project_repo = _FakeProjectRepo([("Especie inventada", 3)])
    reference_repo = _FakeReferenceRepo({})

    out = contrast_project_species(1, project_repo, reference_repo)

    assert len(out) == 1
    dto = out[0]
    assert dto.has_reference is False
    assert dto.stall_risk is None
    assert dto.mortality_risk is None
    assert "Sin referencia" in dto.narrative


def test_project_without_trees_returns_an_empty_list():
    out = contrast_project_species(1, _FakeProjectRepo([]), _FakeReferenceRepo({}))
    assert out == []


def test_mixes_species_with_and_without_reference():
    project_repo = _FakeProjectRepo([
        ("Especie inventada", 1),
        ("Lafoensia speciosa", 5),
    ])
    reference_repo = _FakeReferenceRepo({
        "Lafoensia speciosa": _FakeEffect(species_name="Lafoensia speciosa", or_stall=4.94),
    })

    out = contrast_project_species(1, project_repo, reference_repo)

    assert [d.has_reference for d in out] == [False, True]
```

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd backend && pytest tests/application/test_contrast_species.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'agrosense.application.use_cases.contrast_species'`).

- [ ] **Step 3: Promover `_risk` y `_log_ci` a nombres públicos en `read_analytics.py`**

En `backend/src/agrosense/application/use_cases/read_analytics.py`, renombra la función `_log_ci` (línea 112) a `log_odds_ci` y `_risk` (línea 92) a `build_risk`, y actualiza sus dos llamadas internas en `_species_dto` y `_plot_dto`:

```python
def log_odds_ci(effect: float | None, se: float | None) -> tuple[float | None, float | None]:
    """Reconstruye el IC en log-odds a partir de efecto y error estandar.

    Publica (sin guion bajo) porque `contrast_species.py` (UC-AN3) tambien
    necesita reconstruir el IC de un efecto de especie, y la formula es la
    misma: no se duplica.
    """
    if effect is None or se is None:
        return None, None
    return effect - 1.96 * se, effect + 1.96 * se


def build_risk(
    or_value: float | None,
    or_lo: float | None,
    or_hi: float | None,
    lo_log: float | None,
    hi_log: float | None,
    significant: bool | None,
    model: str,
) -> RiskDTO:
    return RiskDTO(
        odds_ratio=or_value,
        or_ci95=(or_lo, or_hi) if or_lo is not None and or_hi is not None else None,
        ci95_log_odds=(
            (lo_log, hi_log) if lo_log is not None and hi_log is not None else None
        ),
        significant=significant,
        interpretation=interpret(or_value, or_lo, or_hi, significant, model),
    )
```

Y en `_species_dto`/`_plot_dto`, sustituye cada `_log_ci(` por `log_odds_ci(` y cada `_risk(` por `build_risk(`.

- [ ] **Step 4: Ejecutar la suite de analítica para confirmar que el rename no rompió nada**

Run: `cd backend && pytest tests/analytics/ -v`
Expected: PASS (el rename es interno, el contrato HTTP no cambia).

- [ ] **Step 5: Añadir `SpeciesContrastDTO` a `dtos.py`**

En `backend/src/agrosense/application/dtos.py`, después de `ModelVarianceDTO` (línea ~257), añade:

```python
@dataclass(frozen=True)
class SpeciesContrastDTO:
    """Una especie plantada en un proyecto, frente al Referente cientifico
    (E5, UC-AN3). `has_reference=False` cuando la especie no esta entre las
    del referente: no es un error, se dice en vez de inventar un efecto."""

    species: str
    n_trees_in_project: int
    has_reference: bool
    gremio: str | None
    stall_risk: RiskDTO | None
    mortality_risk: RiskDTO | None
    narrative: str
```

- [ ] **Step 6: Escribir `contrast_species.py`**

Crea `backend/src/agrosense/application/use_cases/contrast_species.py`:

```python
"""UC-AN3: contrastar las especies plantadas de un proyecto con el Referente
cientifico (E5).

Cruza `trees.species` (por proyecto) contra la version activa de
`reference_species_effects`. Reutiliza `build_risk`/`log_odds_ci`/
`interpret` de `read_analytics.py`: la interpretacion de un OR es la MISMA
regla de negocio aqui que en el ranking del referente, y AGENTS.md prohibe
duplicarla.
"""
from __future__ import annotations

from typing import Protocol

from agrosense.application.dtos import RiskDTO, SpeciesContrastDTO
from agrosense.application.use_cases.read_analytics import (
    MODEL_MORTALITY,
    MODEL_STALL,
    build_risk,
    log_odds_ci,
)

_SIN_REFERENCIA = (
    "Sin referencia: esta especie no esta entre las del dataset cientifico. "
    "Todavia no se puede comparar."
)


class ProjectSpeciesReader(Protocol):
    def list_species(self, project_id: int) -> list[tuple[str, int]]: ...


class ReferenceSpeciesReader(Protocol):
    def get_species(self, name: str) -> object | None: ...


def _narrative(species: str, n_trees: int, stall: RiskDTO, mortality: RiskDTO) -> str:
    arboles = "arbol" if n_trees == 1 else "arboles"
    return (
        f"Planto {n_trees} {arboles} de {species}. "
        f"Estancamiento: {stall.interpretation} "
        f"Mortalidad: {mortality.interpretation}"
    )


def contrast_project_species(
    project_id: int,
    project_repo: ProjectSpeciesReader,
    reference_repo: ReferenceSpeciesReader,
) -> list[SpeciesContrastDTO]:
    out: list[SpeciesContrastDTO] = []
    for species, n_trees in project_repo.list_species(project_id):
        row = reference_repo.get_species(species)
        if row is None:
            out.append(
                SpeciesContrastDTO(
                    species=species,
                    n_trees_in_project=n_trees,
                    has_reference=False,
                    gremio=None,
                    stall_risk=None,
                    mortality_risk=None,
                    narrative=_SIN_REFERENCIA,
                )
            )
            continue

        lo_s, hi_s = log_odds_ci(row.effect_stall, row.se_stall)
        stall = build_risk(
            row.or_stall, row.or_stall_lo, row.or_stall_hi, lo_s, hi_s,
            row.sig_stall, MODEL_STALL,
        )
        lo_m, hi_m = log_odds_ci(row.effect_mort, row.se_mort)
        mortality = build_risk(
            row.or_mort, row.or_mort_lo, row.or_mort_hi, lo_m, hi_m,
            row.sig_mort, MODEL_MORTALITY,
        )
        out.append(
            SpeciesContrastDTO(
                species=species,
                n_trees_in_project=n_trees,
                has_reference=True,
                gremio=row.gremio,
                stall_risk=stall,
                mortality_risk=mortality,
                narrative=_narrative(species, n_trees, stall, mortality),
            )
        )
    return out
```

- [ ] **Step 7: Ejecutar el test para verlo pasar**

Run: `cd backend && pytest tests/application/test_contrast_species.py -v`
Expected: PASS (4 tests).

- [ ] **Step 8: Commit**

```bash
git add backend/src/agrosense/application/use_cases/read_analytics.py backend/src/agrosense/application/use_cases/contrast_species.py backend/src/agrosense/application/dtos.py backend/tests/application/test_contrast_species.py
git commit -m "feat(e5): UC-AN3 - contrastar especies del proyecto con el referente"
```

---

### Task 10: Ruta — `GET /projects/{project_id}/reference-contrast`

**Files:**
- Modify: `backend/src/agrosense/adapters/api/schemas.py` (nuevo `SpeciesContrastResponse`)
- Create: `backend/src/agrosense/adapters/api/routes/reference_contrast.py`
- Modify: `backend/src/agrosense/adapters/api/app.py` (registrar el router)
- Test: `backend/tests/api/test_reference_contrast_api.py` (nuevo)

**Interfaces:**
- Consumes: `contrast_project_species` (Task 9), `ProjectRepository.get_owned` (ya existe), `ProjectSpeciesRepository` (Task 8), `ReferenceRepository` (Task 2).
- Produces: endpoint `GET /projects/{project_id}/reference-contrast -> 200 list[SpeciesContrastResponse] | 404`. Sin prefijo `/api/v1` (mismo patrón que `routes/indices.py` y `routes/map.py`: solo el Referente en sí quedó bajo `/api/v1`, deuda anotada en `docs/deuda-tecnica.md`).

- [ ] **Step 1: Escribir el test que falla**

Crea `backend/tests/api/test_reference_contrast_api.py`:

```python
"""Contraste de especies del proyecto con el referente (E5, UC-AN3)."""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.auth.keys import ENGINEER_B, bearer, fake_verifier

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
X0, Y0 = 4735700.0, 2199400.0

HEADERS = [
    "LOCALIDAD", "Codigo de unidad muestreo", "ID Parcela", "Diseño floristico",
    "Cobertura vegetal asociada", "ID_MUEST", "Especie_M1", "Familia",
    "Coord_X", "Coord_Y", "Altura total (m)_M1", "Sobrevivencia M1",
    "Estado Fitosanitario_M1",
]


def _excel(especies: list[str]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_1"
    ws.append(HEADERS)
    for i, especie in enumerate(especies):
        ws.append([
            "Guayabal", "U1", 1, "Rehabilitación vegetal", "Bosque de galería",
            f"G_{i}", especie, "Fabaceae", X0 + 30 * i, Y0, 0.5, "Vivo", "Bueno",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def client_and_session():
    """Como `tests/api/conftest.py::client`, pero expone la sesion para poder
    sembrar el referente directamente (no hay endpoint HTTP para publicarlo:
    UC-R2 lo hace `scripts/load_analytics.py`)."""
    from agrosense.adapters.api.app import create_app
    from agrosense.adapters.api.deps import get_session, get_token_verifier
    from agrosense.adapters.db.models import Base

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    app = create_app()

    def _override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_token_verifier] = fake_verifier

    with TestClient(app, headers=bearer()) as c:
        yield c, Session
    engine.dispose()


def _publish_reference(Session, species_with_effect: dict[str, float]):
    from agrosense.adapters.db.models import ReferenceSpeciesEffect
    from agrosense.adapters.db.repository import ReferenceRepository
    import sys
    from pathlib import Path

    scripts = Path(__file__).parents[2] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import load_analytics

    s = Session()
    try:
        model = load_analytics.build_reference_model(
            type("B", (), {"species": []})(), version="test"
        )
        rows = [
            ReferenceSpeciesEffect(
                species_name=name, or_stall=or_stall, sig_stall=True,
                effect_stall=0.1, se_stall=0.1,
                or_stall_lo=or_stall * 0.5, or_stall_hi=or_stall * 1.5,
            )
            for name, or_stall in species_with_effect.items()
        ]
        ReferenceRepository(s).publish_version(model, rows, [], [])
    finally:
        s.close()


def test_project_species_in_the_reference_get_their_risk(client_and_session):
    client, Session = client_and_session
    _publish_reference(Session, {"Lafoensia speciosa": 4.94})

    pid = client.post("/projects", json={"name": "Contraste"}).json()["id"]
    client.post(
        f"/projects/{pid}/campaigns",
        files={"file": ("m.xlsx", _excel(["Lafoensia speciosa"]), XLSX)},
    )

    r = client.get(f"/projects/{pid}/reference-contrast")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["species"] == "Lafoensia speciosa"
    assert body[0]["has_reference"] is True
    assert body[0]["n_trees_in_project"] == 1
    assert body[0]["stall_risk"]["odds_ratio"] == pytest.approx(4.94)


def test_project_species_absent_from_the_reference_is_flagged(client_and_session):
    client, Session = client_and_session
    _publish_reference(Session, {"Lafoensia speciosa": 4.94})

    pid = client.post("/projects", json={"name": "Contraste 2"}).json()["id"]
    client.post(
        f"/projects/{pid}/campaigns",
        files={"file": ("m.xlsx", _excel(["Especie sin referencia"]), XLSX)},
    )

    r = client.get(f"/projects/{pid}/reference-contrast")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["has_reference"] is False
    assert body[0]["stall_risk"] is None


def test_a_foreign_project_is_404(client_and_session):
    client, Session = client_and_session
    pid = client.post("/projects", json={"name": "Ajeno"}).json()["id"]

    r = client.get(
        f"/projects/{pid}/reference-contrast", headers=bearer(ENGINEER_B)
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
```

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd backend && pytest tests/api/test_reference_contrast_api.py -v`
Expected: FAIL con 404 en cada request (la ruta no existe todavía).

- [ ] **Step 3: Añadir `SpeciesContrastResponse` a `schemas.py`**

En `backend/src/agrosense/adapters/api/schemas.py`, después de `ModelVarianceResponse`, añade:

```python
class SpeciesContrastResponse(BaseModel):
    """Una especie plantada del proyecto, frente al Referente (E5, UC-AN3)."""

    species: str
    n_trees_in_project: int
    has_reference: bool
    gremio: str | None = None
    stall_risk: RiskResponse | None = None
    mortality_risk: RiskResponse | None = None
    narrative: str
```

- [ ] **Step 4: Escribir `routes/reference_contrast.py`**

```python
"""UC-AN3: contraste de las especies plantadas con el Referente cientifico (E5).

Contrato (exige sesion; proyecto ajeno -> 404):
    GET /projects/{project_id}/reference-contrast -> 200 list[SpeciesContrastResponse]
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import RiskResponse, SpeciesContrastResponse
from agrosense.adapters.db.repository import (
    ProjectRepository,
    ProjectSpeciesRepository,
    ReferenceRepository,
)
from agrosense.application.dtos import RiskDTO, SpeciesContrastDTO
from agrosense.application.errors import AppError
from agrosense.application.use_cases.contrast_species import contrast_project_species

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


def _to_risk(risk: RiskDTO | None) -> RiskResponse | None:
    if risk is None:
        return None
    return RiskResponse(
        odds_ratio=risk.odds_ratio,
        or_ci95=risk.or_ci95,
        ci95_log_odds=risk.ci95_log_odds,
        significant=risk.significant,
        interpretation=risk.interpretation,
    )


def _to_response(dto: SpeciesContrastDTO) -> SpeciesContrastResponse:
    return SpeciesContrastResponse(
        species=dto.species,
        n_trees_in_project=dto.n_trees_in_project,
        has_reference=dto.has_reference,
        gremio=dto.gremio,
        stall_risk=_to_risk(dto.stall_risk),
        mortality_risk=_to_risk(dto.mortality_risk),
        narrative=dto.narrative,
    )


@router.get(
    "/projects/{project_id}/reference-contrast",
    response_model=list[SpeciesContrastResponse],
)
def get_reference_contrast_endpoint(
    project_id: int, session: SessionDep, engineer: CurrentEngineer
) -> list[SpeciesContrastResponse]:
    project = ProjectRepository(session).get_owned(project_id, engineer.id)
    if project is None:
        raise_for_value_error(
            AppError("PROJECT_NOT_FOUND", f"El proyecto {project_id} no existe.")
        )
    dtos = contrast_project_species(
        project_id,
        ProjectSpeciesRepository(session),
        ReferenceRepository(session),
    )
    return [_to_response(d) for d in dtos]
```

- [ ] **Step 5: Registrar el router en `app.py`**

En `backend/src/agrosense/adapters/api/app.py`, después del bloque de `indices_router` (línea ~66), añade:

```python
    # E5: contraste de las especies del proyecto con el referente (UC-AN3)
    from agrosense.adapters.api.routes.reference_contrast import router as contrast_router

    app.include_router(contrast_router)
```

- [ ] **Step 6: Ejecutar el test para verlo pasar**

Run: `cd backend && pytest tests/api/test_reference_contrast_api.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add backend/src/agrosense/adapters/api/schemas.py backend/src/agrosense/adapters/api/routes/reference_contrast.py backend/src/agrosense/adapters/api/app.py backend/tests/api/test_reference_contrast_api.py
git commit -m "feat(e5): GET /projects/{id}/reference-contrast (UC-AN3)"
```

---

### Task 11: Frontend — cliente y tipos del contraste

**Files:**
- Modify: `frontend/src/api/types.ts` (nueva interfaz)
- Create: `frontend/src/api/contrast.ts`
- Test: `frontend/src/api/contrast.test.ts` (nuevo)

**Interfaces:**
- Consumes: `GET /projects/{id}/reference-contrast` (Task 10), `Risk` (ya existe en `types.ts`).
- Produces: `getReferenceContrast(projectId, signal?) -> Promise<SpeciesContrast[]>`.

- [ ] **Step 1: Escribir el test que falla**

Crea `frontend/src/api/contrast.test.ts` (mirroring el estilo de `client.test.ts`):

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { getReferenceContrast } from "./contrast";
import * as http from "./http";

describe("getReferenceContrast", () => {
  afterEach(() => vi.restoreAllMocks());

  it("pide el contraste del proyecto por su id", async () => {
    const spy = vi.spyOn(http, "request").mockResolvedValue([]);

    await getReferenceContrast(42);

    expect(spy).toHaveBeenCalledWith(
      "/projects/42/reference-contrast",
      { signal: undefined },
    );
  });
});
```

(Ajusta la forma exacta de la aserción al patrón real de `client.test.ts` / `indices.test.ts` si difiere en cómo se mockea `request` — revisa esos archivos antes de este paso y replica su estilo exacto de mock.)

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd frontend && npx vitest run src/api/contrast.test.ts`
Expected: FAIL (`Cannot find module './contrast'`).

- [ ] **Step 3: Añadir el tipo `SpeciesContrast` a `types.ts`**

Al final de `frontend/src/api/types.ts`, añade:

```ts
// ── E5: contraste de especies del proyecto con el referente (UC-AN3) ──────

export interface SpeciesContrast {
  species: string;
  n_trees_in_project: number;
  has_reference: boolean;
  gremio: string | null;
  stall_risk: Risk | null;
  mortality_risk: Risk | null;
  narrative: string;
}
```

- [ ] **Step 4: Escribir `contrast.ts`**

Crea `frontend/src/api/contrast.ts`:

```ts
/** Acceso al contraste de especies del proyecto con el referente (E5, UC-AN3). */
import { request } from "./http";
import type { SpeciesContrast } from "./types";

export function getReferenceContrast(
  projectId: number,
  signal?: AbortSignal,
): Promise<SpeciesContrast[]> {
  return request<SpeciesContrast[]>(`/projects/${projectId}/reference-contrast`, { signal });
}
```

- [ ] **Step 5: Ejecutar el test para verlo pasar**

Run: `cd frontend && npx vitest run src/api/contrast.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/contrast.ts frontend/src/api/contrast.test.ts
git commit -m "feat(e5): cliente del contraste de especies (UC-AN3)"
```

---

### Task 12: Frontend — extraer `RiskBlock`, página de contraste y enlace desde el proyecto

**Files:**
- Create: `frontend/src/components/RiskBlock.tsx`
- Modify: `frontend/src/components/SpeciesDetail.tsx` (usa el componente extraído)
- Create: `frontend/src/pages/ContrastPage.tsx`
- Modify: `frontend/src/pages/ProjectDetailPage.tsx` (enlace nuevo)
- Modify: `frontend/src/App.tsx` (ruta nueva)
- Test: `frontend/src/components/ContrastPage.test.tsx` (nuevo)

**Interfaces:**
- Consumes: `getReferenceContrast` (Task 11), `getProject` (ya existe), `useAsync` (ya existe).
- Produces: componente `RiskBlock` reutilizable, página `ContrastPage` en la ruta `/proyectos/:id/referente-contraste`.

- [ ] **Step 1: Escribir el test de la página que falla**

Crea `frontend/src/components/ContrastPage.test.tsx` (sigue el patrón de `AnalyticsPage.test.tsx`: mockea el módulo `api/contrast` y `api/projects`, renderiza con `MemoryRouter`):

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ContrastPage } from "../pages/ContrastPage";

vi.mock("../api/contrast", () => ({
  getReferenceContrast: vi.fn().mockResolvedValue([
    {
      species: "Lafoensia speciosa",
      n_trees_in_project: 12,
      has_reference: true,
      gremio: "Tardia",
      stall_risk: {
        odds_ratio: 4.94, or_ci95: [2.71, 9.02], ci95_log_odds: null,
        significant: true, interpretation: "Se estanca ~4.9x mas de lo esperado.",
      },
      mortality_risk: {
        odds_ratio: 1.0, or_ci95: [0.4, 2.5], ci95_log_odds: null,
        significant: false, interpretation: "Sin efecto significativo.",
      },
      narrative: "Planto 12 arboles de Lafoensia speciosa...",
    },
    {
      species: "Especie inventada",
      n_trees_in_project: 3,
      has_reference: false,
      gremio: null,
      stall_risk: null,
      mortality_risk: null,
      narrative: "Sin referencia: esta especie no esta entre las del dataset cientifico.",
    },
  ]),
}));

vi.mock("../api/projects", () => ({
  getProject: vi.fn().mockResolvedValue({ id: 1, name: "Proyecto de prueba" }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/proyectos/1/referente-contraste"]}>
      <Routes>
        <Route path="/proyectos/:id/referente-contraste" element={<ContrastPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ContrastPage", () => {
  it("muestra la especie con referente y su lectura", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Lafoensia speciosa"));
    expect(screen.getByText(/4.9x mas/)).toBeInTheDocument();
  });

  it("marca la especie sin referencia en vez de omitirla", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Especie inventada"));
    expect(screen.getByText(/Sin referencia/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Ejecutar el test para verlo fallar**

Run: `cd frontend && npx vitest run src/components/ContrastPage.test.tsx`
Expected: FAIL (`Cannot find module '../pages/ContrastPage'`).

- [ ] **Step 3: Extraer `RiskBlock` de `SpeciesDetail.tsx`**

Crea `frontend/src/components/RiskBlock.tsx`:

```tsx
/**
 * Bloque de una metrica de riesgo (estancamiento o mortalidad).
 *
 * Extraido de `SpeciesDetail.tsx` (Slice 5) para reutilizarlo en el
 * contraste de especies del proyecto (E5, UC-AN3): la misma regla de
 * "IC que cruza 1 no es un hallazgo" aplica en los dos sitios, y AGENTS.md
 * prohibe duplicar la logica de negocio en el frontend — aqui ademas se
 * duplicaria el MARKUP, que es peor.
 */
import type { Risk } from "../api/types";
import { COLORS } from "../theme";

interface Props {
  label: string;
  risk: Risk;
}

export function RiskBlock({ label, risk }: Props) {
  const color =
    risk.significant !== true
      ? COLORS.inconclusive
      : (risk.odds_ratio ?? 1) > 1
        ? COLORS.risk
        : COLORS.protective;

  return (
    <div className="risk-block">
      <h4>{label}</h4>
      {risk.odds_ratio === null ? (
        <p className="muted">Sin estimación disponible.</p>
      ) : (
        <>
          <p className="risk-or" style={{ color }}>
            OR {risk.odds_ratio.toFixed(2)}
            {risk.significant === true ? (
              <span className="badge badge-sig">IC concluyente</span>
            ) : (
              <span className="badge badge-nosig">IC cruza 1</span>
            )}
          </p>
          {risk.or_ci95 && (
            <p className="muted">
              IC 95%: [{risk.or_ci95[0].toFixed(2)}, {risk.or_ci95[1].toFixed(2)}]
            </p>
          )}
          <p>{risk.interpretation}</p>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Actualizar `SpeciesDetail.tsx` para usar el componente extraído**

En `frontend/src/components/SpeciesDetail.tsx`, borra la función `RiskBlock` local (líneas 17-50) y su import de `COLORS` si queda sin uso, y añade:

```tsx
import type { Risk, SpeciesAnalytics } from "../api/types";
import { RiskBlock } from "./RiskBlock";
```

(El resto del archivo —`SpeciesDetail`, el JSX que ya llama a `<RiskBlock label=... risk=.../>`— no cambia: la firma del componente extraído es idéntica a la que tenía la función local.)

- [ ] **Step 5: Ejecutar los tests de `SpeciesDetail` para confirmar que la extracción no rompió nada**

Run: `cd frontend && npx vitest run src/components/SpeciesDetail.test.tsx`
Expected: PASS.

- [ ] **Step 6: Escribir `ContrastPage.tsx`**

Crea `frontend/src/pages/ContrastPage.tsx`:

```tsx
/**
 * Contraste de las especies plantadas del proyecto con el Referente
 * cientifico (E5, UC-AN3): "plantaste X, que segun el referente se estanca
 * ~4.9x mas de lo esperado".
 *
 * Una especie sin fila en el referente no se omite: se marca como "sin
 * referencia" para que el ingeniero sepa que la comparacion no existe
 * todavia, en vez de asumir que no hay riesgo.
 */
import { Link, useParams } from "react-router-dom";

import { getReferenceContrast } from "../api/contrast";
import { getProject } from "../api/projects";
import type { SpeciesContrast } from "../api/types";
import { RiskBlock } from "../components/RiskBlock";
import { useAsync } from "../hooks/useAsync";

function ContrastCard({ item }: { item: SpeciesContrast }) {
  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2 className="species-name">{item.species}</h2>
          <p className="muted">
            {item.n_trees_in_project} {item.n_trees_in_project === 1 ? "árbol" : "árboles"}
            {item.gremio && ` · ${item.gremio}`}
          </p>
        </div>
      </header>

      {item.has_reference ? (
        <div className="risk-grid">
          <RiskBlock label="Estancamiento" risk={item.stall_risk!} />
          <RiskBlock label="Mortalidad" risk={item.mortality_risk!} />
        </div>
      ) : (
        <p className="muted">{item.narrative}</p>
      )}
    </section>
  );
}

export function ContrastPage() {
  const { id } = useParams();
  const projectId = Number(id);

  const project = useAsync((signal) => getProject(projectId, signal), [projectId]);
  const contraste = useAsync(
    (signal) => getReferenceContrast(projectId, signal),
    [projectId],
  );

  const volver = (
    <Link to={`/proyectos/${projectId}`}>{project.data?.name ?? "Volver al proyecto"}</Link>
  );

  if (contraste.loading && !contraste.data) {
    return <p className="state">Cargando el contraste…</p>;
  }
  if (contraste.error) {
    return (
      <div className="state">
        <h2>No se pudo abrir el contraste</h2>
        <p className="muted">{contraste.error.message}</p>
        {volver}
      </div>
    );
  }

  const items = contraste.data!;

  return (
    <div className="page page-wide">
      <header className="page-head">
        <p className="muted">
          <Link to="/proyectos">Mis proyectos</Link> / {volver} / Contraste con el referente
        </p>
        <h1>Contraste con el Referente científico</h1>
        <p className="subtitle">
          Las especies plantadas en este proyecto, frente a los efectos estimados sobre el
          dataset de referencia (30 especies, 856 árboles).
        </p>
      </header>

      {items.length === 0 ? (
        <div className="state">
          <h2>Todavía no hay especies</h2>
          <p className="muted">Cargue un monitoreo con árboles para ver el contraste.</p>
        </div>
      ) : (
        items.map((item) => <ContrastCard key={item.species} item={item} />)
      )}
    </div>
  );
}
```

- [ ] **Step 7: Ejecutar el test de la página para verlo pasar**

Run: `cd frontend && npx vitest run src/components/ContrastPage.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 8: Registrar la ruta en `App.tsx`**

En `frontend/src/App.tsx`, después de la línea 71 (`/proyectos/:id/ndvi`), añade:

```tsx
      <Route
        path="/proyectos/:id/referente-contraste"
        element={<Privada><ContrastPage /></Privada>}
      />
```

Y añade el import junto a los demás de `pages/`:

```tsx
import { ContrastPage } from "./pages/ContrastPage";
```

- [ ] **Step 9: Enlazar desde `ProjectDetailPage.tsx`**

En `frontend/src/pages/ProjectDetailPage.tsx`, junto al botón existente de NDVI (línea ~125), añade:

```tsx
              <Link to={`/proyectos/${p.id}/referente-contraste`} className="btn btn-ghost">
                Contraste con el referente
              </Link>
```

- [ ] **Step 10: Ejecutar toda la suite de frontend**

Run: `cd frontend && npx vitest run`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/components/RiskBlock.tsx frontend/src/components/SpeciesDetail.tsx frontend/src/pages/ContrastPage.tsx frontend/src/components/ContrastPage.test.tsx frontend/src/App.tsx frontend/src/pages/ProjectDetailPage.tsx
git commit -m "feat(e5): pagina de contraste de especies del proyecto (UC-AN3)"
```

---

### Task 13: Gate de verificación — Slice 2 (y cierre de E5)

**Files:** ninguno (solo comandos).

- [ ] **Step 1: Backend — suite completa**

Run: `cd backend && pytest -q`
Expected: 0 failed.

- [ ] **Step 2: Backend — lint y tipos**

Run: `cd backend && ruff check . && mypy src/agrosense`
Expected: sin errores.

- [ ] **Step 3: Frontend — suite completa, lint y build**

Run: `cd frontend && npx vitest run && npm run lint && npm run build`
Expected: 0 failed, sin errores de lint, build exitoso.

- [ ] **Step 4: Verificación manual del journey completo**

Levanta backend y frontend. Crea un proyecto, sube un Excel con al menos una especie que SÍ esté en `data/processed/efectos_aleatorios.csv` (p. ej. "Lafoensia speciosa") y una que no. Abre `/proyectos/{id}/referente-contraste` y confirma que:
  - la especie conocida muestra su OR e interpretación;
  - la especie desconocida se marca "sin referencia" en vez de desaparecer o mostrar un error.

- [ ] **Step 5: Actualizar el roadmap**

En `docs/obsidian-agrosense/01-Proyecto/Roadmap.md`, marca la épica E5 como hecha y actualiza la sección "Slices Planificados" para reflejar el estado real (E5 ✅, siguiente: E9 · IA con Ollama, según el orden aprobado en `docs/04-vision-producto.md` §11).

- [ ] **Step 6: Commit final**

```bash
git add docs/obsidian-agrosense/01-Proyecto/Roadmap.md
git commit -m "docs(e5): referente versionado + contraste de especies, cerrado"
```

---

## Self-Review

- **Cobertura del spec:** provenance/versionado (Task 1-3), rename del contrato (Task 4-6), UC-R1 sigue funcionando bajo el nuevo contrato (Task 4), UC-R2 "publicar una version nueva" (Task 2-3, vía `publish_version`), UC-AN3 "contrastar especies del proyecto" (Task 8-12). Las tres tablas del §6.7 (`reference_species_effects`, `reference_plot_effects`, `variance_components`) están cubiertas.
- **No placeholders:** cada task trae el código completo de migración, modelo, repositorio, caso de uso, ruta, schema y componente — sin "TODO" ni "similar a la Task N" sin repetir el código.
- **Consistencia de tipos:** `ReferenceRepository` (no `AnalyticsRepository`) se usa igual en Task 4, 9 y 10; `SpeciesContrastDTO`/`SpeciesContrastResponse`/`SpeciesContrast` (backend DTO, schema Pydantic, tipo TS) tienen los mismos campos en las tres capas; `build_risk`/`log_odds_ci` se definen en Task 9 Step 3 y se usan igual en `contrast_species.py`.
- **Límite de alcance explícito:** el rename de DTOs/schemas/tipos TS que llevan "Analytics" en el nombre queda fuera a propósito (ver Global Constraints) — si el equipo decide que también hay que renombrarlos, es un slice aparte, no una sorpresa de este plan.
