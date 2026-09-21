"""Smoke del slice 5 contra Supabase REAL.

    pytest -m supabase

Que verifica aqui, y NO en `tests/analytics/` (que corre sobre SQLite):

  1. **Tipos reales de Postgres.** SQLite no tiene BOOLEAN: guarda 0/1 y los
     devuelve como int. `sig_stall` podria estar poblado con enteros y los
     tests locales pasarian igual. Aqui se comprueba que Postgres devuelve
     `True`/`False` y que un `WHERE sig_stall` filtra de verdad.
  2. **NULL vs 0.** Las 3 parcelas que solo existen en el panel de mortalidad
     deben tener `or_stall IS NULL`. Un 0.0 ahi seria un OR de "nunca se
     estanca", que es una afirmacion falsa, no un dato faltante.
  3. **UTF-8 de punta a punta.** `Tardía` (U+00ED) y la ausencia del NBSP de
     `Inga punctata` sobreviven al round-trip por el dialecto real. Un
     encoding mal declarado en el loader no falla: guarda mojibake.
  4. **Las constraints existen en la DB**, no solo en el model.
  5. **La API contra Postgres**, no contra SQLite en memoria.

Requiere que la analitica este cargada (`python scripts/load_analytics.py`).
Si no lo esta, los tests hacen skip con el motivo: el smoke informa, no miente.

Estos tests son de SOLO LECTURA sobre las tablas analiticas salvo
`test_reload_is_idempotent`, que recarga y vuelve a dejar el mismo contenido.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import inspect, text

from agrosense.adapters.db.models import (
    Base,
    PlotAnalytics,
    SpeciesAnalytics,
    VarianceComponent,
)

pytestmark = [
    pytest.mark.supabase,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL ausente (backend/.env)",
    ),
]

ANALYTICS_TABLES = ("species_analytics", "plot_analytics", "variance_components")


@pytest.fixture()
def session():
    from agrosense.adapters.db.session import get_session_factory

    factory = get_session_factory()
    s = factory()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def loaded(session):
    """Salta —sin fallar— si la analitica no esta cargada en esta DB."""
    n = session.query(SpeciesAnalytics).count()
    if n == 0:
        pytest.skip(
            "analitica no cargada en Supabase: ejecuta "
            "`python scripts/load_analytics.py`"
        )
    return session


# ── Esquema ────────────────────────────────────────────────────────────────

def test_analytics_tables_exist_in_postgres(session):
    """La migracion b1c4a7f20e51 esta realmente aplicada en Supabase."""
    reales = set(inspect(session.get_bind()).get_table_names())
    faltan = [t for t in ANALYTICS_TABLES if t not in reales]
    assert not faltan, f"falta aplicar la migracion: {faltan}"


@pytest.mark.parametrize("table", ANALYTICS_TABLES)
def test_columns_match_the_model(session, table):
    inspector = inspect(session.get_bind())
    reales = {c["name"] for c in inspector.get_columns(table)}
    esperadas = {c.name for c in Base.metadata.tables[table].columns}
    assert esperadas <= reales, f"columnas ausentes en {table}: {sorted(esperadas - reales)}"


def test_postgres_types_are_the_intended_ones(session):
    """BOOLEAN y TIMESTAMPTZ de verdad — lo que SQLite no distingue."""
    tipos = {
        c["name"]: str(c["type"]).upper()
        for c in inspect(session.get_bind()).get_columns("species_analytics")
    }
    assert "BOOLEAN" in tipos["sig_stall"]
    assert "BOOLEAN" in tipos["sig_mort"]
    assert "INTEGER" in tipos["n_trees"]
    assert "TIMESTAMP" in tipos["updated_at"]


def test_variance_unique_constraint_exists_in_the_database(session):
    """Sin ella, dos cargas seguidas podrian duplicar los ICC."""
    nombres = {
        u["name"]
        for u in inspect(session.get_bind()).get_unique_constraints("variance_components")
    }
    assert "uq_variance_model_grouping" in nombres


def test_indexes_were_created(session):
    idx = {i["name"] for i in inspect(session.get_bind()).get_indexes("species_analytics")}
    assert "ix_species_analytics_or_stall" in idx
    assert "ix_species_analytics_gremio" in idx


# ── Contenido ──────────────────────────────────────────────────────────────

def test_row_counts(loaded):
    assert loaded.query(SpeciesAnalytics).count() == 30
    assert loaded.query(PlotAnalytics).count() == 45
    assert loaded.query(VarianceComponent).count() == 4


def test_booleans_filter_as_booleans_in_postgres(loaded):
    """`sig_*` es BOOLEAN real: un WHERE sobre el filtra de verdad.

    En SQLite estos valores son 0/1 y este mismo assert pasaria aunque la
    columna estuviera poblada con enteros.
    """
    sig_stall = loaded.execute(
        text("select count(*) from species_analytics where sig_stall")
    ).scalar()
    sig_mort = loaded.execute(
        text("select count(*) from species_analytics where sig_mort")
    ).scalar()
    assert sig_stall == 8
    assert sig_mort == 1

    valor = loaded.execute(
        text("select sig_stall from species_analytics where species_name = :n"),
        {"n": "Lafoensia speciosa"},
    ).scalar()
    assert valor is True
    assert isinstance(valor, bool)


def test_missing_effects_are_null_not_zero(loaded):
    """Las 3 parcelas solo del panel de mortalidad conservan NULL.

    Un 0.0 aqui no seria un dato faltante: seria afirmar un OR de 1.0
    (exp(0)), es decir "esta parcela se comporta como el promedio" — una
    conclusion que el modelo nunca emitio.
    """
    filas = loaded.execute(
        text(
            "select plot_code, or_stall, or_mort from plot_analytics "
            "where or_stall is null order by plot_code"
        )
    ).all()
    assert len(filas) == 3
    for _, or_stall, or_mort in filas:
        assert or_stall is None
        assert or_mort is not None

    assert loaded.execute(
        text("select count(*) from plot_analytics where or_stall = 0")
    ).scalar() == 0


def test_utf8_survives_the_round_trip(loaded):
    """Acentos y NBSP tras pasar por el dialecto real.

    Un encoding mal declarado en el loader NO falla: guarda mojibake. La
    unica forma de detectarlo es mirar los codepoints de vuelta.
    """
    gremios = {
        g for (g,) in loaded.execute(text("select distinct gremio from species_analytics"))
    }
    assert gremios == {"Inicial", "Intermedia", "Tardía"}
    assert "Tard\xeda" in gremios, "la í debe ser U+00ED, no mojibake"

    nombre = loaded.execute(
        text("select species_name from species_analytics where sig_mort")
    ).scalar()
    assert nombre == "Inga punctata"
    assert "\xa0" not in nombre, "el NBSP del CSV llego hasta la base de datos"
    assert len(nombre) == 13


def test_the_report_numbers_survived(loaded):
    """Control puntual contra el informe, leido desde Postgres."""
    fila = loaded.execute(
        text(
            "select or_stall, or_stall_lo, or_stall_hi, gremio, n_trees "
            "from species_analytics where species_name = :n"
        ),
        {"n": "Lafoensia speciosa"},
    ).one()
    assert fila[0] == pytest.approx(4.94, abs=0.01)
    assert fila[1] == pytest.approx(2.25, abs=0.01)
    assert fila[2] == pytest.approx(10.86, abs=0.01)
    assert fila[3] == "Inicial"

    icc = {
        (m, g): i
        for m, g, i in loaded.execute(
            text("select model, grouping, icc from variance_components")
        )
    }
    assert icc[("stall", "especie")] == pytest.approx(0.190, abs=0.001)
    assert icc[("mortality", "parcela")] == pytest.approx(0.091, abs=0.001)


def test_ci_consistency_computed_by_postgres(loaded):
    """`or_lo < or < or_hi` verificado por el motor, no por Python."""
    malas = loaded.execute(
        text(
            "select species_name from species_analytics "
            "where or_stall is not null "
            "and not (or_stall_lo < or_stall and or_stall < or_stall_hi)"
        )
    ).all()
    assert not malas, f"IC inconsistente en: {[m[0] for m in malas]}"

    no_positivos = loaded.execute(
        text("select count(*) from species_analytics where or_stall_lo <= 0")
    ).scalar()
    assert no_positivos == 0, "un OR nunca es <= 0"


def test_analytics_is_independent_of_projects(session):
    """Ninguna FK hacia `projects` — decision de diseno, verificada en la DB."""
    inspector = inspect(session.get_bind())
    for table in ANALYTICS_TABLES:
        assert inspector.get_foreign_keys(table) == [], (
            f"{table} gano una FK; la analitica es independiente del grafo de "
            f"proyectos (ver models.SpeciesAnalytics)"
        )


# ── Recarga ────────────────────────────────────────────────────────────────

def test_reload_is_idempotent(loaded):
    """Recargar deja exactamente el mismo contenido, no duplicados.

    Es la propiedad que hace seguro volver a ejecutar el script tras un corte
    de red a mitad de carga.
    """
    import sys
    from pathlib import Path

    scripts = Path(__file__).parents[2] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import load_analytics

    from agrosense.adapters.analytics.effects_loader import build_bundle
    from agrosense.adapters.db.repository import AnalyticsRepository

    processed = Path(__file__).parents[2] / "data" / "processed"
    if not (processed / "efectos_aleatorios.csv").exists():
        pytest.skip("CSV de los modelos mixtos ausentes")

    antes = loaded.execute(
        text("select species_name, or_stall from species_analytics order by species_name")
    ).all()

    counts = AnalyticsRepository(loaded).replace_all(
        *load_analytics.to_orm(build_bundle(processed))
    )
    assert counts == {"species": 30, "plots": 45, "variance": 4}

    despues = loaded.execute(
        text("select species_name, or_stall from species_analytics order by species_name")
    ).all()
    assert len(despues) == 30, "la recarga duplico filas"
    assert [r[0] for r in antes] == [r[0] for r in despues]
    for (_, a), (_, d) in zip(antes, despues, strict=True):
        assert a == pytest.approx(d)


# ── API contra Postgres ────────────────────────────────────────────────────

@pytest.fixture()
def api_client(loaded):
    """TestClient apuntando a Supabase, no a SQLite en memoria."""
    from fastapi.testclient import TestClient

    from agrosense.adapters.api.app import create_app
    from agrosense.adapters.api.deps import get_session, get_token_verifier
    from agrosense.adapters.db.session import get_session_factory
    from tests.auth.keys import bearer, fake_verifier

    factory = get_session_factory()
    app = create_app()

    def _override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    app.dependency_overrides[get_token_verifier] = fake_verifier
    with TestClient(app, headers=bearer()) as c:
        yield c


def test_api_species_ranking_against_postgres(api_client):
    r = api_client.get("/api/v1/analytics/species")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 30
    assert body[0]["species"] == "Lafoensia speciosa"
    assert body[0]["stall_risk"]["odds_ratio"] == pytest.approx(4.94, abs=0.01)


def test_api_species_detail_with_accents_and_spaces(api_client):
    """El nombre viaja por la URL, el dialecto y de vuelta sin romperse."""
    r = api_client.get("/api/v1/analytics/species/Inga punctata")
    assert r.status_code == 200
    body = r.json()
    assert body["mortality_risk"]["significant"] is True
    assert body["gremio"] == "Intermedia"


def test_api_guild_filter_uses_the_index(api_client):
    r = api_client.get("/api/v1/analytics/species", params={"gremio": "Tardía"})
    assert r.status_code == 200
    body = r.json()
    assert body, "el filtro por un gremio con acento no devolvio nada"
    assert {s["gremio"] for s in body} == {"Tardía"}


def test_api_variance_decomposition_against_postgres(api_client):
    r = api_client.get("/api/v1/analytics/variance-decomposition")
    assert r.status_code == 200
    por_modelo = {m["model"]: m for m in r.json()}
    assert por_modelo["stall"]["species_to_plot_ratio"] == pytest.approx(2.7, abs=0.1)
    assert por_modelo["mortality"]["species_to_plot_ratio"] == pytest.approx(1.1, abs=0.1)


def test_api_top_risk_stall_against_postgres(api_client):
    body = api_client.get("/api/v1/analytics/species/top-risk-stall").json()
    assert [s["species"] for s in body] == [
        "Lafoensia speciosa",
        "Delostoma integrifolium",
        "Persea caerulea",
        "Delostoma roseum",
        "Cedrela montana",
    ]


def test_api_plots_null_effects_serialize_as_null(api_client):
    body = api_client.get("/api/v1/analytics/plots").json()
    assert len(body) == 45
    sin_stall = [p for p in body if p["stall_risk"]["odds_ratio"] is None]
    assert len(sin_stall) == 3
    for p in sin_stall:
        assert p["stall_risk"]["or_ci95"] is None
        assert "sin estimacion" in p["stall_risk"]["interpretation"].lower()
