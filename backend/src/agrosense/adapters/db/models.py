"""Modelos SQLAlchemy (adapters/db — el UNICO lugar que toca el ORM).

Derivados del dominio (docs/02-domain.md): Project 1-N CampaignFile,
Project 1-N TreeRow, TreeRow 1-N ObservationRow.

Slice 5 anade dos tablas ANALITICAS (SpeciesAnalytics, PlotAnalytics) que no
son parte de ese grafo: no cuelgan de Project ni tienen FKs hacia el. Son el
resultado ya ajustado de los modelos mixtos sobre el dataset de referencia
(`backend/data/processed/efectos_aleatorios*.csv`), cargado por
`scripts/load_analytics.py`. Se modelan aparte a proposito — ver el docstring
de SpeciesAnalytics.
"""
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    locality: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    campaigns: Mapped[list["CampaignFile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    trees: Mapped[list["TreeRow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
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

    project: Mapped["Project"] = relationship(back_populates="campaigns")


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
    plot_id: Mapped[str | None] = mapped_column(String(100))
    locality: Mapped[str | None] = mapped_column(String(200))
    coord_x: Mapped[float | None] = mapped_column(Float)
    coord_y: Mapped[float | None] = mapped_column(Float)
    elevation_m: Mapped[float | None] = mapped_column(Float)

    project: Mapped["Project"] = relationship(back_populates="trees")
    observations: Mapped[list["ObservationRow"]] = relationship(
        back_populates="tree", cascade="all, delete-orphan"
    )


class ObservationRow(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("tree_row_id", "campaign", name="uq_observation_tree_campaign"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tree_row_id: Mapped[int] = mapped_column(
        ForeignKey("trees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign: Mapped[int] = mapped_column(Integer, nullable=False)
    height_m: Mapped[float | None] = mapped_column(Float)
    crown_diameter_m: Mapped[float | None] = mapped_column(Float)
    dap_cm: Mapped[float | None] = mapped_column(Float)
    dap_status: Mapped[str] = mapped_column(String(20), nullable=False)
    phytosanitary: Mapped[str | None] = mapped_column(String(50))
    alive: Mapped[bool | None] = mapped_column(Boolean)
    colonization: Mapped[str | None] = mapped_column(JSON)

    tree: Mapped["TreeRow"] = relationship(back_populates="observations")


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
