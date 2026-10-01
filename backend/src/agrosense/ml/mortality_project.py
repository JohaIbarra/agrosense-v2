"""Modelo PROPIO de mortalidad + gate automatico (E8, ADR-014 §2-3). Python puro.

En el monitoreo t, los intervalos CERRADOS del proyecto son u -> u+1 con
u+1 <= t (todo lo que usa ya esta medido en t: no hay fuga). El gate:

  1. Sin intervalos cerrados -> modelo general.
  2. Prueba = el ultimo intervalo cerrado; entrenamiento del gate = los
     anteriores. Con < MIN_TRAIN_EVENTS muertes de entrenamiento o
     < MIN_HOLDOUT_EVENTS de prueba -> general ("pocos_eventos").
  3. Se compara PR-AUC propio vs general en la prueba. Si gana el propio, se
     REENTRENA con todos los intervalos cerrados y se sirve; si no, general.

La decision y sus cifras viajan en el resultado (y en el snapshot): el
ingeniero ve que modelo se uso y por que. Con un solo intervalo de prueba la
eleccion es ruidosa; se documenta en ADR-014 en vez de ocultarse.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from agrosense.domain.entities import Observation, Tree
from agrosense.ml.logistic import fit_logistic_l2, predict_scores
from agrosense.ml.mortality_features import (
    PROJECT_CATEGORICAL,
    PROJECT_NUMERIC,
    build_mortality_wave,
    mortality_fingerprint,
)
from agrosense.ml.mortality_model import GeneralMortalityModel
from agrosense.ml.preprocessing import fit_preprocessor, transform
from agrosense.ml.stall_features import WaveRow

PROJECT_C = 0.5
MIN_TRAIN_EVENTS = 10
MIN_HOLDOUT_EVENTS = 5
MIN_LEVEL_ROWS = 10  # niveles categoricos mas raros se agrupan
OTHER = "(otras)"
PROJECT_MODEL_VERSION = "mortality-project-2026-09-30.1"


def average_precision(y: Sequence[int], scores: Sequence[float]) -> float:
    """PR-AUC como `sklearn.metrics.average_precision_score` (empates agrupados)."""
    pairs = sorted(zip(scores, y, strict=True), key=lambda p: -p[0])
    positives = sum(y)
    if positives == 0:
        return 0.0
    ap = tp = seen = 0.0
    prev_recall = 0.0
    i = 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            tp += pairs[j][1]
            seen += 1
            j += 1
        recall = tp / positives
        ap += (recall - prev_recall) * (tp / seen)
        prev_recall = recall
        i = j
    return ap


@dataclass(frozen=True)
class MortalityResult:
    kind: str  # "general" | "project"
    scores: dict[str, float]
    decision: dict


def _closed_waves(observations: Sequence[Observation], t: int) -> list[int]:
    waves = sorted({o.campaign for o in observations if o.campaign <= t})
    return [u for u in waves if u + 1 in waves]


def _group_rare(rows: list[dict], levels: dict[str, set[object]]) -> list[dict]:
    out = []
    for r in rows:
        r = dict(r)
        for c in PROJECT_CATEGORICAL:
            if r.get(c) is not None and r[c] not in levels[c]:
                r[c] = OTHER
        out.append(r)
    return out


class _ProjectModel:
    def __init__(self, train: list[WaveRow]):
        counts = {c: Counter(r.features.get(c) for r in train) for c in PROJECT_CATEGORICAL}
        self.levels: dict[str, set[object]] = {
            c: {v for v, n in counts[c].items() if v is not None and n >= MIN_LEVEL_ROWS}
            for c in PROJECT_CATEGORICAL
        }
        feats = _group_rare([dict(r.features) for r in train], self.levels)
        # En el primer intervalo nadie tiene historia (estanco_lag, dh_lag): esas
        # columnas no existen para este ajuste en vez de imputarse de la nada.
        numeric = tuple(c for c in PROJECT_NUMERIC if any(f.get(c) is not None for f in feats))
        self.params = fit_preprocessor(feats, numeric, PROJECT_CATEGORICAL)
        self.fit = fit_logistic_l2(transform(self.params, feats),
                                   [int(bool(r.label)) for r in train], C=PROJECT_C)

    def score(self, rows: Sequence[WaveRow]) -> list[float]:
        feats = _group_rare([dict(r.features) for r in rows], self.levels)
        return predict_scores(self.fit, transform(self.params, feats))


class MortalityScorer:
    """Scorer compuesto que la API inyecta en el caso de uso (puerto en application/)."""

    def __init__(self, general: GeneralMortalityModel):
        self.general = general

    @property
    def model_version(self) -> str:
        return f"{self.general.model_version}+{PROJECT_MODEL_VERSION}"

    @property
    def artifact_sha256(self) -> str:
        return self.general.artifact_sha256

    @property
    def model_card(self) -> dict:
        return dict(self.general.model_card)

    def fingerprint(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> str:
        return mortality_fingerprint(trees, observations, t)

    def _general_scores(self, rows: Sequence[WaveRow]) -> list[float]:
        return self.general.score_rows([r.features for r in rows])

    def assess(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> MortalityResult:
        obs = [o for o in observations if o.campaign <= t]  # nada del futuro
        current = build_mortality_wave(trees, obs, t, labeled=False)
        general = dict(zip((r.tree_id for r in current), self._general_scores(current),
                           strict=True))
        closed = _closed_waves(obs, t)
        if not closed:
            return MortalityResult("general", general, {"reason": "sin_intervalos_cerrados"})

        by_wave = {u: build_mortality_wave(trees, obs, u, labeled=True) for u in closed}
        holdout = by_wave[closed[-1]]
        gate_train = [r for u in closed[:-1] for r in by_wave[u]]
        train_events = sum(bool(r.label) for r in gate_train)
        holdout_events = sum(bool(r.label) for r in holdout)
        decision: dict = {
            "closed_intervals": len(closed),
            "train_events": train_events,
            "holdout_events": holdout_events,
            "holdout_interval": f"M{closed[-1]}→M{closed[-1] + 1}",
        }
        if (train_events < MIN_TRAIN_EVENTS or holdout_events < MIN_HOLDOUT_EVENTS
                or train_events == len(gate_train) or holdout_events == len(holdout)):
            return MortalityResult("general", general, {**decision, "reason": "pocos_eventos"})

        y = [int(bool(r.label)) for r in holdout]
        prevalence = holdout_events / len(holdout)
        own = average_precision(y, _ProjectModel(gate_train).score(holdout))
        gen = average_precision(y, self._general_scores(holdout))
        decision.update({
            "holdout_prevalence": round(prevalence, 4),
            "holdout_lift_project": round(own / prevalence, 3),
            "holdout_lift_general": round(gen / prevalence, 3),
        })
        if own <= gen:
            return MortalityResult("general", general, {**decision, "reason": "general_mejor"})

        final = _ProjectModel([r for u in closed for r in by_wave[u]])
        scores = dict(zip((r.tree_id for r in current), final.score(current), strict=True))
        return MortalityResult("project", scores, {**decision, "reason": "propio_mejor"})
