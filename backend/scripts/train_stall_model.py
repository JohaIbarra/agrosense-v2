"""Entrena y evalua el modelo de estancamiento (E7, ADR-013). EL comando unico.

Uso (desde backend/, con `pip install -e ".[dev,ml]"`):
    python scripts/train_stall_model.py --data data/raw/anexo1.xlsx
    python scripts/train_stall_model.py --data data/raw/anexo1.xlsx --check

Sin `--check`: evalua (temporal + GroupKFold por parcela + bootstrap +
control permutado + lineas base), aplica el ML eval gate y, SOLO si lo pasa,
escribe el artefacto versionado y el informe de metricas.
Con `--check`: reentrena y compara contra el artefacto versionado; no
escribe nada. Es la prueba de reproducibilidad de AGENTS.md.

Este script es el composition root: lee el Excel con el adapter de ingesta
(el mismo que usa la carga de la API) y le pasa entidades de dominio a ml/,
que no puede importar adapters/ (ADR-003).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "src"))

from agrosense.adapters.ingester.column_mapping import MAPPING_VERSION  # noqa: E402
from agrosense.adapters.ingester.excel_source import (  # noqa: E402
    SHEET_NAME,
    ExcelCampaignSource,
)
from agrosense.ml.stall_model import ARTIFACT_PATH  # noqa: E402
from agrosense.ml.train_stall import (  # noqa: E402
    StallTrainConfig,
    diff_artifacts,
    render_report,
    train_and_evaluate,
)

REPORT_PATH = REPO / "docs" / "ml" / "evaluacion-estancamiento.md"


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


def _provenance(data_path: Path, sha: str) -> dict:
    import numpy
    import sklearn

    status = _git("status", "--porcelain")
    return {
        "dataset_file": data_path.name,
        "dataset_sha256": sha,
        "sheet": SHEET_NAME,
        "mapping_version": MAPPING_VERSION,
        "git_commit": _git("rev-parse", "HEAD") or "desconocido",
        "git_dirty": bool(status),
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
        "numpy": numpy.__version__,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Entrena y evalua el modelo de estancamiento.")
    parser.add_argument("--data", type=Path, required=True, help="Excel de campo (Monitoreo_4)")
    parser.add_argument("--out", type=Path, default=ARTIFACT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument(
        "--check", action="store_true", help="reentrena y compara; no escribe nada"
    )
    parser.add_argument(
        "--allow-other-data",
        action="store_true",
        help="acepta un dataset distinto del versionado (su huella queda en el artefacto)",
    )
    args = parser.parse_args(argv)
    config = StallTrainConfig()
    # La consola de Windows (cp1252) no sabe escribir "→" del informe.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    raw = args.data.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != config.expected_dataset_sha256 and not args.allow_other_data:
        print(
            f"El dataset no es la version esperada (sha256 {sha[:12]}..., se esperaba "
            f"{config.expected_dataset_sha256[:12]}...). Use --allow-other-data si es intencional.",
            file=sys.stderr,
        )
        return 2

    campaign = ExcelCampaignSource().read(raw, args.data.name)
    artifact = train_and_evaluate(
        campaign.trees, campaign.observations, config, _provenance(args.data, sha)
    )
    report = render_report(artifact)
    passed = artifact["evaluation"]["gate"]["passed"]

    if args.check:
        if not args.out.exists():
            print(f"No hay artefacto versionado en {args.out}", file=sys.stderr)
            return 1
        committed = json.loads(args.out.read_text(encoding="utf-8"))
        diffs = diff_artifacts(committed, artifact)
        if diffs:
            print(
                "El reentrenamiento NO reproduce el artefacto:\n  " + "\n  ".join(diffs),
                file=sys.stderr,
            )
            return 1
        print(f"Reproducible: {artifact['model_version']} coincide con {args.out.name}.")
        return 0 if passed else 1

    if not passed:
        print(report)
        print("ML eval gate RECHAZADO: no se escribe el artefacto.", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(report)
    print(f"Artefacto: {args.out}\nInforme: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
