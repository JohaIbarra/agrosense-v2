"""E0 / T5: la migracion del territorio y los monitoreos no pierde datos.

Las tablas del slice 2 estan vacias en produccion, pero la migracion tiene que
funcionar sobre cualquier base con datos: se construye una base en la
revision ANTERIOR (b1c4a7f20e51), con datos en la forma vieja
(`trees.locality`, `trees.plot_id`, `observations.campaign`), y se comprueba
que el upgrade los traslada y que el downgrade los devuelve intactos.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import Base

BACKEND = Path(__file__).parents[2]
BEFORE_E0 = "b1c4a7f20e51"
E0 = "c2d8e41f6a07"

_SEED = [
    "INSERT INTO projects (id, name, created_at) VALUES "
    "(1, 'P1', '2026-09-01'), (2, 'P2', '2026-09-01')",
    "INSERT INTO campaign_files (id, project_id, filename, sha256, mapping_version, "
    "ingested_at, trees, observations, deaths) VALUES "
    "(1, 1, 'a.xlsx', 'x', 'v', '2026-09-01', 3, 5, 1)",
    # Mismo ID Parcela "1" en dos predios: deben quedar como parcelas DISTINTAS
    "INSERT INTO trees (id, project_id, tree_id, species, plot_id, locality) VALUES "
    "(1, 1, 'T1', 'Senna viarum', '1', 'Guayabal'),"
    "(2, 1, 'T2', 'Senna viarum', '1', 'Tres Jotas'),"
    "(3, 1, 'T3', 'Inga punctata', '2', 'Guayabal'),"
    "(4, 1, 'T4', 'Inga punctata', NULL, NULL),"
    "(5, 2, 'T1', 'Cedrela montana', '1', 'Guayabal')",
    "INSERT INTO observations (id, tree_row_id, campaign, height_m, dap_status, alive) VALUES "
    "(1, 1, 1, 0.20, 'bajo_umbral_dap', 1),"
    "(2, 1, 2, 0.30, 'bajo_umbral_dap', 1),"
    "(3, 2, 1, 0.25, 'bajo_umbral_dap', 1),"
    "(4, 3, 4, 0.50, 'bajo_umbral_dap', 0),"
    "(5, 5, 3, 0.40, 'bajo_umbral_dap', 1)",
]


def _cfg(conn) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", "sqlite://")
    cfg.attributes["connection"] = conn
    return cfg


def _migrate(engine, target: str, direction: str = "upgrade") -> None:
    with engine.connect() as conn:
        getattr(command, direction)(_cfg(conn), target)
        conn.commit()


def _new_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture()
def engine_with_slice2_data():
    """Base en la revision previa a E0, con datos en la forma vieja."""
    engine = _new_engine()
    _migrate(engine, BEFORE_E0)
    with engine.begin() as c:
        for sql in _SEED:
            c.execute(text(sql))
    yield engine
    engine.dispose()


def test_upgrade_moves_properties_and_plots_out_of_trees(engine_with_slice2_data):
    eng = engine_with_slice2_data
    _migrate(eng, E0)
    with eng.connect() as c:
        props = c.execute(text(
            "SELECT project_id, name FROM properties ORDER BY project_id, name"
        )).all()
        assert props == [(1, "Guayabal"), (1, "Tres Jotas"), (2, "Guayabal")]

        plots = c.execute(text(
            "SELECT project_id, code, plot_label FROM plots ORDER BY project_id, code"
        )).all()
        assert plots == [
            (1, "Guayabal/1", "1"),
            (1, "Guayabal/2", "2"),
            (1, "Tres Jotas/1", "1"),
            (2, "Guayabal/1", "1"),
        ]

        # Cada arbol queda en su parcela; el que no tenia parcela, sin ella
        enlaces = dict(c.execute(text(
            "SELECT t.id, pl.code FROM trees t LEFT JOIN plots pl ON pl.id = t.plot_row_id"
        )).all())
        assert enlaces == {
            1: "Guayabal/1", 2: "Tres Jotas/1", 3: "Guayabal/2", 4: None, 5: "Guayabal/1",
        }


def test_upgrade_turns_campaign_numbers_into_monitorings(engine_with_slice2_data):
    eng = engine_with_slice2_data
    _migrate(eng, E0)
    with eng.connect() as c:
        mons = c.execute(text(
            "SELECT project_id, number FROM monitorings ORDER BY project_id, number"
        )).all()
        assert mons == [(1, 1), (1, 2), (1, 4), (2, 3)]

        # Ninguna observacion pierde su monitoreo ni su valor
        filas = c.execute(text(
            "SELECT o.id, m.number, o.height_m FROM observations o "
            "JOIN monitorings m ON m.id = o.monitoring_id ORDER BY o.id"
        )).all()
        assert filas == [
            (1, 1, 0.20), (2, 2, 0.30), (3, 1, 0.25), (4, 4, 0.50), (5, 3, 0.40),
        ]


def test_old_files_are_not_linked_to_invented_monitorings(engine_with_slice2_data):
    """Hasta E0 no se registraba que monitoreos traia cada archivo."""
    eng = engine_with_slice2_data
    _migrate(eng, E0)
    with eng.connect() as c:
        n = c.execute(text("SELECT COUNT(*) FROM campaign_file_monitorings")).scalar()
        assert n == 0


def test_old_columns_are_gone_after_upgrade(engine_with_slice2_data):
    eng = engine_with_slice2_data
    _migrate(eng, E0)
    insp = inspect(eng)
    assert "campaign" not in {c["name"] for c in insp.get_columns("observations")}
    tree_cols = {c["name"] for c in insp.get_columns("trees")}
    assert "plot_id" not in tree_cols and "locality" not in tree_cols


def test_downgrade_restores_the_old_shape(engine_with_slice2_data):
    eng = engine_with_slice2_data
    _migrate(eng, E0)
    _migrate(eng, BEFORE_E0, direction="downgrade")
    with eng.connect() as c:
        arboles = c.execute(text("SELECT id, plot_id, locality FROM trees ORDER BY id")).all()
        assert arboles == [
            (1, "1", "Guayabal"), (2, "1", "Tres Jotas"), (3, "2", "Guayabal"),
            (4, None, None), (5, "1", "Guayabal"),
        ]
        obs = c.execute(text("SELECT id, campaign FROM observations ORDER BY id")).all()
        assert obs == [(1, 1), (2, 2), (3, 1), (4, 4), (5, 3)]
    tablas = set(inspect(eng).get_table_names())
    assert not {"properties", "plots", "monitorings", "campaign_file_monitorings"} & tablas


def test_upgrade_downgrade_upgrade_is_stable(engine_with_slice2_data):
    eng = engine_with_slice2_data
    _migrate(eng, E0)
    _migrate(eng, BEFORE_E0, direction="downgrade")
    _migrate(eng, E0)
    with eng.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM observations")).scalar() == 5
        assert c.execute(text("SELECT COUNT(*) FROM monitorings")).scalar() == 4


def test_every_model_table_matches_the_migrated_schema():
    """Tras migrar a head, el esquema coincide columna a columna con los modelos.

    Cubre TODAS las tablas, no solo las de E0: si alguien anade un
    `mapped_column` y olvida la migracion, este test cae en local, antes de
    llegar a Supabase.
    """
    engine = _new_engine()
    _migrate(engine, "head")
    insp = inspect(engine)
    for name, table in Base.metadata.tables.items():
        real = {c["name"] for c in insp.get_columns(name)}
        esperado = {c.name for c in table.columns}
        assert real == esperado, (
            f"{name}: solo en la migracion {sorted(real - esperado)}; "
            f"solo en el modelo {sorted(esperado - real)}"
        )
    engine.dispose()
