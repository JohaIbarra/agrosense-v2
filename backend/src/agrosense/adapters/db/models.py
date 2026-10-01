"""Modelos SQLAlchemy (adapters/db — el UNICO lugar que toca el ORM).

Derivados del dominio (docs/02-domain.md): Project 1-N CampaignFile,
Project 1-N TreeRow, TreeRow 1-N ObservationRow.

E0 (docs/04-vision-producto.md) anade el territorio y el monitoreo como
entidades: Project 1-N PropertyRow (predio) 1-N PlotRow (unidad de muestreo)
1-N TreeRow, y Project 1-N MonitoringRow 1-N ObservationRow. Un archivo subido
(CampaignFile) puede traer varios monitoreos: relacion N:N.

Slice 5 (luego versionado en E5) anade tablas ANALITICAS (ReferenceModel,
ReferenceSpeciesEffect, ReferencePlotEffect, VarianceComponent) que no son
parte de ese grafo: no cuelgan de Project ni tienen FKs hacia el. Son el
resultado ya ajustado de los modelos mixtos sobre el dataset de referencia
(`backend/data/processed/efectos_aleatorios*.csv`), cargado por
`scripts/load_analytics.py`. Se modelan aparte a proposito — ver ADR-007
(docs/adr/007-separacion-proyecto-referente.md).
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
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
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
    # Excel crudo (deuda D, ADR-014): NULL en cargas anteriores a E8.
    content: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
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
    # Fix wave (E7, item 2): predio del arbol INDEPENDIENTE de la parcela.
    # `plot_row_id` solo se fija cuando `domain.rules.plot_key` reconoce una
    # parcela (codigo de unidad o predio/ID Parcela); un archivo que trae
    # `LOCALIDAD` sin ninguno de los dos deja al arbol sin parcela, y antes
    # eso tambien le borraba el predio al servir (`locality` solo miraba
    # `plot.property`), aunque la ruta de entrenamiento (directa desde el
    # Excel) si lo conservaba. `plot_key` no cambia: esto es solo donde se
    # guarda el predio para exponerlo igual por las dos rutas.
    property_id: Mapped[int | None] = mapped_column(
        ForeignKey("properties.id", ondelete="SET NULL"), index=True
    )
    coord_x: Mapped[float | None] = mapped_column(Float)
    coord_y: Mapped[float | None] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float)

    project: Mapped["Project"] = relationship(back_populates="trees")
    plot: Mapped["PlotRow | None"] = relationship(back_populates="trees", lazy="joined")
    # Nombre `property_row` (no `property`): un atributo de clase llamado
    # `property` en el cuerpo de la clase taparia el `@property` builtin
    # para los descriptores de mas abajo.
    property_row: Mapped["PropertyRow | None"] = relationship(lazy="joined")
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
        if self.plot is not None and self.plot.property is not None:
            return self.plot.property.name
        return self.property_row.name if self.property_row is not None else None

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
        # La lectura de la serie filtra por proyecto e indice y ordena por fecha.
        Index("ix_satellite_index_values_project", "project_id", "index_name", "acquired_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
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


class AIReportRow(Base):
    """Borrador de informe generado por IA para UN monitoreo (E9, UC-IA1/2/3).

    Cubre el resumen del monitoreo Y la comparacion con el anterior: ambos
    viven en el MISMO snapshot (`monitoring_analyses`, ADR-008), asi que un
    solo informe basta -- no hay una tabla `comparison_analyses` de la que
    colgar un segundo informe (docs/adr/008-analisis-como-snapshot.md).

    `input_hash` ata el borrador a las cifras EXACTAS que vio el LLM, no al
    snapshot del proyecto entero: `application/use_cases/ai_report.py:
    _figures_fingerprint` (fix wave 2026-09-27, item 3). Si esas cifras
    cambian, el borrador viejo se sigue sirviendo pero marcado "stale" (se
    detecta comparando este campo contra el fingerprint actual) -- nunca se
    reescribe solo. Antes se ataba al `input_hash` del snapshot (todo el
    dataset del proyecto): subir un monitoreo nuevo volvia obsoletos los
    borradores de TODOS los monitoreos anteriores, aunque sus propias
    cifras no hubieran cambiado.

    Uno por monitoreo (`UNIQUE(monitoring_id)`): regenerar REEMPLAZA, igual
    que el propio snapshot.
    """

    __tablename__ = "ai_reports"
    __table_args__ = (
        UniqueConstraint("monitoring_id", name="uq_ai_report_monitoring"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    monitoring_id: Mapped[int] = mapped_column(
        ForeignKey("monitorings.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    unverified_numbers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StallAssessmentRow(Base):
    """Deteccion de estancados de UN monitoreo (E7, UC-AN4).

    Snapshot, como `monitoring_analyses` (ADR-008): la lista de arboles con
    su probabilidad, si entran en el presupuesto de alertas y la regla de
    negocio observada. Procedencia por fila (AGENTS.md, ADR-013): que modelo
    (`model_version` + `artifact_sha256`), que datos (`input_hash`, solo
    observaciones <= este monitoreo) y que REGLAS de negocio
    (`rules_version`, fix wave item 4: ALERT_BUDGET, PERSISTENT_STALL_INTERVALS
    y la definicion de la etiqueta) lo produjeron. Si cambia cualquiera de
    los cuatro, el caso de uso lo recalcula y REEMPLAZA.
    """

    __tablename__ = "stall_assessments"
    __table_args__ = (
        UniqueConstraint("monitoring_id", name="uq_stall_assessment_monitoring"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    monitoring_id: Mapped[int] = mapped_column(
        ForeignKey("monitorings.id", ondelete="CASCADE"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rules_version: Mapped[str] = mapped_column(String(50), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


def _analytics_updated() -> datetime:
    return _utcnow()


# ── E5: referente cientifico versionado (efectos de los modelos mixtos) ────
#
# `reference_models` es la version: cada fila es UNA corrida completa de los
# modelos mixtos (lme4::glmer binomial). Las tres tablas de efectos cuelgan
# de una version por `reference_model_id`, y su PK ahora es compuesta
# (version, nivel): asi conviven varias versiones sin pisarse.
#
# `is_active` marca cual version sirve la API hoy. Publicar una version
# nueva NO borra las anteriores (antes de E5 una recarga borraba la version
# vieja sin rastro, doc 04-vision-producto.md §6.7) — quedan en la base,
# consultables por su `reference_model_id`, fuera de lectura por defecto.
#
# Sin FK hacia `projects`: los efectos se estimaron sobre el dataset de
# referencia completo (856 arboles, 30 especies), que es conceptualmente
# "la evidencia del programa", no de un proyecto — decision documentada en
# ADR-007 (docs/adr/007-separacion-proyecto-referente.md).


class ReferenceModel(Base):
    """Una corrida versionada de los modelos mixtos de estancamiento/mortalidad."""

    __tablename__ = "reference_models"
    __table_args__ = (
        UniqueConstraint("version", name="uq_reference_models_version"),
        # A lo sumo UNA fila activa (ADR-007): forzado por la base, no solo
        # por `ReferenceRepository.publish_version`. `sqlite_where` ademas de
        # `postgresql_where` porque los tests locales corren sobre SQLite.
        Index(
            "uq_reference_models_single_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(300), nullable=False)
    method: Mapped[str] = mapped_column(String(100), nullable=False)
    n_observations: Mapped[int | None] = mapped_column(Integer)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ReferenceSpeciesEffect(Base):
    """Efecto aleatorio por especie de UNA version del referente.

    `effect_*` es el log-odds; `or_* = exp(effect_*)`; `or_*_lo/hi` son los
    extremos del IC 95% YA exponenciados (`exp(efecto +- 1.96*se)`).
    `sig_*` es True cuando el IC 95% en log-odds no cruza 0.
    """

    __tablename__ = "reference_species_effects"
    # Indices de orden/filtro de /api/v1/reference/species (migracion c7e9f2a4b6d8).
    __table_args__ = (
        Index("ix_reference_species_effects_or_stall", "or_stall"),
        Index("ix_reference_species_effects_or_mort", "or_mort"),
        Index("ix_reference_species_effects_gremio", "gremio"),
    )

    reference_model_id: Mapped[int] = mapped_column(
        ForeignKey("reference_models.id", ondelete="CASCADE"), primary_key=True
    )
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


class ReferencePlotEffect(Base):
    """Efecto aleatorio por parcela (`Codigo de unidad muestreo`) de UNA version."""

    __tablename__ = "reference_plot_effects"
    __table_args__ = (Index("ix_reference_plot_effects_localidad", "localidad"),)

    reference_model_id: Mapped[int] = mapped_column(
        ForeignKey("reference_models.id", ondelete="CASCADE"), primary_key=True
    )
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
    """Descomposicion de varianza de UNA version (una fila por modelo x nivel)."""

    __tablename__ = "variance_components"
    __table_args__ = (
        UniqueConstraint(
            "reference_model_id", "model", "grouping", name="uq_variance_model_grouping"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reference_model_id: Mapped[int] = mapped_column(
        ForeignKey("reference_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
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
