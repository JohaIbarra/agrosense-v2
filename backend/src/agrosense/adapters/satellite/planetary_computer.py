"""Indices espectrales de Sentinel-2 vía Microsoft Planetary Computer (E10a).

Por que este proveedor: sirve el catalogo STAC de Sentinel-2 L2A y calcula
estadisticos por poligono **sin cuenta, sin clave y sin GDAL**. La alternativa
—descargar el COG y abrirlo con rasterio— habria metido ~60 MB de GDAL en el
backend para leer un recorte de 65 x 91 pixeles.

Lo que hace este adaptador y nada mas: hablar HTTP con el proveedor y traducir
su respuesta a los DTO del puerto. Que significa un NDVI de 0,48 o cuantos
pixeles hacen falta para creerselo son reglas de dominio
(`domain/satellite_rules.py`).

Fallos de red: el proveedor es un tercero gratuito y la maquina de campo tiene
DNS intermitente (documentado en verificacion-e1). Por eso hay timeout corto,
un reintento y un error de aplicacion claro — nunca una excepcion de urllib
saliendo por la API.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

from agrosense.application.dtos import SatelliteScene, SceneStatistics
from agrosense.application.errors import AppError

logger = logging.getLogger(__name__)

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
DATA_URL = "https://planetarycomputer.microsoft.com/api/data/v1/item/statistics"
COLLECTION = "sentinel-2-l2a"

# Expresiones por indice, en las bandas de Sentinel-2 L2A. Vive aqui porque
# los nombres de banda son del sensor, no del dominio.
_EXPRESSIONS = {"NDVI": "(B08-B04)/(B08+B04)"}

_TIMEOUT = 45
_RETRIES = 2
_USER_AGENT = "AgroSense/2.0 (+restauracion ecologica)"


def _post(url: str, body: dict, timeout: int = _TIMEOUT) -> dict:
    """POST JSON con un reintento. Traduce cualquier fallo a AppError."""
    ultimo: Exception | None = None
    for intento in range(_RETRIES):
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return json.load(response)
        except urllib.error.HTTPError as exc:
            # 4xx es culpa nuestra (pedimos algo imposible): no se reintenta
            if 400 <= exc.code < 500:
                logger.warning("Planetary Computer rechazo la peticion (%s)", exc.code)
                raise AppError(
                    "SATELLITE_UNAVAILABLE",
                    "El proveedor de imágenes rechazó la consulta. "
                    "Pruebe con otro rango de fechas.",
                ) from exc
            ultimo = exc
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            ultimo = exc
        if intento + 1 < _RETRIES:
            time.sleep(1.5)
    logger.warning("Planetary Computer no respondio: %s", ultimo)
    raise AppError(
        "SATELLITE_UNAVAILABLE",
        "No se pudo consultar las imágenes satelitales ahora mismo. "
        "Vuelva a intentarlo en unos minutos.",
    )


def _acquired(texto: str) -> date:
    """`2024-12-18T15:26:59.024000Z` → 2024-12-18."""
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).date()


class PlanetaryComputerIndexSource:
    """Implementacion del puerto `SatelliteIndexSource`."""

    name = "planetary-computer/sentinel-2-l2a"

    def search_scenes(
        self,
        bbox: tuple[float, float, float, float],
        start: date,
        end: date,
        max_cloud: float,
        limit: int,
    ) -> list[SatelliteScene]:
        cuerpo = {
            "collections": [COLLECTION],
            "bbox": list(bbox),
            "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
            "limit": limit,
            "query": {"eo:cloud_cover": {"lt": max_cloud}},
            "sortby": [{"field": "properties.datetime", "direction": "desc"}],
        }
        datos = _post(STAC_URL, cuerpo)
        escenas = []
        for item in datos.get("features", []):
            props = item.get("properties", {})
            fecha = props.get("datetime")
            if not fecha:
                continue
            escenas.append(
                SatelliteScene(
                    scene_id=item["id"],
                    acquired_at=_acquired(fecha),
                    cloud_cover=props.get("eo:cloud_cover"),
                )
            )
        # El proveedor puede devolver varias escenas del mismo dia (orbitas
        # solapadas): nos quedamos con la primera de cada fecha, que es la
        # menos nubosa por el orden de la consulta.
        vistas: dict[date, SatelliteScene] = {}
        for escena in escenas:
            vistas.setdefault(escena.acquired_at, escena)
        return sorted(vistas.values(), key=lambda e: e.acquired_at, reverse=True)

    def index_statistics(
        self, scene_id: str, polygon: list[list[float]], index: str
    ) -> SceneStatistics | None:
        expresion = _EXPRESSIONS.get(index)
        if expresion is None:
            raise AppError(
                "SATELLITE_UNAVAILABLE", f"Este proveedor no calcula el índice {index}."
            )
        consulta = urllib.parse.urlencode(
            {
                "collection": COLLECTION,
                "item": scene_id,
                "assets": "B04",
                "asset_as_band": "true",
                "expression": expresion,
            }
        )
        # GeoJSON va en (lon, lat); el resto del sistema usa (lat, lon)
        anillo = [[lon, lat] for lat, lon in polygon]
        if anillo[0] != anillo[-1]:
            anillo.append(anillo[0])
        feature = {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [anillo]},
        }
        datos = _post(f"{DATA_URL}?{consulta}", feature)
        estadisticos = datos.get("properties", {}).get("statistics", {})
        valores = estadisticos.get(expresion)
        if not valores:
            return None
        cuenta = int(valores.get("count") or 0)
        media = valores.get("mean")
        if not cuenta or media is None:
            # Poligono fuera de la escena, o todo enmascarado por nubes
            return None
        return SceneStatistics(
            mean=float(media),
            median=_float(valores.get("median")),
            minimum=_float(valores.get("min")),
            maximum=_float(valores.get("max")),
            std=_float(valores.get("std")),
            valid_pixels=cuenta,
        )


def _float(value) -> float | None:
    return None if value is None else float(value)
