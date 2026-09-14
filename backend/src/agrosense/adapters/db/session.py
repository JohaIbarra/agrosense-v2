"""Engine/session de SQLAlchemy desde DATABASE_URL (.env).

Unica fuente de conexion en el backend. Los tests de integracion y la
app comparten get_engine(); la sesion se inyecta como dependencia.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "")


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
