"""Entrenamiento y gate del modelo GENERAL de mortalidad (E8, plan D2/D6)."""
from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from agrosense.ml.mortality_model import GeneralMortalityModel  # noqa: E402
from agrosense.ml.train_mortality import (  # noqa: E402
    MortalityTrainConfig,
    SourceProject,
    train_and_evaluate,
)
from tests.ml.builders import mortality_panel  # noqa: E402


def _projects(signal=True):
    return [
        SourceProject(name, *mortality_panel(name, signal=signal, seed=s), source={"id": name})
        for s, name in enumerate(("P1", "P2", "P3"))
    ]


def test_with_signal_the_gate_passes_and_the_coefficient_is_negative():
    art = train_and_evaluate(_projects(), MortalityTrainConfig())
    assert art["gate"]["passed"], art["gate"]
    assert art["model"]["coefficients"][0] < 0
    for held in art["evaluation"]["lopo"]:
        assert held["lift_over_random"] >= 1.2
        assert held["coefficient"] < 0
        # El azar empirico queda cerca de 1 (con sesgo positivo por pocos eventos)
        assert 0.8 < held["random_median_lift"] < 1.5


def test_without_signal_the_gate_fails():
    art = train_and_evaluate(_projects(signal=False), MortalityTrainConfig())
    assert not art["gate"]["passed"]


def test_artifact_is_servable_and_ranks_small_trees_first():
    art = train_and_evaluate(_projects(), MortalityTrainConfig())
    model = GeneralMortalityModel.from_dict(art, sha256="x" * 64)
    scores = model.score_rows([{"h_pct": 0.1}, {"h_pct": 0.9}])
    assert scores[0] > scores[1]
    assert model.model_version == art["model_version"]
