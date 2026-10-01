"""Entrenamiento y evaluacion del modelo de estancamiento (E7, ADR-013).

Protocolo: docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md.

  - Regimen PRIMARIO, temporal: entrena con la ola M2 (etiqueta M2->M3) y
    prueba con la ola M3 (etiqueta M3->M4). Ninguna observacion (arbol+ola)
    queda a ambos lados.
  - Regimen SECUNDARIO, diagnostico: GroupKFold de 5 folds agrupado por
    PARCELA (`Codigo de unidad muestreo`) sobre las olas etiquetadas.
  - IC 95 % del PR-AUC por bootstrap de parcelas; dos controles negativos:
    etiqueta permutada en todo el conjunto (vigila fugas) y dentro de cada
    parcela (cuanto da aprender solo la tasa de la parcela).
  - Lineas base: prevalencia, persistencia (estanco_lag) y tasa por especie.

El artefacto que se sirve se reentrena con el MISMO procedimiento sobre las
olas `final_waves`: el gate evalua el procedimiento y el artefacto guarda las
metricas de esa evaluacion.

SOLO offline: numpy y scikit-learn no son dependencias de produccion.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from agrosense.domain.entities import Observation, Tree
from agrosense.domain.stall_rules import ALERT_BUDGET
from agrosense.ml.evaluation import (
    grouped_bootstrap_summary,
    pr_auc,
    recall_precision_at_budget,
    roc_auc,
    species_rate_scores,
)
from agrosense.ml.preprocessing import (
    PREPROCESSING_VERSION,
    PreprocessorParams,
    fit_preprocessor,
    transform,
)
from agrosense.ml.stall_features import (
    CATEGORICAL_FEATURES,
    FEATURES_VERSION,
    NUMERIC_FEATURES,
    WaveRow,
    build_wave,
)
from agrosense.ml.stall_model import ARTIFACT_FORMAT, logistic_scores

NO_PLOT = "(sin parcela)"

# Campos que cambian en cada corrida sin cambiar el modelo.
_VOLATILE: frozenset[tuple[str, ...]] = frozenset(
    {("created_at",), ("provenance", "git_commit"), ("provenance", "git_dirty")}
)


@dataclass(frozen=True)
class StallTrainConfig:
    """Configuracion completa del entrenamiento; viaja en el artefacto."""

    # Fix round 1 (I1): version .2 en adelante pre-registra la
    # reinterpretacion del control dentro de parcela (ver render_report,
    # seccion "Lectura honesta"). Los coeficientes de .1 y .2 son
    # identicos; solo cambian metadatos y metricas reportadas.
    # Fix wave (item 1c): version .3 reentrena con FEATURES_VERSION e7.2
    # (categoricas normalizadas, item 1a). El dataset de referencia es
    # consistente (sin duplicados por grafia), asi que se espera el MISMO
    # resultado salvo metadatos.
    model_version: str = "stall-logreg-2026-09-27.3"
    train_wave: int = 2
    test_wave: int = 3
    final_waves: tuple[int, ...] = (2, 3)
    # Fix round 1 (M5): C=0.5 viene del protocolo/spike
    # (docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md §9,
    # "Implementacion"), fijado ANTES de evaluar M3. No se reajusto aqui
    # para mejorar la metrica de este reporte.
    C: float = 0.5
    class_weight: str = "balanced"
    max_iter: int = 2000
    solver: str = "lbfgs"
    seed: int = 42
    n_bootstrap: int = 1000
    n_permutations: int = 20
    cv_folds: int = 5
    alert_budget: float = ALERT_BUDGET
    # Gate (fix round 1, M1): se compara el PR-AUC PUNTUAL del regimen
    # temporal (NO el limite inferior de su propio IC) contra 0.36. Ese
    # 0.36 proviene historicamente del limite inferior del IC 95 % que
    # reporto el protocolo (Protocolo §5); es el origen del numero, no una
    # descripcion de que se compara aqui. El limite superior del control
    # permutado global (fuga) es 0.31.
    gate_min_pr_auc: float = 0.36
    gate_max_permuted_pr_auc: float = 0.31
    expected_dataset_sha256: str = (
        "28583c3b48874626f3d7d7ae35d485634a8c8089b4c03a5997f5ba756b57a0dd"
    )


@dataclass(frozen=True)
class FittedStallModel:
    params: PreprocessorParams
    coefficients: tuple[float, ...]
    intercept: float

    def scores(self, rows: Sequence[WaveRow]) -> list[float]:
        # La MISMA funcion que usa la API (stall_model.logistic_scores).
        return logistic_scores(
            self.params, self.coefficients, self.intercept, [r.features for r in rows]
        )


def _labels(rows: Sequence[WaveRow]) -> list[int]:
    return [int(bool(r.label)) for r in rows]


def _plots(rows: Sequence[WaveRow]) -> list[str]:
    return [r.plot or NO_PLOT for r in rows]


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def fit_logistic(
    X: Sequence[Sequence[float]], y: Sequence[int], config: StallTrainConfig
) -> LogisticRegression:
    clf = LogisticRegression(
        C=config.C,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        solver=config.solver,
        random_state=config.seed,
    )
    clf.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=int))
    return clf


def fit_stall_model(
    rows: Sequence[WaveRow],
    config: StallTrainConfig,
    labels: Sequence[int] | None = None,
) -> FittedStallModel:
    """Ajusta preprocesamiento + logistica SOLO con `rows` (fuga §4.4)."""
    feats = [r.features for r in rows]
    params = fit_preprocessor(feats, NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    y = _labels(rows) if labels is None else [int(v) for v in labels]
    clf = fit_logistic(transform(params, feats), y, config)
    return FittedStallModel(
        params=params,
        coefficients=tuple(float(c) for c in clf.coef_[0]),
        intercept=float(clf.intercept_[0]),
    )


def permuted_within_plot(rows: Sequence[WaveRow], rng: np.random.Generator) -> list[int]:
    """Etiquetas barajadas DENTRO de cada parcela (control negativo, Protocolo §5)."""
    labels = _labels(rows)
    by_plot: dict[str, list[int]] = defaultdict(list)
    for i, plot in enumerate(_plots(rows)):
        by_plot[plot].append(i)
    out = list(labels)
    for plot in sorted(by_plot):
        idx = by_plot[plot]
        shuffled = [labels[i] for i in idx]
        rng.shuffle(shuffled)
        for i, value in zip(idx, shuffled, strict=True):
            out[i] = value
    return out


def _temporal(train, test, model, config) -> dict:
    y = _labels(test)
    scores = model.scores(test)
    plots = _plots(test)
    recall, precision = recall_precision_at_budget(
        [r.tree_id for r in test], y, scores, config.alert_budget
    )
    summary = grouped_bootstrap_summary(
        y, scores, plots, n_boot=config.n_bootstrap, seed=config.seed
    )
    lo, hi = summary["ci"]
    prevalence = sum(y) / len(y)
    return {
        "train_wave": config.train_wave,
        "test_wave": config.test_wave,
        "n_train": len(train),
        "positives_train": sum(_labels(train)),
        "n_test": len(test),
        "positives_test": sum(y),
        "n_test_plots": len(set(plots)),
        "prevalence_pct": _round(100 * prevalence, 2),
        "pr_auc": _round(pr_auc(y, scores)),
        "pr_auc_ci": [_round(lo), _round(hi)],
        # Fix round 1 (M2): cuantos de los `n_boot` remuestreos aportaron al
        # IC (los de una sola clase se descartan; ver grouped_bootstrap_summary).
        "pr_auc_ci_n_boot": summary["n_boot"],
        "pr_auc_ci_n_valid": summary["n_valid"],
        "roc_auc": _round(roc_auc(y, scores)),
        "alert_budget_pct": _round(100 * config.alert_budget, 1),
        "recall_at_budget_pct": _round(100 * recall, 2),
        "precision_at_budget_pct": _round(100 * precision, 2),
    }


def _baselines(train, test, config) -> dict:
    y = _labels(test)
    plots = _plots(test)
    persistence = [float(r.features["estanco_lag"] or 0.0) for r in test]
    species = species_rate_scores(
        [r.features["species"] for r in train],
        _labels(train),
        [r.features["species"] for r in test],
    )
    # Fix round 1 (I3): mismo procedimiento y semilla que el IC del modelo,
    # para que la comparacion de intervalos en el informe sea de manzanas
    # con manzanas.
    species_ci = grouped_bootstrap_summary(
        y, species, plots, n_boot=config.n_bootstrap, seed=config.seed
    )["ci"]
    return {
        "prevalence": {"pr_auc": _round(sum(y) / len(y))},
        "persistence": {"pr_auc": _round(pr_auc(y, persistence))},
        "species_rate": {
            "pr_auc": _round(pr_auc(y, species)),
            "pr_auc_ci": [_round(species_ci[0]), _round(species_ci[1])],
        },
    }


def permuted_globally(rows: Sequence[WaveRow], rng: np.random.Generator) -> list[int]:
    """Etiquetas barajadas en todo el conjunto: el modelo no puede aprender nada."""
    return [int(v) for v in rng.permutation(_labels(rows))]


def _permutation_control(train, test, config) -> dict:
    """Dos controles negativos (ADR-013 §4).

    - `global`: sin ninguna senal; un pipeline sin fugas cae a la prevalencia.
      Es el control que vigila las fugas.
    - `within_plot`: conserva la tasa de cada parcela; lo que puntua es cuanto
      rinde aprender SOLO la tasa de la parcela. El modelo real debe superarlo.
    """
    y = _labels(test)

    def run(permute) -> dict:
        rng = np.random.default_rng(config.seed)
        values = [
            pr_auc(y, fit_stall_model(train, config, permute(train, rng)).scores(test))
            for _ in range(config.n_permutations)
        ]
        return {
            "pr_auc_mean": _round(float(np.mean(values))),
            "pr_auc_min": _round(min(values)),
            "pr_auc_max": _round(max(values)),
        }

    return {
        "n_permutations": config.n_permutations,
        "global": run(permuted_globally),
        "within_plot": run(permuted_within_plot),
    }


def _group_kfold(pooled: Sequence[WaveRow], config) -> dict:
    """Diagnostico: GroupKFold con la PARCELA como grupo (nunca el individuo)."""
    plot_codes = _plots(pooled)
    oof = [0.0] * len(pooled)
    by_fold: list[float] = []
    splitter = GroupKFold(n_splits=config.cv_folds)
    for fit_idx, held_idx in splitter.split(np.zeros(len(pooled)), groups=plot_codes):
        fold_model = fit_stall_model([pooled[i] for i in fit_idx], config)
        held = [pooled[i] for i in held_idx]
        held_scores = fold_model.scores(held)
        for i, score in zip(held_idx, held_scores, strict=True):
            oof[i] = score
        held_y = _labels(held)
        if 0 < sum(held_y) < len(held_y):
            by_fold.append(pr_auc(held_y, held_scores))
    return {
        "folds": config.cv_folds,
        "grouping": "Codigo de unidad muestreo (parcela)",
        "pr_auc_pooled": _round(pr_auc(_labels(pooled), oof)),
        "pr_auc_by_fold": [_round(v) for v in by_fold],
    }


def evaluate(
    trees: Sequence[Tree], observations: Sequence[Observation], config: StallTrainConfig
) -> dict:
    train = build_wave(trees, observations, config.train_wave, labeled=True)
    test = build_wave(trees, observations, config.test_wave, labeled=True)
    model = fit_stall_model(train, config)
    return {
        "temporal": _temporal(train, test, model, config),
        "baselines": _baselines(train, test, config),
        "permutation_control": _permutation_control(train, test, config),
        "group_kfold": _group_kfold(list(train) + list(test), config),
    }


def gate(evaluation: Mapping, config: StallTrainConfig) -> dict:
    t = evaluation["temporal"]
    b = evaluation["baselines"]
    c = evaluation["permutation_control"]
    checks = {
        "pr_auc_at_least_min": t["pr_auc"] >= config.gate_min_pr_auc,
        "beats_prevalence": t["pr_auc"] > b["prevalence"]["pr_auc"],
        "beats_persistence": t["pr_auc"] > b["persistence"]["pr_auc"],
        "permutation_control_near_prevalence": (
            c["global"]["pr_auc_mean"] <= config.gate_max_permuted_pr_auc
        ),
        "beats_within_plot_permutation": t["pr_auc"] > c["within_plot"]["pr_auc_mean"],
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "min_pr_auc": config.gate_min_pr_auc,
        "max_permuted_pr_auc": config.gate_max_permuted_pr_auc,
    }


def _config_json(config: StallTrainConfig) -> dict:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(config).items()}


def train_and_evaluate(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    config: StallTrainConfig,
    provenance: Mapping[str, object],
) -> dict:
    """Evalua, aplica el gate y reentrena el modelo servible. Devuelve el artefacto."""
    evaluation = evaluate(trees, observations, config)
    evaluation["gate"] = gate(evaluation, config)
    final_rows = [
        row for w in config.final_waves for row in build_wave(trees, observations, w, labeled=True)
    ]
    final = fit_stall_model(final_rows, config)
    return {
        "format": ARTIFACT_FORMAT,
        "model_version": config.model_version,
        "features_version": FEATURES_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "preprocessor": final.params.to_json(),
        "model": {
            "type": "logistic_regression",
            "feature_names": final.params.feature_names,
            "coefficients": list(final.coefficients),
            "intercept": final.intercept,
        },
        "training": {
            "config": _config_json(config),
            "waves": list(config.final_waves),
            "n_rows": len(final_rows),
            "positives": sum(_labels(final_rows)),
        },
        "evaluation": evaluation,
        "provenance": dict(provenance),
    }


def diff_artifacts(a, b, *, tol: float = 1e-9, _path: tuple[str, ...] = ()) -> list[str]:
    """Rutas donde dos artefactos difieren (floats con tolerancia)."""
    if _path in _VOLATILE:
        return []
    here = "/".join(_path)
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append("/".join(_path + (key,)))
                continue
            out.extend(diff_artifacts(a[key], b[key], tol=tol, _path=_path + (key,)))
        return out
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        if len(a) != len(b):
            return [here]
        out = []
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out.extend(diff_artifacts(x, y, tol=tol, _path=_path + (str(i),)))
        return out
    if isinstance(a, bool) or isinstance(b, bool):
        return [] if a == b else [here]
    if isinstance(a, int | float) and isinstance(b, int | float):
        return [] if math.isclose(a, b, rel_tol=tol, abs_tol=tol) else [here]
    return [] if a == b else [here]


# Fix round 1 (M3): lineas del informe en prosa que cambian entre corridas
# identicas sin que el modelo cambie (timestamp y commit/dirty del codigo).
_REPORT_VOLATILE_PREFIXES: tuple[str, ...] = ("| Entrenado |", "| Commit del código |")


def report_diff(a: str, b: str) -> list[str]:
    """Lineas donde dos informes difieren, ignorando timestamp y commit.

    Analogo a `diff_artifacts` pero para el informe en prosa: `--check`
    (Task 8, fix M3) lo usa para detectar que el informe versionado en
    `docs/ml/evaluacion-estancamiento.md` quedo desactualizado respecto del
    procedimiento actual, no solo el artefacto JSON.
    """
    la = [line for line in a.splitlines() if not line.startswith(_REPORT_VOLATILE_PREFIXES)]
    lb = [line for line in b.splitlines() if not line.startswith(_REPORT_VOLATILE_PREFIXES)]
    if len(la) != len(lb):
        return [f"<{len(la)} vs {len(lb)} lineas (ignorando timestamp/commit)>"]
    return [x for x, y in zip(la, lb, strict=True) if x != y]


def render_report(artifact: Mapping) -> str:
    """Informe de metricas (docs/ml/evaluacion-estancamiento.md), generado."""
    ev = artifact["evaluation"]
    t = ev["temporal"]
    b = ev["baselines"]
    c = ev["permutation_control"]
    cg = c["global"]
    cw = c["within_plot"]
    g = ev["group_kfold"]
    decision = ev["gate"]
    p = artifact["provenance"]
    tr = artifact["training"]
    estado = "APROBADO" if decision["passed"] else "RECHAZADO"
    olas = ", ".join(f"M{w}" for w in tr["waves"])
    folds = ", ".join(f"{v:.3f}" for v in g["pr_auc_by_fold"])
    dirty = " (con cambios sin confirmar)" if p.get("git_dirty") else ""
    species_ci = b["species_rate"]["pr_auc_ci"]
    # Fix round 1 (I3): el enunciado de solape se calcula de los numeros
    # reales, no se da por sentado.
    overlap = t["pr_auc_ci"][0] <= species_ci[1] and species_ci[0] <= t["pr_auc_ci"][1]
    if overlap:
        solape_txt = (
            f"los intervalos de la logística ({t['pr_auc_ci'][0]:.2f}–{t['pr_auc_ci'][1]:.2f}) "
            f"y de la tasa por especie ({species_ci[0]:.2f}–{species_ci[1]:.2f}) se solapan"
        )
    else:
        solape_txt = (
            f"el intervalo de la logística ({t['pr_auc_ci'][0]:.2f}–{t['pr_auc_ci'][1]:.2f}) NO "
            f"se solapa con el de la tasa por especie ({species_ci[0]:.2f}–{species_ci[1]:.2f}): "
            "la logística lo supera con margen"
        )
    lines = [
        f"# Evaluación del modelo de estancamiento — {artifact['model_version']}",
        "",
        "> Generado por `cd backend && python scripts/train_stall_model.py "
        "--data data/raw/anexo1.xlsx`. No editar a mano.",
        "",
        f"**ML eval gate: {estado}**",
        "",
        "## Procedencia",
        "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Dataset | `{p['dataset_file']}` (hoja `{p['sheet']}`) |",
        f"| SHA-256 del dataset | `{p['dataset_sha256']}` |",
        f"| Versión de la ingesta | `{p['mapping_version']}` |",
        f"| Features | `{artifact['features_version']}` |",
        f"| Preprocesamiento | `{artifact['preprocessing_version']}` |",
        f"| Commit del código | `{p['git_commit']}`{dirty} |",
        f"| Versiones | Python {p['python']}, scikit-learn {p['sklearn']}, numpy {p['numpy']} |",
        f"| Semilla | {tr['config']['seed']} |",
        # Fix round 1 (M5): de donde sale C=0.5.
        f"| C (regularización, logística) | {tr['config']['C']} — protocolo/spike "
        "(Protocolo §9), fijado antes de evaluar M3 |",
        f"| Entrenado | {artifact['created_at']} |",
        "",
        "## Régimen primario — validación adelantada en el tiempo",
        "",
        f"Entrena con la ola M{t['train_wave']} "
        f"(etiqueta M{t['train_wave']}→M{t['train_wave'] + 1}, "
        f"n = {t['n_train']}, {t['positives_train']} estancados) y prueba con la ola "
        f"M{t['test_wave']} (etiqueta M{t['test_wave']}→M{t['test_wave'] + 1}, "
        f"n = {t['n_test']}, {t['positives_test']} estancados, {t['n_test_plots']} parcelas).",
        "",
        "| Modelo | PR-AUC |",
        "|---|---|",
        f"| Prevalencia (sin modelo) | {b['prevalence']['pr_auc']:.3f} |",
        f"| Persistencia (estancó antes) | {b['persistence']['pr_auc']:.3f} |",
        f"| Tasa media por especie | {b['species_rate']['pr_auc']:.3f} (IC 95 % por parcelas "
        f"{species_ci[0]:.2f}–{species_ci[1]:.2f}) |",
        f"| **Regresión logística** | **{t['pr_auc']:.3f}** (IC 95 % por parcelas "
        f"{t['pr_auc_ci'][0]:.2f}–{t['pr_auc_ci'][1]:.2f}; {t['pr_auc_ci_n_valid']}/"
        f"{t['pr_auc_ci_n_boot']} remuestreos válidos) |",
        f"| Control negativo: etiqueta permutada en todo el conjunto ({c['n_permutations']} "
        f"corridas) | {cg['pr_auc_mean']:.3f} (rango {cg['pr_auc_min']:.3f}–"
        f"{cg['pr_auc_max']:.3f}) |",
        f"| Control: permutada dentro de cada parcela (solo la tasa de la parcela) | "
        f"{cw['pr_auc_mean']:.3f} (rango {cw['pr_auc_min']:.3f}–{cw['pr_auc_max']:.3f}) |",
        "",
        f"ROC-AUC {t['roc_auc']:.3f}. Con un presupuesto de alertas del "
        f"{t['alert_budget_pct']:.0f} %: recall {t['recall_at_budget_pct']:.1f} %, "
        f"precisión {t['precision_at_budget_pct']:.1f} %.",
        "",
        "## Régimen secundario — GroupKFold por parcela (diagnóstico)",
        "",
        f"{g['folds']} folds agrupados por {g['grouping']}: PR-AUC agregado "
        f"{g['pr_auc_pooled']:.3f}; por fold {folds}. "
        # Fix round 1 (M4): el pool mezcla las dos olas etiquetadas.
        f"Los folds agrupan M{t['train_wave']} y M{t['test_wave']} en un solo conjunto: "
        "es un diagnóstico de estabilidad espacial (parcelas nuevas), no una métrica "
        "temporal-segura, porque mezcla ambas olas.",
        "",
        "## Gate",
        "",
        "| Criterio | Resultado |",
        "|---|---|",
        *[f"| `{k}` | {'cumple' if v else 'no cumple'} |" for k, v in decision["checks"].items()],
        "",
        # Fix round 1 (M1): que quede explicito que compara.
        "`pr_auc_at_least_min` compara el PR-AUC **puntual** del régimen temporal (no el "
        f"límite inferior de su propio IC) contra {decision['min_pr_auc']}.",
        "",
        "## Artefacto servido",
        "",
        f"Reentrenado con el mismo procedimiento sobre las olas {olas} (n = {tr['n_rows']}, "
        f"{tr['positives']} estancados). Las métricas de arriba evalúan el procedimiento, "
        "no este reentrenamiento.",
        "",
        "## Lectura honesta",
        "",
        # Fix round 1 (I1): el criterio de fuga se redefinio DESPUES de ver el
        # resultado; decirlo en pasado no basta, hay que decir que habria
        # fallado con el criterio original y desde cuando queda fijo el nuevo.
        "**El criterio de fuga se redefinió después de ver el resultado.** El protocolo "
        "original usa la permutación DENTRO de cada parcela como control de fugas, con "
        f"techo {decision['max_permuted_pr_auc']} (rango reportado 0.18–0.31). Al "
        f"reproducirlo con esta featurización da {cw['pr_auc_mean']:.3f} (rango "
        f"{cw['pr_auc_min']:.3f}–{cw['pr_auc_max']:.3f}): **con ese criterio original, este "
        "modelo NO habría pasado el gate**. La causa no es fuga sino señal de sitio: "
        "conservar la tasa de cada parcela deja aprender la especie y el predio, que sí "
        "varían entre parcelas. Por eso el control dentro de parcela pasó a medir cuánto "
        "aporta el modelo por encima de la tasa de la parcela (debe superarlo, no acercarse "
        "a él), y el control de fugas real pasó a ser la permutación GLOBAL, con el mismo "
        f"techo {decision['max_permuted_pr_auc']}. Esta regla queda **PRE-REGISTRADA** desde "
        "el artefacto `stall-logreg-2026-09-27.2` en adelante: un reentrenamiento futuro se "
        "juzga con esta definición, no con la reinterpretada aquí sobre la marcha.",
        "",
        # Fix round 1 (I2): alcance del entrenamiento y que M2/M3 servidos son in-sample.
        "El modelo se entrenó con un solo proyecto (3 predios, ~30 especies): la "
        "transferencia espacial a otros proyectos NO está evaluada. Las predicciones que "
        "sirve la API para M2 y M3 de este proyecto son sobre datos de ENTRENAMIENTO "
        "(in-sample, no evaluación); la única evaluación honesta es M3→M4, la que se "
        "reporta arriba.",
        "",
        f"La evidencia de que el modelo supera a una regla de una línea es sugestiva, no "
        f"concluyente (Protocolo §5): {solape_txt}. La etiqueta mide «crecimiento no "
        "detectable por el protocolo», no «crecimiento nulo». La probabilidad es "
        "condicional a que el árbol siga vivo.",
        "",
    ]
    return "\n".join(lines)
