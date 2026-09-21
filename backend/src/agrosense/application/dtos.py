"""DTOs de la capa de aplicacion (ADR-003).

Lo que los casos de uso devuelven y lo que cruza el boundary hacia los
adapters. Dataclasses de stdlib a proposito: `application/` no debe
depender de pydantic-como-contrato-HTTP ni de SQLAlchemy.

`adapters/api/schemas.py` sigue siendo la fuente de verdad del contrato
OpenAPI; la route traduce DTO -> schema. La direccion importa: el adapter
conoce el DTO, el DTO no conoce al adapter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from agrosense.domain.entities import Observation, Tree

# ── Datos de una campana ingerida ──────────────────────────────────────────


@dataclass
class CampaignData:
    """Campana de monitoreo ya traducida a entidades de dominio validadas.

    Es el tipo que cruza el boundary de ingesta: lo PRODUCE un adapter que
    implementa `ports.CampaignSource` (hoy Excel) y lo CONSUME el adapter de
    persistencia. Vive en application/ justamente para que ambos adapters
    dependan hacia adentro (antes vivia en adapters/ingester y obligaba a
    application/ a importar un adapter — violacion de ADR-003).

    `warnings` son avisos de dominio que NO bloquean la ingesta
    (docs/02-domain.md seccion 5); viajan hasta la respuesta del upload.
    """

    trees: list[Tree]
    observations: list[Observation]
    warnings: list[Exception] = field(default_factory=list)
    mapping_version: str = "unknown"


# ── Resultados de los casos de uso ─────────────────────────────────────────


@dataclass(frozen=True)
class ProjectSummary:
    """UC1/UC3: proyecto con su conteo de campanas."""

    id: int
    name: str
    locality: str | None
    description: str | None
    created_at: datetime
    campaigns_count: int


@dataclass(frozen=True)
class WarningDTO:
    """Aviso de ingesta accionable para el ingeniero de campo.

    `type` es el vocabulario estable del contrato: contraction | revival |
    census_gap (ver schemas.WarningItem).
    """

    type: str
    tree_id: str
    message: str


@dataclass(frozen=True)
class UploadResult:
    """UC2: resultado de ingerir una campana.

    `deaths` cuenta OBSERVACIONES con estado muerto, no arboles distintos
    (un arbol muerto en M2 aporta un registro por campana posterior). Ver
    docs/deuda-tecnica.md #F antes de usarlo como metrica de mortalidad.
    """

    valid: bool
    campaign_id: int | None
    trees: int
    observations: int
    deaths: int
    warnings: list[WarningDTO] = field(default_factory=list)


# ── Slice 5: analitica de los modelos mixtos ───────────────────────────────


@dataclass(frozen=True)
class RiskDTO:
    """Efecto de un nivel (especie o parcela) sobre UN desenlace.

    Todo lo que sale de aqui hacia la UI esta en escala de **odds ratio**;
    el log-odds viaja aparte (`ci95_log_odds`) solo para trazabilidad contra
    los CSV del modelo mixto. La regla de conversion es fija:
    `or = exp(efecto)`, `or_lo = exp(lo)`, `or_hi = exp(hi)`.

    `interpretation` es la frase que se muestra al ingeniero de campo; se
    arma en `application/` y no en la route porque decidir que significa un
    IC que cruza 1 es negocio, no presentacion.
    """

    odds_ratio: float | None
    or_ci95: tuple[float, float] | None
    ci95_log_odds: tuple[float, float] | None
    significant: bool | None
    interpretation: str


@dataclass(frozen=True)
class SpeciesAnalyticsDTO:
    species: str
    stall_risk: RiskDTO
    mortality_risk: RiskDTO
    n_observations: int | None
    n_trees: int | None
    gremio: str | None


@dataclass(frozen=True)
class PlotAnalyticsDTO:
    plot_code: str
    localidad: str | None
    stall_risk: RiskDTO
    mortality_risk: RiskDTO
    n_trees: int | None


@dataclass(frozen=True)
class VarianceComponentDTO:
    model: str
    grouping: str
    variance: float
    sd: float
    icc: float
    n_levels: int | None
    n_observations: int | None
    n_events: int | None


@dataclass(frozen=True)
class ModelVarianceDTO:
    """Descomposicion de UN modelo, con la lectura ya hecha.

    `species_to_plot_ratio` es el numero que decide la estrategia: 2.7 en
    estancamiento (elegir bien que plantar) frente a 1.1 en mortalidad
    (mejorar las condiciones del sitio).
    """

    model: str
    components: list[VarianceComponentDTO]
    species_to_plot_ratio: float | None
    interpretation: str
