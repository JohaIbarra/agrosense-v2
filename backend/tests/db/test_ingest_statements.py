"""Regresion de #G: la ingesta escribe en un numero FIJO de sentencias.

Medido contra Supabase el 2026-09-22: subir el dataset de referencia tardaba
91.9s, y el perfil por sentencia mostro que los 856 arboles entraban en UNA
sentencia (0.43s) mientras que las 3146 observaciones se partian en **615**
(34.9s + 20.1s + 14.7s + …). El motivo no es el volumen: al pasar los dicts
por el `insert()` de ORM, las filas se agrupan por el conjunto de columnas no
nulas, y en campo cada fila tiene un patron de nulos distinto (un arbol sin
copa, otro sin estado fitosanitario, otro muerto sin medidas). Cada grupo es
un viaje de ida y vuelta contra el pooler.

Este test no mide tiempo (seria inestable): cuenta SENTENCIAS sobre SQLite,
que es donde la regresion es observable de forma determinista.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from agrosense.adapters.db.repository import CampaignRepository, ProjectRepository
from agrosense.application.dtos import CampaignData
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from tests.auth.keys import ENGINEER_A as OWNER


def _tree(i: int) -> Tree:
    return Tree(
        tree_id=f"T{i}",
        species="Senna viarum",
        # Patrones distintos de nulos entre arboles: es lo que partia el INSERT
        family="Fabaceae" if i % 2 else None,
        common_name="Alcaparro" if i % 3 else None,
        locality="Guayabal",
        plot_id="1",
        sampling_unit_code="U1",
        floristic_design="Rehabilitación vegetal" if i % 2 else None,
    )


def _obs(i: int, campaign: int) -> Observation:
    """Cada arbol aporta un patron de nulos distinto (como en campo)."""
    muerto = i % 5 == 0
    return Observation(
        tree_id=f"T{i}",
        campaign=campaign,
        height_m=None if muerto else 0.3 + i / 100,
        crown_diameter_m=None if i % 3 == 0 else 0.2,
        dap_cm=1.5 if i % 7 == 0 else None,
        dap_status=StatusSemantic.MEDIDO if i % 7 == 0 else StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary=None if muerto else ("Bueno" if i % 2 else "Regular"),
        alive=not muerto,
        colonization=None,
        field_notes="Defoliación parcial" if i % 11 == 0 else None,
    )


def _campaign(n_trees: int, campaigns=(1, 2)) -> CampaignData:
    return CampaignData(
        trees=[_tree(i) for i in range(n_trees)],
        observations=[_obs(i, c) for c in campaigns for i in range(n_trees)],
    )


@pytest.fixture()
def counter(engine):
    """Cuenta las sentencias que llegan al driver, con sus filas."""
    seen: list[tuple[str, int]] = []

    @event.listens_for(engine, "after_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):
        rows = len(parameters) if executemany and parameters is not None else 1
        seen.append((" ".join(statement.split())[:40], rows))

    return seen


def _count(seen, prefix: str) -> tuple[int, int]:
    """(sentencias, filas) de las que empiezan por `prefix`."""
    hits = [(s, n) for s, n in seen if s.startswith(prefix)]
    return len(hits), sum(n for _, n in hits)


def test_insert_uses_one_statement_per_table(session, counter):
    """Arboles y observaciones entran cada uno en UNA sentencia."""
    project = ProjectRepository(session).create("Perf", owner_id=OWNER)
    counter.clear()
    CampaignRepository(session).save_ingest(project.id, _campaign(60), "a.xlsx", "h1")

    stmts, rows = _count(counter, "INSERT INTO trees")
    assert (stmts, rows) == (1, 60), f"{stmts} sentencias para los arboles"
    stmts, rows = _count(counter, "INSERT INTO observations")
    assert (stmts, rows) == (1, 120), f"{stmts} sentencias para las observaciones"


def test_reupload_updates_in_one_statement(session, counter):
    """Y un archivo corregido actualiza en UNA sentencia, no fila a fila."""
    repo = CampaignRepository(session)
    project = ProjectRepository(session).create("Perf", owner_id=OWNER)
    repo.save_ingest(project.id, _campaign(60), "a.xlsx", "h1")
    counter.clear()
    corregido = _campaign(60)
    corregido.observations[0] = corregido.observations[0].model_copy(update={"height_m": 9.9})
    repo.save_ingest(project.id, corregido, "b.xlsx", "h2")

    stmts, rows = _count(counter, "UPDATE observations")
    assert (stmts, rows) == (1, 120), f"{stmts} sentencias para actualizar"
    assert _count(counter, "INSERT INTO observations") == (0, 0)
    # el valor corregido manda
    from agrosense.adapters.db.models import ObservationRow

    alturas = [o.height_m for o in session.query(ObservationRow).all()]
    assert 9.9 in alturas
