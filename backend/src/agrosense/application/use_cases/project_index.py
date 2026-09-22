"""UC-I2: Indices espectrales por predio (E10a).

El ingeniero pide el NDVI de sus predios; AgroSense busca las escenas de
Sentinel-2 sobre el poligono de lo plantado, calcula la estadistica de cada
predio y la guarda con su procedencia.

Dos decisiones que se ven en el codigo:

1. **Idempotente.** Lo que ya se midio no se vuelve a pedir: la clave es
   (predio, escena). Repetir la consulta solo trae lo que falta.
2. **Nunca falla del todo.** Si el proveedor deja de responder a mitad, se
   guarda lo conseguido y se informa cuantas escenas quedaron sin medir. Una
   lectura parcial de una serie temporal sigue siendo util; perder las diez
   anteriores porque la undecima fallo, no.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date

from agrosense.application.dtos import IndexReading, ProjectIndexDTO
from agrosense.application.errors import AppError
from agrosense.domain.satellite_rules import (
    MAX_CLOUD_COVER,
    is_reliable,
    ndvi_reading,
    validate_index,
    validate_range,
)

logger = logging.getLogger(__name__)

# Cada escena cuesta una peticion por predio contra un servicio gratuito de un
# tercero. Con tres predios, seis escenas ya son dieciocho peticiones: el tope
# esta puesto para que una consulta no se convierta en una descarga masiva.
DEFAULT_MAX_SCENES = 6
MAX_SCENES_LIMIT = 24


def _owned_project(project_repo, project_id: int, owner_id: str):
    project = project_repo.get_owned(project_id, owner_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", f"El proyecto {project_id} no existe.")
    return project


def _polygon_hash(polygon: list[list[float]]) -> str:
    """Huella del contorno: ata la lectura al poligono que la produjo."""
    return hashlib.sha256(json.dumps(polygon, sort_keys=True).encode()).hexdigest()


def _to_reading(row) -> IndexReading:
    return IndexReading(
        property_name=row.property_name,
        index=row.index_name,
        scene_id=row.scene_id,
        acquired_at=row.acquired_at,
        cloud_cover=row.cloud_cover,
        mean=row.mean_value,
        median=row.median_value,
        minimum=row.min_value,
        maximum=row.max_value,
        std=row.std_value,
        valid_pixels=row.valid_pixels,
        reliable=is_reliable(row.valid_pixels),
        reading=ndvi_reading(row.mean_value) if row.index_name == "NDVI" else None,
        source=row.source,
    )


def get_project_index(
    project_id: int, owner_id: str, index: str, project_repo, index_repo
) -> ProjectIndexDTO:
    """La serie guardada del indice, sin salir a la red.

    Raises:
        AppError("PROJECT_NOT_FOUND")
        InvalidIndexRequestError: indice fuera del vocabulario (→ 422).
    """
    _owned_project(project_repo, project_id, owner_id)
    nombre = validate_index(index)
    filas = index_repo.list_for_project(project_id, nombre)
    lecturas = [_to_reading(f) for f in filas]
    return ProjectIndexDTO(
        project_id=project_id,
        index=nombre,
        properties=sorted({r.property_name for r in lecturas}),
        readings=lecturas,
        last_refreshed_at=max((f.computed_at for f in filas), default=None),
    )


def refresh_project_index(
    project_id: int,
    owner_id: str,
    index: str,
    start: date,
    end: date,
    today: date,
    project_repo,
    analysis_repo,
    index_repo,
    source,
    outline_builder,
    max_scenes: int = DEFAULT_MAX_SCENES,
) -> tuple[ProjectIndexDTO, dict]:
    """Busca escenas nuevas y mide el indice en cada predio.

    Devuelve la serie completa y un resumen de lo que hizo esta consulta.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "NO_COORDINATES" | "SATELLITE_UNAVAILABLE")
        InvalidIndexRequestError: indice o ventana invalidos (→ 422).
    """
    project = _owned_project(project_repo, project_id, owner_id)
    nombre = validate_index(index)
    validate_range(start, end, today)
    tope = max(1, min(max_scenes, MAX_SCENES_LIMIT))

    trees, _ = analysis_repo.load_dataset(project_id)
    srid = getattr(project, "coordinate_srid", None) or 9377
    contornos = outline_builder.outlines(trees, srid)
    if not contornos:
        raise AppError(
            "NO_COORDINATES",
            "El proyecto no tiene árboles con coordenadas: sin ellas no se "
            "puede ubicar el predio en la imagen satelital.",
        )

    bbox = _project_bbox(contornos)
    escenas = source.search_scenes(bbox, start, end, MAX_CLOUD_COVER, tope)
    conocidas = index_repo.known_scenes(project_id, nombre)

    lecturas: list[dict] = []
    sin_dato = 0
    interrumpido = False
    for escena in escenas:
        for predio, contorno in contornos.items():
            if (predio, escena.scene_id) in conocidas:
                continue
            try:
                stats = source.index_statistics(escena.scene_id, contorno["hull"], nombre)
            except AppError:
                # El proveedor se cayo a mitad: se guarda lo logrado
                logger.warning(
                    "Consulta de %s interrumpida en la escena %s", nombre, escena.scene_id
                )
                interrumpido = True
                break
            if stats is None:
                sin_dato += 1
                continue
            lecturas.append(
                {
                    "property_name": predio,
                    "index_name": nombre,
                    "scene_id": escena.scene_id,
                    "acquired_at": escena.acquired_at,
                    "cloud_cover": escena.cloud_cover,
                    "mean_value": stats.mean,
                    "median_value": stats.median,
                    "min_value": stats.minimum,
                    "max_value": stats.maximum,
                    "std_value": stats.std,
                    "valid_pixels": stats.valid_pixels,
                    "source": getattr(source, "name", "desconocido"),
                    "polygon_hash": _polygon_hash(contorno["hull"]),
                }
            )
        if interrumpido:
            break

    guardadas = index_repo.save_readings(project_id, lecturas)
    resumen = {
        "scenes_found": len(escenas),
        "readings_added": guardadas,
        "without_data": sin_dato,
        "interrupted": interrumpido,
        "properties": sorted(contornos),
    }
    if interrumpido and not guardadas and not conocidas:
        # No se logro nada y no habia nada antes: decirlo como fallo, no como
        # un resultado vacio que parece «no hay imagenes».
        raise AppError(
            "SATELLITE_UNAVAILABLE",
            "No se pudo consultar las imágenes satelitales ahora mismo. "
            "Vuelva a intentarlo en unos minutos.",
        )
    return get_project_index(project_id, owner_id, nombre, project_repo, index_repo), resumen


def _project_bbox(contornos: dict[str, dict]) -> tuple[float, float, float, float]:
    """Caja que cubre todos los predios, en (oeste, sur, este, norte)."""
    cajas = [c["bbox"] for c in contornos.values()]
    return (
        min(b[0] for b in cajas),
        min(b[1] for b in cajas),
        max(b[2] for b in cajas),
        max(b[3] for b in cajas),
    )
