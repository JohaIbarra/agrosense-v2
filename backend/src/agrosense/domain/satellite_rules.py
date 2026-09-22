"""Reglas de los indices espectrales por predio (E10a).

El NDVI se calcula sobre imagenes Sentinel-2 (10 m por pixel). Las reglas que
viven aqui son las que deciden si una cifra SIGNIFICA algo y como se lee; de
donde salen los pixeles es asunto del adaptador.
"""

from __future__ import annotations

from datetime import date

from agrosense.domain.errors import DomainError

# Indices que AgroSense sabe interpretar. Ampliar esta tupla es una decision
# de dominio (que significa el numero), no solo de calculo.
SPECTRAL_INDICES: tuple[str, ...] = ("NDVI",)

# Un pixel de Sentinel-2 mide 10 x 10 m = 100 m². Por debajo de este numero de
# pixeles validos, la media del poligono es ruido de borde: una parcela de
# 20 x 20 m son cuatro pixeles, y tres de ellos tocan lo que hay al lado. Por
# eso el indice se publica POR PREDIO y no por parcela.
#
# El umbral se fijo en 25 pixeles (2 500 m²) con el dato real: el predio
# San Antonio del Anexo (69 arboles en una franja estrecha) devuelve **10**
# pixeles validos, y en una franja de un pixel de ancho TODOS son pixeles
# mezclados con lo que hay al lado. Con 10 su NDVI parecia igual de solido que
# el de Guayabal, que tiene 1 308. No lo es, y ahora se marca.
MIN_PIXELS_FOR_INDEX = 25

# Nubosidad de la escena por encima de la cual ni se pide: la mascara de
# nubes de L2A deja huecos y la media del predio deja de ser comparable.
MAX_CLOUD_COVER = 60.0

# Sentinel-2 empezo a operar en 2015; pedir antes es un error del usuario,
# no una consulta sin resultados.
FIRST_SENTINEL2_DATE = date(2015, 6, 23)

# Ventana maxima de una consulta. Cada escena es una peticion al proveedor.
MAX_RANGE_DAYS = 3 * 365


class InvalidIndexRequestError(DomainError):
    def __init__(self, message: str):
        super().__init__("INVALID_INDEX_REQUEST", message)


def validate_index(index: str) -> str:
    """Normaliza el nombre del indice, o falla.

    Raises:
        InvalidIndexRequestError: el indice no esta en el vocabulario.
    """
    limpio = (index or "").strip().upper()
    if limpio not in SPECTRAL_INDICES:
        conocidos = ", ".join(SPECTRAL_INDICES)
        raise InvalidIndexRequestError(
            f"AgroSense no calcula «{index}». Índices disponibles: {conocidos}."
        )
    return limpio


def validate_range(start: date, end: date, today: date) -> None:
    """La ventana de consulta: ordenada, no futura, no anterior a Sentinel-2.

    Raises:
        InvalidIndexRequestError
    """
    if end < start:
        raise InvalidIndexRequestError("La fecha final es anterior a la inicial.")
    if start < FIRST_SENTINEL2_DATE:
        raise InvalidIndexRequestError(
            f"Sentinel-2 no tiene imágenes anteriores al "
            f"{FIRST_SENTINEL2_DATE.isoformat()}."
        )
    if start > today:
        raise InvalidIndexRequestError("La fecha inicial está en el futuro.")
    if (end - start).days > MAX_RANGE_DAYS:
        raise InvalidIndexRequestError(
            f"La ventana no puede pasar de {MAX_RANGE_DAYS // 365} años por consulta."
        )


def is_reliable(valid_pixels: int) -> bool:
    """¿La media del polígono se sostiene, o son cuatro píxeles de borde?"""
    return valid_pixels >= MIN_PIXELS_FOR_INDEX


# Lectura del NDVI. Los cortes son los de uso general en teledeteccion; se
# nombran aqui para que la pantalla no invente su propia escala.
_NDVI_READINGS: tuple[tuple[float, str], ...] = (
    (0.0, "Sin vegetación (agua, nube o suelo desnudo)"),
    (0.2, "Suelo con vegetación escasa"),
    (0.4, "Vegetación moderada"),
    (0.6, "Vegetación densa"),
)


def ndvi_reading(value: float | None) -> str | None:
    """Qué dice un NDVI, en palabras.

    Devuelve None si no hay valor: no se interpreta lo que no se midió.
    """
    if value is None:
        return None
    etiqueta = _NDVI_READINGS[0][1]
    for corte, texto in _NDVI_READINGS:
        if value >= corte:
            etiqueta = texto
    return etiqueta
