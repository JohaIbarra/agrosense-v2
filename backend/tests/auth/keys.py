"""Claves y tokens de prueba: un "Auth" falso con su propia clave EC.

Firma igual que Supabase Auth (ES256) pero con una clave generada aqui, asi
los tests ejercitan la verificacion real sin red ni cuentas de usuario.
"""
from __future__ import annotations

import time

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

from agrosense.adapters.auth.tokens import TokenVerifier

ISSUER = "https://proyecto-de-prueba.supabase.co/auth/v1"

_PRIVATE = ec.generate_private_key(ec.SECP256R1())
PUBLIC = _PRIVATE.public_key()

ENGINEER_A = "11111111-1111-4111-8111-111111111111"
ENGINEER_B = "22222222-2222-4222-8222-222222222222"


def make_token(
    sub: str = ENGINEER_A,
    email: str | None = "ingeniera@example.com",
    *,
    issuer: str = ISSUER,
    audience: str = "authenticated",
    expires_in: int = 3600,
    key=None,
    algorithm: str = "ES256",
    drop: tuple[str, ...] = (),
) -> str:
    claims = {
        "sub": sub,
        "email": email,
        "iss": issuer,
        "aud": audience,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
        "role": "authenticated",
    }
    for k in drop:
        claims.pop(k, None)
    return jwt.encode(claims, key if key is not None else _PRIVATE, algorithm=algorithm)


def fake_verifier() -> TokenVerifier:
    """Verificador que confia solo en la clave publica de este modulo."""
    return TokenVerifier(issuer=ISSUER, key_resolver=lambda _token: PUBLIC)


def bearer(sub: str = ENGINEER_A) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub)}"}
