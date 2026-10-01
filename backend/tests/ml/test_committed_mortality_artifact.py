"""El artefacto versionado del modelo general de mortalidad carga y pasa su gate (E8)."""
from __future__ import annotations

from agrosense.ml.mortality_model import load_general_mortality_model


def test_committed_artifact_loads_and_passed_its_gate():
    model = load_general_mortality_model()
    assert model.model_card["gate_passed"] is True
    assert model.coefficients[0] < 0  # los pequenos mueren mas
    assert {h["held_out"] for h in model.model_card["lopo"]} == {
        "Anexo 1", "Werden 2018", "Werden 2020"
    }
