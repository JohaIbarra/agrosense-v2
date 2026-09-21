import pytest

from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.errors import (
    DeathViolationError,
)
from agrosense.domain.rules import (
    MAX_CONTRACTION_M,
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


def test_dead_revives_warns_not_raises():
    """Ruling replanteo: 'Muerto'->'Vivo' es practica de restauracion
    (6/856 casos reales); es warning, no error."""
    tree = make_tree()
    obs = [make_obs(1, 0.2, False), make_obs(2, 0.3, True)]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 1
    assert "replanteo" in str(warnings[0])


def test_revival_then_healthy_continues():
    """Tras el 'revive' la serie sigue validandose como viva."""
    tree = make_tree()
    obs = [
        make_obs(1, 0.2, True),
        make_obs(2, 0.25, False),
        make_obs(3, 0.5, True),
        make_obs(4, 0.8, True),
    ]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 1


def test_revival_warning_counts_as_death_then_life():
    """El warning de revival aparece UNA vez por transicion M->V."""
    tree = make_tree()
    obs = [
        make_obs(1, 0.2, True),
        make_obs(2, 0.25, False),
        make_obs(3, 0.5, True),
        make_obs(4, 0.8, False),
    ]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 1  # un solo revive (M2->M3)


def test_dead_tree_grows_raises():
    """Invariante dura inequivoca: muerto hasta el final con altura creciendo."""
    tree = make_tree()
    obs = [make_obs(1, 0.2, True), make_obs(2, 0.25, False), make_obs(3, 0.5, False),
           make_obs(4, 0.5, False)]
    with pytest.raises(DeathViolationError):
        validate_tree_observations(tree, obs)


def test_dead_grows_mid_series_warns():
    """FR_1_45 real: M2-Muerto 0.72, M3-Muerto 1.2, M4-Vivo 1.55.
    Muerto->muerto con altura saltando y luego revive = replanteo mal
    registrado (1/856): warning, no error."""
    tree = make_tree()
    obs = [
        make_obs(1, 0.25, True),
        make_obs(2, 0.72, False),
        make_obs(3, 1.20, False),
        make_obs(4, 1.55, True),
    ]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 1  # el revival (M3->M4)


def test_census_gap_warns_not_raises():
    """Ruling logistica de campo: hueco de censo (1/856 casos reales,
    patron [M1, M4]) es warning, no error."""
    tree = make_tree()
    obs = [make_obs(1, 0.2, True), make_obs(4, 0.4, True)]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 1
    assert "no contiguo" in str(warnings[0])


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
    assert "decrece" in str(warnings[0])


def test_contraction_at_tolerance_boundary_is_not_warning():
    """Justo en el umbral (5 cm) NO se anota: el aviso es para lo que lo supera."""
    tree = make_tree()
    obs = [make_obs(1, 0.30, True), make_obs(2, 0.25, True)]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 0


def test_contraction_threshold():
    """Gate del ajuste del 2026-09-21: el umbral NO puede volver a 1 cm.

    Con 1 cm, 12 de las 13 contracciones reales del unico intervalo sin
    corregir del dataset (M1->M2, magnitudes 1-20 cm) generaban aviso. Ese
    volumen de avisos es lo que institucionaliza la monotonizacion artificial
    de la altura (0 % de contracciones en M2->M3 y M3->M4).
    """
    assert MAX_CONTRACTION_M >= 0.05


def test_field_scale_contractions_are_not_flagged():
    """Las contracciones tipicas de campo (1-4 cm) pasan sin anotarse."""
    tree = make_tree()
    for bajada in (0.01, 0.02, 0.03, 0.04):
        obs = [make_obs(1, 1.00, True), make_obs(2, 1.00 - bajada, True)]
        assert validate_tree_observations(tree, obs) == [], f"bajada de {bajada} m anotada"


def test_contraction_note_does_not_ask_to_correct_the_datum():
    """El texto del aviso no debe empujar a "corregir" la altura medida.

    Es la mitad del arreglo: el umbral evita el ruido, la redaccion evita que
    quien lo lee monotonice el dato. Si alguien vuelve a redactarlo como
    "sospechoso" o "error de medicion", este test cae.
    """
    tree = make_tree()
    obs = [make_obs(1, 1.20, True), make_obs(2, 1.00, True)]
    mensaje = str(validate_tree_observations(tree, obs)[0]).lower()
    assert "no corregir" in mensaje
    assert "no es un error de medicion" in mensaje
    assert "sospechos" not in mensaje


def test_empty_series_passes():
    tree = make_tree()
    assert validate_tree_observations(tree, []) == []


def test_growth_between():
    a = make_obs(1, 0.20, True)
    b = make_obs(2, 0.32, True)
    assert growth_between(a, b) == pytest.approx(0.12)
    assert STAGNATION_THRESHOLD_M == 0.05
