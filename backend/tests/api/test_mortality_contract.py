"""Contrato del riesgo de mortalidad (E8): forma y validaciones."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agrosense.adapters.api.errors import _CODE_HTTP
from agrosense.adapters.api.schemas import (
    MortalityDecisionResponse,
    MortalityTreeResponse,
)

TREE = {
    "tree_id": "G_1",
    "species": "Senna viarum",
    "locality": "Guayabal",
    "plot": "U1",
    "height_m": 0.42,
    "score": 0.083,
    "risk_percentile": 97.5,
    "flagged": True,
    "stalled_last_interval": None,
}


def test_tree_shape():
    t = MortalityTreeResponse(**TREE)
    assert t.stalled_last_interval is None
    assert t.risk_percentile == 97.5


def test_percentile_is_bounded():
    with pytest.raises(ValidationError):
        MortalityTreeResponse(**{**TREE, "risk_percentile": 100.1})


def test_decision_only_requires_the_reason():
    d = MortalityDecisionResponse(reason="sin_intervalos_cerrados")
    assert d.model_dump(exclude_unset=True) == {"reason": "sin_intervalos_cerrados"}


def test_decision_reason_is_a_closed_set():
    with pytest.raises(ValidationError):
        MortalityDecisionResponse(reason="otra")


def test_model_unavailable_maps_to_503():
    assert _CODE_HTTP["MORTALITY_MODEL_UNAVAILABLE"] == 503
