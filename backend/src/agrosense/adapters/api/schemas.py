"""Contrato del slice 2 (fuente de verdad — AGENTS.md).

FastAPI expone esto como OpenAPI; el frontend genera sus tipos de aqui.
Los tipos de error/warning documentan los rulings del dominio (slice 1).
"""
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# Semantica explicita en el OpenAPI: el frontend y el modelo de mortalidad
# consumen este numero y no significa lo que el nombre sugiere.
_DEATHS_DESC = (
    "Registros de observación con estado muerto en la campaña. NO es el número de "
    "árboles muertos distintos: un árbol que muere en M2 aporta un registro por cada "
    "campaña posterior. Para mortalidad por árbol ver docs/deuda-tecnica.md #F."
)

# ── UC1: proyectos ─────────────────────────────────────────────


class _ProjectFields(BaseModel):
    """Campos del proyecto (E1, decision D7).

    Aqui se valida forma y longitud; los vocabularios y la coherencia de
    fechas y cantidades son reglas de negocio y las valida el dominio
    (`domain/project.py`) — un valor fuera de vocabulario sale como 422
    INVALID_PROJECT con el mensaje del dominio.
    """

    locality: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    contract_code: str | None = Field(default=None, max_length=100)
    objective: str | None = Field(default=None, max_length=4000)
    executing_org: str | None = Field(default=None, max_length=200)
    contracting_entity: str | None = Field(default=None, max_length=200)
    department: str | None = Field(default=None, max_length=100)
    municipality: str | None = Field(default=None, max_length=100)
    intervention_type: str | None = Field(
        default=None, max_length=50,
        description="rehabilitacion | restauracion_activa | restauracion_pasiva | "
        "enriquecimiento | reforestacion | agroforestal | otro",
    )
    area_ha: float | None = Field(default=None, description="Area intervenida, en hectareas.")
    planted_individuals: int | None = None
    planting_density: float | None = Field(default=None, description="Individuos por hectarea.")
    establishment_date: date | None = Field(default=None, description="Fecha de siembra.")
    start_date: date | None = None
    end_date: date | None = None
    legal_framework: str | None = Field(
        default=None, max_length=50,
        description="compensacion_ambiental | inversion_1_por_ciento | plan_de_manejo | "
        "voluntario | otro",
    )
    environmental_authority: str | None = Field(default=None, max_length=200)
    coordinate_srid: int | None = Field(
        default=None,
        description="Sistema de coordenadas de los archivos del proyecto. Por defecto 9377 "
        "(MAGNA-SIRGAS / Origen Nacional).",
    )


class ProjectCreate(_ProjectFields):
    name: str = Field(min_length=1, max_length=200)


class ProjectUpdate(_ProjectFields):
    """PATCH: solo se modifican los campos presentes en el cuerpo."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, max_length=20, description="activo | cerrado")


class ProjectResponse(BaseModel):
    id: int
    name: str
    locality: str | None
    description: str | None
    created_at: datetime
    campaigns_count: int
    # E1
    project_code: str | None = Field(
        default=None, description="Identificador interno asignado por AgroSense (AGS-año-n)."
    )
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


# ── E1: perfil del ingeniero ───────────────────────────────────


class EngineerResponse(BaseModel):
    id: str
    email: str | None
    full_name: str | None
    professional_license: str | None = Field(
        description="Matricula profesional: firma los informes tecnicos."
    )
    organization: str | None


class CatalogsResponse(BaseModel):
    """Vocabularios del dominio que el frontend ofrece en sus formularios."""

    intervention_types: list[str]
    legal_frameworks: list[str]
    project_statuses: list[str]
    default_srid: int


class EngineerUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    professional_license: str | None = Field(default=None, max_length=100)
    organization: str | None = Field(default=None, max_length=200)


# ── UC2: upload de campaña ─────────────────────────────────────


class WarningItem(BaseModel):
    type: str = Field(
        pattern=(
            "^(contraction|revival|census_gap|event_mismatch|project_mismatch|unknown_columns)$"
        ),
        description=(
            "contraction | revival | census_gap: avisos de un arbol. "
            "event_mismatch | project_mismatch | unknown_columns: avisos del ARCHIVO "
            "(E0), con "
            "tree_id vacio."
        ),
    )
    tree_id: str
    message: str


class ErrorItem(BaseModel):
    code: str
    message: str
    tree_id: str | None = None
    campaign: int | None = None


class UploadResultResponse(BaseModel):
    valid: bool
    campaign_id: int | None
    trees: int
    observations: int
    deaths: int = Field(description=_DEATHS_DESC)
    warnings: list[WarningItem]
    errors: list[ErrorItem]
    monitorings: list[int] = Field(
        default_factory=list,
        description="Numeros de monitoreo que traia el archivo (uno o varios, E0).",
    )
    analyzed: list[int] = Field(
        default_factory=list,
        description=(
            "Monitoreos cuyo analisis exploratorio quedo recalculado tras la carga (E3). "
            "Vacio si el analisis no pudo calcularse ahora: se calculara al consultarlo."
        ),
    )


class CampaignResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    mapping_version: str
    ingested_at: datetime
    trees: int
    observations: int
    deaths: int = Field(description=_DEATHS_DESC)


class TreeRowResponse(BaseModel):
    id: int
    tree_id: str
    species: str
    family: str | None
    common_name: str | None
    guild: str | None
    locality: str | None
    elevation_m: float | None
    # E0 — atributos de la parcela del arbol (campos nuevos, aditivos)
    plot_id: str | None = None
    sampling_unit_code: str | None = Field(
        default=None, description="`Codigo de unidad muestreo` de la parcela."
    )
    monitoring_unit: str | None = None
    floristic_design: str | None = None
    associated_cover: str | None = None
    establishment_cover: str | None = None


class MonitoringResponse(BaseModel):
    """Un monitoreo del proyecto (E0)."""

    number: int = Field(description="Numero de monitoreo: 1 = M1, 2 = M2…")
    monitoring_date: date | None = Field(
        default=None,
        description="Fecha del monitoreo. Null hasta que el ingeniero la registre: "
        "el formato de campo no la trae.",
    )
    field_crew: str | None = None
    recorder: str | None = None
    notes: str | None = None
    observations: int = Field(description="Observaciones registradas en este monitoreo.")


class MonitoringUpdate(BaseModel):
    """PATCH de un monitoreo (E2): solo los campos presentes se cambian.

    Reglas del dominio (→ 422 INVALID_MONITORING_DATE): la fecha no puede estar
    en el futuro, y debe quedar despues de la del monitoreo anterior y antes
    de la del siguiente.
    """

    monitoring_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


# ── E3: analisis exploratorio por monitoreo ────────────────────────────────


class AnalysisColumn(BaseModel):
    key: str
    label: str
    kind: Literal["text", "int", "decimal", "percent"] = Field(
        description="Tipo del valor. `percent` viene en escala 0–100."
    )
    decimals: int | None = Field(default=None, description="Decimales con que se muestra.")
    group: str | None = Field(
        default=None,
        description="Encabezado agrupador (p. ej. el diseno florístico sobre «M3 | M4»).",
    )


class AnalysisTable(BaseModel):
    id: str
    title: str
    property: str | None = Field(default=None, description="Predio de la tabla; null = proyecto.")
    columns: list[AnalysisColumn]
    rows: list[dict[str, Any]] = Field(
        description=(
            "Filas: {key de columna: valor}. `_flags` puede traer `low_sample` cuando el "
            "porcentaje sale de menos arboles que el minimo del dominio."
        )
    )
    footer: list[dict[str, Any]] = Field(description="Filas de totales o medias generales.")
    notes: list[str]


class AnalysisChart(BaseModel):
    id: str
    title: str
    table: str = Field(description="Id de la tabla de la que salen los datos.")
    kind: Literal["bar"]
    x: str = Field(description="Key de la columna de categorias.")
    series: list[str] = Field(description="Keys de las columnas a graficar.")
    stacked: bool
    percent: bool
    y_label: str
    property: str | None = None


class AnalysisSection(BaseModel):
    id: str
    title: str
    description: str
    tables: list[AnalysisTable]
    charts: list[AnalysisChart]
    notes: list[str] = Field(default_factory=list)


class SummaryItem(BaseModel):
    key: str
    label: str
    kind: Literal["int", "decimal", "percent"]
    decimals: int | None = None
    unit: str | None = None
    value: float | int | None


class MonitoringAnalysisResponse(BaseModel):
    """Analisis exploratorio de un monitoreo: las 7 hojas del Anexo 1 (E3).

    Todas las cifras las calcula el backend; el frontend y el reporte .xlsx
    solo las presentan, con el tipo y los decimales que declara cada columna.
    """

    project_id: int
    monitoring: int
    monitoring_date: date | None
    previous: int | None = Field(description="Monitoreo con el que se compara (k-1), o null.")
    monitorings: list[int]
    properties: list[str]
    analysis_version: str
    input_hash: str = Field(description="SHA-256 de los datos de entrada (provenance).")
    computed_at: datetime
    summary: list[SummaryItem]
    sections: list[AnalysisSection]


# ── E6: mapa del predio ────────────────────────────────────────────────────


class MapBounds(BaseModel):
    """Extension que encuadra el mapa, en grados WGS84."""

    south: float
    west: float
    north: float
    east: float


class MapTree(BaseModel):
    """Un arbol ubicado. `states` y `heights` se indexan por el NUMERO DE
    MONITOREO COMO CADENA ("1", "2", …): JSON no admite claves numericas."""

    id: str
    species: str | None
    property: str | None
    plot: str | None
    plot_key: str | None
    lat: float
    lon: float
    elevation_m: float | None
    states: dict[str, str] = Field(
        description="Estado por monitoreo: bueno · regular · malo · muerto · sin_dato."
    )
    heights: dict[str, float | None]


class PlotMetric(BaseModel):
    n: int
    survival: float = Field(description="Porcentaje 0-100 de arboles vivos en ese monitoreo.")
    mean_height: float | None


class MapPlot(BaseModel):
    """Una parcela: su contorno para el mapa de calor y sus cifras."""

    key: str
    property: str | None
    plot: str | None
    n: int
    low_sample: bool = Field(description="Menos arboles que el minimo para un porcentaje.")
    centroid: dict[str, float]
    hull: list[list[float]] = Field(
        description="Contorno [[lat, lon], …]. Con 1 o 2 arboles no hay poligono."
    )
    metrics: dict[str, PlotMetric]


class ImageryLayerCreate(BaseModel):
    """Alta de una capa de imagen: AgroSense guarda la direccion, no el archivo."""

    name: str = Field(min_length=1, max_length=120)
    tile_template: str = Field(
        max_length=1000,
        description="Plantilla XYZ sobre https, con {z}, {x} e {y}.",
        examples=["https://tiles.openaerialmap.org/.../{z}/{x}/{y}.png"],
    )
    attribution: str | None = Field(default=None, max_length=300)
    min_zoom: int | None = Field(default=None, ge=0, le=24)
    max_zoom: int | None = Field(default=None, ge=0, le=24)
    opacity: float | None = Field(default=None, ge=0, le=1)


class ImageryLayerResponse(BaseModel):
    id: int
    name: str
    tile_template: str
    attribution: str | None
    min_zoom: int | None
    max_zoom: int | None
    opacity: float


class ProjectMapResponse(BaseModel):
    """Todo el mapa del proyecto en una respuesta (E6).

    Incluye TODOS los monitoreos para que la linea de tiempo se mueva sin
    volver a pedir datos. Las coordenadas llegan ya proyectadas a WGS84: el
    frontend no sabe de sistemas de referencia.
    """

    project_id: int
    version: str
    srid: int
    monitorings: list[int]
    properties: list[str]
    bounds: MapBounds | None
    without_coordinates: int = Field(
        description="Arboles del proyecto sin coordenada: no se dibujan, se cuentan."
    )
    trees: list[MapTree]
    plots: list[MapPlot]
    imagery: list[ImageryLayerResponse] = Field(
        default_factory=list,
        description="Capas de imagen del proyecto, para dibujar bajo los arboles.",
    )


class IndexReadingResponse(BaseModel):
    """Una lectura de indice espectral de un predio en una fecha (E10a)."""

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
    reliable: bool = Field(
        description="False si el poligono cubre muy pocos pixeles para promediar."
    )
    reading: str | None = Field(description="Que dice el valor, en palabras.")
    source: str = Field(description="Proveedor y coleccion de la imagen (provenance).")


class ProjectIndexResponse(BaseModel):
    """Serie guardada de un indice espectral. Leerla no consulta al proveedor."""

    project_id: int
    index: str
    properties: list[str]
    last_refreshed_at: datetime | None
    readings: list[IndexReadingResponse]


class IndexRefreshSummary(BaseModel):
    scenes_found: int
    readings_added: int
    without_data: int = Field(
        description="Mediciones sin pixeles validos: nubes o escena que no cubre el predio."
    )
    interrupted: bool = Field(
        description="El proveedor dejo de responder; lo conseguido se guardo igual."
    )
    properties: list[str]


class IndexRefreshResponse(ProjectIndexResponse):
    summary: IndexRefreshSummary


class ObservationResponse(BaseModel):
    campaign: int
    height_m: float | None
    crown_diameter_m: float | None
    dap_cm: float | None
    dap_status: str
    phytosanitary: str | None
    alive: bool | None
    colonization: str | None


# ── Slice 5: analitica de los modelos mixtos ───────────────────────────────

# Regla del contrato, y la unica forma de que la UI no se confunda de escala:
# lo que se muestra al usuario es SIEMPRE el odds ratio. El log-odds viaja en
# un campo con el nombre pegado a su escala (`ci95_log_odds`) y existe solo
# para poder cotejar la respuesta contra los CSV del modelo mixto.
_OR_DESC = (
    "Odds ratio respecto a la media global de especies: exp(efecto aleatorio). "
    "1.0 = como el promedio; 4.94 = casi 5 veces mas probable."
)
_OR_CI_DESC = (
    "IC 95% del ODDS RATIO — ya exponenciado: [exp(lo), exp(hi)]. Es lo que "
    "debe dibujar la UI. Si contiene 1.0, el efecto no es concluyente."
)
_LOG_CI_DESC = (
    "IC 95% en LOG-ODDS (efecto ± 1.96·se), la escala en la que lo estimo el "
    "modelo mixto. Se expone para trazabilidad contra "
    "`data/processed/efectos_aleatorios*.csv`; NO mostrarlo en la UI. Si "
    "contiene 0.0, el efecto no es concluyente."
)
_SIG_DESC = (
    "True si el IC 95% no cruza 0 en log-odds (equivalente: no cruza 1 en OR). "
    "False significa 'no distinguible del promedio', NO 'sin efecto'."
)


class RiskResponse(BaseModel):
    """Efecto de una especie o parcela sobre un desenlace."""

    odds_ratio: float | None = Field(default=None, description=_OR_DESC)
    or_ci95: tuple[float, float] | None = Field(default=None, description=_OR_CI_DESC)
    ci95_log_odds: tuple[float, float] | None = Field(
        default=None, description=_LOG_CI_DESC
    )
    significant: bool | None = Field(default=None, description=_SIG_DESC)
    interpretation: str = Field(
        description="Lectura en lenguaje llano, ya resuelta en application/."
    )


class SpeciesAnalyticsResponse(BaseModel):
    species: str
    stall_risk: RiskResponse
    mortality_risk: RiskResponse
    n_observations: int | None = Field(
        default=None,
        description="Observaciones arbol-intervalo de la especie en el panel de "
        "estancamiento.",
    )
    n_trees: int | None = Field(default=None, description="Arboles distintos.")
    gremio: str | None = Field(
        default=None, description="Gremio ecologico: Inicial | Intermedia | Tardia."
    )


class PlotAnalyticsResponse(BaseModel):
    plot_code: str = Field(description="`Codigo de unidad muestreo` de la parcela.")
    localidad: str | None = None
    stall_risk: RiskResponse
    mortality_risk: RiskResponse
    n_trees: int | None = None


class VarianceComponentResponse(BaseModel):
    grouping: str = Field(description="Nivel de agrupamiento: especie | parcela.")
    variance: float
    sd: float
    icc: float = Field(
        description="Correlacion intraclase: fraccion de la varianza total "
        "atribuible a este nivel."
    )
    n_levels: int | None = Field(
        default=None, description="Niveles distintos (ej. 30 especies, 42 parcelas)."
    )
    n_observations: int | None = None
    n_events: int | None = Field(
        default=None,
        description="Eventos positivos. Con 70 muertes en 1.405 observaciones, "
        "un ICC alto descansa sobre poca evidencia: leerlo junto al ICC.",
    )


class ModelVarianceResponse(BaseModel):
    model_config = {"populate_by_name": True, "protected_namespaces": ()}

    model_name: str = Field(
        description="stall | mortality.",
        # `model_` es prefijo reservado de pydantic v2; el contrato expone
        # `model` y el schema lo recibe con alias para no renombrar la API.
        alias="model",
        serialization_alias="model",
    )
    components: list[VarianceComponentResponse]
    species_to_plot_ratio: float | None = Field(
        default=None,
        description="Varianza de especie / varianza de parcela. >1.5 = domina la "
        "especie (que plantar); ~1 = pesan igual (que plantar Y donde).",
    )
    interpretation: str


class SpeciesContrastResponse(BaseModel):
    """Una especie plantada del proyecto, frente al Referente (E5, UC-AN3)."""

    species: str
    n_trees_in_project: int
    has_reference: bool
    gremio: str | None = None
    stall_risk: RiskResponse | None = None
    mortality_risk: RiskResponse | None = None
    narrative: str


class AIReportResponse(BaseModel):
    """Borrador de informe generado por IA de un monitoreo (E9, UC-IA1/2/3)."""

    model_config = {"protected_namespaces": ()}

    project_id: int
    monitoring: int
    model_name: str
    prompt_version: str
    content: str
    unverified_numbers: list[str] = Field(
        default_factory=list,
        description="Numeros del texto generado que no aparecen entre las cifras dadas al modelo.",
    )
    created_at: datetime
    stale: bool = Field(
        description="True si el analisis del monitoreo cambio desde que se generó este borrador."
    )


# ── E7: deteccion de estancados (UC-AN4) ─────────────────────────────────────


class StallTreeResponse(BaseModel):
    """Un arbol vivo y medido en el monitoreo, con su riesgo de estancarse."""

    tree_id: str
    species: str
    locality: str | None
    plot: str | None
    probability: float = Field(
        ge=0.0,
        le=1.0,
        description="P(la altura no cambie hasta el proximo monitoreo | sigue vivo).",
    )
    flagged: bool = Field(
        description="Entra en el presupuesto de alertas para revision en campo."
    )
    stalled_last_interval: bool | None = Field(
        description="No crecio desde el monitoreo anterior (estancó_intervalo_previo). "
        "null = sin historia medida."
    )
    stall_streak: int = Field(
        ge=0, description="Intervalos seguidos sin crecer hasta este monitoreo."
    )
    persistent: bool
    known_species: bool = Field(description="La especie estaba en los datos de entrenamiento.")
    unknown_categories: list[str] = Field(
        description="Nombres de las features categoricas (especie incluida) cuyo valor no "
        "vio el entrenamiento. Vacia si todas se reconocen."
    )


class StallSummaryResponse(BaseModel):
    at_risk: int = Field(ge=0)
    flagged: int = Field(ge=0)
    stalled_last_interval: int = Field(ge=0)
    persistent: int = Field(ge=0)
    without_history: int = Field(ge=0)
    unknown_species: int = Field(ge=0)
    unknown_category_trees: int = Field(
        ge=0,
        description="Arboles con al menos una categoria (especie u otra) no vista al entrenar.",
    )
    mostly_without_history: bool = Field(
        description="`without_history` es al menos la mitad de los arboles puntuados: la "
        "mayoria de las predicciones de este monitoreo son extrapolacion, no evaluacion."
    )


class StallModelCardResponse(BaseModel):
    """Que modelo produjo el resultado y cuanto vale, segun su evaluacion honesta."""

    model_config = {"protected_namespaces": ()}

    model_version: str
    artifact_sha256: str
    dataset_sha256: str
    trained_on: str
    pr_auc: float
    pr_auc_ci_low: float
    pr_auc_ci_high: float
    roc_auc: float
    prevalence_pct: float
    recall_at_budget_pct: float
    precision_at_budget_pct: float


class StallAssessmentResponse(BaseModel):
    """Deteccion de estancados de un monitoreo (E7, UC-AN4)."""

    model_config = {"protected_namespaces": ()}

    project_id: int
    monitoring: int
    input_hash: str
    computed_at: datetime
    alert_budget_pct: float = Field(description="Porcentaje de arboles marcados (escala 0-100).")
    persistent_min_intervals: int
    model: StallModelCardResponse
    summary: StallSummaryResponse
    trees: list[StallTreeResponse]
