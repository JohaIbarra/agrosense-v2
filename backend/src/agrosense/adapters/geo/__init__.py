"""Adaptador geoespacial (E6): proyeccion de coordenadas y payload del mapa."""

from __future__ import annotations

from collections.abc import Sequence

from agrosense.adapters.geo.map_payload import MAP_VERSION, build_map
from agrosense.adapters.geo.projection import UnsupportedSridError, to_wgs84
from agrosense.domain.entities import Observation, Tree

__all__ = ["MAP_VERSION", "MapBuilder", "UnsupportedSridError", "build_map", "to_wgs84"]


class MapBuilder:
    """Lo que el caso de uso recibe por parametro (ADR-003: sin puerto)."""

    version = MAP_VERSION

    def build(
        self, trees: Sequence[Tree], observations: Sequence[Observation], srid: int
    ) -> dict:
        return build_map(trees, observations, srid)
