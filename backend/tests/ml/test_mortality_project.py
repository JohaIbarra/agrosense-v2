"""Modelo PROPIO de mortalidad y gate automatico (E8, plan D4/D5, ADR-014)."""
from __future__ import annotations

import random

from agrosense.ml.mortality_model import load_general_mortality_model
from agrosense.ml.mortality_project import MortalityScorer
from tests.ml.builders import mortality_panel, obs, tree


def _species_driven(n=300, waves=4, seed=3):
    """La especie 'Fragilis' muere mucho sin importar su tamano: el general no lo ve."""
    rng = random.Random(seed)
    trees, observations = [], []
    for i in range(n):
        tid = f"S_{i}"
        fragile = i % 4 == 0
        trees.append(tree(tid, species="Fragilis" if fragile else "Robusta", plot=f"U{i % 8}"))
        h, alive = 0.3 + rng.random() * 0.6, True
        for c in range(1, waves + 1):
            if not alive:
                observations.append(obs(tid, c, None, alive=False, phyto=None))
                continue
            observations.append(obs(tid, c, round(h, 3)))
            alive = rng.random() >= (0.45 if fragile else 0.03)
            h += rng.random() * 0.1
    return trees, observations


SCORER = MortalityScorer(load_general_mortality_model())


def test_first_monitoring_uses_the_general_model():
    trees, o = mortality_panel("A", seed=1)
    res = SCORER.assess(trees, o, 1)
    assert res.kind == "general"
    assert res.decision["reason"] == "sin_intervalos_cerrados"


def test_project_with_its_own_signal_and_history_uses_its_own_model():
    trees, o = _species_driven()
    res = SCORER.assess(trees, o, 3)
    assert res.kind == "project", res.decision
    d = res.decision
    assert d["holdout_lift_project"] > d["holdout_lift_general"]
    assert d["train_events"] >= 10 and d["holdout_events"] >= 5


def test_too_few_events_falls_back_to_the_general_model():
    trees, o = mortality_panel("B", n=40, seed=2)
    res = SCORER.assess(trees, o, 3)
    assert res.kind == "general"
    assert res.decision["reason"] in {"pocos_eventos", "general_mejor"}


def test_scores_cover_exactly_the_trees_at_risk_and_ignore_the_future():
    trees, o = _species_driven()
    res = SCORER.assess(trees, o, 2)
    alive_t2 = {x.tree_id for x in o if x.campaign == 2 and x.alive and x.height_m is not None}
    assert set(res.scores) == alive_t2
    future_changed = [x if x.campaign <= 2 else obs(x.tree_id, x.campaign, 9.9) for x in o]
    again = SCORER.assess(trees, future_changed, 2)
    assert again.scores == res.scores and again.kind == res.kind
    assert SCORER.fingerprint(trees, o, 2) == SCORER.fingerprint(trees, future_changed, 2)


def test_average_precision_matches_sklearn_with_ties():
    import pytest

    metrics = pytest.importorskip("sklearn.metrics")
    from agrosense.ml.mortality_project import average_precision

    rng = random.Random(5)
    y = [int(rng.random() < 0.2) for _ in range(300)]
    s = [round(rng.random(), 1) for _ in y]  # muchos empates
    assert average_precision(y, s) == pytest.approx(metrics.average_precision_score(y, s))
