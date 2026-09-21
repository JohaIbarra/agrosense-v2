"""Alembic environment: importa Base de los models, URL desde .env.

Acepta una conexion ya abierta en `config.attributes["connection"]` (patron
estandar de Alembic). Es lo que permite aplicar las migraciones contra SQLite
en memoria desde los tests: sin eso, `env.py` abriria SIEMPRE la conexion real
a Supabase y una corrida normal de `pytest` se colgaria contra la red — lo que
`tests/architecture/test_no_remote_db_by_default.py` prohibe.
"""
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from agrosense.adapters.db.models import Base
from agrosense.adapters.db.session import DATABASE_URL

load_dotenv()

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Una conexion inyectada manda sobre el .env (ver docstring).
_injected = config.attributes.get("connection")
if _injected is None:
    config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if _injected is not None:
        context.configure(connection=_injected, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
