"""UC-AN4: deteccion de estancados, con repos y modelo falsos."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agrosense.application.errors import AppError
from agrosense.application.use_cases.stall_detection import (
    build_stall_payload,
    get_stall_assessment,
)
from agrosense.domain.stall_rules import is_at_risk
from tests.ml.builders import obs, tree

CARD = {
    "model_version": "stall-test-1",
    "artifact_sha256": "a" * 64,
    "dataset_sha256": "0" * 64,
    "trained_on": "anexo1.xlsx",
    "pr_auc": 0.47,
    "pr_auc_ci_low": 0.36,
    "pr_auc_ci_high": 0.58,
    "roc_auc": 0.73,
    "prevalence_pct": 21.9,
    "recall_at_budget_pct": 45.0,
    "precision_at_budget_pct": 50.0,
}


def _dataset():
    trees = [
        tree("T1", plot="U1"),
        tree("T2", plot="U1"),
        tree("T3", plot="U2"),
        tree("T4", plot="U2"),
        tree("T5", plot="U2", species="Especie rara"),
    ]
    observations = [
        obs("T1", 1, 0.5), obs("T1", 2, 0.5), obs("T1", 3, 0.5),  # persistente
        obs("T2", 1, 0.4), obs("T2", 2, 0.5), obs("T2", 3, 0.5),  # estanco una vez
        obs("T3", 1, 0.4), obs("T3", 2, 0.5), obs("T3", 3, 0.6),  # crece
        obs("T4", 1, 0.4), obs("T4", 2, 0.5), obs("T4", 3, 0.5, alive=False),  # murio
        obs("T5", 3, 0.3),  # entra en M3, sin historia
    ]
    return trees, observations


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
            model_version=model_version,
            artifact_sha256=artifact_sha256,
            input_hash=input_hash,
            rules_version=rules_version,
            payload=payload,
            computed_at=datetime(2026, 9, 27, tzinfo=UTC),
        )
        self.rows[monitoring_id] = row
        return row


class _Scorer:
    model_version = "stall-test-1"
    artifact_sha256 = "a" * 64
    model_card = CARD
    KNOWN_SPECIES = frozenset({"Senna viarum"})

    def __init__(self):
        self.calls = 0

    def predict(self, trees, observations, t):
        self.calls += 1
        at_risk = sorted(o.tree_id for o in observations if o.campaign == t and is_at_risk(o))
        return {tid: (i + 1) / (len(at_risk) + 1) for i, tid in enumerate(at_risk)}

    def unknown_categories(self, trees, observations, t):
        at_risk = sorted(o.tree_id for o in observations if o.campaign == t and is_at_risk(o))
        by_id = {tr.tree_id: tr for tr in trees}
        return {
            tid: (
                []
                if tid in by_id and by_id[tid].species in self.KNOWN_SPECIES
                else ["species"]
            )
            for tid in at_risk
        }

    def fingerprint(self, trees, observations, t):
        return f"fp-{t}-{len(observations)}"


def _call(dataset=None, assessments=None, scorer=None, owner="eng-1", number=3, **kw):
    trees, observations = dataset or _dataset()
    return get_stall_assessment(
        7,
        number,
        owner,
        _Projects(),
        _Dataset(trees, observations),
        assessments if assessments is not None else _Assessments(),
        scorer or _Scorer(),
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


def test_payload_applies_the_business_rule():
    trees, observations = _dataset()
    probs = {"T1": 0.9, "T2": 0.4, "T3": 0.2, "T5": 0.3}
    unknown = {"T1": [], "T2": [], "T3": [], "T5": ["species"]}
    payload = build_stall_payload(trees, observations, 3, probs, unknown)
    assert payload["alert_budget_pct"] == 20.0
    assert payload["persistent_min_intervals"] == 2
    assert payload["summary"] == {
        "at_risk": 4,
        "flagged": 1,
        "stalled_last_interval": 2,
        "persistent": 1,
        "without_history": 1,
        "unknown_species": 1,
        "unknown_category_trees": 1,
        "mostly_without_history": False,
    }
    rows = {r["tree_id"]: r for r in payload["trees"]}
    assert "T4" not in rows  # muerto en M3: no esta en riesgo
    assert rows["T1"] == {
        "tree_id": "T1",
        "species": "Senna viarum",
        "locality": "Guayabal",
        "plot": "U1",
        "probability": 0.9,
        "flagged": True,
        "stalled_last_interval": True,
        "stall_streak": 2,
        "persistent": True,
        "unknown_categories": [],
        "known_species": True,
    }
    assert rows["T2"]["stall_streak"] == 1 and rows["T2"]["persistent"] is False
    assert rows["T3"]["stalled_last_interval"] is False
    assert rows["T5"]["stalled_last_interval"] is None
    assert rows["T5"]["known_species"] is False
    assert rows["T5"]["unknown_categories"] == ["species"]
    assert [r["tree_id"] for r in payload["trees"]] == ["T1", "T2", "T5", "T3"]


def test_assessment_returns_provenance_and_model_card():
    dto = _call()
    assert dto.monitoring == 3
    assert dto.model_version == "stall-test-1"
    assert dto.input_hash == "fp-3-13"
    assert dto.model_card == CARD
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
    nuevo.model_version = "stall-test-2"
    _call(assessments=assessments, scorer=nuevo)
    assert assessments.saves == 2
    assert assessments.rows[103].model_version == "stall-test-2"


def test_a_new_rules_version_recomputes(monkeypatch):
    # Fix wave (item 4): ALERT_BUDGET/PERSISTENT_STALL_INTERVALS/la etiqueta
    # pueden cambiar sin tocar el modelo; el snapshot debe invalidarse igual.
    import agrosense.application.use_cases.stall_detection as ucd

    assessments = _Assessments()
    _call(assessments=assessments)
    monkeypatch.setattr(ucd, "RULES_VERSION", "otra-version-de-reglas")
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
    assert [t["tree_id"] for t in dto.trees] == ["T5"]  # mayor probabilidad del _Scorer
    assert dto.summary["at_risk"] == 4
