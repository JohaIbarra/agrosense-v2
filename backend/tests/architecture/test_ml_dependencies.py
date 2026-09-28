"""ADR-013: scikit-learn es herramienta de ENTRENAMIENTO, no de servicio.

La inferencia del modelo de estancamiento es Python puro sobre un artefacto
JSON. Si scikit-learn se colara en las dependencias de produccion, la API
cargaria una libreria que no usa y cada aviso de seguridad de sklearn (y de
scipy/joblib) pasaria a ser nuestro.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def _name(requirement: str) -> str:
    return requirement.split("==")[0].split("[")[0].strip().lower()


def test_sklearn_is_not_a_production_dependency():
    assert "scikit-learn" not in {_name(d) for d in _project()["dependencies"]}


def test_ml_extra_pins_exact_versions():
    extra = _project()["optional-dependencies"]["ml"]
    assert {"scikit-learn", "numpy"} <= {_name(d) for d in extra}
    assert all("==" in d for d in extra), f"versiones sin fijar: {extra}"
