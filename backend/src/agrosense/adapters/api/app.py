"""Factory de la aplicacion FastAPI (ADR-003: adapters/api sin logica de negocio).

Lifespan: no llama create_all (regla: migraciones solo via Alembic).
Los tests sobreescriben la sesion via dependency_overrides.
"""
from __future__ import annotations

from fastapi import FastAPI

from agrosense.adapters.api.errors import domain_error_handler
from agrosense.domain.errors import DomainError


def create_app() -> FastAPI:
    """Construye y configura la aplicacion FastAPI."""
    app = FastAPI(
        title="AgroSense API",
        version="2.0.0",
        description="Plataforma de análisis de restauración ecológica — AgroSense v2",
    )

    # Mapeo global: DomainError → 422 con contexto accionable
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]

    # Rutas del slice 2 (UC1/UC2 + reads)
    from agrosense.adapters.api.routes.projects import router

    app.include_router(router)

    return app
