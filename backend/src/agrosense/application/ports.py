"""Puertos: lo que `application/` necesita del mundo exterior (ADR-003).

Structural typing (`typing.Protocol`), no herencia: el adapter no importa
nada de aqui, solo cumple la forma. Cero coste en runtime.

Por que este puerto SI y no uno por repositorio: ADR-003 admite interfaz
"solo donde hoy hay variacion real". El formato de upload la tiene y esta
documentada — discovery seccion 2 y UC2 (docs/02-domain.md) dicen
**CSV/XLSX**, y hoy solo existe XLSX. Los repositorios siguen inyectandose
por parametro sin interfaz, como decidio el ADR.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol

from agrosense.application.dtos import CampaignData, SatelliteScene, SceneStatistics


class CampaignSource(Protocol):
    """Traduce el archivo crudo que sube el ingeniero a entidades de dominio.

    El implementador es duenno del formato (Excel, CSV, ...) y de sus
    librerias (pandas vive de ese lado). Tambien es quien valida los
    invariantes de dominio antes de devolver: si la campana es invalida,
    no se devuelve a medias.
    """

    def read(self, content: bytes, filename: str) -> CampaignData:
        """Parsea `content` a una campana canonica.

        Raises:
            ValueError: con prefijo INVALID_FILE si el archivo es ilegible.
            DomainError: si un invariante duro falla (campana rechazada
                completa, sin persistencia parcial — ADR-004).
        """
        ...


class SatelliteIndexSource(Protocol):
    """Proveedor de indices espectrales sobre imagenes satelitales (E10a).

    Este puerto SI existe, y por la razon que pide ADR-003: hay variacion real
    y demostrada. Hoy lo cumple Planetary Computer (gratis, sin cuenta), pero
    el mismo calculo lo sirven Sentinel Hub, Copernicus y un TiTiler propio, y
    cual se use depende de quien despliegue. Ademas es la unica dependencia de
    RED del sistema: sin puerto, los tests tendrian que salir a internet.
    """

    name: str

    def search_scenes(
        self,
        bbox: tuple[float, float, float, float],
        start: date,
        end: date,
        max_cloud: float,
        limit: int,
    ) -> list[SatelliteScene]:
        """Escenas disponibles sobre `bbox` (WGS84), de la mas reciente atras.

        Raises:
            AppError("SATELLITE_UNAVAILABLE"): el proveedor no responde.
        """
        ...

    def index_statistics(
        self, scene_id: str, polygon: list[list[float]], index: str
    ) -> SceneStatistics | None:
        """Estadisticos del indice dentro del poligono `[[lat, lon], ...]`.

        Devuelve None si la escena no cubre el poligono o no quedan pixeles
        validos tras la mascara de nubes: no hay dato, y eso no es un error.

        Raises:
            AppError("SATELLITE_UNAVAILABLE"): el proveedor no responde.
        """
        ...
