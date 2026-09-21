"""Contrato del slice 2 (fuente de verdad — AGENTS.md).

FastAPI expone esto como OpenAPI; el frontend genera sus tipos de aqui.
Los tipos de error/warning documentan los rulings del dominio (slice 1).
"""
from datetime import date, datetime

from pydantic import BaseModel, Field

# Semantica explicita en el OpenAPI: el frontend y el modelo de mortalidad
# consumen este numero y no significa lo que el nombre sugiere.
_DEATHS_DESC = (
    "Registros de observación con estado muerto en la campaña. NO es el número de "
    "árboles muertos distintos: un árbol que muere en M2 aporta un registro por cada "
    "campaña posterior. Para mortalidad por árbol ver docs/deuda-tecnica.md #F."
)

# ── UC1: proyectos ─────────────────────────────────────────────


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    locality: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ProjectResponse(BaseModel):
    id: int
    name: str
    locality: str | None
    description: str | None
    created_at: datetime
    campaigns_count: int


# ── UC2: upload de campaña ─────────────────────────────────────


class WarningItem(BaseModel):
    type: str = Field(
        pattern="^(contraction|revival|census_gap|event_mismatch|project_mismatch)$",
        description=(
            "contraction | revival | census_gap: avisos de un arbol. "
            "event_mismatch | project_mismatch: avisos del ARCHIVO (E0), con "
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
    observations: int = Field(description="Observaciones registradas en este monitoreo.")


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

    model_config = {"populate_by_name": True, "protected_namespaces": ()}
