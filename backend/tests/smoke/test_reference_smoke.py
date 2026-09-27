"""Smoke del slice 5 contra Supabase REAL.

    pytest -m supabase

Que verifica aqui, y NO en `tests/analytics/` ni `tests/db/` (que corren
sobre SQLite):

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

Requiere que el referente este publicado (`python scripts/load_analytics.py`).
Si no lo esta, los tests hacen skip con el motivo: el smoke informa, no miente.

E5: el referente ahora es versionado (`reference_models` + `is_active`).
Todo lo que este archivo lee filtra por la version activa via join contra
`reference_models`: leer sin ese filtro mezclaria efectos de dos corridas
distintas del modelo mixto, que es exactamente lo que `ReferenceRepository`
evita en produccion.

Estos tests son de SOLO LECTURA sobre las tablas del referente salvo
`test_publishing_twice_keeps_the_active_version_and_the_previous_rows`, que
publica una version nueva (no borra la anterior: publicar nunca borra desde
E5) y comprueba que ambas versiones sobreviven intactas.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import inspect, text

from agrosense.adapters.db.models import (
    Base,
    ReferenceModel,
    ReferencePlotEffect,
    ReferenceSpeciesEffect,
    VarianceComponent,
)

pytestmark = [
    pytest.mark.supabase,
    pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="DATABASE_URL ausente (backend/.env)",
    ),
]

REFERENCE_TABLES = (
    "reference_models",
    "reference_species_effects",
    "reference_plot_effects",
    "variance_components",
)


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
    """Salta —sin fallar— si el referente no esta publicado en esta DB."""
    activo = session.query(ReferenceModel).filter(ReferenceModel.is_active.is_(True)).first()
    if activo is None:
        pytest.skip(
            "referente no publicado en Supabase: ejecuta "
            "`python scripts/load_analytics.py`"
        )
    return session


def _active_id(session) -> int:
    return session.query(ReferenceModel.id).filter(ReferenceModel.is_active.is_(True)).scalar()


# ── Esquema ────────────────────────────────────────────────────────────────

def test_reference_tables_exist_in_postgres(session):
    """La migracion c7e9f2a4b6d8 esta realmente aplicada en Supabase."""
    reales = set(inspect(session.get_bind()).get_table_names())
    faltan = [t for t in REFERENCE_TABLES if t not in reales]
    assert not faltan, f"falta aplicar la migracion: {faltan}"


@pytest.mark.parametrize("table", REFERENCE_TABLES)
def test_columns_match_the_model(session, table):
    inspector = inspect(session.get_bind())
    reales = {c["name"] for c in inspector.get_columns(table)}
    esperadas = {c.name for c in Base.metadata.tables[table].columns}
    assert esperadas <= reales, f"columnas ausentes en {table}: {sorted(esperadas - reales)}"


def test_postgres_types_are_the_intended_ones(session):
    """BOOLEAN y TIMESTAMPTZ de verdad — lo que SQLite no distingue."""
    tipos = {
        c["name"]: str(c["type"]).upper()
        for c in inspect(session.get_bind()).get_columns("reference_species_effects")
    }
    assert "BOOLEAN" in tipos["sig_stall"]
    assert "BOOLEAN" in tipos["sig_mort"]
    assert "INTEGER" in tipos["n_trees"]
    assert "TIMESTAMP" in tipos["updated_at"]


def test_variance_unique_constraint_exists_in_the_database(session):
    """Sin ella, dos filas de la MISMA version podrian duplicar un ICC."""
    nombres = {
        u["name"]
        for u in inspect(session.get_bind()).get_unique_constraints("variance_components")
    }
    assert "uq_variance_model_grouping" in nombres


def test_indexes_were_created(session):
    idx_species = {
        i["name"] for i in inspect(session.get_bind()).get_indexes("reference_species_effects")
    }
    assert "ix_reference_species_effects_or_stall" in idx_species
    assert "ix_reference_species_effects_or_mort" in idx_species
    assert "ix_reference_species_effects_gremio" in idx_species

    idx_plots = {
        i["name"] for i in inspect(session.get_bind()).get_indexes("reference_plot_effects")
    }
    assert "ix_reference_plot_effects_localidad" in idx_plots


def test_reference_tables_have_no_project_foreign_key(session):
    """Ninguna FK hacia `projects`: el referente es independiente de ese grafo.

    Una FK hacia `reference_models` SI se espera (E5: cada fila de efectos
    pertenece a una version) — lo que esta prohibido es colgar el referente
    de un proyecto, no de su propia tabla de versiones.
    """
    inspector = inspect(session.get_bind())
    for table in REFERENCE_TABLES:
        fks = inspector.get_foreign_keys(table)
        assert not any(fk["referred_table"] == "projects" for fk in fks), (
            f"{table} gano una FK hacia projects; el referente es independiente "
            f"del grafo de proyectos (ver models.ReferenceModel)"
        )


# ── Contenido (version activa) ───────────────────────────────────────────────

def test_row_counts(loaded):
    activo = _active_id(loaded)
    assert (
        loaded.query(ReferenceSpeciesEffect)
        .filter(ReferenceSpeciesEffect.reference_model_id == activo)
        .count()
        == 30
    )
    assert (
        loaded.query(ReferencePlotEffect)
        .filter(ReferencePlotEffect.reference_model_id == activo)
        .count()
        == 45
    )
    assert (
        loaded.query(VarianceComponent)
        .filter(VarianceComponent.reference_model_id == activo)
        .count()
        == 4
    )


def test_booleans_filter_as_booleans_in_postgres(loaded):
    """`sig_*` es BOOLEAN real: un WHERE sobre el filtra de verdad.

    En SQLite estos valores son 0/1 y este mismo assert pasaria aunque la
    columna estuviera poblada con enteros.
    """
    sig_stall = loaded.execute(
        text(
            "select count(*) from reference_species_effects rse "
            "join reference_models rm on rm.id = rse.reference_model_id "
            "where rm.is_active and rse.sig_stall"
        )
    ).scalar()
    sig_mort = loaded.execute(
        text(
            "select count(*) from reference_species_effects rse "
            "join reference_models rm on rm.id = rse.reference_model_id "
            "where rm.is_active and rse.sig_mort"
        )
    ).scalar()
    assert sig_stall == 8
    assert sig_mort == 1

    valor = loaded.execute(
        text(
            "select rse.sig_stall from reference_species_effects rse "
            "join reference_models rm on rm.id = rse.reference_model_id "
            "where rm.is_active and rse.species_name = :n"
        ),
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
            "select rpe.plot_code, rpe.or_stall, rpe.or_mort "
            "from reference_plot_effects rpe "
            "join reference_models rm on rm.id = rpe.reference_model_id "
            "where rm.is_active and rpe.or_stall is null "
            "order by rpe.plot_code"
        )
    ).all()
    assert len(filas) == 3
    for _, or_stall, or_mort in filas:
        assert or_stall is None
        assert or_mort is not None

    assert (
        loaded.execute(
            text(
                "select count(*) from reference_plot_effects rpe "
                "join reference_models rm on rm.id = rpe.reference_model_id "
                "where rm.is_active and rpe.or_stall = 0"
            )
        ).scalar()
        == 0
    )


def test_utf8_survives_the_round_trip(loaded):
    """Acentos y NBSP tras pasar por el dialecto real.

    Un encoding mal declarado en el loader NO falla: guarda mojibake. La
    unica forma de detectarlo es mirar los codepoints de vuelta.
    """
    gremios = {
        g
        for (g,) in loaded.execute(
            text(
                "select distinct rse.gremio from reference_species_effects rse "
                "join reference_models rm on rm.id = rse.reference_model_id "
                "where rm.is_active"
            )
        )
    }
    assert gremios == {"Inicial", "Intermedia", "Tardía"}
    assert "Tard\xeda" in gremios, "la í debe ser U+00ED, no mojibake"

    nombre = loaded.execute(
        text(
            "select rse.species_name from reference_species_effects rse "
            "join reference_models rm on rm.id = rse.reference_model_id "
            "where rm.is_active and rse.sig_mort"
        )
    ).scalar()
    assert nombre == "Inga punctata"
    assert "\xa0" not in nombre, "el NBSP del CSV llego hasta la base de datos"
    assert len(nombre) == 13


def test_the_report_numbers_survived(loaded):
    """Control puntual contra el informe, leido desde Postgres."""
    fila = loaded.execute(
        text(
            "select rse.or_stall, rse.or_stall_lo, rse.or_stall_hi, rse.gremio, "
            "rse.n_trees from reference_species_effects rse "
            "join reference_models rm on rm.id = rse.reference_model_id "
            "where rm.is_active and rse.species_name = :n"
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
            text(
                "select vc.model, vc.grouping, vc.icc from variance_components vc "
                "join reference_models rm on rm.id = vc.reference_model_id "
                "where rm.is_active"
            )
        )
    }
    assert icc[("stall", "especie")] == pytest.approx(0.190, abs=0.001)
    assert icc[("mortality", "parcela")] == pytest.approx(0.091, abs=0.001)


def test_ci_consistency_computed_by_postgres(loaded):
    """`or_lo < or < or_hi` verificado por el motor, no por Python."""
    malas = loaded.execute(
        text(
            "select rse.species_name from reference_species_effects rse "
            "join reference_models rm on rm.id = rse.reference_model_id "
            "where rm.is_active and rse.or_stall is not null "
            "and not (rse.or_stall_lo < rse.or_stall and rse.or_stall < rse.or_stall_hi)"
        )
    ).all()
    assert not malas, f"IC inconsistente en: {[m[0] for m in malas]}"

    no_positivos = loaded.execute(
        text(
            "select count(*) from reference_species_effects rse "
            "join reference_models rm on rm.id = rse.reference_model_id "
            "where rm.is_active and rse.or_stall_lo <= 0"
        )
    ).scalar()
    assert no_positivos == 0, "un OR nunca es <= 0"


# ── Publicacion ────────────────────────────────────────────────────────────

def test_publishing_twice_keeps_the_active_version_and_the_previous_rows(loaded):
    """Publicar de nuevo no borra la version anterior (ADR-004, E5).

    Antes de E5, recargar (`AnalyticsRepository.replace_all`) borraba las 30
    filas y las volvia a insertar en el sitio: la propiedad que se probaba
    era "no duplico filas". Ahora publicar SIEMPRE agrega una version nueva
    y activa esa; lo que debe seguir siendo cierto es que (a) la version
    recien publicada tiene las 30 especies y queda activa, y (b) la version
    que era activa antes sigue en la base, intacta, solo que ya no activa.
    """
    import sys
    from pathlib import Path

    scripts = Path(__file__).parents[2] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import load_analytics

    from agrosense.adapters.analytics.effects_loader import build_bundle
    from agrosense.adapters.db.repository import ReferenceRepository

    processed = Path(__file__).parents[2] / "data" / "processed"
    if not (processed / "efectos_aleatorios.csv").exists():
        pytest.skip("CSV de los modelos mixtos ausentes")

    previous_id = _active_id(loaded)
    previous_species = loaded.execute(
        text(
            "select species_name, or_stall from reference_species_effects "
            "where reference_model_id = :id order by species_name"
        ),
        {"id": previous_id},
    ).all()
    assert len(previous_species) == 30

    bundle = build_bundle(processed)
    model = load_analytics.build_reference_model(bundle)
    species, plots, variance = load_analytics.to_orm(bundle)
    published = ReferenceRepository(loaded).publish_version(model, species, plots, variance)

    nueva_activa = loaded.execute(
        text("select count(*) from reference_species_effects where reference_model_id = :id"),
        {"id": published.id},
    ).scalar()
    assert nueva_activa == 30, "la version recien publicada deberia tener las 30 especies"
    assert _active_id(loaded) == published.id

    anterior_intacta = loaded.execute(
        text(
            "select species_name, or_stall from reference_species_effects "
            "where reference_model_id = :id order by species_name"
        ),
        {"id": previous_id},
    ).all()
    assert len(anterior_intacta) == 30, "la version anterior perdio filas al publicar de nuevo"
    assert [r[0] for r in previous_species] == [r[0] for r in anterior_intacta]
    for (_, a), (_, d) in zip(previous_species, anterior_intacta, strict=True):
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
    r = api_client.get("/api/v1/reference/species")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 30
    assert body[0]["species"] == "Lafoensia speciosa"
    assert body[0]["stall_risk"]["odds_ratio"] == pytest.approx(4.94, abs=0.01)


def test_api_species_detail_with_accents_and_spaces(api_client):
    """El nombre viaja por la URL, el dialecto y de vuelta sin romperse."""
    r = api_client.get("/api/v1/reference/species/Inga punctata")
    assert r.status_code == 200
    body = r.json()
    assert body["mortality_risk"]["significant"] is True
    assert body["gremio"] == "Intermedia"


def test_api_guild_filter_uses_the_index(api_client):
    r = api_client.get("/api/v1/reference/species", params={"gremio": "Tardía"})
    assert r.status_code == 200
    body = r.json()
    assert body, "el filtro por un gremio con acento no devolvio nada"
    assert {s["gremio"] for s in body} == {"Tardía"}


def test_api_variance_decomposition_against_postgres(api_client):
    r = api_client.get("/api/v1/reference/variance-decomposition")
    assert r.status_code == 200
    por_modelo = {m["model"]: m for m in r.json()}
    assert por_modelo["stall"]["species_to_plot_ratio"] == pytest.approx(2.7, abs=0.1)
    assert por_modelo["mortality"]["species_to_plot_ratio"] == pytest.approx(1.1, abs=0.1)


def test_api_top_risk_stall_against_postgres(api_client):
    body = api_client.get("/api/v1/reference/species/top-risk-stall").json()
    assert [s["species"] for s in body] == [
        "Lafoensia speciosa",
        "Delostoma integrifolium",
        "Persea caerulea",
        "Delostoma roseum",
        "Cedrela montana",
    ]


def test_api_plots_null_effects_serialize_as_null(api_client):
    body = api_client.get("/api/v1/reference/plots").json()
    assert len(body) == 45
    sin_stall = [p for p in body if p["stall_risk"]["odds_ratio"] is None]
    assert len(sin_stall) == 3
    for p in sin_stall:
        assert p["stall_risk"]["or_ci95"] is None
        assert "sin estimacion" in p["stall_risk"]["interpretation"].lower()
