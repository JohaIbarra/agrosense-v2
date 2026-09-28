"""Contrato de la deteccion de estancados (E7): forma y validaciones."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agrosense.adapters.api.errors import _CODE_HTTP
from agrosense.adapters.api.schemas import (
    StallAssessmentResponse,
    StallModelCardResponse,
    StallSummaryResponse,
    StallTreeResponse,
)

TREE = {
    "tree_id": "FR_1_31",
    "species": "Lafoensia speciosa",
    "locality": "Tres Jotas",
    "plot": "GEB/MED-LV/NV/FR/1",
    "probability": 0.62,
    "flagged": True,
    "stalled_last_interval": None,
    "stall_streak": 0,
    "persistent": False,
    "known_species": True,
}
CARD = {
    "model_version": "stall-logreg-2026-09-27.1",
    "artifact_sha256": "a" * 64,
    "dataset_sha256": "0" * 64,
    "trained_on": "anexo1.xlsx",
    "pr_auc": 0.478,
    "pr_auc_ci_low": 0.37,
    "pr_auc_ci_high": 0.58,
    "roc_auc": 0.738,
    "prevalence_pct": 21.9,
    "recall_at_budget_pct": 43.3,
    "precision_at_budget_pct": 47.6,
}
SUMMARY = {
    "at_risk": 718,
    "flagged": 143,
    "stalled_last_interval": 157,
    "persistent": 24,
    "without_history": 0,
    "unknown_species": 0,
}


def test_tree_shape():
    t = StallTreeResponse(**TREE)
    assert t.stalled_last_interval is None
    assert t.flagged is True


def test_probability_is_a_probability():
    with pytest.raises(ValidationError):
        StallTreeResponse(**{**TREE, "probability": 1.2})


def test_streak_is_never_negative():
    with pytest.raises(ValidationError):
        StallTreeResponse(**{**TREE, "stall_streak": -1})


def test_full_response_shape():
    r = StallAssessmentResponse(
        project_id=7,
        monitoring=4,
        input_hash="h" * 64,
        computed_at="2026-09-27T10:00:00Z",
        alert_budget_pct=20.0,
        persistent_min_intervals=2,
        model=StallModelCardResponse(**CARD),
        summary=StallSummaryResponse(**SUMMARY),
        trees=[StallTreeResponse(**TREE)],
    )
    assert r.model.pr_auc_ci_low == 0.37
    assert r.summary.flagged == 143


def test_model_unavailable_is_a_503():
    assert _CODE_HTTP["STALL_MODEL_UNAVAILABLE"] == 503
