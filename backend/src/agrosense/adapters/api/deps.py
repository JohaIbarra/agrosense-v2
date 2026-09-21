"""Dependencias FastAPI — punto unico de inyeccion de sesion y de identidad.

Los tests sobreescriben `get_session` (SQLite en memoria) y
`get_token_verifier` (verificador con una clave de prueba) via
`app.dependency_overrides`: nada de esto toca Supabase en una corrida normal.
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from agrosense.adapters.auth.tokens import InvalidToken, TokenVerifier, default_verifier
from agrosense.adapters.db.repository import EngineerRepository
from agrosense.adapters.db.session import get_session_factory
from agrosense.application.dtos import EngineerDTO
from agrosense.application.use_cases.engineers import ensure_engineer

logger = logging.getLogger(__name__)


def get_session() -> Generator[Session, None, None]:
    """Genera una sesion SQLAlchemy; cierra al salir del bloque."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def get_token_verifier() -> TokenVerifier:
    return default_verifier()


def _unauthenticated() -> HTTPException:
    # Mismo mensaje para "no hay token" y "token invalido": distinguirlos
    # solo le sirve a quien esta probando tokens.
    return HTTPException(
        status_code=401,
        detail={"code": "UNAUTHENTICATED", "message": "Inicie sesion para continuar."},
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_engineer(
    session: Annotated[Session, Depends(get_session)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    authorization: Annotated[str | None, Header()] = None,
) -> EngineerDTO:
    """El ingeniero autenticado, o 401 (ADR-006).

    Verifica el token de Supabase Auth y asegura su perfil en AgroSense (se
    crea en la primera peticion). El motivo del rechazo va al log del servidor,
    nunca al cliente.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthenticated()
    try:
        user = verifier.verify(authorization[7:].strip())
    except InvalidToken as exc:
        logger.info("Token rechazado: %s", exc.reason)
        raise _unauthenticated() from exc
    return ensure_engineer(EngineerRepository(session), user.user_id, user.email)


CurrentEngineer = Annotated[EngineerDTO, Depends(get_current_engineer)]
