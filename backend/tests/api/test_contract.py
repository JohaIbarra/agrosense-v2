"""Tests del contrato del slice 2: shapes de request/response.

El contrato es la fuente de verdad (AGENTS.md): estos tests documentan
forma, validaciones y tipos de error ANTES de que exista implementacion.
"""
import pytest

from agrosense.adapters.api.schemas import (
    ErrorItem,
    ProjectCreate,
    ProjectResponse,
    UploadResultResponse,
    WarningItem,
)


def test_project_create_valid():
    p = ProjectCreate(name="Restauración Guayabal", locality="Guayabal",
                      description="Piloto de restauración")
    assert p.name == "Restauración Guayabal"
    assert p.locality == "Guayabal"


def test_project_create_locality_optional():
    p = ProjectCreate(name="Proyecto sin localidad")
    assert p.locality is None
    assert p.description is None


def test_project_create_name_required():
    with pytest.raises(Exception):
        ProjectCreate(name="")


def test_project_create_name_max_200():
    with pytest.raises(Exception):
        ProjectCreate(name="x" * 201)


def test_project_response_shape():
    r = ProjectResponse(
        id=1, name="Restauración Guayabal", locality="Guayabal",
        description=None, created_at="2026-09-14T12:00:00Z", campaigns_count=0,
    )
    assert r.id == 1
    assert r.campaigns_count == 0


def test_warning_item_shape():
    w = WarningItem(type="contraction", tree_id="T1", message="encoge 0.04 m")
    assert w.type == "contraction"


def test_warning_types_are_documented():
    """El contrato documenta los 3 tipos de warning del dominio (slice 1)."""
    for t in ("contraction", "revival", "census_gap"):
        WarningItem(type=t, tree_id="T1", message="ok")


def test_error_item_shape():
    e = ErrorItem(code="DEATH_VIOLATION", message="árbol crece tras morir",
                  tree_id="T1", campaign=3)
    assert e.code == "DEATH_VIOLATION"
    assert e.tree_id == "T1"
    assert e.campaign == 3


def test_error_item_tree_optional():
    e = ErrorItem(code="SPECIES_MISMATCH", message="...")
    assert e.tree_id is None
    assert e.campaign is None


def test_upload_result_response_shape():
    r = UploadResultResponse(
        valid=True, campaign_id=1, trees=856, observations=3146, deaths=340,
        warnings=[WarningItem(type="revival", tree_id="T1", message="replanteo")],
        errors=[],
    )
    assert r.valid is True
    assert r.trees == 856
    assert len(r.warnings) == 1
    assert r.errors == []


def test_upload_result_invalid_shape():
    """Respuesta de rechazo (422): valid=False + errores accionables."""
    r = UploadResultResponse(
        valid=False, campaign_id=None, trees=0, observations=0, deaths=0,
        warnings=[],
        errors=[ErrorItem(code="DEATH_VIOLATION", message="...", tree_id="T9", campaign=4)],
    )
    assert r.valid is False
    assert r.errors[0].code == "DEATH_VIOLATION"
