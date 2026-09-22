"""Mapeo de errores a respuestas HTTP.

Reglas de AGENTS.md que gobiernan este archivo:
  - "Never expose internal exceptions or stack traces"
  - "External errors are sanitized"

Todo error sale con la misma forma: {"detail": {"code", "message"}}.
El `code` se toma del atributo del error, NUNCA buscandolo dentro del texto
(hallazgo R2: el nombre de archivo del usuario elegia el status).
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from agrosense.application.errors import AppError
from agrosense.domain.errors import DomainError

logger = logging.getLogger(__name__)

# Vocabulario cerrado: codigo de aplicacion -> status HTTP
_CODE_HTTP: dict[str, int] = {
    "DUPLICATE_NAME": 409,
    "DUPLICATE_FILE": 409,
    "DUPLICATE_TREE": 409,
    "PROJECT_NOT_FOUND": 404,
    "TREE_NOT_FOUND": 404,
    "MONITORING_NOT_FOUND": 404,
    "SPECIES_NOT_FOUND": 404,
    "ANALYTICS_NOT_LOADED": 404,
    "INVALID_SORT": 400,
    "INVALID_MODEL": 400,
    "INVALID_FILE": 400,
    "FILE_TOO_LARGE": 413,
}


def raise_for_value_error(exc: ValueError) -> None:
    """Traduce un error de aplicacion a HTTPException. Siempre lanza.

    Un `AppError` lleva su codigo como atributo. Un `ValueError` cualquiera
    es un fallo que no previmos: se registra completo del lado del servidor
    y al cliente le llega un 400 generico, sin su texto.
    """
    if isinstance(exc, AppError):
        raise HTTPException(
            status_code=_CODE_HTTP.get(exc.code, 400),
            detail={"code": exc.code, "message": exc.message},
        )

    logger.warning("ValueError sin codigo en la capa de aplicacion", exc_info=exc)
    raise HTTPException(
        status_code=400,
        detail={"code": "BAD_REQUEST", "message": "La peticion no pudo procesarse."},
    )


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """DomainError (invariante roto) -> 422 con contexto accionable."""
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Red de seguridad: nada sale del backend sin la forma del contrato.

    Antes, un fallo no mapeado (p.ej. el IntegrityError del hallazgo R1)
    llegaba al cliente como un 500 sin cuerpo estructurado, imposible de
    diagnosticar desde el frontend. El detalle se registra aqui, no se envia.
    """
    logger.exception("Error no controlado en %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "INTERNAL",
                "message": "Error interno del servidor. Reintente o contacte soporte.",
            }
        },
    )
