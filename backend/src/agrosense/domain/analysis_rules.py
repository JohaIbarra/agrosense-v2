"""Definiciones del analisis exploratorio por monitoreo (E3).

Aqui viven las REGLAS («que es una plantula», «que estados fitosanitarios
existen», «desde cuantos arboles un porcentaje dice algo»). La AGREGACION
(agrupar 856 arboles por especie x diseno) vive en `adapters/analysis/` con
pandas: la regla de negocio no depende de la libreria (docs/04 §7).

Fuente: las hojas del Anexo 1, que son el analisis que el ingeniero hace a
mano. Donde el Anexo no define algo, se dice y no se inventa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from agrosense.domain.errors import DomainError

# ── Categoria de desarrollo (hoja «Edades», bloque «ELABORACIÓN DEL RANGO») ──


@dataclass(frozen=True)
class DevelopmentClass:
    name: str
    upper_m: float | None  # limite superior INCLUSIVO; None = sin techo


# El Anexo escribe los rangos con dos decimales (0,01–0,5 · 0,51–3 · 3,1–6).
# Con alturas continuas eso deja huecos (0,505 m); se cierran tomando el
# limite superior como inclusivo y el inferior como exclusivo.
#
# El Anexo nombra ademas Subadulto, Adulto I y Adulto II, pero SIN rango (sus
# columnas estan en cero). Inventar umbrales seria presentar una convencion
# nuestra como si fuera del ingeniero: todo lo que supera 6 m cae en una sola
# clase explicita hasta que se definan.
DEVELOPMENT_CLASSES: tuple[DevelopmentClass, ...] = (
    DevelopmentClass("Plántula", 0.5),
    DevelopmentClass("Juvenil I", 3.0),
    DevelopmentClass("Juvenil II", 6.0),
    DevelopmentClass("Mayor de 6 m", None),
)


def development_class(height_m: float | None) -> str | None:
    """Clase de desarrollo de un arbol vivo segun su altura total.

    None si no hay altura o es 0: el Anexo cuenta la altura 0 como «Muertos»,
    y quien decide si el arbol esta muerto es su estado, no su altura.
    """
    if height_m is None or height_m <= 0:
        return None
    for cls in DEVELOPMENT_CLASSES:
        if cls.upper_m is None or height_m <= cls.upper_m:
            return cls.name
    return None  # inalcanzable: la ultima clase no tiene techo


# ── Estado fitosanitario ─────────────────────────────────────────────────────

PHYTOSANITARY_STATES: tuple[str, ...] = ("Bueno", "Regular", "Malo")
_PHYTO_BY_KEY = {s.casefold(): s for s in PHYTOSANITARY_STATES}


def normalize_phytosanitary(raw: str | None) -> str | None:
    """Estado del vocabulario, o None si esta en blanco o no se reconoce.

    El M2 del dataset real trae celdas con un espacio: son blancos de campo,
    no un cuarto estado.
    """
    if raw is None:
        return None
    return _PHYTO_BY_KEY.get(str(raw).strip().casefold())


# ── Estado de un arbol en un monitoreo ───────────────────────────────────────

# De mejor a peor, y al final lo que no es un estado sino una ausencia. El
# orden importa: es el de la leyenda y el de cualquier tabla que los ordene.
TREE_STATES: tuple[str, ...] = ("bueno", "regular", "malo", "muerto", "sin_dato")


def tree_state(alive: bool | None, phytosanitary: str | None) -> str:
    """En que estado esta el arbol, en una sola palabra.

    Un arbol muerto es "muerto" aunque la fila traiga estado fitosanitario:
    en campo esa celda suele quedar con el valor del monitoreo anterior, y
    pintarlo de verde seria afirmar algo que el dato no dice. Si no consta si
    vive, tampoco se deduce su estado.
    """
    if alive is None:
        return "sin_dato"
    if not alive:
        return "muerto"
    estado = normalize_phytosanitary(phytosanitary)
    return estado.casefold() if estado else "sin_dato"


# ── Tamano minimo de muestra ─────────────────────────────────────────────────

# Por debajo de este numero de arboles, un porcentaje (supervivencia, estado
# fitosanitario) se muestra MARCADO: «50 %» con 2 arboles no es un hallazgo.
# Riesgo registrado en docs/04-vision-producto.md §14.
MIN_SAMPLE_FOR_PERCENT = 5


def is_low_sample(n: int) -> bool:
    return n < MIN_SAMPLE_FOR_PERCENT


# ── Fechas de monitoreo ──────────────────────────────────────────────────────


class InvalidMonitoringDateError(DomainError):
    def __init__(self, message: str):
        super().__init__("INVALID_MONITORING_DATE", message)


def validate_monitoring_date(
    number: int,
    new_date: date,
    known_dates: dict[int, date],
    today: date,
) -> None:
    """Las fechas crecen con el numero de monitoreo y no estan en el futuro.

    `known_dates` son las fechas ya registradas del proyecto ({numero: fecha});
    la del propio monitoreo se ignora porque es la que se esta cambiando.
    Sin fechas coherentes no se puede anualizar el crecimiento, que es el
    motivo por el que la fecha existe (ADR-005).
    """
    if new_date > today:
        raise InvalidMonitoringDateError(
            f"La fecha del M{number} ({new_date:%d/%m/%Y}) esta en el futuro."
        )
    for other, other_date in known_dates.items():
        if other < number and other_date >= new_date:
            raise InvalidMonitoringDateError(
                f"La fecha del M{number} ({new_date:%d/%m/%Y}) debe ser posterior a "
                f"la del M{other} ({other_date:%d/%m/%Y})."
            )
        if other > number and other_date <= new_date:
            raise InvalidMonitoringDateError(
                f"La fecha del M{number} ({new_date:%d/%m/%Y}) debe ser anterior a "
                f"la del M{other} ({other_date:%d/%m/%Y})."
            )
