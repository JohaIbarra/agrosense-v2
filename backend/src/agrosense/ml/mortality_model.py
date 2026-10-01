"""Modelo GENERAL de mortalidad servible (E8, ADR-014): artefacto JSON + Python puro.

Una sola variable (`h_pct`) y una logistica: el puntaje ORDENA a los arboles
por riesgo relativo dentro de la ola. No se presenta como probabilidad
absoluta (plan D3): la prevalencia cambia de 5 % a 71 % entre proyectos.

El cargador rechaza un artefacto de otro formato o de otra version de
features: si alguien cambia la featurizacion sin reentrenar, la API responde
503 en vez de servir puntajes con otra semantica (mismo criterio que E7).
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from agrosense.ml.logistic import sigmoid
from agrosense.ml.mortality_features import GENERAL_FEATURES, MORTALITY_FEATURES_VERSION

MORTALITY_ARTIFACT_FORMAT = 1
MORTALITY_ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "mortality_general.json"


class MortalityModelError(ValueError):
    """Artefacto ausente, corrupto o de otra version."""


@dataclass(frozen=True)
class GeneralMortalityModel:
    model_version: str
    artifact_sha256: str
    feature_names: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    model_card: dict

    @classmethod
    def from_dict(cls, data: Mapping, sha256: str) -> GeneralMortalityModel:
        if data.get("format") != MORTALITY_ARTIFACT_FORMAT:
            raise MortalityModelError("Formato de artefacto de mortalidad desconocido.")
        if data.get("features_version") != MORTALITY_FEATURES_VERSION:
            raise MortalityModelError(
                "El artefacto de mortalidad es de otra version de features: reentrenar."
            )
        model = data["model"]
        names = tuple(model["feature_names"])
        if names != GENERAL_FEATURES:
            raise MortalityModelError(f"Variables inesperadas en el artefacto: {names}")
        evaluation = data.get("evaluation", {})
        card = {
            "model_version": data["model_version"],
            "trained_on": [p.get("name") for p in data.get("provenance", {}).get("projects", [])],
            "lopo": [
                {"held_out": h["held_out"], "median_lift": h["median_lift"]}
                for h in evaluation.get("lopo", [])
            ],
            "gate_passed": bool(data.get("gate", {}).get("passed")),
        }
        return cls(
            model_version=data["model_version"],
            artifact_sha256=sha256,
            feature_names=names,
            coefficients=tuple(float(c) for c in model["coefficients"]),
            intercept=float(model["intercept"]),
            model_card=card,
        )

    def score_rows(self, rows: Sequence[Mapping[str, float | str | None]]) -> list[float]:
        out = []
        for r in rows:
            z = self.intercept
            for name, coef in zip(self.feature_names, self.coefficients, strict=True):
                value = r.get(name)
                z += coef * float(value if isinstance(value, int | float) else 0.5)
            out.append(sigmoid(z))
        return out


@lru_cache(maxsize=1)
def load_general_mortality_model(
    path: Path = MORTALITY_ARTIFACT_PATH,
) -> GeneralMortalityModel:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise MortalityModelError("No hay artefacto del modelo general de mortalidad.") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise MortalityModelError("Artefacto de mortalidad corrupto.") from exc
    return GeneralMortalityModel.from_dict(data, hashlib.sha256(raw).hexdigest())
