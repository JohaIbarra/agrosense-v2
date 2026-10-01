"""Etiqueta de mortalidad (E8, plan D1, ADR-014)."""
from __future__ import annotations

from agrosense.domain.mortality_rules import MORTALITY_RULES_VERSION, died_in_interval
from tests.ml.builders import obs


def test_alive_then_dead_is_a_death():
    assert died_in_interval(obs("A", 1, 0.4), obs("A", 2, None, alive=False)) is True


def test_alive_then_alive_is_not_a_death():
    assert died_in_interval(obs("A", 1, 0.4), obs("A", 2, 0.5)) is False


def test_alive_then_alive_without_height_still_counts_as_survival():
    # Sobrevivir no exige que la altura se haya medido en t+1
    assert died_in_interval(obs("A", 1, 0.4), obs("A", 2, None)) is False


def test_no_record_or_unknown_status_in_t_plus_1_is_excluded():
    assert died_in_interval(obs("A", 1, 0.4), None) is None
    assert died_in_interval(obs("A", 1, 0.4), obs("A", 2, None, alive=None)) is None


def test_outside_population_at_risk_in_t_is_excluded():
    # Muerto o sin altura en t: no esta en riesgo (misma poblacion que E7)
    assert died_in_interval(obs("A", 1, None, alive=False), obs("A", 2, None, alive=False)) is None
    assert died_in_interval(obs("A", 1, None), obs("A", 2, None, alive=False)) is None
    assert died_in_interval(None, obs("A", 2, None, alive=False)) is None


def test_rules_version_is_declared():
    assert MORTALITY_RULES_VERSION.startswith("2026-09-30")
