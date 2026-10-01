"""Preprocesamiento UNICO del modelo de estancamiento (ADR-013 §3).

Reproduce, en Python puro, el `ColumnTransformer` del protocolo:

    numericas:   SimpleImputer(median)        -> StandardScaler (ddof=0)
    categoricas: SimpleImputer(most_frequent) -> OneHotEncoder(handle_unknown="ignore")

Por que no el de scikit-learn: la API no debe cargar scikit-learn, y un
pickle del Pipeline seria una caja negra (AGENTS.md). Los parametros
ajustados son numeros y listas: viajan en el artefacto JSON. Un test de
paridad compara contra scikit-learn.

Fuga por preprocesamiento (Protocolo §4.4): `fit_preprocessor` se llama SOLO
con filas de entrenamiento; la inferencia solo llama `transform`.
"""
from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

PREPROCESSING_VERSION = "2026-09-27-e7.1"

Row = Mapping[str, float | str | None]


@dataclass(frozen=True)
class PreprocessorParams:
    numeric: tuple[str, ...]
    categorical: tuple[str, ...]
    medians: dict[str, float]
    means: dict[str, float]
    scales: dict[str, float]
    modes: dict[str, str]
    categories: dict[str, tuple[str, ...]]

    @property
    def feature_names(self) -> list[str]:
        names = list(self.numeric)
        for col in self.categorical:
            names.extend(f"{col}={value}" for value in self.categories[col])
        return names

    def to_json(self) -> dict:
        return {
            "numeric": list(self.numeric),
            "categorical": list(self.categorical),
            "medians": dict(self.medians),
            "means": dict(self.means),
            "scales": dict(self.scales),
            "modes": dict(self.modes),
            "categories": {k: list(v) for k, v in self.categories.items()},
        }

    @classmethod
    def from_json(cls, data: Mapping) -> PreprocessorParams:
        return cls(
            numeric=tuple(data["numeric"]),
            categorical=tuple(data["categorical"]),
            medians={k: float(v) for k, v in data["medians"].items()},
            means={k: float(v) for k, v in data["means"].items()},
            scales={k: float(v) for k, v in data["scales"].items()},
            modes={k: str(v) for k, v in data["modes"].items()},
            categories={k: tuple(str(c) for c in v) for k, v in data["categories"].items()},
        )


def fit_preprocessor(
    rows: Sequence[Row], numeric: Sequence[str], categorical: Sequence[str]
) -> PreprocessorParams:
    if not rows:
        raise ValueError("fit_preprocessor necesita al menos una fila de entrenamiento")
    medians: dict[str, float] = {}
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    for col in numeric:
        present = [float(cast("float", r[col])) for r in rows if r.get(col) is not None]
        if not present:
            raise ValueError(f"la columna numerica {col!r} no tiene ningun valor en entrenamiento")
        median = float(statistics.median(present))
        imputed = [float(cast("float", r[col])) if r.get(col) is not None else median for r in rows]
        std = statistics.pstdev(imputed)
        medians[col] = median
        means[col] = statistics.fmean(imputed)
        scales[col] = std if std > 0 else 1.0

    modes: dict[str, str] = {}
    categories: dict[str, tuple[str, ...]] = {}
    for col in categorical:
        present_cat = [str(r[col]) for r in rows if r.get(col) is not None]
        if not present_cat:
            raise ValueError(f"la columna categorica {col!r} no tiene valores en entrenamiento")
        counts = Counter(present_cat)
        top = max(counts.values())
        modes[col] = min(value for value, n in counts.items() if n == top)
        categories[col] = tuple(sorted(counts))

    return PreprocessorParams(
        numeric=tuple(numeric),
        categorical=tuple(categorical),
        medians=medians,
        means=means,
        scales=scales,
        modes=modes,
        categories=categories,
    )


def unknown_categories(params: PreprocessorParams, rows: Sequence[Row]) -> list[list[str]]:
    """Por fila, columnas categoricas con un valor que el entrenamiento no vio.

    Fix wave (item 1b): antes, un valor "no visto" solo se notaba como un
    one-hot en ceros (silencioso). Un valor ausente (`None`) se imputa con la
    moda y NO cuenta como desconocido: lo que se marca aqui es un valor que
    SI llego pero no coincide con ninguna categoria de entrenamiento.
    """
    out: list[list[str]] = []
    for r in rows:
        bad: list[str] = []
        for col in params.categorical:
            raw = r.get(col)
            if raw is not None and str(raw) not in params.categories[col]:
                bad.append(col)
        out.append(bad)
    return out


def transform(params: PreprocessorParams, rows: Sequence[Row]) -> list[list[float]]:
    out: list[list[float]] = []
    for r in rows:
        vector: list[float] = []
        for col in params.numeric:
            raw = r.get(col)
            value = params.medians[col] if raw is None else float(raw)
            vector.append((value - params.means[col]) / params.scales[col])
        for col in params.categorical:
            raw_cat = r.get(col)
            value_cat = params.modes[col] if raw_cat is None else str(raw_cat)
            vector.extend(1.0 if value_cat == c else 0.0 for c in params.categories[col])
        out.append(vector)
    return out
