"""Constructores de entidades de dominio para los tests de E7."""
from __future__ import annotations

from agrosense.domain.entities import Observation, StatusSemantic, Tree


def obs(
    tree_id: str,
    campaign: int,
    height: float | None,
    *,
    crown: float | None = 0.30,
    alive: bool | None = True,
    phyto: str | None = "Bueno",
) -> Observation:
    return Observation(
        tree_id=tree_id,
        campaign=campaign,
        height_m=height,
        crown_diameter_m=crown,
        dap_cm=None,
        dap_status=StatusSemantic.SIN_CENSO,
        phytosanitary=phyto,
        alive=alive,
        colonization=None,
    )


def tree(
    tree_id: str,
    *,
    species: str = "Senna viarum",
    plot: str | None = "U1",
    locality: str | None = "Guayabal",
    unit: str | None = "Parcela",
) -> Tree:
    return Tree(
        tree_id=tree_id,
        species=species,
        locality=locality,
        sampling_unit_code=plot,
        monitoring_unit=unit,
    )


def synthetic_panel(n_plots: int = 10, per_plot: int = 12) -> tuple[list[Tree], list[Observation]]:
    """Panel de 4 monitoreos con senal: la especie "Lenta lenta" casi no crece.

    Determinista (sin azar) y con ambas clases en cada ola y en cada parcela,
    para que GroupKFold y el bootstrap por parcela tengan con que trabajar.
    """
    trees: list[Tree] = []
    observations: list[Observation] = []
    for p in range(n_plots):
        for i in range(per_plot):
            tid = f"P{p}_T{i}"
            slow = i % 3 == 0
            trees.append(
                tree(
                    tid,
                    species="Lenta lenta" if slow else "Rapida rapida",
                    plot=f"U{p}",
                    locality="Guayabal" if p % 2 else "Tres Jotas",
                )
            )
            h = 0.30 + 0.01 * i
            for c in range(1, 5):
                observations.append(obs(tid, c, round(h, 3), crown=round(0.20 + 0.1 * h, 3)))
                stalls = slow and (c + p) % 4 != 0
                h += 0.0 if stalls else 0.05 * (1 + (i + p + c) % 3)
    return trees, observations


def artifact_dict(params, coefficients, intercept, *, model_version: str = "stall-test-1") -> dict:
    """Artefacto minimo valido con el formato de ADR-013 (sin entrenar)."""
    from agrosense.ml.preprocessing import PREPROCESSING_VERSION
    from agrosense.ml.stall_features import FEATURES_VERSION
    from agrosense.ml.stall_model import ARTIFACT_FORMAT

    return {
        "format": ARTIFACT_FORMAT,
        "model_version": model_version,
        "features_version": FEATURES_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "created_at": "2026-09-27T00:00:00+00:00",
        "preprocessor": params.to_json(),
        "model": {
            "type": "logistic_regression",
            "feature_names": params.feature_names,
            "coefficients": list(coefficients),
            "intercept": intercept,
        },
        "training": {},
        "evaluation": {
            "temporal": {
                "pr_auc": 0.47,
                "pr_auc_ci": [0.36, 0.58],
                "roc_auc": 0.73,
                "prevalence_pct": 21.9,
                "recall_at_budget_pct": 45.0,
                "precision_at_budget_pct": 50.0,
            }
        },
        "provenance": {"dataset_file": "anexo1.xlsx", "dataset_sha256": "0" * 64},
    }
