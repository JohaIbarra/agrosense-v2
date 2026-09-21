"""Proyecto de restauracion: campos y reglas (E1, decision D7).

Pydantic solo como validador de construccion, igual que `entities.py`: un
proyecto con reglas rotas no puede existir. El contrato HTTP valida forma y
longitudes; aqui viven las reglas de NEGOCIO (vocabularios, coherencia de
fechas y cantidades), que no deben depender de quien llame.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, model_validator

from agrosense.domain.errors import DomainError

# Tipos de intervencion. El dataset de referencia es "Rehabilitacion vegetal";
# un proyecto agroforestal entra como un valor mas, sin cambiar el modelo.
INTERVENTION_TYPES = (
    "rehabilitacion",
    "restauracion_activa",
    "restauracion_pasiva",
    "enriquecimiento",
    "reforestacion",
    "agroforestal",
    "otro",
)

# Marco legal: determina que informe exige la autoridad ambiental.
LEGAL_FRAMEWORKS = (
    "compensacion_ambiental",
    "inversion_1_por_ciento",
    "plan_de_manejo",
    "voluntario",
    "otro",
)

PROJECT_STATUSES = ("activo", "cerrado")

# MAGNA-SIRGAS / Origen Nacional: sistema oficial de Colombia y el del dataset
# de referencia (confirmado en E0, ADR-005).
DEFAULT_SRID = 9377


class InvalidProjectError(DomainError):
    def __init__(self, message: str):
        super().__init__("INVALID_PROJECT", message)


class ProjectSpec(BaseModel):
    """Los datos que describen un proyecto, validados contra el dominio."""

    name: str
    contract_code: str | None = None
    objective: str | None = None
    description: str | None = None
    locality: str | None = None
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
    coordinate_srid: int = DEFAULT_SRID

    @model_validator(mode="after")
    def _reglas(self) -> ProjectSpec:
        if not self.name or not self.name.strip():
            raise InvalidProjectError("El proyecto necesita un nombre.")
        if self.intervention_type is not None and self.intervention_type not in INTERVENTION_TYPES:
            raise InvalidProjectError(
                f"Tipo de intervencion no reconocido: '{self.intervention_type}'. "
                f"Use uno de: {', '.join(INTERVENTION_TYPES)}."
            )
        if self.legal_framework is not None and self.legal_framework not in LEGAL_FRAMEWORKS:
            raise InvalidProjectError(
                f"Marco legal no reconocido: '{self.legal_framework}'. "
                f"Use uno de: {', '.join(LEGAL_FRAMEWORKS)}."
            )
        if self.status not in PROJECT_STATUSES:
            raise InvalidProjectError(
                f"Estado no reconocido: '{self.status}'. Use: {', '.join(PROJECT_STATUSES)}."
            )
        if self.area_ha is not None and self.area_ha <= 0:
            raise InvalidProjectError("El area del proyecto debe ser mayor que cero.")
        if self.planted_individuals is not None and self.planted_individuals < 0:
            raise InvalidProjectError("Los individuos plantados no pueden ser negativos.")
        if self.planting_density is not None and self.planting_density <= 0:
            raise InvalidProjectError("La densidad de plantacion debe ser mayor que cero.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise InvalidProjectError(
                "La fecha de finalizacion no puede ser anterior a la de inicio."
            )
        if self.coordinate_srid <= 0:
            raise InvalidProjectError("El sistema de coordenadas (SRID) no es valido.")
        return self
