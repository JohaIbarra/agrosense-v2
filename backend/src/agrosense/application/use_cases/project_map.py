"""UC-MP1: Ver el mapa del proyecto (E6).

Devuelve, en una sola lectura, los arboles ubicados en grados con su estado en
cada monitoreo, las parcelas con su contorno y sus metricas, y el encuadre.

El CONSTRUCTOR del mapa se inyecta por parametro, como el motor de analisis
(ADR-003: sin puerto donde no hay variacion real). Debe ofrecer:

    builder.version                          -> str
    builder.build(trees, observations, srid) -> dict

Autorizacion: un proyecto ajeno responde igual que uno inexistente.

Un proyecto sin cargas **no es un error**: existe y su mapa esta vacio. Es la
diferencia entre «no tiene derecho a verlo» y «todavia no hay nada que ver».
"""
from __future__ import annotations

from agrosense.application.dtos import ProjectMapDTO
from agrosense.application.errors import AppError

DEFAULT_SRID = 9377


def get_project_map(
    project_id: int,
    owner_id: str,
    project_repo,
    analysis_repo,
    map_builder,
) -> ProjectMapDTO:
    """El mapa completo del proyecto.

    Raises:
        AppError("PROJECT_NOT_FOUND"): no existe o es de otro ingeniero.
        ValueError: el proyecto declara un sistema de coordenadas desconocido
            (`UnsupportedSridError` lo hereda) → 422 en el adaptador.
    """
    project = project_repo.get_owned(project_id, owner_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", f"El proyecto {project_id} no existe.")

    trees, observations = analysis_repo.load_dataset(project_id)
    srid = getattr(project, "coordinate_srid", None) or DEFAULT_SRID
    payload = map_builder.build(trees, observations, srid)
    return ProjectMapDTO(project_id=project_id, payload=payload)
