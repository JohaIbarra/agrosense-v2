"""UC-AN5: riesgo de mortalidad de los arboles de un monitoreo (E8, ADR-014).

Para el monitoreo `number` (= instante de prediccion t), cada arbol vivo y
medido en t recibe un puntaje del scorer inyectado:
  - modelo general (`model_kind = "general"`): RIESGO RELATIVO, nunca una
    probabilidad absoluta (`score_kind = "relative_risk"`).
  - modelo propio del proyecto (`"project"`): probabilidad
    (`score_kind = "probability"`).
  - `risk_percentile`: rango del puntaje dentro de la ola (100 = mas riesgo).
  - `flagged`: entra en el presupuesto de alertas de E7 (`select_alerts`).
  - `stalled_last_interval`: regla de negocio observada, como en E7.

El resultado se guarda como snapshot por monitoreo (`mortality_assessments`)
con la version del modelo, la huella del artefacto general, la huella de los
datos (que tambien versiona al modelo propio, entrenado con ellos) y
`MORTALITY_RULES_VERSION`; se recalcula solo si cambia alguna.

El scorer se inyecta por parametro (ADR-003). `MortalityScorerPort` solo
describe su forma: application/ no importa ml/.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from typing import Protocol

from agrosense.application.dtos import MortalityAssessmentDTO
from agrosense.application.errors import AppError
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.mortality_rules import MORTALITY_RULES_VERSION
from agrosense.domain.rules import plot_key
from agrosense.domain.stall_rules import ALERT_BUDGET, select_alerts, stalled_previous_interval


class MortalityResultPort(Protocol):
    @property
    def kind(self) -> str: ...

    @property
    def scores(self) -> Mapping[str, float]: ...

    @property
    def decision(self) -> Mapping[str, object]: ...


class MortalityScorerPort(Protocol):
    # Solo lectura: el scorer concreto es el de ml/mortality_project.py
    @property
    def model_version(self) -> str: ...

    @property
    def artifact_sha256(self) -> str: ...

    @property
    def model_card(self) -> dict: ...

    def assess(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> MortalityResultPort: ...

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


def _percentiles(scores: Mapping[str, float]) -> dict[str, float]:
    """Rango (0-100) de cada puntaje en la ola; empates comparten el rango medio."""
    n = len(scores)
    if n == 1:
        return {tid: 100.0 for tid in scores}
    values = sorted(scores.values())
    out: dict[str, float] = {}
    for tid, s in scores.items():
        lower = sum(1 for v in values if v < s)
        equal = sum(1 for v in values if v == s)
        out[tid] = round(100.0 * (lower + (equal - 1) / 2) / (n - 1), 1)
    return out


def build_mortality_payload(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    number: int,
    result: MortalityResultPort,
    budget: float = ALERT_BUDGET,
) -> dict:
    """Arma el snapshot: puntaje del modelo + percentil + regla de negocio de dominio."""
    history: dict[str, dict[int, Observation]] = defaultdict(dict)
    for o in observations:
        if o.campaign <= number:
            history[o.tree_id][o.campaign] = o
    scores = result.scores
    flagged = select_alerts(scores, budget)
    percentile = _percentiles(scores) if scores else {}

    rows: list[dict] = []
    for tr in trees:
        if tr.tree_id not in scores:
            continue
        own = history[tr.tree_id]
        current = own.get(number)
        rows.append(
            {
                "tree_id": tr.tree_id,
                "species": tr.species,
                "locality": tr.locality,
                "plot": plot_key(tr),
                "height_m": current.height_m if current is not None else None,
                "score": float(scores[tr.tree_id]),
                "risk_percentile": percentile[tr.tree_id],
                "flagged": tr.tree_id in flagged,
                "stalled_last_interval": stalled_previous_interval(own, number),
            }
        )
    rows.sort(key=lambda r: (-r["score"], r["tree_id"]))

    summary = {
        "at_risk": len(rows),
        "flagged": sum(1 for r in rows if r["flagged"]),
        "stalled_last_interval": sum(1 for r in rows if r["stalled_last_interval"] is True),
        "without_history": sum(1 for r in rows if r["stalled_last_interval"] is None),
    }
    return {
        "model_kind": result.kind,
        "score_kind": "probability" if result.kind == "project" else "relative_risk",
        "decision": dict(result.decision),
        "alert_budget_pct": round(budget * 100, 1),
        "summary": summary,
        "trees": rows,
    }


def get_mortality_assessment(
    project_id: int,
    number: int,
    owner_id: str,
    project_repo,
    analysis_repo,
    assessment_repo,
    scorer_factory: Callable[[], MortalityScorerPort],
    *,
    only_flagged: bool = False,
) -> MortalityAssessmentDTO:
    """UC-AN5. Reutiliza el snapshot si modelo, artefacto, datos y reglas no cambiaron.

    `scorer_factory` se resuelve DESPUES de las comprobaciones de dueño y
    monitoreo (como E7): un modelo caido no debe delatar con un 503 que el
    proyecto existe a quien no es su dueño.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "MONITORING_NOT_FOUND")
        cualquier error que levante `scorer_factory` (p. ej. modelo caido),
        pero solo DESPUES de las dos comprobaciones anteriores.
    """
    _owned_project(project_repo, project_id, owner_id)
    monitoring = _monitoring(project_repo, project_id, number)
    scorer = scorer_factory()
    trees, observations = analysis_repo.load_dataset(project_id)
    input_hash = scorer.fingerprint(trees, observations, number)

    row = assessment_repo.get(monitoring.id)
    fresh = (
        row is not None
        and row.model_version == scorer.model_version
        and row.artifact_sha256 == scorer.artifact_sha256
        and row.input_hash == input_hash
        and row.rules_version == MORTALITY_RULES_VERSION
    )
    if not fresh:
        result = scorer.assess(trees, observations, number)
        payload = build_mortality_payload(trees, observations, number, result)
        row = assessment_repo.save(
            project_id,
            monitoring.id,
            result.kind,
            scorer.model_version,
            scorer.artifact_sha256,
            input_hash,
            MORTALITY_RULES_VERSION,
            payload,
        )

    payload = row.payload
    rows = [t for t in payload["trees"] if t["flagged"]] if only_flagged else list(payload["trees"])
    return MortalityAssessmentDTO(
        project_id=project_id,
        monitoring=number,
        model_kind=payload["model_kind"],
        score_kind=payload["score_kind"],
        model_version=row.model_version,
        artifact_sha256=row.artifact_sha256,
        input_hash=row.input_hash,
        computed_at=row.computed_at,
        decision=dict(payload["decision"]),
        model_card=dict(scorer.model_card),
        alert_budget_pct=float(payload["alert_budget_pct"]),
        summary=dict(payload["summary"]),
        trees=rows,
    )
