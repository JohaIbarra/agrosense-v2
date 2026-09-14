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


def test_campaign_out_of_range_rejected():
    with pytest.raises(ValueError):
        make_obs(campaign=5)


def test_campaign_bounds_inclusive():
    assert make_obs(campaign=1).campaign == 1
    assert make_obs(campaign=4).campaign == 4


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


def test_tree_requires_species():
    with pytest.raises(Exception):
        Tree(tree_id="T1", species="")


def test_status_semantic_values():
    assert {s.value for s in StatusSemantic} == {"sin_censo", "bajo_umbral_dap", "medido"}
