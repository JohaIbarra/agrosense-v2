"""El comando unico de entrenamiento se niega a entrenar con otros datos."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

SCRIPT = Path(__file__).parents[2] / "scripts" / "train_stall_model.py"


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
