"""Entrena y evalua el modelo GENERAL de mortalidad (E8, ADR-014). EL comando unico.

Uso (desde backend/, con `pip install -e ".[dev,ml]"`):
    python scripts/train_mortality_general.py --data data/raw/anexo1.xlsx
    python scripts/train_mortality_general.py --data data/raw/anexo1.xlsx --check

Proyectos: Anexo 1 (local, no se versiona) + Werden et al. 2018 y 2020
(Costa Rica, CC0), que se descargan de Zenodo a `data/external/` y se
verifican por SHA-256 antes de usarse. Este script es el composition root:
convierte cada fuente a entidades de dominio y ml/ hace el resto con la MISMA
featurizacion que sirve la API.

Sin `--check`: evalua (LOPO + azar empirico), aplica el gate y SOLO si lo pasa
escribe el artefacto y `docs/ml/evaluacion-mortalidad.md`.
Con `--check`: reentrena y compara contra lo versionado; no escribe nada.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import platform
import subprocess
import sys
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "src"))

from agrosense.adapters.ingester.column_mapping import MAPPING_VERSION  # noqa: E402
from agrosense.adapters.ingester.excel_source import ExcelCampaignSource  # noqa: E402
from agrosense.domain.entities import Observation, StatusSemantic, Tree  # noqa: E402
from agrosense.ml.mortality_model import MORTALITY_ARTIFACT_PATH  # noqa: E402
from agrosense.ml.train_mortality import (  # noqa: E402
    MortalityTrainConfig,
    SourceProject,
    render_report,
    train_and_evaluate,
)
from agrosense.ml.train_stall import diff_artifacts  # noqa: E402

REPORT_PATH = REPO / "docs" / "ml" / "evaluacion-mortalidad.md"
EXTERNAL = BACKEND / "data" / "external"
ANEXO_SHA256 = "28583c3b48874626f3d7d7ae35d485634a8c8089b4c03a5997f5ba756b57a0dd"

WERDEN = {
    "Werden 2018": {
        "url": "https://zenodo.org/records/4956588/files/survival_growth_surveys_Werden_et_al.csv?download=1",
        "file": "werden2018_survival_growth_surveys.csv",
        "sha256": "0818530bde31b05dd73e4b74e6af881c64250ab2fceb1f8a0fccc68283a3bfc2",
        "doi": "10.5061/dryad.fd57r", "license": "CC0-1.0",
        # La altura solo se mide en estos censos; los demas son solo supervivencia.
        "surveys": [1, 4, 8, 10, 11, 12, 13],
        "species": "spCode", "height_cm": "height_cm", "group": "block",
    },
    "Werden 2020": {
        "url": "https://zenodo.org/records/4968196/files/seedlingSurveys_WerdenEtAl2020_EcolApps.csv?download=1",
        "file": "werden2020_seedling_surveys.csv",
        "sha256": "7f5d59d44ef52b95ca0d77a7abd13a8919e761e0d8b2326881c86c2f0daf9df5",
        "doi": "10.5061/dryad.jm63xsj6p", "license": "CC0-1.0",
        "surveys": [1, 2, 3, 4],
        "species": "sppCode", "height_cm": "height", "group": "plot",
    },
}


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                              check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


def _fetch(spec: dict) -> bytes:
    path = EXTERNAL / spec["file"]
    if not path.exists():
        EXTERNAL.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(spec["url"], timeout=120) as resp:  # noqa: S310 (URL fija)
            path.write_bytes(resp.read())
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        raise SystemExit(f"{path.name}: SHA-256 inesperado; borre el archivo y reintente.")
    return raw


def werden_project(name: str, spec: dict) -> SourceProject:
    """Werden -> entidades de dominio. Monitoreo k = k-esimo censo con altura."""
    wave = {s: i + 1 for i, s in enumerate(spec["surveys"])}
    prefix = name.lower().replace(" ", "")
    trees: dict[str, Tree] = {}
    observations: list[Observation] = []
    for r in csv.DictReader(io.StringIO(_fetch(spec).decode("utf-8-sig"))):
        survey = int(r["surveyNumber"])
        if survey not in wave:
            continue
        tid = f"{prefix}-{r['seedlingID']}"
        trees.setdefault(tid, Tree(
            tree_id=tid, species=r[spec["species"]], locality=f"{spec['group']} {r[spec['group']]}",
            sampling_unit_code=f"{prefix}-{r[spec['group']]}",
        ))
        h = r[spec["height_cm"]].strip()
        observations.append(Observation(
            tree_id=tid, campaign=wave[survey],
            height_m=float(h) / 100 if h not in ("", "NA") else None,
            crown_diameter_m=None, dap_cm=None, dap_status=StatusSemantic.SIN_CENSO,
            phytosanitary=None, alive=r["survival"].strip() == "1", colonization=None,
        ))
    source = {k: spec[k] for k in ("doi", "license", "sha256", "url")}
    return SourceProject(name, list(trees.values()), observations, source)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Entrena el modelo general de mortalidad.")
    parser.add_argument("--data", type=Path, required=True, help="Anexo 1 (Monitoreo_4)")
    parser.add_argument("--out", type=Path, default=MORTALITY_ARTIFACT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--check", action="store_true", help="reentrena y compara")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    raw = args.data.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ANEXO_SHA256:
        print("El Anexo 1 no es la version esperada.", file=sys.stderr)
        return 2
    anexo = ExcelCampaignSource().read(raw, args.data.name)
    projects = [
        SourceProject("Anexo 1", anexo.trees, anexo.observations,
                      {"sha256": ANEXO_SHA256, "mapping_version": MAPPING_VERSION}),
        *(werden_project(n, s) for n, s in WERDEN.items()),
    ]
    import numpy
    import sklearn

    provenance = {"git_commit": _git("rev-parse", "HEAD") or "desconocido",
                  "python": platform.python_version(), "sklearn": sklearn.__version__,
                  "numpy": numpy.__version__}
    artifact = train_and_evaluate(projects, MortalityTrainConfig(), provenance)
    report = render_report(artifact)
    print(report)

    if args.check:
        committed = json.loads(args.out.read_text(encoding="utf-8"))
        diffs = diff_artifacts(committed, artifact)
        diffs = [d for d in diffs if "git_commit" not in d]
        if diffs:
            print("NO reproduce el artefacto:\n  " + "\n  ".join(diffs), file=sys.stderr)
            return 1
        print("Reproducible: el reentrenamiento coincide con el artefacto versionado.")
        return 0
    if not artifact["gate"]["passed"]:
        print(f"El modelo NO pasa el gate: {artifact['gate']['checks']}", file=sys.stderr)
        return 1
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    args.report.write_text(report, encoding="utf-8")
    print(f"Artefacto: {args.out}\nInforme: {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
