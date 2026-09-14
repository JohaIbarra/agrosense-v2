"""Entidades de dominio (docs/02-domain.md).

Pydantic SOLO como validador de construccion (decision ADR-003): garantiza
que una Observation/Tree invalido no pueda existir. No hay logica de DB ni
de API aqui.
"""
from enum import Enum

from pydantic import BaseModel, field_validator

from agrosense.domain.errors import NegativeMeasurementError


class StatusSemantic(str, Enum):
    """Semantica de los datos faltantes del formato de campo.

    Descubierta en el dataset real: DAP=0.0 en 714/717 casos de M1 es un
    MARCADOR de 'no alcanza umbral', no una medicion. Nunca imputar (la
    senal esta en el estado, no en el valor).
    """

    SIN_CENSO = "sin_censo"
    BAJO_UMBRAL_DAP = "bajo_umbral_dap"
    MEDIDO = "medido"


class Observation(BaseModel):
    """Estado de un arbol en una campana de monitoreo (nucleo del dominio)."""

    tree_id: str
    campaign: int
    height_m: float | None
    crown_diameter_m: float | None
    dap_cm: float | None
    dap_status: StatusSemantic
    phytosanitary: str | None
    alive: bool | None
    colonization: str | None

    @field_validator("tree_id")
    @classmethod
    def tree_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("tree_id no puede estar vacio")
        return v.strip()

    @field_validator("campaign")
    @classmethod
    def campaign_in_range(cls, v: int) -> int:
        if not 1 <= v <= 4:
            raise ValueError(f"campaign debe ser 1-4, recibido {v}")
        return v

    @field_validator("height_m", "crown_diameter_m", "dap_cm")
    @classmethod
    def measurement_not_negative(cls, v, info):
        if v is not None and v < 0:
            raise NegativeMeasurementError(
                info.field_name, v, tree_id="?", campaign=0
            )
        return v


class Tree(BaseModel):
    """Un individuo plantado en un proyecto; identidad persistente."""

    tree_id: str
    species: str
    family: str | None = None
    common_name: str | None = None
    guild: str | None = None
    plot_id: str | None = None
    locality: str | None = None
    coord_x: float | None = None
    coord_y: float | None = None
    elevation_m: float | None = None

    @field_validator("tree_id", "species")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("identidad del arbol no puede estar vacia")
        return v.strip()
