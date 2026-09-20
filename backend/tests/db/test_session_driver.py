"""Un solo driver de PostgreSQL en todo el backend (ADR-002: psycopg3).

`.env` trae la URL tal cual la da Supabase (`postgresql://...`), que en
SQLAlchemy resuelve al dialecto por defecto = psycopg2. Normalizamos en un
unico punto para que nadie tenga que editar su `.env` ni recordar el sufijo.

Funcion pura: estos tests no abren ninguna conexion.
"""
from __future__ import annotations

import pytest

from agrosense.adapters.db.session import normalize_database_url

PSYCOPG3 = "postgresql+psycopg://"


class TestNormalizeDatabaseUrl:
    def test_bare_postgresql_scheme_becomes_psycopg3(self):
        url = normalize_database_url("postgresql://user:pw@host:5432/postgres")
        assert url.startswith(PSYCOPG3)
        assert url.endswith("user:pw@host:5432/postgres")

    def test_legacy_postgres_scheme_becomes_psycopg3(self):
        """Algunos proveedores emiten el alias `postgres://`."""
        assert normalize_database_url("postgres://u:p@h/db").startswith(PSYCOPG3)

    def test_psycopg2_driver_is_rewritten(self):
        """ADR-002 admite UN driver: una URL con psycopg2 se corrige, no se acepta."""
        assert normalize_database_url("postgresql+psycopg2://u:p@h/db").startswith(PSYCOPG3)

    def test_already_psycopg3_is_untouched(self):
        url = "postgresql+psycopg://u:p@h/db"
        assert normalize_database_url(url) == url

    def test_is_idempotent(self):
        once = normalize_database_url("postgresql://u:p@h/db")
        assert normalize_database_url(once) == once

    def test_non_postgres_url_is_untouched(self):
        """SQLite (tests locales) pasa sin tocar."""
        assert normalize_database_url("sqlite:///:memory:") == "sqlite:///:memory:"

    def test_empty_stays_empty(self):
        """Sin .env, get_engine debe poder dar su error accionable."""
        assert normalize_database_url("") == ""

    def test_credentials_are_preserved_verbatim(self):
        """Normalizar el esquema no puede romper una password con caracteres raros."""
        raw = "postgresql://user:p%40ss%3Aword@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"
        assert normalize_database_url(raw) == PSYCOPG3 + raw.split("://", 1)[1]


def test_engine_uses_psycopg3_dialect():
    """El engine construido desde una URL de Supabase usa el driver de ADR-002."""
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine(
        normalize_database_url("postgresql://u:p@h:5432/postgres"),
        # No conecta: solo resuelve el dialecto
    )
    assert engine.dialect.driver == "psycopg"
