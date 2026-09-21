"""Cliente de API con la analitica real ya cargada en SQLite.

Se carga el bundle REAL desde `data/processed/` en vez de fixtures a mano:
lo que estos tests verifican es que el contrato transporte correctamente los
numeros del modelo mixto, y un fixture inventado no podria detectar, por
ejemplo, que el IC se quedo en log-odds.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

PROCESSED = Path(__file__).parents[2] / "data" / "processed"
SCRIPTS = Path(__file__).parents[2] / "scripts"


def _load_analytics_module():
    """Importa `scripts/load_analytics.py`, que no es un paquete instalable.

    Se importa el script de verdad (y no una copia de su logica) para que el
    test cubra la traduccion a ORM que se ejecuta en produccion.
    """
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import load_analytics

    return load_analytics


@pytest.fixture(scope="module")
def analytics_client():
    if not (PROCESSED / "efectos_aleatorios.csv").exists():
        pytest.skip("CSV de los modelos mixtos ausentes (data/processed/)")

    from agrosense.adapters.api.app import create_app
    from agrosense.adapters.api.deps import get_session
    from agrosense.adapters.db.models import Base
    from agrosense.adapters.db.repository import AnalyticsRepository

    from agrosense.adapters.analytics.effects_loader import build_bundle  # isort: skip

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    load_analytics = _load_analytics_module()
    bundle = build_bundle(PROCESSED)
    seed = TestingSession()
    try:
        AnalyticsRepository(seed).replace_all(*load_analytics.to_orm(bundle))
    finally:
        seed.close()

    app = create_app()

    def _override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    engine.dispose()


@pytest.fixture()
def empty_analytics_client():
    """Misma app, pero con las tablas analiticas vacias.

    Sirve para verificar que "no cargado" se distingue de "cargado y vacio"
    en la respuesta, en vez de devolver un 200 con lista vacia que la UI
    interpretaria como "no hay riesgo".
    """
    from agrosense.adapters.api.app import create_app
    from agrosense.adapters.api.deps import get_session
    from agrosense.adapters.db.models import Base

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
    with TestClient(app) as c:
        yield c
    engine.dispose()
