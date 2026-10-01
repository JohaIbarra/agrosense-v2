"""Tests de repositorios contra SQLite local (fixture `session`).

Corren SIEMPRE, en cada `pytest`: no dependen de DATABASE_URL ni de la red.
El equivalente contra Postgres real es `tests/smoke/test_supabase_smoke.py`
(marcado `supabase`), que verifica lo unico que SQLite no puede: que la
migracion aplicada en Supabase coincide con estos models.
"""
from pathlib import Path

import pytest

from agrosense.adapters.db.models import CampaignFile, ObservationRow, TreeRow
from agrosense.adapters.db.repository import CampaignRepository, ProjectRepository
from agrosense.application.dtos import CampaignData
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from tests.auth.keys import ENGINEER_A as OWNER

DATASET = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"


def sample_campaign() -> CampaignData:
    """Campana minima: 2 arboles, 3 observaciones, 1 muerte."""

    def obs(tree_id: str, campaign: int, alive: bool) -> Observation:
        return Observation(
            tree_id=tree_id,
            campaign=campaign,
            height_m=1.2,
            crown_diameter_m=0.8,
            dap_cm=None,
            dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
            phytosanitary="Sano",
            alive=alive,
            colonization=None,
        )

    return CampaignData(
        trees=[
            Tree(tree_id="T1", species="Cedrela odorata", locality="Guayabal"),
            Tree(tree_id="T2", species="Inga edulis", locality="Guayabal"),
        ],
        observations=[obs("T1", 1, True), obs("T1", 2, True), obs("T2", 1, False)],
        warnings=[],
        mapping_version="test-1",
    )


class TestProjectRepository:
    def test_create_and_get(self, session):
        repo = ProjectRepository(session)
        p = repo.create(owner_id=OWNER, name="repo-test-project", locality="Guayabal")
        assert p.id > 0
        assert p.name == "repo-test-project"

        fetched = repo.get(p.id)
        assert fetched is not None
        assert fetched.locality == "Guayabal"

    def test_duplicate_name_rejected(self, session):
        repo = ProjectRepository(session)
        repo.create(owner_id=OWNER, name="repo-test-project")
        with pytest.raises(ValueError, match="DUPLICATE_NAME"):
            repo.create(owner_id=OWNER, name="repo-test-project")

    def test_list_all_contains_created(self, session):
        repo = ProjectRepository(session)
        repo.create(owner_id=OWNER, name="repo-test-project")
        names = [p.name for p in repo.list_all()]
        assert "repo-test-project" in names

    def test_get_missing_returns_none(self, session):
        repo = ProjectRepository(session)
        assert repo.get(999_999_999) is None

    def test_campaigns_count_starts_at_zero(self, session):
        repo = ProjectRepository(session)
        p = repo.create(owner_id=OWNER, name="sin-campanas")
        assert repo.campaigns_count(p.id) == 0


class TestCampaignRepositoryReads:
    """Lecturas que alimentan los GET del contrato (UC3 / UC7)."""

    @pytest.fixture()
    def project_with_campaign(self, session):
        prepo = ProjectRepository(session)
        proj = prepo.create(owner_id=OWNER, name="lecturas")
        CampaignRepository(session).save_ingest(
            project_id=proj.id,
            result=sample_campaign(),
            filename="m1.xlsx",
            sha256="c" * 64,
        )
        return proj

    def test_get_campaigns_returns_provenance(self, session, project_with_campaign):
        repo = ProjectRepository(session)
        campaigns = repo.get_campaigns(project_with_campaign.id)
        assert len(campaigns) == 1
        assert campaigns[0].filename == "m1.xlsx"
        assert campaigns[0].sha256 == "c" * 64
        assert campaigns[0].mapping_version == "test-1"

    def test_get_trees_is_paginated(self, session, project_with_campaign):
        repo = ProjectRepository(session)
        assert len(repo.get_trees(project_with_campaign.id)) == 2
        assert len(repo.get_trees(project_with_campaign.id, limit=1)) == 1
        assert len(repo.get_trees(project_with_campaign.id, limit=1, offset=1)) == 1
        assert repo.get_trees(project_with_campaign.id, offset=99) == []

    def test_get_observations_ordered_by_campaign(self, session, project_with_campaign):
        repo = ProjectRepository(session)
        tree = next(
            t for t in repo.get_trees(project_with_campaign.id) if t.tree_id == "T1"
        )
        obs = repo.get_observations(tree.id)
        assert [o.campaign for o in obs] == [1, 2]

    def test_get_tree_row_is_scoped_to_project(self, session, project_with_campaign):
        """Un arbol de otro proyecto no se puede leer por id (aislamiento)."""
        repo = ProjectRepository(session)
        tree = repo.get_trees(project_with_campaign.id)[0]
        other = repo.create(owner_id=OWNER, name="otro")
        assert repo.get_tree_row(project_with_campaign.id, tree.id) is not None
        assert repo.get_tree_row(other.id, tree.id) is None


class TestCampaignRepositoryWrites:
    def test_save_ingest_persists_trees_and_observations(self, session):
        prepo = ProjectRepository(session)
        proj = prepo.create(owner_id=OWNER, name="escritura")

        stats = CampaignRepository(session).save_ingest(
            project_id=proj.id,
            result=sample_campaign(),
            filename="m1.xlsx",
            sha256="d" * 64,
        )
        assert stats["trees"] == 2
        assert stats["observations"] == 3
        assert stats["deaths"] == 1
        assert stats["campaign_id"] is not None

        assert session.query(TreeRow).filter_by(project_id=proj.id).count() == 2
        assert (
            session.query(ObservationRow).join(TreeRow).filter(
                TreeRow.project_id == proj.id
            ).count()
            == 3
        )

    def test_duplicate_sha_rejected(self, session):
        """Provenance: el mismo archivo no se ingesta dos veces al proyecto."""
        prepo = ProjectRepository(session)
        proj = prepo.create(owner_id=OWNER, name="repo-test-dup")
        crepo = CampaignRepository(session)

        crepo.save_ingest(proj.id, sample_campaign(), "f.xlsx", "b" * 64)
        with pytest.raises(ValueError, match="DUPLICATE_FILE"):
            crepo.save_ingest(proj.id, sample_campaign(), "f.xlsx", "b" * 64)

    def test_same_sha_allowed_in_another_project(self, session):
        """El unique es (project_id, sha256): otro proyecto puede subir el mismo archivo."""
        prepo = ProjectRepository(session)
        a = prepo.create(owner_id=OWNER, name="proy-a")
        b = prepo.create(owner_id=OWNER, name="proy-b")
        crepo = CampaignRepository(session)

        crepo.save_ingest(a.id, sample_campaign(), "f.xlsx", "e" * 64)
        stats = crepo.save_ingest(b.id, sample_campaign(), "f.xlsx", "e" * 64)
        assert stats["trees"] == 2

    def test_deleting_project_cascades(self, session):
        """Sin huerfanos: borrar el proyecto se lleva arboles y observaciones."""
        prepo = ProjectRepository(session)
        proj = prepo.create(owner_id=OWNER, name="cascada")
        CampaignRepository(session).save_ingest(
            proj.id, sample_campaign(), "f.xlsx", "f" * 64
        )

        session.delete(proj)
        session.commit()

        assert session.query(TreeRow).count() == 0
        assert session.query(ObservationRow).count() == 0
        assert session.query(CampaignFile).count() == 0

    def test_save_ingest_of_real_dataset(self, session):
        """Dataset de referencia completo: 856 arboles, 3146 observaciones."""
        if not DATASET.exists():
            pytest.skip("dataset de referencia local ausente")

        import pandas as pd

        from agrosense.adapters.ingester.ingest import ingest_wide

        prepo = ProjectRepository(session)
        proj = prepo.create(owner_id=OWNER, name="dataset-real")
        result = ingest_wide(pd.read_excel(DATASET, sheet_name="Monitoreo_4"))

        stats = CampaignRepository(session).save_ingest(
            project_id=proj.id,
            result=result,
            filename="anexo1.xlsx",
            sha256="a" * 64,
        )
        assert stats["trees"] == 856
        assert stats["observations"] == 3146
        assert stats["deaths"] == 340

        assert session.query(TreeRow).filter_by(project_id=proj.id).count() == 856
        assert (
            session.query(ObservationRow).join(TreeRow).filter(
                TreeRow.project_id == proj.id
            ).count()
            == 3146
        )

    def test_failed_ingest_leaves_nothing_behind(self, session):
        """ADR-004: sin persistencia parcial. Si la escritura falla, rollback total."""
        prepo = ProjectRepository(session)
        proj = prepo.create(owner_id=OWNER, name="atomico")

        data = sample_campaign()
        # Observacion que apunta a un arbol inexistente: revienta a mitad del guardado
        data.observations.append(
            Observation(
                tree_id="FANTASMA",
                campaign=1,
                height_m=1.0,
                crown_diameter_m=None,
                dap_cm=None,
                dap_status=StatusSemantic.SIN_CENSO,
                phytosanitary=None,
                alive=True,
                colonization=None,
            )
        )

        with pytest.raises(Exception):
            CampaignRepository(session).save_ingest(
                proj.id, data, "roto.xlsx", "9" * 64
            )

        assert session.query(TreeRow).filter_by(project_id=proj.id).count() == 0
        assert session.query(ObservationRow).count() == 0
        assert session.query(CampaignFile).count() == 0


class TestRawFileIsKept:
    """Deuda D (cerrada en E8, ADR-014): el Excel crudo se guarda con su hash."""

    def test_save_ingest_stores_the_raw_bytes(self, session):
        from agrosense.adapters.db.models import CampaignFile

        proj = ProjectRepository(session).create(owner_id=OWNER, name="crudo")
        CampaignRepository(session).save_ingest(
            project_id=proj.id,
            result=sample_campaign(),
            filename="m1.xlsx",
            sha256="e" * 64,
            content=b"PK\x03\x04 excel crudo",
        )
        row = session.query(CampaignFile).filter_by(project_id=proj.id).one()
        assert row.content == b"PK\x03\x04 excel crudo"

    def test_content_is_optional_for_legacy_callers(self, session):
        from agrosense.adapters.db.models import CampaignFile

        proj = ProjectRepository(session).create(owner_id=OWNER, name="sin crudo")
        CampaignRepository(session).save_ingest(
            project_id=proj.id, result=sample_campaign(), filename="m1.xlsx", sha256="f" * 64
        )
        assert session.query(CampaignFile).filter_by(project_id=proj.id).one().content is None
