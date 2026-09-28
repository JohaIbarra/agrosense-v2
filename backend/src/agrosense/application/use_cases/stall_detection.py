"""UC-AN4: detectar arboles estancados en un monitoreo (E7).

Para el monitoreo `number` (= instante de prediccion t), cada arbol vivo y
medido en t recibe:
  - `probability`: P(su altura no cambie hasta t+1 | sigue vivo), del modelo
    versionado (ADR-013), calculada por el `scorer` inyectado.
  - `flagged`: entra en el presupuesto de alertas (el 20 % con mayor
    probabilidad, Protocolo §6). Nunca un umbral de 0.5.
  - La regla de negocio OBSERVADA: `stalled_last_interval` (no crecio en
    (t-1, t]; es `estancó_intervalo_previo`), `stall_streak` y `persistent`.

El resultado se guarda como snapshot por monitoreo (`stall_assessments`,
criterio de ADR-008) con la version del modelo, la huella del artefacto y la
huella de los datos; se recalcula solo si cambia alguna de las tres.

El scorer se inyecta por parametro (ADR-003). `StallScorer` solo describe su
forma: application/ no importa ml/ (la flecha va hacia adentro).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Protocol

from agrosense.application.dtos import StallAssessmentDTO
from agrosense.application.errors import AppError
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.rules import plot_key
from agrosense.domain.stall_rules import (
    ALERT_BUDGET,
    PERSISTENT_STALL_INTERVALS,
    is_persistent_stall,
    select_alerts,
    stall_streak,
    stalled_previous_interval,
)


class StallScorer(Protocol):
    model_version: str
    artifact_sha256: str
    model_card: dict
    known_species: frozenset[str]

    def predict(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> dict[str, float]: ...

    def fingerprint(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> str: ...


def _owned_project(project_repo, project_id: int, owner_id: str):
    project = project_repo.get_owned(project_id, owner_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", f"El proyecto {project_id} no existe.")
    return project


def _monitoring(project_repo, project_id: int, number: int):
    monitoring = project_repo.get_monitoring(project_id, number)
    if monitoring is None:
        raise AppError(
            "MONITORING_NOT_FOUND",
            f"El proyecto no tiene el monitoreo M{number}. Cargue su Excel primero.",
        )
    return monitoring


def build_stall_payload(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    number: int,
    probabilities: Mapping[str, float],
    known_species: frozenset[str],
    budget: float = ALERT_BUDGET,
) -> dict:
    """Arma el snapshot: probabilidad del modelo + regla de negocio de dominio."""
    history: dict[str, dict[int, Observation]] = defaultdict(dict)
    for o in observations:
        if o.campaign <= number:
            history[o.tree_id][o.campaign] = o
    flagged = select_alerts(probabilities, budget)

    rows: list[dict] = []
    for tr in trees:
        if tr.tree_id not in probabilities:
            continue
        own = history[tr.tree_id]
        streak = stall_streak(own, number)
        rows.append(
            {
                "tree_id": tr.tree_id,
                "species": tr.species,
                "locality": tr.locality,
                "plot": plot_key(tr),
                "probability": float(probabilities[tr.tree_id]),
                "flagged": tr.tree_id in flagged,
                "stalled_last_interval": stalled_previous_interval(own, number),
                "stall_streak": streak,
                "persistent": is_persistent_stall(streak),
                "known_species": tr.species in known_species,
            }
        )
    rows.sort(key=lambda r: (-r["probability"], r["tree_id"]))

    summary = {
        "at_risk": len(rows),
        "flagged": sum(1 for r in rows if r["flagged"]),
        "stalled_last_interval": sum(1 for r in rows if r["stalled_last_interval"] is True),
        "persistent": sum(1 for r in rows if r["persistent"]),
        "without_history": sum(1 for r in rows if r["stalled_last_interval"] is None),
        "unknown_species": sum(1 for r in rows if not r["known_species"]),
    }
    return {
        "alert_budget_pct": round(budget * 100, 1),
        "persistent_min_intervals": PERSISTENT_STALL_INTERVALS,
        "summary": summary,
        "trees": rows,
    }


def get_stall_assessment(
    project_id: int,
    number: int,
    owner_id: str,
    project_repo,
    analysis_repo,
    assessment_repo,
    scorer: StallScorer,
    *,
    only_flagged: bool = False,
) -> StallAssessmentDTO:
    """UC-AN4. Reutiliza el snapshot si modelo, artefacto y datos no cambiaron.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "MONITORING_NOT_FOUND")
    """
    _owned_project(project_repo, project_id, owner_id)
    monitoring = _monitoring(project_repo, project_id, number)
    trees, observations = analysis_repo.load_dataset(project_id)
    input_hash = scorer.fingerprint(trees, observations, number)

    row = assessment_repo.get(monitoring.id)
    fresh = (
        row is not None
        and row.model_version == scorer.model_version
        and row.artifact_sha256 == scorer.artifact_sha256
        and row.input_hash == input_hash
    )
    if not fresh:
        payload = build_stall_payload(
            trees,
            observations,
            number,
            scorer.predict(trees, observations, number),
            scorer.known_species,
        )
        row = assessment_repo.save(
            project_id,
            monitoring.id,
            scorer.model_version,
            scorer.artifact_sha256,
            input_hash,
            payload,
        )

    payload = row.payload
    rows = [t for t in payload["trees"] if t["flagged"]] if only_flagged else list(payload["trees"])
    return StallAssessmentDTO(
        project_id=project_id,
        monitoring=number,
        model_version=row.model_version,
        artifact_sha256=row.artifact_sha256,
        input_hash=row.input_hash,
        computed_at=row.computed_at,
        model_card=dict(scorer.model_card),
        alert_budget_pct=float(payload["alert_budget_pct"]),
        persistent_min_intervals=int(payload["persistent_min_intervals"]),
        summary=dict(payload["summary"]),
        trees=rows,
    )
