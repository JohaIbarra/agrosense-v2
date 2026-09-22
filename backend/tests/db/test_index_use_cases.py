"""Casos de uso del índice espectral (E10a) contra SQLite, con un proveedor
falso: aquí se prueba la política —qué se pide, qué se guarda, qué pasa cuando
el proveedor falla—, no la red.
"""

from datetime import date

import pytest

from agrosense.adapters.db.repository import (
    CampaignRepository,
    ProjectAnalysisRepository,
    ProjectRepository,
    SatelliteIndexRepository,
)
from agrosense.adapters.geo import property_outlines
from agrosense.application.dtos import CampaignData, SatelliteScene, SceneStatistics
from agrosense.application.errors import AppError
from agrosense.application.use_cases.project_index import (
    get_project_index,
    refresh_project_index,
)
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from tests.auth.keys import ENGINEER_A as OWNER

HOY = date(2026, 9, 22)
DESDE, HASTA = date(2024, 1, 1), date(2024, 12, 31)
X0, Y0 = 4735700.0, 2199400.0


class _Outlines:
    """El constructor de contornos, inyectado igual que el motor de análisis."""

    def outlines(self, trees, srid):
        return property_outlines(trees, srid)


class _FakeSource:
    def __init__(self, escenas, stats=None, falla_en=None):
        self.name = "proveedor-de-prueba"
        self._escenas = escenas
        self._stats = stats if stats is not None else SceneStatistics(
            mean=0.48, median=0.49, minimum=0.27, maximum=0.62, std=0.05, valid_pixels=2952
        )
        self._falla_en = falla_en
        self.pedidos: list[tuple[str, str]] = []
        self.busquedas: list[tuple] = []

    def search_scenes(self, bbox, start, end, max_cloud, limit):
        self.busquedas.append((bbox, start, end, max_cloud, limit))
        return self._escenas[:limit]

    def index_statistics(self, scene_id, polygon, index):
        self.pedidos.append((scene_id, index))
        if self._falla_en and scene_id == self._falla_en:
            raise AppError("SATELLITE_UNAVAILABLE", "El proveedor no responde.")
        return self._stats


def _campaign(predios=("Guayabal", "Tres Jotas")):
    trees, obs = [], []
    for p, predio in enumerate(predios):
        for i in range(4):
            tid = f"{predio[:2]}-{i}"
            trees.append(
                Tree(
                    tree_id=tid,
                    species="Senna viarum",
                    locality=predio,
                    plot_id="11",
                    sampling_unit_code=f"{predio}/11",
                    coord_x=X0 + 200 * p + 30 * i,
                    coord_y=Y0 + 200 * p + 30 * (i % 2),
                )
            )
            obs.append(
                Observation(
                    tree_id=tid, campaign=1, height_m=0.5, crown_diameter_m=None,
                    dap_cm=None, dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
                    phytosanitary="Bueno", alive=True, colonization=None,
                )
            )
    return CampaignData(trees=trees, observations=obs, mapping_version="t")


@pytest.fixture()
def proyecto(session):
    p = ProjectRepository(session).create("NDVI", owner_id=OWNER)
    CampaignRepository(session).save_ingest(p.id, _campaign(), "a.xlsx", "h" * 64)
    return p


@pytest.fixture()
def repos(session):
    return {
        "project_repo": ProjectRepository(session),
        "analysis_repo": ProjectAnalysisRepository(session),
        "index_repo": SatelliteIndexRepository(session),
        "outline_builder": _Outlines(),
    }


ESCENAS = [
    SatelliteScene("S2_2024_12", date(2024, 12, 18), 12.0),
    SatelliteScene("S2_2024_06", date(2024, 6, 10), 30.0),
]


def _refresh(proyecto, repos, source, **kw):
    return refresh_project_index(
        proyecto.id, OWNER, "NDVI", DESDE, HASTA, HOY, source=source, **repos, **kw
    )


def test_mide_cada_predio_en_cada_escena(proyecto, repos):
    source = _FakeSource(ESCENAS)
    dto, resumen = _refresh(proyecto, repos, source)

    assert resumen["scenes_found"] == 2
    assert resumen["readings_added"] == 4  # 2 escenas x 2 predios
    assert dto.properties == ["Guayabal", "Tres Jotas"]
    assert len(dto.readings) == 4
    assert len(source.pedidos) == 4


def test_la_lectura_trae_su_interpretacion_y_su_procedencia(proyecto, repos):
    dto, _ = _refresh(proyecto, repos, _FakeSource(ESCENAS))
    lectura = dto.readings[0]
    assert lectura.mean == pytest.approx(0.48)
    assert "moderada" in lectura.reading
    assert lectura.reliable is True
    assert lectura.source == "proveedor-de-prueba"
    assert lectura.scene_id in {"S2_2024_12", "S2_2024_06"}


def test_pocos_pixeles_se_marcan_como_poco_fiables(proyecto, repos):
    pocos = SceneStatistics(mean=0.5, median=0.5, minimum=0.4, maximum=0.6, std=0.1, valid_pixels=3)
    dto, _ = _refresh(proyecto, repos, _FakeSource(ESCENAS, stats=pocos))
    assert all(r.reliable is False for r in dto.readings)


def test_no_se_vuelve_a_pedir_lo_que_ya_se_midio(proyecto, repos):
    primero = _FakeSource(ESCENAS)
    _refresh(proyecto, repos, primero)
    segundo = _FakeSource(ESCENAS)
    _, resumen = _refresh(proyecto, repos, segundo)

    assert resumen["readings_added"] == 0
    assert segundo.pedidos == [], "ni una petición por algo que ya estaba"


def test_una_escena_sin_datos_se_cuenta_pero_no_se_guarda(proyecto, repos):
    source = _FakeSource(ESCENAS, stats=None)
    source._stats = None  # nubes sobre el predio
    dto, resumen = _refresh(proyecto, repos, source)
    assert resumen["readings_added"] == 0
    assert resumen["without_data"] == 4
    assert dto.readings == []


def test_si_el_proveedor_se_cae_a_mitad_se_guarda_lo_conseguido(proyecto, repos):
    """Una serie parcial sirve; perderla entera porque falló la última, no."""
    source = _FakeSource(ESCENAS, falla_en="S2_2024_06")
    dto, resumen = _refresh(proyecto, repos, source)

    assert resumen["interrupted"] is True
    assert resumen["readings_added"] == 2, "las dos del predio de la primera escena"
    assert {r.scene_id for r in dto.readings} == {"S2_2024_12"}


def test_si_no_se_logro_nada_y_no_habia_nada_se_dice_que_fallo(proyecto, repos):
    source = _FakeSource(ESCENAS, falla_en="S2_2024_12")
    with pytest.raises(AppError) as exc:
        _refresh(proyecto, repos, source)
    assert exc.value.code == "SATELLITE_UNAVAILABLE"


def test_el_tope_de_escenas_se_respeta(proyecto, repos):
    source = _FakeSource(ESCENAS)
    _refresh(proyecto, repos, source, max_scenes=1)
    assert source.busquedas[0][4] == 1
    assert len(source.pedidos) == 2  # una escena x dos predios


def test_un_proyecto_sin_coordenadas_no_puede_ubicarse(session, repos):
    p = ProjectRepository(session).create("Sin coordenadas", owner_id=OWNER)
    data = _campaign()
    data.trees = [t.model_copy(update={"coord_x": None, "coord_y": None}) for t in data.trees]
    CampaignRepository(session).save_ingest(p.id, data, "b.xlsx", "i" * 64)

    with pytest.raises(AppError) as exc:
        _refresh(p, repos, _FakeSource(ESCENAS))
    assert exc.value.code == "NO_COORDINATES"


def test_el_proyecto_de_otro_ingeniero_no_existe(proyecto, repos):
    with pytest.raises(AppError) as exc:
        refresh_project_index(
            proyecto.id, "00000000-0000-0000-0000-000000000999", "NDVI",
            DESDE, HASTA, HOY, source=_FakeSource(ESCENAS), **repos,
        )
    assert exc.value.code == "PROJECT_NOT_FOUND"


def test_leer_la_serie_no_sale_a_la_red(proyecto, repos):
    _refresh(proyecto, repos, _FakeSource(ESCENAS))
    dto = get_project_index(
        proyecto.id, OWNER, "ndvi", repos["project_repo"], repos["index_repo"]
    )
    assert dto.index == "NDVI"
    assert len(dto.readings) == 4
    assert dto.last_refreshed_at is not None
    # ordenadas por fecha: la serie se dibuja tal cual llega
    fechas = [r.acquired_at for r in dto.readings]
    assert fechas == sorted(fechas)
