"""Modelo de estancamiento servible (E7, ADR-013 §5).

Carga el artefacto JSON versionado y puntua arboles en Python puro: la API
no importa scikit-learn. `logistic_scores` es la UNICA implementacion de la
prediccion: la usa la inferencia y tambien la evaluacion del entrenamiento,
asi que las metricas del informe salen del mismo codigo que sirve la API.

El cargador falla (`StallModelError`) si el artefacto no existe, no es JSON,
esta incompleto o se entreno con otra version de features o de
preprocesamiento: nunca se sirve una prediccion con semantica distinta a la
evaluada.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agrosense.domain.entities import Observation, Tree
from agrosense.ml.preprocessing import PREPROCESSING_VERSION, PreprocessorParams, transform
from agrosense.ml.stall_features import (
    FEATURES_VERSION,
    FeatureValue,
    build_wave,
)
from agrosense.ml.stall_features import (
    fingerprint as data_fingerprint,
)

ARTIFACT_FORMAT = 1
ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "stall_logreg.json"


class StallModelError(ValueError):
    """El artefacto del modelo falta o no es valido para este codigo."""


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def logistic_scores(
    params: PreprocessorParams,
    coefficients: Sequence[float],
    intercept: float,
    rows: Sequence[Mapping[str, FeatureValue]],
) -> list[float]:
    matrix = transform(params, rows)
    return [
        sigmoid(intercept + sum(c * x for c, x in zip(coefficients, vector, strict=True)))
        for vector in matrix
    ]


@dataclass(frozen=True)
class StallModel:
    model_version: str
    artifact_sha256: str
    params: PreprocessorParams
    coefficients: tuple[float, ...]
    intercept: float
    model_card: dict

    @property
    def known_species(self) -> frozenset[str]:
        return frozenset(self.params.categories.get("species", ()))

    def predict_rows(self, rows: Sequence[Mapping[str, FeatureValue]]) -> list[float]:
        return logistic_scores(self.params, self.coefficients, self.intercept, rows)

    def predict(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> dict[str, float]:
        """P(no crecer hasta t+1 | sigue vivo) de cada arbol vivo y medido en t."""
        rows = build_wave(trees, observations, t, labeled=False)
        scores = self.predict_rows([r.features for r in rows])
        return {r.tree_id: s for r, s in zip(rows, scores, strict=True)}

    def fingerprint(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> str:
        return data_fingerprint(trees, observations, t)


def _model_card(data: Mapping, sha: str) -> dict:
    temporal = data["evaluation"]["temporal"]
    provenance = data["provenance"]
    return {
        "model_version": str(data["model_version"]),
        "artifact_sha256": sha,
        "dataset_sha256": str(provenance["dataset_sha256"]),
        "trained_on": str(provenance["dataset_file"]),
        "pr_auc": float(temporal["pr_auc"]),
        "pr_auc_ci_low": float(temporal["pr_auc_ci"][0]),
        "pr_auc_ci_high": float(temporal["pr_auc_ci"][1]),
        "roc_auc": float(temporal["roc_auc"]),
        "prevalence_pct": float(temporal["prevalence_pct"]),
        "recall_at_budget_pct": float(temporal["recall_at_budget_pct"]),
        "precision_at_budget_pct": float(temporal["precision_at_budget_pct"]),
    }


def load_stall_model(path: Path = ARTIFACT_PATH) -> StallModel:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        name = Path(path).name
        raise StallModelError(f"no se encontro el artefacto del modelo ({name})") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise StallModelError("el artefacto del modelo no es JSON valido") from exc
    if not isinstance(data, dict) or data.get("format") != ARTIFACT_FORMAT:
        raise StallModelError("formato de artefacto desconocido")
    if data.get("features_version") != FEATURES_VERSION:
        raise StallModelError("el artefacto se entreno con otras features: reentrene el modelo")
    if data.get("preprocessing_version") != PREPROCESSING_VERSION:
        raise StallModelError("el artefacto se entreno con otro preprocesamiento: reentrene")
    sha = hashlib.sha256(raw).hexdigest()
    try:
        params = PreprocessorParams.from_json(data["preprocessor"])
        coefficients = tuple(float(c) for c in data["model"]["coefficients"])
        intercept = float(data["model"]["intercept"])
        card = _model_card(data, sha)
        version = str(data["model_version"])
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise StallModelError("el artefacto del modelo esta incompleto") from exc
    if len(coefficients) != len(params.feature_names):
        raise StallModelError("los coeficientes no corresponden a las features del artefacto")
    return StallModel(
        model_version=version,
        artifact_sha256=sha,
        params=params,
        coefficients=coefficients,
        intercept=intercept,
        model_card=card,
    )
