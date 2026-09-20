"""Sesion local para los tests de persistencia: SQLite en memoria.

Por que SQLite y no Supabase (correccion del hallazgo B):
el session pooler remoto tiene ~200ms RTT; usarlo en cada corrida cuelga
`pytest` y deja estado sucio en una DB compartida. Los repositorios se
prueban contra el MISMO `Base.metadata` y el mismo SQLAlchemy, que es lo
que estos tests verifican: queries, transaccionalidad y cascadas.

Lo que SQLite no puede probar (que la migracion Alembic esta realmente
aplicada en Postgres, con sus tipos y constraints) vive en
`tests/smoke/test_supabase_smoke.py`, marcado `supabase`.

Engine fresco por test: cada test parte de una DB vacia y no necesita
limpiar nada.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import Base


@pytest.fixture()
def engine():
    """SQLite en memoria con FKs activas (SQLite las ignora por defecto).

    Sin el PRAGMA, `ondelete="CASCADE"` no se aplicaria y los tests de
    cascada pasarian por la razon equivocada.
    """
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    s = factory()
    yield s
    s.rollback()
    s.close()
