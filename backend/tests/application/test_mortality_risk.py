"""UC-AN5: riesgo de mortalidad, con repos y scorer falsos."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agrosense.application.errors import AppError
from agrosense.application.use_cases.mortality_risk import (
    build_mortality_payload,
    get_mortality_assessment,
)
from agrosense.domain.stall_rules import is_at_risk
from tests.ml.builders import obs, tree

CARD = {
    "model_version": "mortality-general-test",
    "trained_on": ["Anexo 1"],
    "lopo": [{"held_out": "Anexo 1", "median_lift": 1.683}],
    "gate_passed": True,
}


def _dataset():
    trees = [
        tree("T1", plot="U1"),
        tree("T2", plot="U1"),
        tree("T3", plot="U2"),
        tree("T4", plot="U2"),
        tree("T5", plot="U2"),
    ]
    observations = [
        obs("T1", 1, 0.5), obs("T1", 2, 0.5), obs("T1", 3, 0.5),  # estancado
        obs("T2", 1, 0.4), obs("T2", 2, 0.5), obs("T2", 3, 0.5),  # estancado
        obs("T3", 1, 0.4), obs("T3", 2, 0.5), obs("T3", 3, 0.6),  # crece
        obs("T4", 1, 0.4), obs("T4", 2, 0.5), obs("T4", 3, 0.5, alive=False),  # murio
        obs("T5", 3, 0.3),  # entra en M3, sin historia
    ]
    return trees, observations


def _result(kind="general", scores=None, decision=None):
    return SimpleNamespace(
        kind=kind,
        scores=scores or {"T1": 0.9, "T2": 0.4, "T3": 0.2, "T5": 0.3},
        decision=decision or {"reason": "sin_intervalos_cerrados"},
    )


class _Projects:
    def __init__(self):
        self.monitorings = {n: SimpleNamespace(id=100 + n, number=n) for n in (1, 2, 3)}

    def get_owned(self, project_id, owner_id):
        return SimpleNamespace(id=project_id) if owner_id == "eng-1" else None

    def get_monitoring(self, project_id, number):
        return self.monitorings.get(number)


class _Dataset:
    def __init__(self, trees, observations):
        self.trees, self.observations = trees, observations

    def load_dataset(self, project_id):
        return self.trees, self.observations


class _Assessments:
    def __init__(self):
        self.rows: dict = {}
        self.saves = 0

    def get(self, monitoring_id):
        return self.rows.get(monitoring_id)

    def save(
        self,
        project_id,
        monitoring_id,
        model_kind,
        model_version,
        artifact_sha256,
        input_hash,
        rules_version,
        payload,
    ):
        self.saves += 1
        row = SimpleNamespace(
            project_id=project_id,
            monitoring_id=monitoring_id,
            model_kind=model_kind,
            model_version=model_version,
            artifact_sha256=artifact_sha256,
            input_hash=input_hash,
            rules_version=rules_version,
            payload=payload,
            computed_at=datetime(2026, 9, 30, tzinfo=UTC),
        )
        self.rows[monitoring_id] = row
        return row


class _Scorer:
    model_version = "mortality-general-test+mortality-project-test"
    artifact_sha256 = "a" * 64
    model_card = CARD

    def __init__(self, kind="general"):
        self.calls = 0
        self.kind = kind

    def assess(self, trees, observations, t):
        self.calls += 1
        ids = sorted(o.tree_id for o in observations if o.campaign == t and is_at_risk(o))
        scores = {tid: (i + 1) / (len(ids) + 1) for i, tid in enumerate(ids)}
        return _result(self.kind, scores, {"reason": "propio_mejor"})

    def fingerprint(self, trees, observations, t):
        return f"fp-{t}-{len(observations)}"


def _call(
    dataset=None, assessments=None, scorer=None, scorer_factory=None, owner="eng-1",
    number=3, **kw,
):
    trees, observations = dataset or _dataset()
    factory = scorer_factory or (lambda: scorer or _Scorer())
    return get_mortality_assessment(
        7,
        number,
        owner,
        _Projects(),
        _Dataset(trees, observations),
        assessments if assessments is not None else _Assessments(),
        factory,
        **kw,
    )


def test_foreign_project_is_not_found():
    with pytest.raises(AppError) as err:
        _call(owner="otro")
    assert err.value.code == "PROJECT_NOT_FOUND"


def test_missing_monitoring_is_not_found():
    with pytest.raises(AppError) as err:
        _call(number=9)
    assert err.value.code == "MONITORING_NOT_FOUND"


def _broken_scorer_factory():
    raise AppError("MORTALITY_MODEL_UNAVAILABLE", "El modelo no está disponible.")


def test_a_non_owner_gets_not_found_even_if_the_model_is_down():
    with pytest.raises(AppError) as err:
        _call(owner="otro", scorer_factory=_broken_scorer_factory)
    assert err.value.code == "PROJECT_NOT_FOUND"


def test_a_missing_monitoring_is_not_found_even_if_the_model_is_down():
    with pytest.raises(AppError) as err:
        _call(number=9, scorer_factory=_broken_scorer_factory)
    assert err.value.code == "MONITORING_NOT_FOUND"


def test_the_model_being_down_is_still_reported_for_an_owned_project():
    with pytest.raises(AppError) as err:
        _call(scorer_factory=_broken_scorer_factory)
    assert err.value.code == "MORTALITY_MODEL_UNAVAILABLE"


def test_payload_ranks_and_flags_the_wave():
    trees, observations = _dataset()
    payload = build_mortality_payload(trees, observations, 3, _result(), 0.2)
    assert payload["model_kind"] == "general"
    assert payload["score_kind"] == "relative_risk"
    assert payload["decision"] == {"reason": "sin_intervalos_cerrados"}
    assert payload["alert_budget_pct"] == 20.0
    assert payload["summary"] == {
        "at_risk": 4,
        "flagged": 1,
        "stalled_last_interval": 2,
        "without_history": 1,
    }
    rows = {r["tree_id"]: r for r in payload["trees"]}
    assert "T4" not in rows  # muerto en M3: sin puntaje
    assert rows["T1"] == {
        "tree_id": "T1",
        "species": "Senna viarum",
        "locality": "Guayabal",
        "plot": "U1",
        "height_m": 0.5,
        "score": 0.9,
        "risk_percentile": 100.0,
        "flagged": True,
        "stalled_last_interval": True,
    }
    assert rows["T3"]["risk_percentile"] == 0.0
    assert rows["T3"]["stalled_last_interval"] is False
    assert rows["T5"]["stalled_last_interval"] is None
    assert [r["tree_id"] for r in payload["trees"]] == ["T1", "T2", "T5", "T3"]


def test_percentile_is_the_rank_within_the_wave():
    trees, observations = _dataset()
    payload = build_mortality_payload(trees, observations, 3, _result(), 0.2)
    pct = {r["tree_id"]: r["risk_percentile"] for r in payload["trees"]}
    assert pct == {"T1": 100.0, "T2": 66.7, "T5": 33.3, "T3": 0.0}


def test_ties_share_the_same_percentile_and_order_by_tree_id():
    trees, observations = _dataset()
    scores = {"T1": 0.5, "T2": 0.5, "T3": 0.1, "T5": 0.9}
    payload = build_mortality_payload(trees, observations, 3, _result(scores=scores), 0.2)
    assert [r["tree_id"] for r in payload["trees"]] == ["T5", "T1", "T2", "T3"]
    pct = {r["tree_id"]: r["risk_percentile"] for r in payload["trees"]}
    assert pct["T1"] == pct["T2"] == 50.0


def test_a_single_tree_is_the_top_percentile():
    trees, observations = _dataset()
    payload = build_mortality_payload(trees, observations, 3, _result(scores={"T1": 0.3}), 0.2)
    assert payload["trees"][0]["risk_percentile"] == 100.0


def test_project_model_scores_are_probabilities():
    trees, observations = _dataset()
    payload = build_mortality_payload(trees, observations, 3, _result("project"), 0.2)
    assert payload["model_kind"] == "project"
    assert payload["score_kind"] == "probability"


def test_assessment_returns_provenance_and_model_card():
    dto = _call()
    assert dto.monitoring == 3
    assert dto.model_kind == "general"
    assert dto.score_kind == "relative_risk"
    assert dto.model_version == "mortality-general-test+mortality-project-test"
    assert dto.input_hash == "fp-3-13"
    assert dto.model_card == CARD
    assert dto.decision["reason"] == "propio_mejor"
    assert dto.summary["at_risk"] == 4


def test_snapshot_is_reused_when_nothing_changed():
    assessments, scorer = _Assessments(), _Scorer()
    _call(assessments=assessments, scorer=scorer)
    _call(assessments=assessments, scorer=scorer)
    assert scorer.calls == 1
    assert assessments.saves == 1


def test_a_new_model_recomputes():
    assessments = _Assessments()
    _call(assessments=assessments)
    nuevo = _Scorer()
    nuevo.model_version = "mortality-general-test-2+x"
    _call(assessments=assessments, scorer=nuevo)
    assert assessments.saves == 2


def test_a_new_artifact_recomputes():
    assessments = _Assessments()
    _call(assessments=assessments)
    nuevo = _Scorer()
    nuevo.artifact_sha256 = "b" * 64
    _call(assessments=assessments, scorer=nuevo)
    assert assessments.saves == 2


def test_a_new_rules_version_recomputes(monkeypatch):
    import agrosense.application.use_cases.mortality_risk as uc

    assessments = _Assessments()
    _call(assessments=assessments)
    monkeypatch.setattr(uc, "MORTALITY_RULES_VERSION", "otra-version-de-reglas")
    _call(assessments=assessments)
    assert assessments.saves == 2
    assert assessments.rows[103].rules_version == "otra-version-de-reglas"


def test_changed_data_recomputes():
    assessments = _Assessments()
    trees, observations = _dataset()
    _call(dataset=(trees, observations), assessments=assessments)
    _call(dataset=(trees, observations + [obs("T6", 3, 0.2)]), assessments=assessments)
    assert assessments.saves == 2


def test_only_flagged_filters_trees_but_not_the_summary():
    dto = _call(only_flagged=True)
    assert [t["tree_id"] for t in dto.trees] == ["T5"]  # mayor puntaje del _Scorer
    assert dto.summary["at_risk"] == 4
