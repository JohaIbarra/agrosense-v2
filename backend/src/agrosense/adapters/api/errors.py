"""Mapeo de errores de dominio y de aplicacion a respuestas HTTP.

Regla AGENTS.md: nunca exponer stack traces ni excepciones internas.
Cada error lleva {code, message} suficiente para que el ingeniero de campo
pueda corregir el dato sin ayuda tecnica.
"""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from agrosense.domain.errors import DomainError

# Mapeo de codigos de ValueError a HTTP status
_VALUE_ERROR_HTTP: dict[str, int] = {
    "DUPLICATE_NAME": 409,
    "DUPLICATE_FILE": 409,
    "PROJECT_NOT_FOUND": 404,
    "TREE_NOT_FOUND": 404,
    "INVALID_FILE": 400,
}


def raise_for_value_error(exc: ValueError) -> None:
    """Convierte ValueError con codigo conocido en HTTPException con status correcto.

    Siempre lanza — nunca retorna.
    """
    msg = str(exc)
    for code, status in _VALUE_ERROR_HTTP.items():
        if code in msg:
            raise HTTPException(
                status_code=status,
                detail={"code": code, "message": msg},
            )
    # ValueError sin codigo reconocido → 400 generico
    raise HTTPException(
        status_code=400,
        detail={"code": "BAD_REQUEST", "message": msg},
    )


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """DomainError (invariante de dominio roto) → 422 con contexto accionable."""
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": exc.code, "message": exc.message}},
    )
