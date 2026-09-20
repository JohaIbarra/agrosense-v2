"""Engine/session de SQLAlchemy desde DATABASE_URL (.env).

Unica fuente de conexion del backend, y unico lugar donde se decide el
driver de PostgreSQL: **psycopg3** (ADR-002). Supabase entrega la URL como
`postgresql://...`, que SQLAlchemy resuelve a psycopg2 por defecto; aqui se
normaliza para que el `.env` no tenga que saberlo y para que no convivan
dos drivers en el proyecto.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Driver unico de Postgres del proyecto (ADR-002)
POSTGRES_DRIVER = "postgresql+psycopg"

# Esquemas que hay que reescribir al driver unico
_POSTGRES_SCHEMES = (
    "postgresql+psycopg2",
    "postgresql+psycopg",
    "postgresql",
    "postgres",
)


def normalize_database_url(url: str) -> str:
    """Fuerza el driver de ADR-002 en una URL de PostgreSQL.

    Idempotente. Deja intactas las URLs que no son Postgres (SQLite en los
    tests locales) y la cadena vacia (para que get_engine de su error).
    Solo toca el esquema: credenciales y query params pasan verbatim.
    """
    if not url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if scheme.lower() in _POSTGRES_SCHEMES:
        return f"{POSTGRES_DRIVER}://{rest}"
    return url


DATABASE_URL = normalize_database_url(os.environ.get("DATABASE_URL", ""))


def get_engine():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL no configurada. Crea backend/.env con la URL de Supabase "
            "(ver docs/adr/002-database.md)"
        )
    # pool_pre_ping: conexiones largas en serverless suelen morir; re-validar
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def get_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)
