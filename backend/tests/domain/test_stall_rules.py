"""Reglas de estancamiento (E7): Protocolo Estancamiento §2 y §6."""
from __future__ import annotations

import pytest

from agrosense.domain.stall_rules import (
    ALERT_BUDGET,
    PERSISTENT_STALL_INTERVALS,
    RULES_VERSION,
    alert_count,
    height_unchanged,
    is_at_risk,
    is_persistent_stall,
    phytosanitary_worsened,
    select_alerts,
    stall_label,
    stall_streak,
    stalled_previous_interval,
)
from tests.ml.builders import obs


def test_same_height_is_a_stall():
    assert stall_label(obs("A", 1, 0.40), obs("A", 2, 0.40)) is True


def test_any_growth_is_not_a_stall():
    assert stall_label(obs("A", 1, 0.40), obs("A", 2, 0.41)) is False


def test_half_centimetre_counts_as_growth():
    # Regresion FR_1_31 del dataset real: 0.24 -> 0.245 crecio 5 mm.
    assert height_unchanged(0.24, 0.245) is False


def test_float_noise_is_not_growth():
    assert height_unchanged(0.3, 0.1 + 0.2) is True


def test_a_contraction_is_not_a_stall():
    assert stall_label(obs("A", 1, 0.50), obs("A", 2, 0.45)) is False


@pytest.mark.parametrize(
    "prev, curr",
    [
        (obs("A", 1, 0.40), obs("A", 2, 0.40, alive=False)),  # muere: es mortalidad
        (obs("A", 1, 0.40, alive=False), obs("A", 2, 0.40)),  # revive: replanteo
        (obs("A", 1, None), obs("A", 2, 0.40)),  # sin altura
        (obs("A", 1, 0.40), obs("A", 2, 0.40, alive=None)),  # supervivencia en blanco
        (None, obs("A", 2, 0.40)),  # entra en este monitoreo
        (obs("A", 1, 0.40), None),  # sin censo en t+1
    ],
)
def test_outside_the_population_at_risk_there_is_no_label(prev, curr):
    assert stall_label(prev, curr) is None


def test_is_at_risk_requires_alive_and_measured():
    assert is_at_risk(obs("A", 1, 0.4)) is True
    assert is_at_risk(obs("A", 1, 0.4, alive=False)) is False
    assert is_at_risk(obs("A", 1, None)) is False
    assert is_at_risk(None) is False


def test_stalled_previous_interval_looks_at_t_minus_1_and_t_only():
    serie = {1: obs("A", 1, 0.40), 2: obs("A", 2, 0.40), 3: obs("A", 3, 0.50)}
    assert stalled_previous_interval(serie, 2) is True
    assert stalled_previous_interval(serie, 3) is False
    assert stalled_previous_interval(serie, 1) is None  # M1 no tiene intervalo previo


def test_streak_counts_consecutive_stalls_ending_at_t():
    serie = {
        1: obs("A", 1, 0.50),
        2: obs("A", 2, 0.50),
        3: obs("A", 3, 0.50),
        4: obs("A", 4, 0.60),
    }
    assert stall_streak(serie, 3) == 2
    assert stall_streak(serie, 4) == 0
    assert stall_streak(serie, 1) == 0


def test_persistent_means_at_least_two_intervals():
    assert PERSISTENT_STALL_INTERVALS == 2
    assert is_persistent_stall(1) is False
    assert is_persistent_stall(2) is True


@pytest.mark.parametrize(
    "prev, curr, expected",
    [
        ("Bueno", "Regular", True),
        ("Regular", "Malo", True),
        ("Regular", "Bueno", False),
        ("Bueno", "Bueno", False),
        (" regular ", "MALO", True),
        (" ", "Malo", None),
        ("Bueno", None, None),
    ],
)
def test_phytosanitary_worsened(prev, curr, expected):
    assert phytosanitary_worsened(prev, curr) is expected


def test_alert_budget_is_twenty_percent():
    assert ALERT_BUDGET == 0.20
    assert alert_count(717) == 143  # Protocolo §6: "~143 de 717"
    assert alert_count(0) == 0
    assert alert_count(3) == 1  # nunca cero alertas si hay arboles en riesgo
    assert alert_count(15) == 3


def test_alert_budget_must_be_a_fraction():
    with pytest.raises(ValueError):
        alert_count(10, budget=0.0)
    with pytest.raises(ValueError):
        alert_count(10, budget=1.5)


def test_select_alerts_takes_the_highest_scores_and_breaks_ties_by_tree_id():
    scores = {"C": 0.9, "A": 0.5, "B": 0.5, "D": 0.1, "E": 0.2}
    assert select_alerts(scores, budget=0.4) == frozenset({"C", "A"})


def test_rules_version_is_declared():
    # Fix wave (item 4): version de ALERT_BUDGET/PERSISTENT_STALL_INTERVALS
    # y la regla de la etiqueta, distinta de las versiones de ml/.
    assert RULES_VERSION
