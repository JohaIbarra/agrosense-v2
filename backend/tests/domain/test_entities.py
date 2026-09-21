import pytest

from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.errors import NegativeMeasurementError


def make_obs(**overrides):
    base = dict(
        tree_id="T1",
        campaign=2,
        height_m=0.45,
        crown_diameter_m=0.30,
        dap_cm=None,
        dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary="Bueno",
        alive=True,
        colonization=None,
    )
    base.update(overrides)
    return Observation(**base)


def test_observation_valid():
    obs = make_obs()
    assert obs.tree_id == "T1"
    assert obs.campaign == 2
    assert obs.alive is True


def test_negative_height_rejected():
    with pytest.raises(NegativeMeasurementError):
        make_obs(height_m=-0.1)


def test_negative_crown_rejected():
    with pytest.raises(NegativeMeasurementError):
        make_obs(crown_diameter_m=-0.5)


def test_negative_dap_rejected():
    with pytest.raises(NegativeMeasurementError):
        make_obs(dap_cm=-1.5, dap_status=StatusSemantic.MEDIDO)


def test_campaign_below_one_rejected():
    """El numero de monitoreo empieza en 1 (M1)."""
    with pytest.raises(ValueError):
        make_obs(campaign=0)
    with pytest.raises(ValueError):
        make_obs(campaign=-1)


def test_campaign_has_no_upper_bound():
    """E0: un proyecto puede tener M5, M6... (docs/04-vision-producto.md).

    Antes el validador cortaba en 4 porque el dataset de referencia tiene
    cuatro monitoreos: el quinto de cualquier proyecto habria sido rechazado.
    """
    assert make_obs(campaign=1).campaign == 1
    assert make_obs(campaign=4).campaign == 4
    assert make_obs(campaign=5).campaign == 5
    assert make_obs(campaign=12).campaign == 12


def test_observation_field_notes_optional():
    assert make_obs().field_notes is None
    assert make_obs(field_notes="Defoliacion parcial").field_notes == "Defoliacion parcial"


def test_null_measurements_allowed():
    obs = make_obs(height_m=None, crown_diameter_m=None, alive=None, phytosanitary=None)
    assert obs.height_m is None
    assert obs.alive is None


def test_tree_valid():
    tree = Tree(
        tree_id="T1", species="Quercus humboldtii", family="Fagaceae",
        common_name="Roble", guild="Tardía", plot_id="28", locality="Guayabal",
        coord_x=4735725.0, coord_y=2199477.0, elevation_m=2729.0,
    )
    assert tree.species == "Quercus humboldtii"
    assert tree.elevation_m == 2729


def test_tree_carries_plot_attributes_for_ingestion():
    """El arbol transporta los atributos de su parcela desde la ingesta.

    La normalizacion a `plots` es del repositorio; el dominio solo exige
    que el dato no se pierda en el camino (hallazgo H2 de E0).
    """
    tree = Tree(
        tree_id="T1", species="Senna viarum",
        sampling_unit_code="GEB/MED-LV/NV/FR/11", plot_id="11",
        monitoring_unit="Parcela", floristic_design="Rehabilitacion vegetal",
        associated_cover="Bosque de galeria",
        establishment_cover="Mosaico de pastos con espacios naturales",
    )
    assert tree.sampling_unit_code == "GEB/MED-LV/NV/FR/11"
    assert tree.floristic_design == "Rehabilitacion vegetal"


def test_tree_plot_attributes_default_to_none():
    """Los archivos sin esas columnas siguen siendo validos."""
    tree = Tree(tree_id="T1", species="Senna viarum")
    assert tree.sampling_unit_code is None
    assert tree.associated_cover is None


def test_tree_requires_species():
    with pytest.raises(Exception):
        Tree(tree_id="T1", species="")


def test_status_semantic_values():
    assert {s.value for s in StatusSemantic} == {"sin_censo", "bajo_umbral_dap", "medido"}
