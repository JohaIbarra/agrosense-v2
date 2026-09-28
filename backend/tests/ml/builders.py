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
