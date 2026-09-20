"""Dependencias FastAPI — punto único de inyección de sesión.

Los tests sobreescriben get_session via app.dependency_overrides
para inyectar SQLite en memoria sin tocar Supabase.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from agrosense.adapters.db.session import get_session_factory


def get_session() -> Generator[Session, None, None]:
    """Genera una sesión SQLAlchemy; cierra al salir del bloque."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()
