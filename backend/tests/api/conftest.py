"""Fixture SQLite en memoria para tests de API.

Crea un engine fresco por test (function scope) e inyecta la sesion
via dependency_overrides — sin tocar Supabase.

StaticPool: fuerza que TODAS las conexiones del engine compartan la misma
conexion sqlite en memoria. Sin esto, create_all y la sesion de la request
usarian conexiones distintas y las tablas serian invisibles entre si.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def _build_client(raise_server_exceptions: bool, authenticated: bool = True):
    """Cliente contra SQLite en memoria.

    Desde E1 toda la API exige sesion: por defecto el cliente va autenticado
    como ENGINEER_A, con tokens firmados por el "Auth" de prueba
    (`tests/auth/keys.py`) y verificados de verdad, sin red.
    """
    from agrosense.adapters.api.app import create_app
    from agrosense.adapters.api.deps import get_session, get_token_verifier
    from agrosense.adapters.db.models import Base
    from tests.auth.keys import bearer, fake_verifier

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    app = create_app()

    def _override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_token_verifier] = fake_verifier
    return TestClient(
        app,
        raise_server_exceptions=raise_server_exceptions,
        headers=bearer() if authenticated else None,
    )


@pytest.fixture()
def client():
    with _build_client(raise_server_exceptions=True) as c:
        yield c


@pytest.fixture()
def lenient_client():
    """Como `client`, pero deja que el handler de 500 responda en vez de
    re-lanzar. Necesario para verificar que una excepcion no mapeada sale
    como {code, message} y no como stack trace."""
    with _build_client(raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def anon_client():
    """Mismo backend, sin token: para verificar los 401."""
    with _build_client(raise_server_exceptions=True, authenticated=False) as c:
        yield c
