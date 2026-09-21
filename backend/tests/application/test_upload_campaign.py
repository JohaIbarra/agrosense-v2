"""Tests TDD para UC1 (create_project) y UC2 (upload_campaign).

Usan fake repos en memoria — cero dependencias de DB ni HTTP.

Además fijan la regla de ADR-003 por el lado del comportamiento: los use
cases devuelven DTOs de `application/` (no schemas de la API) y reciben el
parser de archivos como puerto inyectado (no saben que existe Excel).
El test de arquitectura verifica lo mismo por el lado de los imports.
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
    owner_id: str = "ing-1"


class FakeProjectRepository:
    """Implementación en memoria para tests unitarios."""

    def __init__(self) -> None:
        self._projects: dict[int, FakeProject] = {}
        self._next_id = 1

    def create(
        self,
        name: str,
        locality: str | None = None,
        description: str | None = None,
        *,
        owner_id: str = "ing-1",
        **_fields,
    ) -> FakeProject:
        for p in self._projects.values():
            if p.name == name and p.owner_id == owner_id:
                raise ValueError("DUPLICATE_NAME")
        p = FakeProject(
            id=self._next_id, name=name, locality=locality, description=description,
            owner_id=owner_id,
        )
        self._projects[self._next_id] = p
        self._next_id += 1
        return p

    def get(self, project_id: int) -> FakeProject | None:
        return self._projects.get(project_id)

    def get_owned(self, project_id: int, owner_id: str) -> FakeProject | None:
        p = self._projects.get(project_id)
        return p if p is not None and p.owner_id == owner_id else None

    def list_for_owner(self, owner_id: str) -> list[FakeProject]:
        return [p for p in self._projects.values() if p.owner_id == owner_id]

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


# ── Fake source: implementa el puerto CampaignSource sin tocar Excel ───────

class FakeCampaignSource:
    """Puerto CampaignSource servido desde memoria.

    Existe para probar que UC2 NO sabe de Excel: si el use case pasa estos
    tests, es porque depende del puerto y no de pandas.
    """

    def __init__(self, data=None, raises: Exception | None = None) -> None:
        self._data = data
        self._raises = raises
        self.calls: list[tuple[bytes, str]] = []

    def read(self, content: bytes, filename: str):
        self.calls.append((content, filename))
        if self._raises is not None:
            raise self._raises
        return self._data


def canned_campaign():
    """CampaignData minimo: 2 arboles, 2 observaciones, 1 muerto."""
    from agrosense.application.dtos import CampaignData
    from agrosense.domain.entities import Observation, StatusSemantic, Tree

    def obs(tree_id: str, alive: bool) -> Observation:
        return Observation(
            tree_id=tree_id,
            campaign=1,
            height_m=1.0,
            crown_diameter_m=None,
            dap_cm=None,
            dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
            phytosanitary=None,
            alive=alive,
            colonization=None,
        )

    return CampaignData(
        trees=[Tree(tree_id="T1", species="Sp"), Tree(tree_id="T2", species="Sp")],
        observations=[obs("T1", True), obs("T2", False)],
        warnings=[],
        mapping_version="fake-1",
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def make_repos() -> tuple[FakeProjectRepository, FakeCampaignRepository]:
    proj_repo = FakeProjectRepository()
    camp_repo = FakeCampaignRepository(proj_repo)
    return proj_repo, camp_repo


def excel_source():
    """El adapter real — sigue siendo quien parsea el dataset de referencia."""
    from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

    return ExcelCampaignSource()


DATASET = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"


# ── UC1: create_project ────────────────────────────────────────────────────

class TestCreateProject:
    def test_create_returns_response_with_id(self):
        from agrosense.application.use_cases.create_project import create_project

        proj_repo, _ = make_repos()
        result = create_project(
            repo=proj_repo,
            owner_id="ing-1",
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
            repo=proj_repo, owner_id="ing-1", name="Sin localidad", locality=None, description=None
        )
        assert result.locality is None

    def test_duplicate_name_raises(self):
        from agrosense.application.use_cases.create_project import create_project

        proj_repo, _ = make_repos()
        create_project(repo=proj_repo, owner_id="ing-1", name="Duplicado")
        with pytest.raises(ValueError, match="DUPLICATE_NAME"):
            create_project(repo=proj_repo, owner_id="ing-1", name="Duplicado")

    def test_result_is_application_dto_not_api_schema(self):
        """ADR-003: el use case devuelve un DTO de application/, no un schema de la API.

        Si esto vuelve a ser un ProjectResponse, application/ depende de
        adapters/api y la flecha de dependencia se invierte otra vez.
        """
        from agrosense.application.dtos import ProjectSummary
        from agrosense.application.use_cases.create_project import create_project

        proj_repo, _ = make_repos()
        result = create_project(repo=proj_repo, owner_id="ing-1", name="Schema test")
        assert isinstance(result, ProjectSummary)


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
            owner_id="ing-1",
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=DATASET.read_bytes(),
            project_repo=proj_repo,
            campaign_repo=camp_repo,
            source=excel_source(),
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
            owner_id="ing-1",
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=DATASET.read_bytes(),
            project_repo=proj_repo,
            campaign_repo=camp_repo,
            source=excel_source(),
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
            owner_id="ing-1",
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=DATASET.read_bytes(),
            project_repo=proj_repo,
            campaign_repo=camp_repo,
            source=excel_source(),
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
            owner_id="ing-1",
                project_id=999,
                filename="dummy.xlsx",
                content=b"",
                project_repo=proj_repo,
                campaign_repo=camp_repo,
                source=excel_source(),
            )

    def test_upload_invalid_bytes_raises_value_error(self):
        """Bytes que no son un Excel válido → ValueError claro (no stack trace)."""
        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Test Invalid", None, None)
        with pytest.raises(ValueError, match="INVALID_FILE"):
            upload_campaign(
            owner_id="ing-1",
                project_id=proj.id,
                filename="notexcel.txt",
                content=b"esto no es un xlsx",
                project_repo=proj_repo,
                campaign_repo=camp_repo,
                source=excel_source(),
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
            owner_id="ing-1",
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=content,
            project_repo=proj_repo,
            campaign_repo=camp_repo,
            source=excel_source(),
        )
        with pytest.raises(ValueError, match="DUPLICATE_FILE"):
            upload_campaign(
            owner_id="ing-1",
                project_id=proj.id,
                filename="anexo1.xlsx",
                content=content,
                project_repo=proj_repo,
                campaign_repo=camp_repo,
                source=excel_source(),
            )

    def test_result_is_application_dto_not_api_schema(self):
        """ADR-003: UC2 devuelve UploadResult (application/), no el schema de la API."""
        if not DATASET.exists():
            pytest.skip("dataset de referencia local ausente")

        from agrosense.application.dtos import UploadResult
        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Schema Result Test", None, None)

        result = upload_campaign(
            owner_id="ing-1",
            project_id=proj.id,
            filename="anexo1.xlsx",
            content=DATASET.read_bytes(),
            project_repo=proj_repo,
            campaign_repo=camp_repo,
            source=excel_source(),
        )
        assert isinstance(result, UploadResult)


# ── UC2: el puerto CampaignSource (ADR-003) ────────────────────────────────

class TestCampaignSourcePort:
    """UC2 no sabe que existe Excel: recibe un puerto y lo usa.

    Estos tests NO tocan pandas ni el dataset: si pasan, el parsing quedo
    del lado del adapter y el use case es independiente del formato.
    """

    def test_upload_works_with_a_source_that_is_not_excel(self):
        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Fuente no-Excel", None, None)

        result = upload_campaign(
            owner_id="ing-1",
            project_id=proj.id,
            filename="campaña.csv",
            content=b"cualquier cosa; el puerto decide como leerla",
            project_repo=proj_repo,
            campaign_repo=camp_repo,
            source=FakeCampaignSource(canned_campaign()),
        )
        assert result.valid is True
        assert result.trees == 2
        assert result.observations == 2
        assert result.deaths == 1

    def test_source_receives_raw_bytes_and_filename(self):
        """El use case delega el parsing integro: no pre-procesa el archivo."""
        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Delegacion", None, None)
        source = FakeCampaignSource(canned_campaign())
        content = b"bytes crudos"

        upload_campaign(
            owner_id="ing-1",
            project_id=proj.id,
            filename="m5.csv",
            content=content,
            project_repo=proj_repo,
            campaign_repo=camp_repo,
            source=source,
        )
        assert source.calls == [(content, "m5.csv")]

    def test_source_failure_propagates_as_value_error(self):
        """Un archivo ilegible lo detecta el adapter; el use case no lo envuelve."""
        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Fuente rota", None, None)

        with pytest.raises(ValueError, match="INVALID_FILE"):
            upload_campaign(
            owner_id="ing-1",
                project_id=proj.id,
                filename="roto.xlsx",
                content=b"no es un xlsx",
                project_repo=proj_repo,
                campaign_repo=camp_repo,
                source=FakeCampaignSource(raises=ValueError("INVALID_FILE: ilegible")),
            )

    def test_project_is_checked_before_parsing(self):
        """Proyecto inexistente: ni se intenta leer el archivo."""
        from agrosense.application.use_cases.upload_campaign import upload_campaign

        proj_repo, camp_repo = make_repos()
        source = FakeCampaignSource(canned_campaign())

        with pytest.raises(ValueError, match="PROJECT_NOT_FOUND"):
            upload_campaign(
            owner_id="ing-1",
                project_id=404,
                filename="x.xlsx",
                content=b"x",
                project_repo=proj_repo,
                campaign_repo=camp_repo,
                source=source,
            )
        assert source.calls == []

    def test_warnings_are_application_dtos(self):
        """Los warnings de dominio se mapean a WarningDTO de application/."""
        from agrosense.application.dtos import CampaignData, WarningDTO
        from agrosense.application.use_cases.upload_campaign import upload_campaign
        from agrosense.domain.errors import (
            CensusGapWarning,
            LargeContractionNoted,
            SuspiciousRevivalWarning,
        )

        data = canned_campaign()
        with_warnings = CampaignData(
            trees=data.trees,
            observations=data.observations,
            warnings=[
                LargeContractionNoted("T1", 2, 0.04),
                SuspiciousRevivalWarning("T2", 3),
                CensusGapWarning("T1", [1, 4]),
            ],
            mapping_version=data.mapping_version,
        )

        proj_repo, camp_repo = make_repos()
        proj = proj_repo.create("Warnings DTO", None, None)
        result = upload_campaign(
            owner_id="ing-1",
            project_id=proj.id,
            filename="x.xlsx",
            content=b"x",
            project_repo=proj_repo,
            campaign_repo=camp_repo,
            source=FakeCampaignSource(with_warnings),
        )
        assert [w.type for w in result.warnings] == ["contraction", "revival", "census_gap"]
        assert all(isinstance(w, WarningDTO) for w in result.warnings)
        assert result.warnings[0].tree_id == "T1"
