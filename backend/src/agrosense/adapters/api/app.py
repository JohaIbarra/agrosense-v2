"""Factory de la aplicacion FastAPI (ADR-003: adapters/api sin logica de negocio).

Lifespan: no llama create_all (regla: migraciones solo via Alembic).
Los tests sobreescriben la sesion via dependency_overrides.
"""
from __future__ import annotations

from fastapi import FastAPI

from agrosense.adapters.api.errors import domain_error_handler, unhandled_error_handler
from agrosense.adapters.api.middleware import BodySizeLimitMiddleware
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

    # Red de seguridad: ningun fallo sale sin la forma {code, message}
    app.add_exception_handler(Exception, unhandled_error_handler)

    # Rutas del slice 2 (UC1/UC2 + reads)
    from agrosense.adapters.api.routes.projects import MAX_UPLOAD_BYTES, router

    app.include_router(router)

    # E5: Referente cientifico (efectos de los modelos mixtos, solo lectura).
    # Lleva prefijo /api/v1 mientras que las rutas de proyecto no: es deuda
    # conocida del contrato, anotada en docs/deuda-tecnica.md. Versionar las
    # existentes rompe al consumidor de esas rutas, asi que se unifica cuando
    # haya un cambio de contrato que lo justifique, no de paso.
    from agrosense.adapters.api.routes.reference import router as reference_router

    app.include_router(reference_router)

    # E1: perfil del ingeniero autenticado
    from agrosense.adapters.api.routes.me import router as me_router

    app.include_router(me_router)

    # E2/E3: fecha del monitoreo, analisis exploratorio y reporte .xlsx
    from agrosense.adapters.api.routes.monitorings import router as monitorings_router

    app.include_router(monitorings_router)

    # E6: mapa del predio
    from agrosense.adapters.api.routes.map import router as map_router

    app.include_router(map_router)

    # E6b: capas de imagen (ortofoto) del proyecto
    from agrosense.adapters.api.routes.imagery import router as imagery_router

    app.include_router(imagery_router)

    # E10a: indices espectrales (NDVI) por predio
    from agrosense.adapters.api.routes.indices import router as indices_router

    app.include_router(indices_router)

    # E5: contraste de las especies del proyecto con el referente (UC-AN3)
    from agrosense.adapters.api.routes.reference_contrast import router as contrast_router

    app.include_router(contrast_router)

    # E9: borrador de informe con IA local (Ollama) de un monitoreo
    from agrosense.adapters.api.routes.ai_reports import router as ai_reports_router

    app.include_router(ai_reports_router)

    # E7: deteccion de estancados (UC-AN4)
    from agrosense.adapters.api.routes.stall import router as stall_router

    app.include_router(stall_router)

    # E8: riesgo de mortalidad (UC-AN5)
    from agrosense.adapters.api.routes.mortality import router as mortality_router

    app.include_router(mortality_router)

    # Techo del cuerpo ANTES de que el parser de multipart toque disco.
    # Se anade el ultimo para que quede el mas externo de la pila.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_UPLOAD_BYTES)

    return app
