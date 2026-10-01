"""Entrenamiento y evaluacion OFFLINE del modelo general de mortalidad (E8, ADR-014).

Solo entrenamiento (importa `ml.evaluation`, que usa scikit-learn): adapters/
no puede importarlo (tests/architecture).

Evaluacion: dejar un PROYECTO fuera (LOPO). Por cada proyecto fuera se
entrena con los demas y se mide, en cada intervalo t->t+1 del proyecto fuera,
el lift = PR-AUC / prevalencia, y el mismo lift con sus etiquetas permutadas
(azar empirico).

Gate pre-registrado (plan E8, D6), ANTES de ver el resultado real: en cada
proyecto fuera, (mediana del lift por intervalo) / (mediana del lift con sus
etiquetas permutadas) >= 1.2, y coeficiente de `h_pct` negativo (los
pequenos mueren mas).
"""
from __future__ import annotations

import random
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from agrosense.domain.entities import Observation, Tree
from agrosense.ml.evaluation import pr_auc
from agrosense.ml.logistic import fit_logistic_l2, predict_scores
from agrosense.ml.mortality_features import (
    GENERAL_FEATURES,
    MORTALITY_FEATURES_VERSION,
    build_mortality_wave,
)
from agrosense.ml.mortality_model import MORTALITY_ARTIFACT_FORMAT

MODEL_VERSION = "mortality-general-2026-09-30.1"


@dataclass(frozen=True)
class MortalityTrainConfig:
    C: float = 1.0
    seed: int = 42
    permutations: int = 20
    min_lift_over_random: float = 1.2


@dataclass(frozen=True)
class SourceProject:
    name: str
    trees: list[Tree]
    observations: list[Observation]
    source: dict = field(default_factory=dict)


Interval = tuple[list[list[float]], list[int]]  # (X, y) de un intervalo t->t+1


def project_intervals(project: SourceProject) -> list[Interval]:
    waves = sorted({o.campaign for o in project.observations})
    out: list[Interval] = []
    for t in waves[:-1]:
        rows = build_mortality_wave(project.trees, project.observations, t, labeled=True)
        if rows:
            out.append(
                ([[float(r.features[f] or 0.0) for f in GENERAL_FEATURES] for r in rows],
                 [int(bool(r.label)) for r in rows])
            )
    return out


def _pooled(intervals: Sequence[Interval]) -> Interval:
    X: list[list[float]] = []
    y: list[int] = []
    for xi, yi in intervals:
        X += xi
        y += yi
    return X, y


def _lifts(model, intervals: Sequence[Interval]) -> list[dict]:
    out = []
    for t, (X, y) in enumerate(intervals):
        if 0 < sum(y) < len(y):
            prev = sum(y) / len(y)
            ap = pr_auc(y, predict_scores(model, X))
            out.append({"interval": t, "n": len(y), "deaths": sum(y),
                        "prevalence": round(prev, 4), "pr_auc": round(ap, 4),
                        "lift": round(ap / prev, 3)})
    return out


def _median(values: Sequence[float]) -> float:
    return round(statistics.median(values), 3) if values else 0.0


def evaluate(projects: Sequence[SourceProject], config: MortalityTrainConfig) -> dict:
    by_name = {p.name: project_intervals(p) for p in projects}
    lopo: list[dict[str, Any]] = []
    for held in projects:
        train = _pooled([iv for n, ivs in by_name.items() if n != held.name for iv in ivs])
        model = fit_logistic_l2(*train, C=config.C)
        lifts = _lifts(model, by_name[held.name])
        lopo.append({"held_out": held.name, "coefficient": round(model.coef[0], 4),
                     "median_lift": _median([x["lift"] for x in lifts]), "intervals": lifts})

    # Azar EMPIRICO por proyecto fuera: sus etiquetas permutadas dentro de cada
    # intervalo. Hace falta porque el PR-AUC de un orden aleatorio no es la
    # prevalencia cuando hay pocos eventos (sesgo positivo, ~1.16x con 10-20
    # muertes por intervalo). Permutar las de ENTRENAMIENTO no sirve con una
    # sola variable: el orden solo depende del signo del coeficiente. Ambas
    # cosas las revelo el test sintetico, antes de correr con datos reales.
    rng = random.Random(config.seed)
    for held, entry in zip(projects, lopo, strict=True):
        train = _pooled([iv for n, ivs in by_name.items() if n != held.name for iv in ivs])
        model = fit_logistic_l2(*train, C=config.C)
        permuted: list[float] = []
        for _ in range(config.permutations):
            shuffled = []
            for X, y in by_name[held.name]:
                y2 = list(y)
                rng.shuffle(y2)
                shuffled.append((X, y2))
            permuted += [x["lift"] for x in _lifts(model, shuffled)]
        entry["random_median_lift"] = _median(permuted)
        entry["lift_over_random"] = (
            round(entry["median_lift"] / entry["random_median_lift"], 3)
            if entry["random_median_lift"] else 0.0
        )
    return {"lopo": lopo, "permutations": config.permutations}


def gate(evaluation: dict, config: MortalityTrainConfig) -> dict:
    checks = {
        f"lopo_{h['held_out']}": h["lift_over_random"] >= config.min_lift_over_random
        and h["coefficient"] < 0
        for h in evaluation["lopo"]
    }
    return {"passed": all(checks.values()), "checks": checks,
            "thresholds": {"min_lift_over_random": config.min_lift_over_random}}


def train_and_evaluate(
    projects: Sequence[SourceProject],
    config: MortalityTrainConfig,
    provenance: dict | None = None,
) -> dict:
    evaluation = evaluate(projects, config)
    final = fit_logistic_l2(
        *_pooled([iv for p in projects for iv in project_intervals(p)]), C=config.C
    )
    return {
        "format": MORTALITY_ARTIFACT_FORMAT,
        "model_version": MODEL_VERSION,
        "features_version": MORTALITY_FEATURES_VERSION,
        "model": {"type": "logistic_regression_l2", "feature_names": list(GENERAL_FEATURES),
                  "coefficients": [round(c, 6) for c in final.coef],
                  "intercept": round(final.intercept, 6)},
        "config": asdict(config),
        "evaluation": evaluation,
        "gate": gate(evaluation, config),
        "provenance": {**(provenance or {}),
                       "projects": [{"name": p.name, **p.source} for p in projects]},
    }


def render_report(artifact: dict) -> str:
    ev, g = artifact["evaluation"], artifact["gate"]
    lines = [
        "# Evaluación del modelo general de mortalidad (E8)",
        "",
        "> Generado por `python scripts/train_mortality_general.py`. No editar a mano.",
        "",
        f"- **Modelo:** `{artifact['model_version']}` · variables: "
        f"{', '.join(artifact['model']['feature_names'])} · "
        f"coeficiente {artifact['model']['coefficients'][0]} · intercepto "
        f"{artifact['model']['intercept']}",
        f"- **Gate (pre-registrado, ADR-014):** {'PASA' if g['passed'] else 'NO PASA'} "
        f"— {g['checks']}",
        f"- **Azar empírico:** etiquetas del proyecto fuera permutadas {ev['permutations']} "
        f"veces; umbral lift/azar ≥ {g['thresholds']['min_lift_over_random']}",
        "",
        "## Validación dejando un proyecto fuera",
        "",
        "| Proyecto fuera | Coeficiente | Mediana lift | Azar empírico | Lift / azar "
        "| Intervalos (lift · prevalencia · muertes) |",
        "|---|---|---|---|---|---|",
    ]
    for h in ev["lopo"]:
        cells = "; ".join(f"t{x['interval']}: {x['lift']}× · {x['prevalence']} · {x['deaths']}"
                          for x in h["intervals"])
        lines.append(f"| {h['held_out']} | {h['coefficient']} | {h['median_lift']}× | "
                     f"{h['random_median_lift']}× | {h['lift_over_random']} | {cells} |")
    lines += ["", "## Procedencia", ""]
    for p in artifact["provenance"]["projects"]:
        lines.append(f"- {p}")
    for k, v in artifact["provenance"].items():
        if k != "projects":
            lines.append(f"- {k}: {v}")
    return "\n".join(lines) + "\n"
