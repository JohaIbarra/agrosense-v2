"""Las migraciones y `Base.metadata` describen EXACTAMENTE el mismo esquema.

AGENTS.md: "Database schema must be derived from the domain model" y "Every
schema change must use a migration". Si divergen, el proximo
`alembic revision --autogenerate` propone borrar indices intencionales (o
crear redundantes) sin que nadie lo note en la revision. Regresion de la
revision de integracion del 2026-09-30: 6 indices desalineados (E5, E10a).
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import Base

BACKEND = Path(__file__).parents[2]


def test_migrations_match_models():
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
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    # Solo diferencias de estructura (tablas, columnas, indices, constraints);
    # SQLite no reporta tipos de forma fiable, asi que no se comparan tipos.
    structural = [d for d in diff if not (isinstance(d, list) or d[0].startswith("modify_"))]
    assert structural == []
