"""Guard: `pytest` a secas no puede tocar Supabase.

El historial del proyecto lo justifica (briefing): el session pooler tiene
~200ms RTT; una corrida que lo usa por defecto se cuelga y deja estado
sucio. La regla es: todo lo que abra la conexion REAL (`adapters.db.session`)
vive marcado `supabase` y se corre a proposito con `pytest -m supabase`.

Esto NO es un skip: los tests de repositorio corren siempre, contra SQLite.
Lo que se marca es solo el smoke que necesita Postgres de verdad.
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS = Path(__file__).parents[1]

# Fabricas que abren la conexion real desde DATABASE_URL. Importar el
# modulo no conecta (hay funciones puras ahi); LLAMARLAS si.
REAL_DB_FACTORIES = {"get_engine", "get_session_factory"}


def _factories_called(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    called: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in REAL_DB_FACTORIES:
            called.add(name)
    return called


def _has_supabase_marker(source: str) -> bool:
    return "pytest.mark.supabase" in source


def test_only_marked_tests_open_the_real_connection() -> None:
    offenders = []
    for py in sorted(TESTS.rglob("*.py")):
        source = py.read_text(encoding="utf-8")
        if _factories_called(py) and not _has_supabase_marker(source):
            offenders.append(str(py.relative_to(TESTS)))
    assert not offenders, (
        "Estos tests abren la conexion real sin marker 'supabase' "
        f"(se colgarian en una corrida normal): {offenders}"
    )


def test_supabase_marker_is_registered() -> None:
    """El marker existe en pyproject: sin registrar, --strict-markers lo rompe."""
    pyproject = (TESTS.parents[0] / "pyproject.toml").read_text(encoding="utf-8")
    assert "supabase:" in pyproject, "falta registrar el marker 'supabase' en pyproject.toml"
    assert 'not supabase' in pyproject, (
        "falta addopts con -m 'not supabase': la corrida por defecto tocaria la red"
    )
