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

# Excepcion acotada: un test PUEDE llamar a esas fabricas si antes redirige
# `DATABASE_URL` a SQLite, porque entonces no hay conexion remota que abrir.
# Es el caso de los tests del engine cacheado (fase 6 del slice 5): lo que
# verifican es que el engine se reutilice entre requests, y para eso tienen
# que construirlo.
#
# La excepcion exige las DOS marcas en el mismo archivo — parchear
# `DATABASE_URL` y apuntar a sqlite —, no solo una. Un test que parchee la
# variable hacia otra cosa sigue siendo una violacion.
_REDIRECT_MARKS = ('"DATABASE_URL"', "'DATABASE_URL'")
_SQLITE_MARK = "sqlite://"


# El conftest del smoke (E1) crea el ingeniero de prueba en Supabase. Un
# conftest no puede llevar `pytestmark`, pero solo se ejecuta cuando corren
# tests de su carpeta; la exencion es segura MIENTRAS todos ellos esten
# marcados `supabase`, y eso lo exige test_every_smoke_module_is_marked_supabase.
SMOKE_CONFTEST = "smoke/conftest.py"


def _redirects_to_sqlite(source: str) -> bool:
    """El archivo apunta DATABASE_URL a SQLite antes de usar las fabricas."""
    parchea = any(
        f"setattr(mod, {mark}" in source or f"setattr({mark}" in source
        for mark in _REDIRECT_MARKS
    ) or any(
        f"monkeypatch.setenv({mark}" in source for mark in _REDIRECT_MARKS
    )
    return parchea and _SQLITE_MARK in source


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
        if not _factories_called(py):
            continue
        if _has_supabase_marker(source) or _redirects_to_sqlite(source):
            continue
        if py.relative_to(TESTS).as_posix() == SMOKE_CONFTEST:
            continue  # ver test_every_smoke_module_is_marked_supabase
        offenders.append(str(py.relative_to(TESTS)))
    assert not offenders, (
        "Estos tests abren la conexion real sin marker 'supabase' "
        f"(se colgarian en una corrida normal): {offenders}"
    )


def test_the_sqlite_exception_is_not_a_blank_cheque() -> None:
    """La excepcion exige AMBAS marcas, no basta con nombrar DATABASE_URL.

    Sin esto, la excepcion que se abrio para los tests del engine cacheado
    dejaria pasar cualquier test que mencionara la variable — que es
    exactamente como un gate deja de servir para algo.
    """
    solo_parche = 'monkeypatch.setattr(mod, "DATABASE_URL", "postgresql://real/db")'
    solo_sqlite = 'engine = create_engine("sqlite://")'
    ambas = solo_parche.replace("postgresql://real/db", "sqlite:///:memory:")

    assert not _redirects_to_sqlite(solo_parche)
    assert not _redirects_to_sqlite(solo_sqlite)
    assert _redirects_to_sqlite(ambas)


def test_supabase_marker_is_registered() -> None:
    """El marker existe en pyproject: sin registrar, --strict-markers lo rompe."""
    pyproject = (TESTS.parents[0] / "pyproject.toml").read_text(encoding="utf-8")
    assert "supabase:" in pyproject, "falta registrar el marker 'supabase' en pyproject.toml"
    assert 'not supabase' in pyproject, (
        "falta addopts con -m 'not supabase': la corrida por defecto tocaria la red"
    )


def test_every_smoke_module_is_marked_supabase() -> None:
    """Condicion de la exencion del conftest del smoke.

    Si un test sin marcar entrara en `tests/smoke/`, correria en el `pytest`
    por defecto y arrastraria el fixture que abre la conexion real.
    """
    sin_marca = [
        py.name
        for py in sorted((TESTS / "smoke").glob("test_*.py"))
        if not _has_supabase_marker(py.read_text(encoding="utf-8"))
    ]
    assert not sin_marca, f"tests de smoke sin el marker supabase: {sin_marca}"
