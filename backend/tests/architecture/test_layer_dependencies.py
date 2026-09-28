"""Gate ejecutable de la regla de dependencia de ADR-003.

    domain/  <-  application/  <-  adapters/ | ml/

Las flechas apuntan HACIA ADENTRO. Este test lee los imports reales de
cada modulo (AST, sin importarlos) y falla si alguna capa mira hacia
afuera. Sustituye al item manual del gate de Task 6 del plan del slice 2
("application/ no importa fastapi ni sqlalchemy") — que como chequeo
humano ya se nos habia escapado una vez.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "src" / "agrosense"

# Que NO puede importar cada capa. La clave es "agrosense.adapters":
# una capa interna que importa un adapter invierte la flecha de ADR-003.
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "domain": (
        "agrosense.application",
        "agrosense.adapters",
        "agrosense.ml",
        "fastapi",
        "sqlalchemy",
        "pandas",
    ),
    "application": (
        "agrosense.adapters",
        # ADR-003/ADR-013: ml/ es capa exterior; el caso de uso recibe el
        # modelo inyectado, no lo importa.
        "agrosense.ml",
        "fastapi",
        "sqlalchemy",
        "pandas",
    ),
    # ADR-003: "Modulo ml/ no puede importar adapters/ — solo domain/".
    "ml": (
        "agrosense.application",
        "agrosense.adapters",
        "fastapi",
        "sqlalchemy",
    ),
    # Regla del plan de slice 2: la API no parsea datos, delega en el ingester.
    "adapters/api": ("pandas",),
}


def _imports_of(path: Path) -> list[tuple[str, int]]:
    """(modulo importado, linea) de un archivo, sin ejecutarlo."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module, node.lineno))
    return found


def _violations(layer: str, forbidden: tuple[str, ...]) -> list[str]:
    layer_dir = SRC / Path(layer)
    if not layer_dir.exists():
        pytest.skip(f"capa {layer} aun no existe")
    out = []
    for py in sorted(layer_dir.rglob("*.py")):
        for module, lineno in _imports_of(py):
            for banned in forbidden:
                if module == banned or module.startswith(banned + "."):
                    rel = py.relative_to(SRC.parent)
                    out.append(f"{rel}:{lineno} importa {module!r} (prohibido en {layer}/)")
    return out


@pytest.mark.parametrize("layer", list(FORBIDDEN))
def test_layer_does_not_import_outwards(layer: str) -> None:
    violations = _violations(layer, FORBIDDEN[layer])
    assert not violations, "Violacion de la regla de dependencia (ADR-003):\n" + "\n".join(
        violations
    )


def test_domain_is_self_contained() -> None:
    """domain/ solo se importa a si mismo dentro del paquete agrosense."""
    bad = []
    for py in sorted((SRC / "domain").rglob("*.py")):
        for module, lineno in _imports_of(py):
            if module.startswith("agrosense.") and not module.startswith("agrosense.domain"):
                bad.append(f"{py.relative_to(SRC.parent)}:{lineno} -> {module}")
    assert not bad, "domain/ debe ser autocontenido:\n" + "\n".join(bad)


# ADR-013: la ruta de INFERENCIA corre en cada peticion de la API y debe ser
# Python puro. numpy/sklearn solo existen en el extra `ml` (entrenamiento).
ML_SERVING_MODULES = (
    "ml/__init__.py",
    "ml/stall_features.py",
    "ml/preprocessing.py",
    "ml/stall_model.py",
)
ML_SERVING_FORBIDDEN = ("numpy", "sklearn", "pandas", "scipy", "joblib", "pickle")


def test_ml_serving_path_is_pure_python() -> None:
    presentes = [SRC / m for m in ML_SERVING_MODULES if (SRC / m).exists()]
    if not presentes:
        pytest.skip("la ruta de inferencia de ml/ aun no existe (E7)")
    malos = []
    for py in presentes:
        for module, lineno in _imports_of(py):
            raiz = module.split(".")[0]
            if raiz in ML_SERVING_FORBIDDEN:
                malos.append(f"{py.relative_to(SRC.parent)}:{lineno} importa {module!r}")
    assert not malos, "La inferencia debe ser Python puro (ADR-013):\n" + "\n".join(malos)
