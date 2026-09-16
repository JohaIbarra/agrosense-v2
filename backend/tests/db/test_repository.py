"""Tests de repositorios contra Supabase REAL (integration).

Cada test limpia lo que crea (DELETE por name/unique conocido).
Requiere .env con DATABASE_URL — skip con mensaje claro si falta.
"""
import os

import pytest

from agrosense.adapters.db.models import Base, ObservationRow, Project, TreeRow
from agrosense.adapters.db.repository import CampaignRepository, ProjectRepository

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL ausente (backend/.env)",
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
def cleanup_project(session):
    """Garantiza que el proyecto de test no sobrevive al test."""
    name = "repo-test-project"
    yield name
    proj = session.query(Project).filter_by(name=name).first()
    if proj:
        session.delete(proj)
        session.commit()


class TestProjectRepository:
    def test_create_and_get(self, session, cleanup_project):
        repo = ProjectRepository(session)
        p = repo.create(name=cleanup_project, locality="Guayabal", description=None)
        assert p.id > 0
        assert p.name == cleanup_project

        fetched = repo.get(p.id)
        assert fetched is not None
        assert fetched.locality == "Guayabal"

    def test_duplicate_name_rejected(self, session, cleanup_project):
        repo = ProjectRepository(session)
        repo.create(name=cleanup_project, locality=None, description=None)
        with pytest.raises(ValueError, match="DUPLICATE_NAME"):
            repo.create(name=cleanup_project, locality=None, description=None)

    def test_list_all_contains_created(self, session, cleanup_project):
        repo = ProjectRepository(session)
        repo.create(name=cleanup_project, locality=None, description=None)
        names = [p.name for p in repo.list_all()]
        assert cleanup_project in names

    def test_get_missing_returns_none(self, session):
        repo = ProjectRepository(session)
        assert repo.get(999_999_999) is None


class TestCampaignRepository:
    def test_save_ingest_real_dataset(self, session):
        """Ingesta el dataset de referencia COMPLETO en un proyecto de test."""
        from pathlib import Path

        import pandas as pd
        from agrosense.adapters.ingester.ingest import ingest_wide

        ref = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"
        if not ref.exists():
            pytest.skip("dataset de referencia local ausente")

        prepo = ProjectRepository(session)
        # idempotente: si un run anterior se interrumpio antes del cleanup
        old = session.query(Project).filter_by(name="repo-test-campaign-full").first()
        if old:
            session.delete(old)
            session.commit()
        proj = prepo.create(name="repo-test-campaign-full", locality=None, description=None)
        try:
            df = pd.read_excel(ref, sheet_name="Monitoreo_4")
            result = ingest_wide(df)

            crepo = CampaignRepository(session)
            stats = crepo.save_ingest(
                project_id=proj.id,
                result=result,
                filename="anexo1.xlsx",
                sha256="a" * 64,  # sha de test
            )
            assert stats["trees"] == 856
            assert stats["observations"] == 3146
            assert stats["deaths"] == 340

            # persistencia real verificable
            n_trees = session.query(TreeRow).filter_by(project_id=proj.id).count()
            n_obs = (
                session.query(ObservationRow)
                .join(TreeRow)
                .filter(TreeRow.project_id == proj.id)
                .count()
            )
            assert n_trees == 856
            assert n_obs == 3146
        finally:
            session.delete(proj)  # cascade limpia trees/observations
            session.commit()

    def test_duplicate_sha_rejected(self, session):
        """Provenance: el mismo archivo no se ingesta dos veces al proyecto."""
        from agrosense.adapters.ingester.ingest import IngestResult
        from agrosense.domain.entities import Tree

        prepo = ProjectRepository(session)
        proj = prepo.create(name="repo-test-dup", locality=None, description=None)
        try:
            result = IngestResult(
                trees=[Tree(tree_id="T1", species="S")],
                observations=[],
                warnings=[],
                mapping_version="test",
            )
            crepo = CampaignRepository(session)
            crepo.save_ingest(proj.id, result, "f.xlsx", "b" * 64)
            with pytest.raises(ValueError, match="DUPLICATE_FILE"):
                crepo.save_ingest(proj.id, result, "f.xlsx", "b" * 64)
        finally:
            session.delete(proj)
            session.commit()
