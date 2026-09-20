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
