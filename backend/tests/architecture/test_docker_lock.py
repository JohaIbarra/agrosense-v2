"""Deuda J: la imagen instala EXACTAMENTE las versiones auditadas, verificadas por hash."""
from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).parents[2]
PIN = re.compile(r"^([A-Za-z0-9_.\-]+)==([^\s\;]+)", re.MULTILINE)


def _pins(name: str) -> dict[str, str]:
    text = (BACKEND / name).read_text(encoding="utf-8")
    return {m.group(1).lower(): m.group(2) for m in PIN.finditer(text)}


def test_docker_requirements_pin_the_same_versions_as_the_audited_lock():
    assert _pins("requirements.docker.txt") == _pins("requirements.lock.txt")


def test_every_docker_requirement_has_a_hash():
    text = (BACKEND / "requirements.docker.txt").read_text(encoding="utf-8")
    blocks = re.split(r"\n(?=[A-Za-z0-9_.\-]+==)", text)
    assert all("--hash=sha256:" in b for b in blocks if PIN.match(b))


def test_dockerfile_pins_base_images_by_digest_and_requires_hashes():
    dockerfile = (BACKEND.parent / "Dockerfile").read_text(encoding="utf-8")
    froms = re.findall(r"^FROM\s+(\S+)", dockerfile, re.MULTILINE)
    assert froms and all("@sha256:" in f for f in froms), froms
    assert "--require-hashes --no-deps -r requirements.docker.txt" in dockerfile


def test_extras_needed_at_runtime_are_in_the_lock():
    """Regresion (primer deploy en Render): la imagen instala el lock con --no-deps,
    asi que los extras de pyproject NO se resuelven solos. Sin psycopg-binary no
    hay driver de Postgres (ImportError: no pq wrapper available)."""
    pins = _pins("requirements.lock.txt")
    assert "psycopg-binary" in pins
    assert pins["psycopg-binary"] == pins["psycopg"]
    assert "cryptography" in pins  # PyJWT[crypto]: firmas ES256 de Supabase
