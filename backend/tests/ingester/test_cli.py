import subprocess
import sys


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "agrosense.adapters.ingester.cli", *args],
        capture_output=True,
        text=True,
        cwd=None,
    )


def test_cli_help():
    r = run_cli("--help")
    assert r.returncode == 0
    assert "archivo" in (r.stdout + r.stderr).lower()


def test_cli_missing_file_fails():
    r = run_cli("no_existe.xlsx")
    assert r.returncode == 1
    assert "no encontrado" in r.stderr.lower()


def test_cli_real_dataset():
    """E2E: el CLI digiere el dataset de referencia si existe localmente."""
    from pathlib import Path

    ref = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"
    if not ref.exists():
        import pytest

        pytest.skip("dataset de referencia local ausente")
    r = run_cli(str(ref))
    assert r.returncode == 0
    assert "Arboles: 856" in r.stdout
    # muertes por campana documentadas: 35+66+101+138 = 340
    assert "Muertes registradas: 340" in r.stdout
