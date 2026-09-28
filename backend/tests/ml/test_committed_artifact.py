"""El artefacto versionado carga, paso el gate y es de este dataset."""
from __future__ import annotations

import json

from agrosense.ml.stall_model import ARTIFACT_PATH, load_stall_model

DATASET_SHA256 = "28583c3b48874626f3d7d7ae35d485634a8c8089b4c03a5997f5ba756b57a0dd"


def test_committed_artifact_is_servable():
    model = load_stall_model()
    assert model.model_version.startswith("stall-logreg-")
    assert len(model.coefficients) == len(model.params.feature_names)
    assert model.model_card["dataset_sha256"] == DATASET_SHA256


def test_committed_artifact_passed_the_gate():
    data = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    ev = data["evaluation"]
    assert ev["gate"]["passed"] is True
    assert (ev["temporal"]["n_test"], ev["temporal"]["positives_test"]) == (717, 157)
    assert ev["temporal"]["pr_auc"] >= 0.36
    assert data["provenance"]["git_dirty"] is False
