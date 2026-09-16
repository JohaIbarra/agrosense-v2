"""Tests TDD para UC1 (create_project) y UC2 (upload_campaign).

Usan fake repos en memoria — cero dependencias de DB ni HTTP.
Deben FALLAR antes de que exista la implementación (red phase).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

# ── Fake repos en memoria ──────────────────────────────────────────────────

@dataclass
class FakeProject:
    id: int
    name: str
    locality: str | None
    description: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    campaigns: list = field(default_factory=list)


class FakeProjectRepository:
    """Implementación en memoria para tests unitarios."""

    def __init__(self) -> None:
        self._projects: dict[int, FakeProject] = {}
        self._next_id = 1

    def create(self, name: str, locality: str | None, description: str | None) -> FakeProject:
        for p in self._projects.values():
            if p.name == name:
                raise ValueError("DUPLICATE_NAME")
        p = FakeProject(id=self._next_id, name=name, locality=locality, description=description)
        self._projects[self._next_id] = p
        self._next_id += 1
        return p

    def get(self, project_id: int) -> FakeProject | None:
        return self._projects.get(project_id)

    def campaigns_count(self, project_id: int) -> int:
        p = self._projects.get(project_id)
        return len(p.campaigns) if p else 0


@dataclass
class FakeCampaignFile:
    id: int
    project_id: int
    filename: str
    sha256: str
    trees: int
    observations: int
    deaths: int
    mapping_version: str
    warnings: list


class FakeCampaignRepository:
    """Implementación en memoria para tests unitarios."""

    def __init__(self, project_repo: FakeProjectRepository) -> None:
        self._campaigns: list[FakeCampaignFile] = []
        self._next_id = 1
        self._project_repo = project_repo

    def save_ingest(self, project_id: int, result: Any, filename: str, sha256: str) -> dict:
        # Verificar duplicado SHA en mismo proyecto
        for c in self._campaigns:
            if c.project_id == project_id and c.sha256 == sha256:
                raise ValueError("DUPLICATE_FILE")

        deaths = sum(1 for o in result.observations if o.alive is False)
        cf = FakeCampaignFile(
            id=self._next_id,
            project_id=project_id,
            filename=filename,
            sha256=sha256,
            trees=len(result.trees),
            observations=len(result.observations),
            deaths=deaths,
            mapping_version=result.mapping_version,
            warnings=result.warnings,
        )
        self._campaigns.append(cf)
        proj = self._project_repo.get(project_id)
        if proj is not None:
            proj.campaigns.append(cf)
        self._next_id += 1
        return {
            "campaign_id": cf.id,
            "trees": cf.trees,
            "observations": cf.observations,
            "deaths": cf.deaths,
            "warnings": cf.warnings,
            "mapping_version": cf.mapping_version,
        }


# ── Helpers ────────────────────────────────────────────────────────────────

def make_repos() -> tuple[FakeProjectRepository, FakeCampaignRepository]:
    proj_repo = FakeProjectRepository()
    camp_repo = FakeCampaignRepository(proj_repo)
    return proj_repo, camp_repo


DATASET = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"


# ── UC1: create_project ────────────────────────────────────────────────────

class TestCreateProject:
    def test_create_returns_response_with_id(self):
        from agrosense.application.use_cases.create_project import create_project

        proj_repo, _ = make_repos()
        result = create_project(
            repo=proj_repo,
            name="Restauración Guayabal",
            locality="Guayabal",
            description="Piloto",
        )
        assert result.id > 0
        assert result.name == "Restauración Guayabal"
        assert result.locality == "Guayabal"
        assert result.campaigns_count == 0

    def test_create_locality_optional(self):
        from agrosense.application.use_cases.create_project import create_project

        proj_repo, _ = make_repos()
        result = create_project(
            repo=proj_repo, name="Sin localidad", locality=None, description=None
        )
        assert result.locality is None

    def test_duplicate_name_raises(self):
        from agrosense.application.use_cases.create_project import create_project

        proj_repo, _ = make_repos()
        create_project(repo=proj_repo, name="Duplicado", locality=None, description=None)
        with pytest.raises(ValueError, match="DUPLICATE_NAME"):
            create_project(repo=proj_repo, name="Duplicado", locality=None, description=None)

    def test_response_is_project_response_schema(self):
        """El use case devuelve un ProjectResponse (schema del contrato)."""
        from agrosense.adapters.api.schemas import ProjectResponse
        from agrosense.application.use_cases.create_project import create_project

        proj_repo, _ = make_repos()
        result = create_project(repo=proj_repo, name="Schema test", locality=None, description=None)
        assert isinstance(result, ProjectResponse)


# ── UC2: upload_campaign ───────────────────────────────────────────────────

class TestUploadCampaign:
    def test_upload_dataset_returns_correct_stats(self):
        """E2E con dataset real: 856 trees, 3146 obs, 340 deaths."""
        if not DATASET.exists():
            pytest.skip("dataset de referencia local ausente")

        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Test Upload", None, None)

        result = upload_campaign(
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=DATASET.read_bytes(),
            project_repo=proj_repo,
            campaign_repo=camp_repo,
        )
        assert result.trees == 856
        assert result.observations == 3146
        assert result.deaths == 340
        assert result.valid is True
        assert result.campaign_id is not None

    def test_upload_returns_warnings(self):
        """El resultado incluye warnings del ingester (>0 en dataset real)."""
        if not DATASET.exists():
            pytest.skip("dataset de referencia local ausente")

        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Test Warnings", None, None)

        result = upload_campaign(
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=DATASET.read_bytes(),
            project_repo=proj_repo,
            campaign_repo=camp_repo,
        )
        # El dataset real tiene ~19 warnings (briefing E2E)
        assert len(result.warnings) > 0

    def test_warning_items_have_correct_types(self):
        """Todos los WarningItems tienen type dentro del enum documentado."""
        if not DATASET.exists():
            pytest.skip("dataset de referencia local ausente")

        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Test Warning Types", None, None)

        result = upload_campaign(
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=DATASET.read_bytes(),
            project_repo=proj_repo,
            campaign_repo=camp_repo,
        )
        valid_types = {"contraction", "revival", "census_gap"}
        for w in result.warnings:
            assert w.type in valid_types, f"Tipo de warning desconocido: {w.type!r}"

    def test_upload_project_not_found_raises(self):
        """Proyecto inexistente → ValueError PROJECT_NOT_FOUND."""
        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        with pytest.raises(ValueError, match="PROJECT_NOT_FOUND"):
            upload_campaign(
                project_id=999,
                filename="dummy.xlsx",
                content=b"",
                project_repo=proj_repo,
                campaign_repo=camp_repo,
            )

    def test_upload_invalid_bytes_raises_value_error(self):
        """Bytes que no son un Excel válido → ValueError claro (no stack trace)."""
        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Test Invalid", None, None)
        with pytest.raises(ValueError, match="INVALID_FILE"):
            upload_campaign(
                project_id=proj.id,
                filename="notexcel.txt",
                content=b"esto no es un xlsx",
                project_repo=proj_repo,
                campaign_repo=camp_repo,
            )

    def test_upload_duplicate_file_raises(self):
        """El mismo sha256 no se acepta dos veces en el mismo proyecto."""
        if not DATASET.exists():
            pytest.skip("dataset de referencia local ausente")

        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Test Dup", None, None)
        content = DATASET.read_bytes()

        upload_campaign(
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=content,
            project_repo=proj_repo,
            campaign_repo=camp_repo,
        )
        with pytest.raises(ValueError, match="DUPLICATE_FILE"):
            upload_campaign(
                project_id=proj.id,
                filename="anexo1.xlsx",
                content=content,
                project_repo=proj_repo,
                campaign_repo=camp_repo,
            )

    def test_result_is_upload_result_response_schema(self):
        """El use case devuelve un UploadResultResponse (schema del contrato)."""
        if not DATASET.exists():
            pytest.skip("dataset de referencia local ausente")

        from agrosense.adapters.api.schemas import UploadResultResponse
        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Schema Result Test", None, None)

        result = upload_campaign(
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=DATASET.read_bytes(),
            project_repo=proj_repo,
            campaign_repo=camp_repo,
        )
        assert isinstance(result, UploadResultResponse)
