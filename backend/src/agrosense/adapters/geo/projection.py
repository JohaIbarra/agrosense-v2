"""Proyeccion de coordenadas a WGS84 (E6).

Este es el UNICO punto del sistema que sabe de sistemas de referencia. El
dominio no conoce proyecciones: un arbol tiene `coord_x`/`coord_y` en el
sistema del proyecto (`projects.coordinate_srid`, 9377 por defecto) y el mapa
necesita latitud y longitud.

Por que pyproj y no las formulas a mano: 9377 es MAGNA-SIRGAS / Origen-Nacional
(Transverse Mercator sobre GRS80), y aunque su inversa cabe en 40 lineas, una
errata en un coeficiente mueve los arboles cientos de metros sin fallar ningun
test evidente. pyproj trae PROJ, que es la implementacion de referencia, y
ademas deja la puerta abierta a proyectos en otro sistema sin tocar el codigo.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

from pyproj import Transformer
from pyproj.exceptions import CRSError

WGS84 = 4326


class UnsupportedSridError(ValueError):
    """El sistema de coordenadas del proyecto no existe o no se puede usar."""


@lru_cache(maxsize=8)
def _transformer(srid: int) -> Transformer:
    """Un transformador por srid.

    Construirlo cuesta milisegundos y el mapa lo pide en cada lectura;
    cachearlo es la diferencia entre 40 ms y medio segundo. `Transformer` es
    inmutable y seguro entre hilos (los endpoints corren en el threadpool).
    """
    try:
        return Transformer.from_crs(f"EPSG:{srid}", f"EPSG:{WGS84}", always_xy=True)
    except CRSError as exc:
        raise UnsupportedSridError(
            f"El sistema de coordenadas EPSG:{srid} no se reconoce."
        ) from exc


def to_wgs84(points: Sequence[tuple[float, float]], srid: int) -> list[tuple[float, float]]:
    """Convierte `(x, y)` en `srid` a `(lat, lon)` en WGS84.

    En lote a proposito: proyectar 856 puntos de uno en uno cuesta ~30x mas
    que una sola llamada con dos arreglos.

    Raises:
        UnsupportedSridError: el srid no existe o PROJ no puede usarlo.
    """
    if srid == WGS84:
        # Ya esta en grados; solo cambia el orden de las componentes.
        return [(y, x) for x, y in points]
    transformer = _transformer(srid)
    if not points:
        # Validamos el srid igualmente: un proyecto mal configurado debe
        # fallar aunque hoy no tenga arboles.
        return []
    xs, ys = zip(*points, strict=True)
    lons, lats = transformer.transform(xs, ys)
    return list(zip(lats, lons, strict=True))
