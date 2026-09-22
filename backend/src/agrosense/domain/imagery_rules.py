"""Reglas de las capas de imagen de un proyecto (E6b).

Un proyecto puede llevar su propia ortofoto debajo de los arboles: una
plantilla de teselas XYZ (la que entregan OpenAerialMap, un servidor TiTiler o
la plataforma de drones del ingeniero).

Lo que se acepta es estrecho a proposito, porque la plantilla la escribe el
ingeniero y **la carga su navegador**: cada tesela es una peticion a un
tercero elegido por el usuario. Un esquema que no sea https no solo lo bloquea
el navegador en una pagina https: tambien expone en claro por donde mira el
ingeniero.
"""

from __future__ import annotations

from agrosense.domain.errors import DomainError

# Suficiente para las URL firmadas largas (S3, Azure) sin ser un campo libre
MAX_URL_LENGTH = 1000

_REQUIRED_PLACEHOLDERS = ("{z}", "{x}", "{y}")
# `{s}` exigiria declarar subdominios y `{r}` teselas retina: ninguna de las
# dos se configura hoy, y aceptarlas dejaria plantillas que no cargan nunca.
_REJECTED_PLACEHOLDERS = ("{s}", "{r}", "{a}")


class InvalidImageryLayerError(DomainError):
    def __init__(self, message: str):
        super().__init__("INVALID_IMAGERY_LAYER", message)


def validate_tile_template(template: str) -> str:
    """Devuelve la plantilla lista para guardar, o falla explicando por que.

    Raises:
        InvalidImageryLayerError: esquema, longitud o marcadores invalidos.
    """
    limpia = (template or "").strip()
    if not limpia:
        raise InvalidImageryLayerError("Escriba la dirección de las teselas.")
    if len(limpia) > MAX_URL_LENGTH:
        raise InvalidImageryLayerError(
            f"La dirección supera los {MAX_URL_LENGTH} caracteres."
        )
    if not limpia.lower().startswith("https://"):
        raise InvalidImageryLayerError(
            "La dirección debe empezar por https:// — el navegador bloquea las "
            "imágenes servidas sin cifrar."
        )
    faltan = [p for p in _REQUIRED_PLACEHOLDERS if p not in limpia]
    if faltan:
        raise InvalidImageryLayerError(
            "La plantilla debe incluir {z}, {x} e {y}, como en "
            "https://…/{z}/{x}/{y}.png. Falta: " + ", ".join(faltan) + "."
        )
    sobran = [p for p in _REJECTED_PLACEHOLDERS if p in limpia]
    if sobran:
        raise InvalidImageryLayerError(
            f"AgroSense no admite {', '.join(sobran)} en la plantilla: use una "
            "dirección con un solo servidor."
        )
    return limpia


def normalize_opacity(value: float | None) -> float:
    """Opacidad de la capa, entre 0 y 1 (por defecto, opaca).

    Se redondea a dos decimales: es un control deslizante, no una medida.

    Raises:
        InvalidImageryLayerError: fuera del rango.
    """
    if value is None:
        return 1.0
    if not 0 <= value <= 1:
        raise InvalidImageryLayerError("La opacidad va de 0 a 1.")
    return round(float(value), 2)
