"""Contrato del slice 2 (fuente de verdad — AGENTS.md).

FastAPI expone esto como OpenAPI; el frontend genera sus tipos de aqui.
Los tipos de error/warning documentan los rulings del dominio (slice 1).
"""
from datetime import datetime

from pydantic import BaseModel, Field


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
    type: str = Field(pattern="^(contraction|revival|census_gap)$")
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
    deaths: int
    warnings: list[WarningItem]
    errors: list[ErrorItem]


class CampaignResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    mapping_version: str
    ingested_at: datetime
    trees: int
    observations: int
    deaths: int


class TreeRowResponse(BaseModel):
    tree_id: str
    species: str
    family: str | None
    common_name: str | None
    guild: str | None
    locality: str | None
    elevation_m: float | None
