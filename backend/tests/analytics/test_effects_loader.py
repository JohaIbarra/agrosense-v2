"""Gates del slice 5 sobre los CSV reales de los modelos mixtos.

Estos tests son un CONTROL DE INTEGRIDAD de la fuente de verdad, no una
prueba del codigo: si un CSV se regenera y cambian los conteos, estos tests
caen y obligan a mirar por que antes de que el dashboard publique un ranking
distinto sin que nadie se entere (AGENTS.md, data provenance).

Los numeros vienen de los informes del 2026-09-21:
`informe_varianza_especie_sitio.md` e `informe_varianza_mortalidad.md`.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from agrosense.adapters.analytics.effects_loader import (
    build_bundle,
    is_significant,
    normalize_level,
    odds_ratio,
)

PROCESSED = Path(__file__).parents[2] / "data" / "processed"

pytestmark = pytest.mark.skipif(
    not (PROCESSED / "efectos_aleatorios.csv").exists(),
    reason="CSV de los modelos mixtos ausentes (data/processed/)",
)


@pytest.fixture(scope="module")
def bundle():
    return build_bundle(PROCESSED)


# ── Los gates que pide el contrato del slice ───────────────────────────────

def test_species_coverage(bundle):
    """Exactamente 30 especies, y ninguna repetida por un espacio raro."""
    assert len(bundle.species) == 30
    nombres = [s.species_name for s in bundle.species]
    assert len(set(nombres)) == 30


def test_significant_species_stall(bundle):
    """8 de 30 especies con IC 95% concluyente en estancamiento."""
    sig = [s.species_name for s in bundle.species if s.sig_stall]
    assert len(sig) == 8, sig
    # Las cinco que mas se estancan y las tres protectoras del informe.
    assert set(sig) == {
        "Lafoensia speciosa",
        "Delostoma integrifolium",
        "Persea caerulea",
        "Delostoma roseum",
        "Cedrela montana",
        "Verbesina arborea",
        "Heliocarpus popayanensis",
        "Senna viarum",
    }


def test_significant_species_mort(bundle):
    """Una sola especie concluyente en mortalidad: Inga punctata, protectora.

    Es el resultado mas facil de romper sin darse cuenta: el nombre trae un
    NBSP en el CSV, asi que si alguien quita `normalize_level` la especie se
    parte en dos claves y este test cae.
    """
    sig = [s for s in bundle.species if s.sig_mort]
    assert len(sig) == 1, [s.species_name for s in sig]
    inga = sig[0]
    assert inga.species_name == "Inga punctata"
    assert inga.or_mort == pytest.approx(0.355, abs=0.01)
    assert inga.or_mort < 1, "Inga punctata es protectora, no de riesgo"
    assert not any(s.sig_mort and (s.or_mort or 0) > 1 for s in bundle.species), (
        "ninguna especie tiene riesgo de mortalidad AUMENTADO significativo"
    )


def test_variance_ranges(bundle):
    """Los efectos aleatorios caen en un rango de log-odds razonable.

    [-2.6, 2.6] es aproximadamente un OR entre 0.07 y 13. Un efecto fuera de
    ahi no es una especie extraordinaria: es un nivel con 2 observaciones y
    separacion completa, o una columna mal leida.
    """
    efectos = [
        e
        for s in bundle.species
        for e in (s.effect_stall, s.effect_mort)
        if e is not None
    ] + [
        e
        for p in bundle.plots
        for e in (p.effect_stall, p.effect_mort)
        if e is not None
    ]
    assert efectos, "no se leyo ningun efecto"
    fuera = [e for e in efectos if not (-2.6 <= e <= 2.6)]
    assert not fuera, f"efectos fuera de [-2.6, 2.6]: {fuera}"


def test_ic_consistency(bundle):
    """`or_lo < or < or_hi` en toda fila que tenga IC."""
    for s in bundle.species:
        for nombre, lo, valor, hi in (
            ("stall", s.or_stall_lo, s.or_stall, s.or_stall_hi),
            ("mort", s.or_mort_lo, s.or_mort, s.or_mort_hi),
        ):
            if None in (lo, valor, hi):
                continue
            assert lo < valor < hi, f"{s.species_name} ({nombre}): {lo} < {valor} < {hi}"
            assert lo > 0, f"{s.species_name} ({nombre}): un OR nunca es <= 0"


# ── Escalas y conversiones ─────────────────────────────────────────────────

def test_or_is_exp_of_effect(bundle):
    for s in bundle.species:
        if s.effect_stall is not None:
            assert s.or_stall == pytest.approx(math.exp(s.effect_stall))
        if s.effect_mort is not None:
            assert s.or_mort == pytest.approx(math.exp(s.effect_mort))


def test_ci_bounds_are_exponentiated_log_odds(bundle):
    """`or_lo = exp(efecto - 1.96 se)` y `or_hi = exp(efecto + 1.96 se)`.

    Exponenciar es el paso que mas facil se olvida: sin el, la UI dibujaria
    una barra de [0.81, 2.38] alrededor de un OR de 4.94 — fuera de su propio
    intervalo.
    """
    for s in bundle.species:
        if s.effect_stall is None or s.se_stall is None:
            continue
        assert s.or_stall_lo == pytest.approx(math.exp(s.effect_stall - 1.96 * s.se_stall))
        assert s.or_stall_hi == pytest.approx(math.exp(s.effect_stall + 1.96 * s.se_stall))


def test_significance_matches_ci_not_crossing_one(bundle):
    """`sig` equivale a que el IC del OR no contenga 1.0."""
    for s in bundle.species:
        if s.or_stall_lo is None or s.or_stall_hi is None:
            continue
        cruza_uno = s.or_stall_lo <= 1.0 <= s.or_stall_hi
        assert s.sig_stall is not cruza_uno, s.species_name


def test_lafoensia_matches_the_report(bundle):
    """Control puntual contra el informe: OR 4.94, IC log-odds [0.81, 2.38]."""
    laf = next(s for s in bundle.species if s.species_name == "Lafoensia speciosa")
    assert laf.or_stall == pytest.approx(4.94, abs=0.01)
    assert laf.sig_stall is True
    assert math.log(laf.or_stall_lo) == pytest.approx(0.81, abs=0.01)
    assert math.log(laf.or_stall_hi) == pytest.approx(2.38, abs=0.01)


# ── Parcelas y varianza ────────────────────────────────────────────────────

def test_plot_coverage_is_the_union_of_both_models(bundle):
    """45 parcelas: 42 del panel de estancamiento + 3 solo en mortalidad.

    Las 3 extra deben entrar con `effect_stall` en NULL, no desaparecer: el
    merge tiene que ser outer.
    """
    assert len(bundle.plots) == 45
    solo_mort = [p.plot_code for p in bundle.plots if p.effect_stall is None]
    assert len(solo_mort) == 3, solo_mort
    assert all(p.effect_mort is not None for p in bundle.plots)


def test_plots_carry_localidad(bundle):
    assert all(p.localidad for p in bundle.plots)
    assert {p.localidad for p in bundle.plots} == {
        "Tres Jotas",
        "Guayabal",
        "San Antonio",
    }


def test_variance_decomposition_matches_the_report(bundle):
    por_clave = {(v.model, v.grouping): v for v in bundle.variance}
    assert set(por_clave) == {
        ("stall", "especie"),
        ("stall", "parcela"),
        ("mortality", "especie"),
        ("mortality", "parcela"),
    }

    # Estancamiento: la especie pesa 2.7x mas que la parcela.
    e, p = por_clave[("stall", "especie")], por_clave[("stall", "parcela")]
    assert e.variance == pytest.approx(0.846, abs=0.001)
    assert p.variance == pytest.approx(0.317, abs=0.001)
    assert e.icc == pytest.approx(0.190, abs=0.001)
    assert e.variance / p.variance == pytest.approx(2.7, abs=0.1)
    assert (e.n_events, e.n_observations) == (310, 1335)

    # Mortalidad: pesan casi igual (1.1x).
    e, p = por_clave[("mortality", "especie")], por_clave[("mortality", "parcela")]
    assert e.variance == pytest.approx(0.415, abs=0.001)
    assert p.variance == pytest.approx(0.372, abs=0.001)
    assert e.variance / p.variance == pytest.approx(1.1, abs=0.1)
    assert (e.n_events, e.n_observations) == (70, 1405)


def test_species_carry_guild_and_counts(bundle):
    assert all(s.gremio for s in bundle.species), "toda especie tiene gremio"
    assert all(s.n_trees and s.n_observations for s in bundle.species)
    assert {s.gremio for s in bundle.species} == {"Inicial", "Intermedia", "Tardía"}


# ── Unidades de las funciones puras ────────────────────────────────────────

def test_normalize_level_strips_nbsp():
    assert normalize_level("Inga punctata\xa0") == "Inga punctata"
    assert normalize_level("  Cedrela   montana ") == "Cedrela montana"
    assert normalize_level("GEB/MED-LV/NV/FR/11") == "GEB/MED-LV/NV/FR/11"


def test_odds_ratio_and_significance_rules():
    assert odds_ratio(0.0) == pytest.approx(1.0)
    assert odds_ratio(None) is None
    # IC enteramente por encima de 0 -> riesgo aumentado concluyente
    assert is_significant(0.81, 2.38) is True
    # IC enteramente por debajo -> protector concluyente
    assert is_significant(-2.16, -0.66) is True
    # IC que cruza 0 -> no concluyente
    assert is_significant(-0.25, 0.81) is False
    assert is_significant(None, 0.5) is None
