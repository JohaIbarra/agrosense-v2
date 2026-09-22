"""Adaptador geoespacial (E6): proyeccion de coordenadas y payload del mapa."""

from __future__ import annotations

from collections.abc import Sequence

from agrosense.adapters.geo.map_payload import MAP_VERSION, build_map, property_outlines
from agrosense.adapters.geo.projection import UnsupportedSridError, to_wgs84
from agrosense.domain.entities import Observation, Tree

__all__ = [
    "MAP_VERSION",
    "MapBuilder",
    "PropertyOutlineBuilder",
    "UnsupportedSridError",
    "build_map",
    "property_outlines",
    "to_wgs84",
]


class MapBuilder:
    """Lo que el caso de uso recibe por parametro (ADR-003: sin puerto)."""

    version = MAP_VERSION

    def build(
        self, trees: Sequence[Tree], observations: Sequence[Observation], srid: int
    ) -> dict:
        return build_map(trees, observations, srid)


class PropertyOutlineBuilder:
    """Contornos de predio para el indice espectral (E10a).

    Se inyecta por parametro, como el motor de analisis y el del mapa: el caso
    de uso no importa `adapters/`.
    """

    def outlines(self, trees: Sequence[Tree], srid: int) -> dict[str, dict]:
        return property_outlines(trees, srid)
