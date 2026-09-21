"""E1 / T1: verificacion de tokens de Supabase Auth."""
from __future__ import annotations

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from agrosense.adapters.auth.tokens import InvalidToken
from tests.auth.keys import ENGINEER_A, PUBLIC, fake_verifier, make_token

verifier = fake_verifier()


def test_valid_token_yields_the_user():
    user = verifier.verify(make_token())
    assert user.user_id == ENGINEER_A
    assert user.email == "ingeniera@example.com"


def test_expired_token_is_rejected():
    with pytest.raises(InvalidToken):
        verifier.verify(make_token(expires_in=-10))


def test_token_from_another_project_is_rejected():
    """Firma correcta pero `iss` de otro proyecto Supabase: no vale."""
    with pytest.raises(InvalidToken):
        verifier.verify(make_token(issuer="https://otro.supabase.co/auth/v1"))


def test_anonymous_audience_is_rejected():
    with pytest.raises(InvalidToken):
        verifier.verify(make_token(audience="anon"))


def test_token_signed_with_another_key_is_rejected():
    ajena = ec.generate_private_key(ec.SECP256R1())
    with pytest.raises(InvalidToken):
        verifier.verify(make_token(key=ajena))


def test_unsigned_token_is_rejected():
    """alg=none: el ataque clasico a verificadores permisivos."""
    token = jwt.encode(
        {"sub": ENGINEER_A, "iss": "x", "aud": "authenticated", "exp": 9999999999},
        key=None,
        algorithm="none",
    )
    with pytest.raises(InvalidToken):
        verifier.verify(token)


def test_hs256_signed_with_the_public_key_is_rejected():
    """Confusion de algoritmo: usar la clave PUBLICA como secreto HMAC."""
    from cryptography.hazmat.primitives import serialization

    pem = PUBLIC.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    try:
        token = make_token(key=pem, algorithm="HS256")
    except jwt.InvalidKeyError:
        return  # la propia libreria se niega a firmarlo
    with pytest.raises(InvalidToken):
        verifier.verify(token)


def test_token_without_sub_is_rejected():
    with pytest.raises(InvalidToken):
        verifier.verify(make_token(drop=("sub",)))


def test_garbage_is_rejected():
    with pytest.raises(InvalidToken):
        verifier.verify("esto.no.es-un-jwt")


def test_missing_email_is_allowed():
    """El email es informativo; la identidad es `sub`."""
    user = verifier.verify(make_token(email=None))
    assert user.user_id == ENGINEER_A and user.email is None


def test_default_verifier_requires_configuration(monkeypatch):
    from agrosense.adapters.auth import tokens

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    tokens.default_verifier.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="SUPABASE_URL"):
            tokens.default_verifier()
    finally:
        tokens.default_verifier.cache_clear()
