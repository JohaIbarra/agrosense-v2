"""Verificacion de los tokens de sesion de Supabase Auth (ADR-006).

El Auth del proyecto firma con clave ASIMETRICA (ES256, verificado contra su
JWKS publico el 2026-09-21). El backend verifica con la clave publica: no hay
ningun secreto que guardar ni que pueda filtrarse.

Lo que se exige de un token, y por que:

  - firma valida con una clave del JWKS del proyecto;
  - algoritmo en la lista blanca (nunca `none`, nunca HS256 contra una clave
    publica: el clasico ataque de confusion de algoritmo);
  - `iss` = el Auth de ESTE proyecto (un token de otro proyecto Supabase no
    vale aunque su firma sea correcta);
  - `aud` = "authenticated" (descarta tokens anonimos);
  - `exp` vigente, y `sub` presente: es la identidad del ingeniero.

Cualquier fallo se reporta como `InvalidToken` con un motivo para el log del
servidor; al cliente solo le llega 401, sin detalle.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient

ALLOWED_ALGORITHMS = ("ES256", "RS256")
AUDIENCE = "authenticated"


class InvalidToken(Exception):
    """El token no prueba una sesion valida. `reason` es solo para el log."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class AuthenticatedUser:
    """Lo que el backend sabe de quien llama, sacado de un token verificado."""

    user_id: str
    email: str | None


class TokenVerifier:
    """Verifica tokens contra un JWKS (produccion) o una clave fija (tests).

    `key_resolver` recibe el token crudo y devuelve la clave publica con que
    verificarlo. En produccion es el cliente JWKS, que cachea las claves y
    elige la correcta por `kid`; en los tests, una clave EC generada ahi.
    """

    def __init__(self, issuer: str, key_resolver):
        self._issuer = issuer
        self._key_resolver = key_resolver

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            key = self._key_resolver(token)
            claims = jwt.decode(
                token,
                key=key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=AUDIENCE,
                issuer=self._issuer,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidToken(f"{type(exc).__name__}: {exc}") from exc
        except Exception as exc:
            # El JWKS puede no responder (red): tampoco es una sesion valida,
            # pero el motivo tiene que quedar en el log.
            raise InvalidToken(f"no se pudo resolver la clave: {type(exc).__name__}") from exc

        user_id = str(claims.get("sub") or "").strip()
        if not user_id:
            raise InvalidToken("token sin sub")
        email = claims.get("email")
        return AuthenticatedUser(user_id=user_id, email=email if isinstance(email, str) else None)


def jwks_verifier(supabase_url: str) -> TokenVerifier:
    """Verificador de produccion contra el JWKS publico del proyecto."""
    base = supabase_url.rstrip("/")
    client = PyJWKClient(
        f"{base}/auth/v1/.well-known/jwks.json",
        cache_keys=True,
        lifespan=600,
    )
    return TokenVerifier(
        issuer=f"{base}/auth/v1",
        key_resolver=lambda token: client.get_signing_key_from_jwt(token).key,
    )


@lru_cache(maxsize=1)
def default_verifier() -> TokenVerifier:
    """Verificador unico del proceso, configurado por `SUPABASE_URL`.

    Unico por la misma razon que el engine (hallazgo de la fase 6 del slice
    5): el cliente JWKS cachea las claves, y recrearlo por request pediria el
    JWKS por la red en cada llamada.
    """
    url = os.environ.get("SUPABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "SUPABASE_URL no configurada: el backend no puede verificar sesiones. "
            "Anadala a backend/.env (ver docs/adr/006-identidad-y-proyectos.md)."
        )
    return jwks_verifier(url)
