"""Modelos SQLAlchemy (adapters/db — el UNICO lugar que toca el ORM).

Derivados del dominio (docs/02-domain.md): Project 1-N CampaignFile,
Project 1-N TreeRow, TreeRow 1-N ObservationRow.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
