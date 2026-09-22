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
from datetime import date, datetime

from agrosense.domain.entities import Observation, Tree

# ── Datos de una campana ingerida ──────────────────────────────────────────


@dataclass(frozen=True)
class FileMetadata:
    """Datos que describen el ARCHIVO, no a un arbol (E0).

    En el formato de campo vienen repetidos en cada fila, pero son constantes:
    `Proyecto`, `Evento`, `Responsables` y `Anotador` tienen un unico valor en
    las 856 filas del dataset de referencia (verificado en E0, tarea T1).
    """

    project_label: str | None = None
    event: str | None = None
    field_crew: str | None = None
    recorder: str | None = None


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
    file_metadata: FileMetadata = field(default_factory=FileMetadata)

    @property
    def monitorings(self) -> list[int]:
        """Numeros de monitoreo que el archivo trae CON datos, ordenados.

        Un archivo acumulado trae varios (M1-M4); uno de un solo monitoreo
        trae uno (decision D1). Se deriva de las observaciones y no de las
        columnas: un monitoreo cuyas columnas existen pero estan todas en
        blanco no cuenta como traido.
        """
        return sorted({o.campaign for o in self.observations})


# ── Resultados de los casos de uso ─────────────────────────────────────────


@dataclass(frozen=True)
class ProjectSummary:
    """UC1/UC3: proyecto con su conteo de campanas (E1: con todos sus campos)."""

    id: int
    name: str
    locality: str | None
    description: str | None
    created_at: datetime
    campaigns_count: int
    # E1 (decision D7). Con valores por defecto para no romper a quien ya
    # construye el DTO con los campos del slice 2.
    project_code: str | None = None
    contract_code: str | None = None
    objective: str | None = None
    executing_org: str | None = None
    contracting_entity: str | None = None
    department: str | None = None
    municipality: str | None = None
    intervention_type: str | None = None
    area_ha: float | None = None
    planted_individuals: int | None = None
    planting_density: float | None = None
    establishment_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    legal_framework: str | None = None
    environmental_authority: str | None = None
    status: str = "activo"
    coordinate_srid: int = 9377


@dataclass(frozen=True)
class EngineerDTO:
    """Perfil del ingeniero autenticado (E1)."""

    id: str
    email: str | None
    full_name: str | None
    professional_license: str | None
    organization: str | None


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
    # Monitoreos que traia el archivo (E0, decision D1)
    monitorings: list[int] = field(default_factory=list)
    # Monitoreos cuyo analisis exploratorio quedo recalculado tras la carga (E3)
    analyzed: list[int] = field(default_factory=list)


# ── E2/E3: monitoreos y su analisis exploratorio ───────────────────────────


@dataclass(frozen=True)
class MonitoringDTO:
    number: int
    monitoring_date: date | None
    field_crew: str | None
    recorder: str | None
    notes: str | None


@dataclass(frozen=True)
class AnalysisDTO:
    """Snapshot del analisis exploratorio de un monitoreo (ADR-008).

    `payload` es el resultado del motor tal cual (secciones con tablas tipadas
    y graficas). La pagina y el reporte .xlsx se construyen de el: nadie mas
    calcula.
    """

    project_id: int
    monitoring: int
    monitoring_date: date | None
    analysis_version: str
    input_hash: str
    computed_at: datetime
    payload: dict


@dataclass(frozen=True)
class ReportData:
    """Todo lo que necesita el reporte .xlsx: el analisis y sus datos crudos."""

    project_name: str
    project_code: str | None
    analysis: AnalysisDTO
    trees: list[Tree]
    observations: list[Observation]
    monitoring_dates: dict[int, date]


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


# ── E6: mapa del predio ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProjectMapDTO:
    """El mapa de un proyecto: el payload que arma `adapters/geo`, sin tocar.

    La capa de aplicacion no inspecciona su contenido; solo lo acompana del
    proyecto al que pertenece. La forma la fija el contrato de la API.
    """

    project_id: int
    payload: dict


@dataclass(frozen=True)
class ImageryLayerDTO:
    """Una capa de imagen del proyecto (E6b): donde esta, no la imagen."""

    id: int
    name: str
    tile_template: str
    attribution: str | None
    min_zoom: int | None
    max_zoom: int | None
    opacity: float


# ── E10a: indices espectrales por predio ───────────────────────────────────


@dataclass(frozen=True)
class SatelliteScene:
    """Una imagen satelital disponible, antes de calcular nada."""

    scene_id: str
    acquired_at: date
    cloud_cover: float | None


@dataclass(frozen=True)
class SceneStatistics:
    """Estadisticos de un indice dentro de un poligono, en una escena."""

    mean: float
    median: float | None
    minimum: float | None
    maximum: float | None
    std: float | None
    valid_pixels: int


@dataclass(frozen=True)
class IndexReading:
    """Una lectura publicada: el indice de un predio en una fecha."""

    property_name: str
    index: str
    scene_id: str
    acquired_at: date
    cloud_cover: float | None
    mean: float
    median: float | None
    minimum: float | None
    maximum: float | None
    std: float | None
    valid_pixels: int
    reliable: bool
    reading: str | None
    source: str


@dataclass(frozen=True)
class ProjectIndexDTO:
    """La serie de un indice para todo el proyecto, lista para la pantalla."""

    project_id: int
    index: str
    properties: list[str]
    readings: list[IndexReading]
    last_refreshed_at: datetime | None

