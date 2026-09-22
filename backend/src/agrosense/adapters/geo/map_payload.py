"""Payload del mapa del predio (E6).

Arma de una vez TODO lo que la pantalla necesita: los arboles con su estado y
su altura en cada monitoreo, las parcelas con su contorno y sus metricas, y la
extension para encuadrar. Un solo viaje: con 856 arboles y cuatro monitoreos
el payload pesa ~250 KB, y a cambio la linea de tiempo se mueve sin pedir
nada al servidor.

Como en E3, la pagina NO calcula: recibe el estado ya decidido por el dominio
(`tree_state`) y los porcentajes ya hechos. Aqui no hay snapshot en base de
datos porque no hace falta — derivar esto cuesta ~40 ms y siempre refleja los
datos actuales; guardarlo solo anadiria una copia que invalidar.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from agrosense.adapters.geo.projection import to_wgs84
from agrosense.domain.analysis_rules import MIN_SAMPLE_FOR_PERCENT, is_low_sample, tree_state
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.rules import plot_key

MAP_VERSION = "2026-09-22-e6.1"

__all__ = ["MAP_VERSION", "build_map"]


def _convex_hull(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Contorno de un conjunto de puntos (monotone chain de Andrew).

    Con uno o dos puntos devuelve los puntos tal cual: una parcela de dos
    arboles no tiene area, y dibujar un triangulo inventado seria afirmar una
    superficie que nadie midio.
    """
    unicos = sorted(set(points))
    if len(unicos) <= 2:
        return unicos

    def _media_vuelta(orden: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
        cadena: list[tuple[float, float]] = []
        for p in orden:
            while len(cadena) >= 2 and _cruz(cadena[-2], cadena[-1], p) <= 0:
                cadena.pop()
            cadena.append(p)
        return cadena

    inferior = _media_vuelta(unicos)
    superior = _media_vuelta(reversed(unicos))
    # El ultimo de cada media vuelta es el primero de la otra
    return inferior[:-1] + superior[:-1]


def _cruz(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def build_map(
    trees: Sequence[Tree], observations: Sequence[Observation], srid: int
) -> dict:
    """Todo el mapa de un proyecto, en un diccionario serializable.

    Args:
        trees: arboles del proyecto (con o sin coordenada).
        observations: todas sus observaciones, de todos los monitoreos.
        srid: sistema de coordenadas del PROYECTO (no del arbol).

    Raises:
        UnsupportedSridError: el proyecto declara un srid que PROJ no conoce.
    """
    numbers = sorted({o.campaign for o in observations})
    ubicados = [t for t in trees if t.coord_x is not None and t.coord_y is not None]
    sin_coordenada = len(trees) - len(ubicados)

    coords = to_wgs84([(t.coord_x, t.coord_y) for t in ubicados], srid)
    por_arbol: dict[str, list[Observation]] = {}
    for o in observations:
        por_arbol.setdefault(o.tree_id, []).append(o)

    puntos: list[dict] = []
    for t, (lat, lon) in zip(ubicados, coords, strict=True):
        suyas = {o.campaign: o for o in por_arbol.get(t.tree_id, [])}
        puntos.append(
            {
                "id": t.tree_id,
                "species": t.species,
                "property": t.locality,
                "plot": t.plot_id,
                "plot_key": plot_key(t),
                "lat": round(lat, 7),  # ~1 cm: mas decimales son ruido del GPS
                "lon": round(lon, 7),
                "elevation_m": t.elevation_m,
                "states": {
                    str(n): tree_state(o.alive, o.phytosanitary) for n, o in sorted(suyas.items())
                },
                "heights": {str(n): o.height_m for n, o in sorted(suyas.items())},
            }
        )

    return {
        "version": MAP_VERSION,
        "srid": srid,
        "monitorings": numbers,
        "properties": sorted({t["property"] for t in puntos if t["property"]}),
        "bounds": _bounds(puntos),
        "without_coordinates": sin_coordenada,
        "trees": puntos,
        "plots": _plots(puntos, por_arbol, numbers),
    }


def _bounds(puntos: list[dict]) -> dict | None:
    """Extension que encuadra el mapa, o None si no hay nada que encuadrar."""
    if not puntos:
        return None
    lats = [p["lat"] for p in puntos]
    lons = [p["lon"] for p in puntos]
    return {"south": min(lats), "west": min(lons), "north": max(lats), "east": max(lons)}


def _plots(
    puntos: list[dict], por_arbol: dict[str, list[Observation]], numbers: list[int]
) -> list[dict]:
    """Una entrada por parcela: contorno, centroide y metricas por monitoreo.

    Las metricas son las mismas del analisis de E3 (supervivencia = vivos /
    censados, altura media de los vivos), calculadas sobre los arboles que
    tienen coordenada: es lo que el mapa puede dibujar honestamente.
    """
    agrupadas: dict[str, list[dict]] = {}
    for p in puntos:
        if p["plot_key"]:
            agrupadas.setdefault(p["plot_key"], []).append(p)

    parcelas = []
    for clave, suyos in sorted(agrupadas.items()):
        hull = _convex_hull([(p["lat"], p["lon"]) for p in suyos])
        metricas = {}
        for n in numbers:
            estados = [p["states"].get(str(n)) for p in suyos]
            censados = [e for e in estados if e is not None]
            if not censados:
                continue
            vivos = [e for e in censados if e != "muerto"]
            alturas = [
                h
                for p in suyos
                if (h := p["heights"].get(str(n))) is not None
                and p["states"].get(str(n)) != "muerto"
            ]
            metricas[str(n)] = {
                "n": len(censados),
                "survival": round(100 * len(vivos) / len(censados), 4),
                "mean_height": _mean(alturas),
            }
        parcelas.append(
            {
                "key": clave,
                "property": suyos[0]["property"],
                "plot": suyos[0]["plot"],
                "n": len(suyos),
                "low_sample": is_low_sample(len(suyos)),
                "centroid": {
                    "lat": round(sum(p["lat"] for p in suyos) / len(suyos), 7),
                    "lon": round(sum(p["lon"] for p in suyos) / len(suyos), 7),
                },
                "hull": [[lat, lon] for lat, lon in hull],
                "metrics": metricas,
            }
        )
    return parcelas


# Re-exportado para que quien lea el payload sepa de donde sale la marca
MIN_TREES_FOR_PLOT_METRIC = MIN_SAMPLE_FOR_PERCENT
