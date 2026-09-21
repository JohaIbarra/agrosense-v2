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
    """Estado de un arbol en un monitoreo (nucleo del dominio).

    `campaign` es el NUMERO de monitoreo dentro del proyecto (M1 = 1, M2 = 2…).
    La base de datos lo traduce a una fila de `monitorings`; el dominio no
    necesita saberlo.
    """

    tree_id: str
    campaign: int
    height_m: float | None
    crown_diameter_m: float | None
    dap_cm: float | None
    dap_status: StatusSemantic
    phytosanitary: str | None
    alive: bool | None
    colonization: str | None
    # Nota de campo de la visita (columna `Observa`)
    field_notes: str | None = None

    @field_validator("tree_id")
    @classmethod
    def tree_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("tree_id no puede estar vacio")
        return v.strip()

    @field_validator("campaign")
    @classmethod
    def campaign_is_positive(cls, v: int) -> int:
        """Los monitoreos se numeran desde 1 y SIN techo.

        Hasta E0 el validador cortaba en 4 porque el dataset de referencia
        tiene cuatro monitoreos; el quinto de cualquier proyecto habria sido
        rechazado como dato invalido.
        """
        if v < 1:
            raise ValueError(f"el numero de monitoreo empieza en 1, recibido {v}")
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
    """Un individuo plantado en un proyecto; identidad persistente.

    Ademas de sus datos propios, transporta los atributos de su PARCELA tal
    como llegan del archivo de campo. En el dataset de referencia todos ellos
    son constantes dentro de cada unidad de muestreo (verificado en E0), asi
    que la base de datos los normaliza en `plots`; aqui solo viajan para que
    no se pierdan entre la lectura y la persistencia.
    """

    tree_id: str
    species: str
    family: str | None = None
    common_name: str | None = None
    guild: str | None = None
    plot_id: str | None = None  # `ID Parcela`
    locality: str | None = None  # `LOCALIDAD` = predio
    coord_x: float | None = None
    coord_y: float | None = None
    elevation_m: float | None = None

    # Atributos de la parcela (E0)
    sampling_unit_code: str | None = None  # `Codigo de unidad muestreo`
    monitoring_unit: str | None = None  # `Unidad de monitoreo`
    floristic_design: str | None = None  # `Diseño florístico`
    associated_cover: str | None = None  # `Cobertura vegetal asociada`
    establishment_cover: str | None = None  # `Cobertura donde se establecio…`

    @field_validator("tree_id", "species")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("identidad del arbol no puede estar vacia")
        return v.strip()
