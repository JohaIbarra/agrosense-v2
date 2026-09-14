import pytest

from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.errors import (
    DeathViolationError,
    NonContiguousCensusError,
)
from agrosense.domain.rules import (
    STAGNATION_THRESHOLD_M,
    growth_between,
    validate_tree_observations,
)


def make_obs(campaign, height, alive, tree_id="T1"):
    return Observation(
        tree_id=tree_id,
        campaign=campaign,
        height_m=height,
        crown_diameter_m=0.2,
        dap_cm=None,
        dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary="Bueno",
        alive=alive,
        colonization=None,
    )


def make_tree(species="Quercus humboldtii", tree_id="T1"):
    return Tree(tree_id=tree_id, species=species)


def test_healthy_series_passes():
    tree = make_tree()
    obs = [make_obs(1, 0.2, True), make_obs(2, 0.3, True), make_obs(3, 0.4, True)]
    warnings = validate_tree_observations(tree, obs)
    assert warnings == []


def test_dead_tree_frozen_passes():
    tree = make_tree()
    obs = [
        make_obs(1, 0.2, True),
        make_obs(2, 0.25, False),
        make_obs(3, 0.25, False),
        make_obs(4, 0.25, False),
    ]
    warnings = validate_tree_observations(tree, obs)
    assert warnings == []


def test_dead_tree_revives_raises():
    tree = make_tree()
    obs = [make_obs(1, 0.2, False), make_obs(2, 0.3, True)]
    with pytest.raises(DeathViolationError):
        validate_tree_observations(tree, obs)


def test_dead_tree_grows_raises():
    tree = make_tree()
    obs = [make_obs(1, 0.2, True), make_obs(2, 0.25, False), make_obs(3, 0.5, False)]
    with pytest.raises(DeathViolationError):
        validate_tree_observations(tree, obs)


def test_census_gap_raises():
    tree = make_tree()
    obs = [make_obs(1, 0.2, True), make_obs(3, 0.4, True)]
    with pytest.raises(NonContiguousCensusError):
        validate_tree_observations(tree, obs)


def test_first_census_late_is_contiguous():
    """Arbol que entra en M3 (?|?|Vivo|Vivo, patron real del dataset):
    el censo es contiguo DESDE SU PRIMER censo."""
    tree = make_tree()
    obs = [make_obs(3, 0.2, True), make_obs(4, 0.3, True)]
    warnings = validate_tree_observations(tree, obs)
    assert warnings == []


def test_contraction_small_is_not_warning():
    tree = make_tree()
    obs = [make_obs(1, 0.30, True), make_obs(2, 0.295, True)]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 0


def test_contraction_large_warns_not_raises():
    tree = make_tree()
    obs = [make_obs(1, 0.30, True), make_obs(2, 0.20, True)]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 1
    assert "encoge" in str(warnings[0])


def test_contraction_at_tolerance_boundary_is_not_warning():
    tree = make_tree()
    obs = [make_obs(1, 0.30, True), make_obs(2, 0.29, True)]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 0


def test_empty_series_passes():
    tree = make_tree()
    assert validate_tree_observations(tree, []) == []


def test_growth_between():
    a = make_obs(1, 0.20, True)
    b = make_obs(2, 0.32, True)
    assert growth_between(a, b) == pytest.approx(0.12)
    assert STAGNATION_THRESHOLD_M == 0.05
