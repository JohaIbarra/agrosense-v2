"""ProjectSpeciesRepository: especies plantadas de un proyecto (E5, UC-AN3)."""
from __future__ import annotations

import itertools

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import Base, Project, TreeRow
from agrosense.adapters.db.repository import ProjectSpeciesRepository

# `project_code` es unico global (models.Project): cada proyecto de prueba
# necesita el suyo, no uno fijo compartido entre llamadas a `_project`.
_codigos = itertools.count(1)


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    yield s
    s.close()


def _project(session, owner="eng-1") -> Project:
    codigo = f"AGS-2026-{next(_codigos):04d}"
    p = Project(name="P1", owner_id=owner, project_code=codigo)
    session.add(p)
    session.commit()
    return p


def test_lists_distinct_species_with_tree_count(session):
    p = _project(session)
    session.add_all([
        TreeRow(project_id=p.id, tree_id="T1", species="Lafoensia speciosa"),
        TreeRow(project_id=p.id, tree_id="T2", species="Lafoensia speciosa"),
        TreeRow(project_id=p.id, tree_id="T3", species="Inga punctata"),
    ])
    session.commit()

    rows = ProjectSpeciesRepository(session).list_species(p.id)

    assert rows == [("Inga punctata", 1), ("Lafoensia speciosa", 2)]


def test_only_this_projects_trees_count(session):
    p1 = _project(session, owner="eng-1")
    p2 = _project(session, owner="eng-2")
    session.add_all([
        TreeRow(project_id=p1.id, tree_id="T1", species="Especie A"),
        TreeRow(project_id=p2.id, tree_id="T1", species="Especie B"),
    ])
    session.commit()

    rows = ProjectSpeciesRepository(session).list_species(p1.id)
    assert rows == [("Especie A", 1)]


def test_project_without_trees_is_empty(session):
    p = _project(session)
    assert ProjectSpeciesRepository(session).list_species(p.id) == []
