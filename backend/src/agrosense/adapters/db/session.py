"""Engine/session de SQLAlchemy desde DATABASE_URL (.env).

Unica fuente de conexion del backend, y unico lugar donde se decide el
driver de PostgreSQL: **psycopg3** (ADR-002). Supabase entrega la URL como
`postgresql://...`, que SQLAlchemy resuelve a psycopg2 por defecto; aqui se
normaliza para que el `.env` no tenga que saberlo y para que no convivan
dos drivers en el proyecto.
"""
import os
from functools import lru_cache

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


@lru_cache(maxsize=1)
def get_engine():
    """Engine UNICO del proceso, construido la primera vez que se pide.

    `lru_cache` no es un detalle de rendimiento, es correccion (hallazgo de
    la fase 6 del slice 5, 2026-09-21). Antes esta funcion devolvia un engine
    NUEVO en cada llamada, y `api/deps.get_session` la llama **una vez por
    request HTTP**. Es decir: cada request creaba su propio pool, con su
    resolucion DNS, su handshake TCP y su TLS contra el session pooler de
    Supabase (~200 ms RTT), y el pool anterior quedaba sin `dispose()` hasta
    que pasara el recolector. Consecuencias medidas:

      - el pool nunca reutilizaba nada, que es justo lo que un pool existe
        para hacer;
      - las conexiones se acumulaban contra el limite del proyecto;
      - bajo rafagas, `getaddrinfo` fallaba de forma intermitente y la
        request moria con un 500 que no tenia nada que ver con la peticion.

    Sigue siendo PEREZOSO: importar el modulo no conecta. Eso es lo que
    permite que `pytest` corra offline contra SQLite y lo que verifica
    `tests/architecture/test_no_remote_db_by_default.py`.
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL no configurada. Crea backend/.env con la URL de Supabase "
            "(ver docs/adr/002-database.md)"
        )
    # pool_pre_ping: conexiones largas en serverless suelen morir; re-validar
    return create_engine(DATABASE_URL, pool_pre_ping=True)


def reset_engine_cache() -> None:
    """Cierra el engine cacheado y olvida la instancia.

    Existe para los tests y para un eventual reload de configuracion: sin
    esto, `lru_cache` dejaria el pool abierto y la unica forma de soltarlo
    seria terminar el proceso.
    """
    cached = get_engine.cache_info().currsize
    if cached:
        get_engine().dispose()
    get_engine.cache_clear()


def get_session_factory() -> sessionmaker:
    """Fabrica de sesiones sobre el engine unico.

    Barata de llamar por request: lo caro (el engine y su pool) ya esta
    construido.
    """
    return sessionmaker(bind=get_engine(), expire_on_commit=False)
