"""Modelos SQLAlchemy (adapters/db — el UNICO lugar que toca el ORM).

Derivados del dominio (docs/02-domain.md): Project 1-N CampaignFile,
Project 1-N TreeRow, TreeRow 1-N ObservationRow.

E0 (docs/04-vision-producto.md) anade el territorio y el monitoreo como
entidades: Project 1-N PropertyRow (predio) 1-N PlotRow (unidad de muestreo)
1-N TreeRow, y Project 1-N MonitoringRow 1-N ObservationRow. Un archivo subido
(CampaignFile) puede traer varios monitoreos: relacion N:N.

Slice 5 anade dos tablas ANALITICAS (SpeciesAnalytics, PlotAnalytics) que no
son parte de ese grafo: no cuelgan de Project ni tienen FKs hacia el. Son el
resultado ya ajustado de los modelos mixtos sobre el dataset de referencia
(`backend/data/processed/efectos_aleatorios*.csv`), cargado por
`scripts/load_analytics.py`. Se modelan aparte a proposito — ver el docstring
de SpeciesAnalytics.
"""
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Engineer(Base):
    """Perfil del ingeniero (E1, ADR-006).

    `id` es el `sub` del token de Supabase Auth: usuario y contrasena los
    gestiona Supabase, AgroSense solo guarda el perfil. Se crea en la primera
    peticion autenticada. No hay FK hacia `auth.users` a proposito: esa tabla
    vive en otro esquema, no existe en los tests locales, y la identidad ya la
    garantiza la firma del token.
    """

    __tablename__ = "engineers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320))
    full_name: Mapped[str | None] = mapped_column(String(200))
    professional_license: Mapped[str | None] = mapped_column(String(100))
    organization: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class Project(Base):
    """Proyecto de restauracion. Pertenece a UN ingeniero (E1).

    `project_code` lo asigna AgroSense (`AGS-{año}-{id}`): identificador interno,
    obligatorio y unico global. El nombre es unico por ingeniero, no global:
    dos ingenieros pueden tener «Restauracion Guayabal».
    """

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_project_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_code: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("engineers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    locality: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # E1 — campos del proyecto (decision D7)
    contract_code: Mapped[str | None] = mapped_column(String(100))
    objective: Mapped[str | None] = mapped_column(Text)
    executing_org: Mapped[str | None] = mapped_column(String(200))
    contracting_entity: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(100))
    municipality: Mapped[str | None] = mapped_column(String(100))
    intervention_type: Mapped[str | None] = mapped_column(String(50))
    area_ha: Mapped[float | None] = mapped_column(Float)
    planted_individuals: Mapped[int | None] = mapped_column(Integer)
    planting_density: Mapped[float | None] = mapped_column(Float)
    establishment_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    legal_framework: Mapped[str | None] = mapped_column(String(50))
    environmental_authority: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="activo")
    coordinate_srid: Mapped[int] = mapped_column(Integer, nullable=False, default=9377)

    owner: Mapped["Engineer"] = relationship(back_populates="projects")
    campaigns: Mapped[list["CampaignFile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    trees: Mapped[list["TreeRow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    properties: Mapped[list["PropertyRow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    plots: Mapped[list["PlotRow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    monitorings: Mapped[list["MonitoringRow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


# Puente N:N: un archivo acumulado trae varios monitoreos, y un monitoreo puede
# llegar en varios archivos (el original y sus correcciones).
campaign_file_monitorings = Table(
    "campaign_file_monitorings",
    Base.metadata,
    Column(
        "campaign_file_id",
        ForeignKey("campaign_files.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "monitoring_id",
        ForeignKey("monitorings.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class PropertyRow(Base):
    """Predio: `LOCALIDAD` en el formato de campo (Tres Jotas, Guayabal…)."""

    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_property_project_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    vereda: Mapped[str | None] = mapped_column(String(200))

    project: Mapped["Project"] = relationship(back_populates="properties")
    plots: Mapped[list["PlotRow"]] = relationship(back_populates="property")


class PlotRow(Base):
    """Unidad de muestreo. El diseno y las coberturas son SUYOS, no del arbol.

    En el dataset de referencia son constantes dentro de cada unidad
    (verificado en E0), asi que viven aqui y no se repiten en 856 arboles.

    `code` es la identidad dentro del proyecto (`domain.rules.plot_key`). La
    parcela lleva `project_id` propio aunque el predio ya lo implica: el predio
    es opcional, y la unicidad de la parcela tiene que ser por PROYECTO.
    """

    __tablename__ = "plots"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_plot_project_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[int | None] = mapped_column(
        ForeignKey("properties.id", ondelete="SET NULL"), index=True
    )
    code: Mapped[str] = mapped_column(String(300), nullable=False)
    sampling_unit_code: Mapped[str | None] = mapped_column(String(200))
    plot_label: Mapped[str | None] = mapped_column(String(100))
    monitoring_unit: Mapped[str | None] = mapped_column(String(200))
    floristic_design: Mapped[str | None] = mapped_column(String(300))
    associated_cover: Mapped[str | None] = mapped_column(String(300))
    establishment_cover: Mapped[str | None] = mapped_column(String(300))

    project: Mapped["Project"] = relationship(back_populates="plots")
    property: Mapped["PropertyRow | None"] = relationship(
        back_populates="plots", lazy="joined"
    )
    trees: Mapped[list["TreeRow"]] = relationship(back_populates="plot")


class MonitoringRow(Base):
    """Un monitoreo del proyecto (M1, M2…): la entidad que faltaba (hallazgo H3).

    Sin ella no habia donde guardar la FECHA, que el protocolo de estancamiento
    declara como su limitacion nº 1: sin fechas no se puede anualizar el
    crecimiento. `monitoring_date` es nullable porque el Excel no la trae: la
    registra el ingeniero (E2).
    """

    __tablename__ = "monitorings"
    __table_args__ = (
        UniqueConstraint("project_id", "number", name="uq_monitoring_project_number"),
        CheckConstraint("number >= 1", name="ck_monitoring_number_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    monitoring_date: Mapped[date | None] = mapped_column(Date)
    field_crew: Mapped[str | None] = mapped_column(String(500))
    recorder: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)

    project: Mapped["Project"] = relationship(back_populates="monitorings")
    observations: Mapped[list["ObservationRow"]] = relationship(back_populates="monitoring")
    campaign_files: Mapped[list["CampaignFile"]] = relationship(
        secondary=campaign_file_monitorings, back_populates="monitorings"
    )


class CampaignFile(Base):
    """Provenance de una ingesta: archivo crudo + versiones + stats."""

    __tablename__ = "campaign_files"
    __table_args__ = (
        UniqueConstraint("project_id", "sha256", name="uq_campaign_project_file"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(50), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    trees: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # E0 — lo que el archivo dice de si mismo (columnas de archivo)
    source_project_label: Mapped[str | None] = mapped_column(String(500))
    source_event: Mapped[str | None] = mapped_column(String(200))
    source_field_crew: Mapped[str | None] = mapped_column(String(500))
    source_recorder: Mapped[str | None] = mapped_column(String(300))

    project: Mapped["Project"] = relationship(back_populates="campaigns")
    monitorings: Mapped[list["MonitoringRow"]] = relationship(
        secondary=campaign_file_monitorings, back_populates="campaign_files"
    )


class TreeRow(Base):
    __tablename__ = "trees"
    __table_args__ = (
        UniqueConstraint("project_id", "tree_id", name="uq_tree_project_tree_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tree_id: Mapped[str] = mapped_column(String(200), nullable=False)
    species: Mapped[str] = mapped_column(String(300), nullable=False)
    family: Mapped[str | None] = mapped_column(String(200))
    common_name: Mapped[str | None] = mapped_column(String(300))
    guild: Mapped[str | None] = mapped_column(String(100))
    plot_row_id: Mapped[int | None] = mapped_column(
        ForeignKey("plots.id", ondelete="SET NULL"), index=True
    )
    coord_x: Mapped[float | None] = mapped_column(Float)
    coord_y: Mapped[float | None] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float)

    project: Mapped["Project"] = relationship(back_populates="trees")
    plot: Mapped["PlotRow | None"] = relationship(back_populates="trees", lazy="joined")
    observations: Mapped[list["ObservationRow"]] = relationship(
        back_populates="tree", cascade="all, delete-orphan"
    )

    # ── Vistas de solo lectura sobre la parcela (E0) ───────────────────────
    # Hasta E0 `plot_id` y `locality` eran columnas de `trees`. Pasaron a
    # `plots` / `properties`, pero se siguen exponiendo con el mismo nombre:
    # `domain.rules.validate_tree_identity` y el contrato de la API los leen
    # por atributo y no deben enterarse de la normalizacion.

    @property
    def plot_id(self) -> str | None:
        return self.plot.plot_label if self.plot else None

    @property
    def locality(self) -> str | None:
        if self.plot is None or self.plot.property is None:
            return None
        return self.plot.property.name

    @property
    def sampling_unit_code(self) -> str | None:
        return self.plot.sampling_unit_code if self.plot else None

    @property
    def monitoring_unit(self) -> str | None:
        return self.plot.monitoring_unit if self.plot else None

    @property
    def floristic_design(self) -> str | None:
        return self.plot.floristic_design if self.plot else None

    @property
    def associated_cover(self) -> str | None:
        return self.plot.associated_cover if self.plot else None

    @property
    def establishment_cover(self) -> str | None:
        return self.plot.establishment_cover if self.plot else None


class ObservationRow(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint(
            "tree_row_id", "monitoring_id", name="uq_observation_tree_monitoring"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tree_row_id: Mapped[int] = mapped_column(
        ForeignKey("trees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    monitoring_id: Mapped[int] = mapped_column(
        ForeignKey("monitorings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    height_m: Mapped[float | None] = mapped_column(Float)
    crown_diameter_m: Mapped[float | None] = mapped_column(Float)
    dap_cm: Mapped[float | None] = mapped_column(Float)
    dap_status: Mapped[str] = mapped_column(String(20), nullable=False)
    phytosanitary: Mapped[str | None] = mapped_column(String(50))
    alive: Mapped[bool | None] = mapped_column(Boolean)
    colonization: Mapped[str | None] = mapped_column(JSON)
    field_notes: Mapped[str | None] = mapped_column(Text)

    tree: Mapped["TreeRow"] = relationship(back_populates="observations")
    monitoring: Mapped["MonitoringRow"] = relationship(
        back_populates="observations", lazy="joined"
    )

    @property
    def campaign(self) -> int:
        """Numero de monitoreo, como lo siguen viendo el dominio y la API.

        Hasta E0 era una columna; ahora sale del monitoreo al que pertenece.
        """
        return self.monitoring.number


# ── Slice 5: analitica (efectos de los modelos mixtos) ─────────────────────
#
# Estas dos tablas son un CACHE DE LECTURA de una estimacion offline, no
# datos de monitoreo. Por eso:
#
#   - No cuelgan de `projects`: los efectos se estimaron sobre el dataset de
#     referencia completo (856 arboles, 42-45 parcelas, 30 especies), que
#     hoy es un solo proyecto pero conceptualmente es "la evidencia del
#     programa", no "los datos de este proyecto". Meterles un project_id
#     ahora seria inventar una dimension que el modelo estadistico no tiene.
#   - La PK es el nombre (especie / codigo de parcela) porque es como
#     llegan del CSV de efectos aleatorios y como los pide la API.
#   - Los campos de estancamiento y mortalidad son nullable: una parcela
#     puede tener efecto en un modelo y no en el otro (el panel de
#     mortalidad tiene 45 parcelas, el de estancamiento 42).
#
# Cuando exista multi-proyecto de verdad, esto pide un ADR, no una columna.


class SatelliteIndexValueRow(Base):
    """Un indice espectral (NDVI) de un predio en una escena (E10a, ADR-011).

    Por que esto SI se guarda y el mapa no: la cifra viene de un tercero,
    cuesta una peticion de red por (escena, predio) y no se puede reproducir
    si el proveedor deja de servir la escena. Guardarla con su procedencia
    —que escena, que proveedor, sobre que poligono— es lo que permite que un
    informe la cite dentro de un ano.

    `polygon_hash` es la huella del contorno del predio: si se cargan arboles
    nuevos y el poligono cambia, la lectura vieja sigue siendo cierta para el
    poligono que la produjo, y se ve que ya no corresponde al actual.
    """

    __tablename__ = "satellite_index_values"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "property_name", "index_name", "scene_id",
            name="uq_index_value_scene",
        ),
        CheckConstraint("valid_pixels >= 0", name="ck_index_value_pixels"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_name: Mapped[str] = mapped_column(String(200), nullable=False)
    index_name: Mapped[str] = mapped_column(String(20), nullable=False)
    scene_id: Mapped[str] = mapped_column(String(200), nullable=False)
    acquired_at: Mapped[date] = mapped_column(Date, nullable=False)
    cloud_cover: Mapped[float | None] = mapped_column(Float)
    mean_value: Mapped[float] = mapped_column(Float, nullable=False)
    median_value: Mapped[float | None] = mapped_column(Float)
    min_value: Mapped[float | None] = mapped_column(Float)
    max_value: Mapped[float | None] = mapped_column(Float)
    std_value: Mapped[float | None] = mapped_column(Float)
    valid_pixels: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    polygon_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class ImageryLayerRow(Base):
    """Capa de imagen de un proyecto: su ortofoto (E6b, ADR-009).

    Guardamos una PLANTILLA DE TESELAS, no el archivo. La imagen vive donde el
    ingeniero la tenga (OpenAerialMap, un TiTiler, su plataforma de drones) y
    la carga el navegador. Subir y tilar el GeoTIFF propio exige
    almacenamiento y un tilador: es otra decision, no esta.

    Varias por proyecto (nombre unico dentro del proyecto): una ortofoto por
    campana, por ejemplo.
    """

    __tablename__ = "imagery_layers"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_imagery_layer_project_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    tile_template: Mapped[str] = mapped_column(String(1000), nullable=False)
    attribution: Mapped[str | None] = mapped_column(String(300))
    min_zoom: Mapped[int | None] = mapped_column(Integer)
    max_zoom: Mapped[int | None] = mapped_column(Integer)
    opacity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class MonitoringAnalysisRow(Base):
    """Snapshot del analisis exploratorio de UN monitoreo (E3, ADR-008).

    El analisis es derivado: se recalcula entero y se consume entero (pagina y
    reporte .xlsx), nunca se consulta por dentro con SQL. Por eso vive como un
    JSON inmutable y versionado, y no como tablas:

      - `analysis_version`: version del calculo que lo produjo. Si el codigo
        cambia de version, el snapshot se recalcula al leerse;
      - `input_hash`: huella de los datos de entrada (arboles + observaciones
        del proyecto). Ata el resultado a lo que lo produjo (AGENTS.md,
        Data provenance).

    Uno por monitoreo (`UNIQUE(monitoring_id)`): recalcular REEMPLAZA.
    """

    __tablename__ = "monitoring_analyses"
    __table_args__ = (
        UniqueConstraint("monitoring_id", name="uq_monitoring_analysis_monitoring"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    monitoring_id: Mapped[int] = mapped_column(
        ForeignKey("monitorings.id", ondelete="CASCADE"), nullable=False
    )
    analysis_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


def _analytics_updated() -> datetime:
    return _utcnow()


class SpeciesAnalytics(Base):
    """Efecto aleatorio por especie en los modelos mixtos de estancamiento y
    mortalidad (`lme4::glmer` binomial), en escala log-odds respecto a la
    media global.

    `effect_*` es el log-odds; `or_* = exp(effect_*)`; `or_*_lo/hi` son los
    extremos del IC 95% YA exponenciados (`exp(efecto +- 1.96*se)`).
    `sig_*` es True cuando el IC 95% en log-odds no cruza 0 — equivalente a
    que el IC del OR no cruce 1.
    """

    __tablename__ = "species_analytics"

    species_name: Mapped[str] = mapped_column(String(300), primary_key=True)

    # Estancamiento
    effect_stall: Mapped[float | None] = mapped_column(Float)
    se_stall: Mapped[float | None] = mapped_column(Float)
    or_stall: Mapped[float | None] = mapped_column(Float)
    or_stall_lo: Mapped[float | None] = mapped_column(Float)
    or_stall_hi: Mapped[float | None] = mapped_column(Float)
    sig_stall: Mapped[bool | None] = mapped_column(Boolean)

    # Mortalidad
    effect_mort: Mapped[float | None] = mapped_column(Float)
    se_mort: Mapped[float | None] = mapped_column(Float)
    or_mort: Mapped[float | None] = mapped_column(Float)
    or_mort_lo: Mapped[float | None] = mapped_column(Float)
    or_mort_hi: Mapped[float | None] = mapped_column(Float)
    sig_mort: Mapped[bool | None] = mapped_column(Boolean)

    # Metadatos
    n_observations: Mapped[int | None] = mapped_column(Integer)
    n_trees: Mapped[int | None] = mapped_column(Integer)
    gremio: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_analytics_updated, nullable=False
    )


class PlotAnalytics(Base):
    """Efecto aleatorio por parcela (`Codigo de unidad muestreo`).

    Es la contraparte espacial de SpeciesAnalytics y la razon por la que la
    validacion cruzada agrupa por parcela y no por arbol: la parcela explica
    ICC 0.07 del estancamiento y 0.09 de la mortalidad.

    No lleva IC ni `sig_*`: solo 3 de 42 parcelas resultaron significativas en
    estancamiento y 1 de 45 en mortalidad, asi que el ranking por parcela se
    presenta como magnitud, no como hallazgo. El `se_*` queda para que la UI
    pueda dibujar la barra de incertidumbre.
    """

    __tablename__ = "plot_analytics"

    plot_code: Mapped[str] = mapped_column(String(100), primary_key=True)
    localidad: Mapped[str | None] = mapped_column(String(200))

    effect_stall: Mapped[float | None] = mapped_column(Float)
    se_stall: Mapped[float | None] = mapped_column(Float)
    or_stall: Mapped[float | None] = mapped_column(Float)

    effect_mort: Mapped[float | None] = mapped_column(Float)
    se_mort: Mapped[float | None] = mapped_column(Float)
    or_mort: Mapped[float | None] = mapped_column(Float)

    n_trees: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_analytics_updated, nullable=False
    )


class VarianceComponent(Base):
    """Descomposicion de varianza de cada modelo mixto (una fila por
    modelo x nivel de agrupamiento).

    Alimenta `GET /api/v1/analytics/variance-decomposition`, que es el
    endpoint que sostiene la lectura estrategica del slice: en estancamiento
    la especie pesa 2.7x mas que la parcela (ICC 0.190 vs 0.071); en
    mortalidad pesan casi igual (0.102 vs 0.091).
    """

    __tablename__ = "variance_components"
    __table_args__ = (
        UniqueConstraint("model", "grouping", name="uq_variance_model_grouping"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str] = mapped_column(String(20), nullable=False)  # stall | mortality
    grouping: Mapped[str] = mapped_column(String(20), nullable=False)  # especie | parcela
    variance: Mapped[float] = mapped_column(Float, nullable=False)
    sd: Mapped[float] = mapped_column(Float, nullable=False)
    icc: Mapped[float] = mapped_column(Float, nullable=False)
    n_levels: Mapped[int | None] = mapped_column(Integer)
    n_observations: Mapped[int | None] = mapped_column(Integer)
    n_events: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_analytics_updated, nullable=False
    )
