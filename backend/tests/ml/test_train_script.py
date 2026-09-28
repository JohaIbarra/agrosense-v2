"""El comando unico de entrenamiento se niega a entrenar con otros datos."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

SCRIPT = Path(__file__).parents[2] / "scripts" / "train_stall_model.py"
REFERENCE_PATH = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"


def _load():
    spec = importlib.util.spec_from_file_location("train_stall_model", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rejects_a_dataset_that_is_not_the_versioned_one(tmp_path):
    data = tmp_path / "otro.xlsx"
    data.write_bytes(b"no es el anexo")
    out = tmp_path / "a.json"
    code = _load().main(
        ["--data", str(data), "--out", str(out), "--report", str(tmp_path / "r.md")]
    )
    assert code == 2
    assert not out.exists()


@pytest.mark.skipif(
    not REFERENCE_PATH.exists(),
    reason="dataset de referencia local ausente (data/raw/anexo1.xlsx)",
)
def test_check_fails_if_the_committed_report_is_stale(tmp_path):
    """Fix round 1 (M3): `--check` tambien vigila el informe, no solo el JSON."""
    module = _load()
    out = tmp_path / "a.json"
    report = tmp_path / "r.md"
    code = module.main(
        ["--data", str(REFERENCE_PATH), "--out", str(out), "--report", str(report)]
    )
    assert code == 0
    # El informe documentado queda desactualizado respecto del que generaria
    # el codigo actual (p. ej. alguien edito render_report sin reentrenar).
    report.write_text(report.read_text(encoding="utf-8") + "\ntexto espurio\n", encoding="utf-8")
    code = module.main(
        ["--data", str(REFERENCE_PATH), "--out", str(out), "--report", str(report), "--check"]
    )
    assert code == 1
