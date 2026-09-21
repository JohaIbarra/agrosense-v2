"""Contrato de `/api/v1/analytics/*` contra la analitica real cargada."""
from __future__ import annotations

import math

import pytest

# ── Ranking de especies ────────────────────────────────────────────────────

def test_list_species_returns_all_thirty(analytics_client):
    r = analytics_client.get("/api/v1/analytics/species")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 30
    assert {s["species"] for s in body} != {""}


def test_list_species_default_sort_is_stall_risk_desc(analytics_client):
    body = analytics_client.get("/api/v1/analytics/species").json()
    ors = [s["stall_risk"]["odds_ratio"] for s in body]
    assert ors == sorted(ors, reverse=True)
    assert body[0]["species"] == "Lafoensia speciosa"


def test_list_species_sort_by_mortality(analytics_client):
    body = analytics_client.get(
        "/api/v1/analytics/species", params={"sort": "mortality_risk"}
    ).json()
    ors = [s["mortality_risk"]["odds_ratio"] for s in body]
    assert ors == sorted(ors, reverse=True)


def test_invalid_sort_is_rejected_at_the_edge(analytics_client):
    """Un `sort` fuera del vocabulario no llega al caso de uso: 422."""
    r = analytics_client.get("/api/v1/analytics/species", params={"sort": "drop table"})
    assert r.status_code == 422


def test_filter_by_guild(analytics_client):
    body = analytics_client.get(
        "/api/v1/analytics/species", params={"gremio": "Inicial"}
    ).json()
    assert body
    assert {s["gremio"] for s in body} == {"Inicial"}
    assert len(body) < 30


def test_filter_by_unknown_guild_is_empty_not_error(analytics_client):
    r = analytics_client.get("/api/v1/analytics/species", params={"gremio": "Nope"})
    assert r.status_code == 200
    assert r.json() == []


# ── Detalle ────────────────────────────────────────────────────────────────

def test_species_detail_matches_the_report(analytics_client):
    r = analytics_client.get("/api/v1/analytics/species/Lafoensia speciosa")
    assert r.status_code == 200
    body = r.json()
    assert body["species"] == "Lafoensia speciosa"
    assert body["stall_risk"]["odds_ratio"] == pytest.approx(4.94, abs=0.01)
    assert body["stall_risk"]["significant"] is True
    assert body["gremio"]
    assert body["n_observations"] and body["n_trees"]


def test_species_detail_404_has_the_contract_shape(analytics_client):
    r = analytics_client.get("/api/v1/analytics/species/Ficus inventada")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "SPECIES_NOT_FOUND"


def test_species_with_nbsp_in_the_source_is_reachable(analytics_client):
    """`Inga punctata` viene con NBSP en el CSV; debe consultarse normal.

    Si `normalize_level` desaparece, esta ruta devuelve 404 justo para la
    unica especie con efecto significativo en mortalidad.
    """
    r = analytics_client.get("/api/v1/analytics/species/Inga punctata")
    assert r.status_code == 200
    body = r.json()
    assert body["mortality_risk"]["significant"] is True
    assert body["mortality_risk"]["odds_ratio"] == pytest.approx(0.355, abs=0.01)


# ── Escala: OR siempre, log-odds etiquetado ────────────────────────────────

def test_confidence_intervals_are_exponentiated_for_the_ui(analytics_client):
    """`or_ci95` contiene al OR; `ci95_log_odds` contiene a su logaritmo.

    Es el error que este contrato existe para impedir: publicar
    [0.81, 2.38] como si fuera el intervalo de un OR de 4.94.
    """
    body = analytics_client.get("/api/v1/analytics/species").json()
    for s in body:
        riesgo = s["stall_risk"]
        lo_or, hi_or = riesgo["or_ci95"]
        lo_log, hi_log = riesgo["ci95_log_odds"]
        assert lo_or < riesgo["odds_ratio"] < hi_or
        assert lo_or > 0, "un OR nunca es negativo"
        assert math.log(lo_or) == pytest.approx(lo_log, abs=1e-6)
        assert math.log(hi_or) == pytest.approx(hi_log, abs=1e-6)


def test_significance_means_ci_excludes_one(analytics_client):
    body = analytics_client.get("/api/v1/analytics/species").json()
    for s in body:
        lo, hi = s["stall_risk"]["or_ci95"]
        assert s["stall_risk"]["significant"] is not (lo <= 1.0 <= hi), s["species"]


def test_interpretation_never_claims_an_effect_when_ci_crosses_one(analytics_client):
    """Un IC que cruza 1 no puede leerse como hallazgo.

    Sin esta regla, el dashboard diria "se estanca 1.9x mas" de una especie
    con 21 arboles y un IC de [0.82, 4.44] — y el vivero dejaria de plantarla.
    """
    body = analytics_client.get("/api/v1/analytics/species").json()
    no_sig = [s for s in body if not s["stall_risk"]["significant"]]
    assert no_sig
    for s in no_sig:
        texto = s["stall_risk"]["interpretation"].lower()
        assert "sin efecto significativo" in texto, s["species"]
        assert "cruza 1" in texto


def test_protective_species_are_read_as_protective(analytics_client):
    body = analytics_client.get("/api/v1/analytics/species/Verbesina arborea").json()
    texto = body["stall_risk"]["interpretation"].lower()
    assert body["stall_risk"]["odds_ratio"] < 1
    assert "menos" in texto and "protector" in texto


# ── Atajos del dashboard ───────────────────────────────────────────────────

def test_top_risk_stall_returns_five_significant_species(analytics_client):
    r = analytics_client.get("/api/v1/analytics/species/top-risk-stall")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 5
    assert [s["species"] for s in body] == [
        "Lafoensia speciosa",
        "Delostoma integrifolium",
        "Persea caerulea",
        "Delostoma roseum",
        "Cedrela montana",
    ]
    assert all(s["stall_risk"]["significant"] for s in body)
    assert all(s["stall_risk"]["odds_ratio"] > 1 for s in body)


def test_top_risk_route_is_not_swallowed_by_the_name_parameter(analytics_client):
    """`/species/top-risk-stall` no debe resolverse como especie "top-risk-stall"."""
    r = analytics_client.get("/api/v1/analytics/species/top-risk-stall")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_top_protective_stall(analytics_client):
    body = analytics_client.get("/api/v1/analytics/species/top-protective").json()
    assert [s["species"] for s in body] == [
        "Verbesina arborea",
        "Heliocarpus popayanensis",
        "Senna viarum",
    ]
    assert all(s["stall_risk"]["odds_ratio"] < 1 for s in body)


def test_top_protective_mortality_is_only_inga(analytics_client):
    body = analytics_client.get(
        "/api/v1/analytics/species/top-protective", params={"model": "mortality"}
    ).json()
    assert [s["species"] for s in body] == ["Inga punctata"]


def test_top_protective_rejects_unknown_model(analytics_client):
    r = analytics_client.get(
        "/api/v1/analytics/species/top-protective", params={"model": "growth"}
    )
    assert r.status_code == 422


# ── Parcelas ───────────────────────────────────────────────────────────────

def test_list_plots(analytics_client):
    body = analytics_client.get("/api/v1/analytics/plots").json()
    assert len(body) == 45
    assert all(p["plot_code"].startswith("GEB/") for p in body)
    assert {p["localidad"] for p in body} == {
        "Tres Jotas",
        "Guayabal",
        "San Antonio",
    }


def test_plots_only_in_the_mortality_panel_keep_null_stall(analytics_client):
    """Las 3 parcelas que solo existen en mortalidad no se inventan un efecto."""
    body = analytics_client.get("/api/v1/analytics/plots").json()
    sin_stall = [p for p in body if p["stall_risk"]["odds_ratio"] is None]
    assert len(sin_stall) == 3
    for p in sin_stall:
        assert p["mortality_risk"]["odds_ratio"] is not None
        assert "sin estimacion" in p["stall_risk"]["interpretation"].lower()


def test_filter_plots_by_locality(analytics_client):
    body = analytics_client.get(
        "/api/v1/analytics/plots", params={"localidad": "Guayabal"}
    ).json()
    assert body
    assert {p["localidad"] for p in body} == {"Guayabal"}


# ── Descomposicion de varianza ─────────────────────────────────────────────

def test_variance_decomposition_tells_the_two_strategies_apart(analytics_client):
    r = analytics_client.get("/api/v1/analytics/variance-decomposition")
    assert r.status_code == 200
    por_modelo = {m["model"]: m for m in r.json()}
    assert set(por_modelo) == {"stall", "mortality"}

    stall = por_modelo["stall"]
    assert stall["species_to_plot_ratio"] == pytest.approx(2.7, abs=0.1)
    assert "seleccion de especies" in stall["interpretation"].lower()

    mort = por_modelo["mortality"]
    assert mort["species_to_plot_ratio"] == pytest.approx(1.1, abs=0.1)
    assert "similar" in mort["interpretation"].lower()

    # El ICC va acompanado del volumen de evidencia que lo sostiene.
    especie_mort = next(c for c in mort["components"] if c["grouping"] == "especie")
    assert especie_mort["n_events"] == 70
    assert especie_mort["n_observations"] == 1405
    assert especie_mort["n_levels"] == 30


def test_variance_decomposition_404_when_not_loaded(empty_analytics_client):
    """Sin analitica cargada la respuesta lo dice, no devuelve una lista vacia."""
    r = empty_analytics_client.get("/api/v1/analytics/variance-decomposition")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "ANALYTICS_NOT_LOADED"


def test_species_list_is_empty_when_not_loaded(empty_analytics_client):
    r = empty_analytics_client.get("/api/v1/analytics/species")
    assert r.status_code == 200
    assert r.json() == []
