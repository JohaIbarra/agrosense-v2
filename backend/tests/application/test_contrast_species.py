"""UC-AN3: contrastar las especies plantadas de un proyecto con el referente.

Signature (I-2): la propiedad del proyecto se valida DENTRO del caso de uso
(patron `_owned_project` de `project_index.py`), no en la route. Orden (I-2):
propiedad primero, REFERENCE_NOT_LOADED despues (I-1).
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from agrosense.application.errors import AppError
from agrosense.application.use_cases.contrast_species import contrast_project_species

OWNER = "engineer-a"


@dataclass
class _FakeEffect:
    species_name: str
    effect_stall: float | None = None
    se_stall: float | None = None
    or_stall: float | None = None
    or_stall_lo: float | None = None
    or_stall_hi: float | None = None
    sig_stall: bool | None = None
    effect_mort: float | None = None
    se_mort: float | None = None
    or_mort: float | None = None
    or_mort_lo: float | None = None
    or_mort_hi: float | None = None
    sig_mort: bool | None = None
    gremio: str | None = None


class _FakeProject:
    """Objeto opaco: al caso de uso solo le importa si `get_owned` devuelve
    algo o None, nunca sus atributos."""


class _FakeProjectRepo:
    """Repositorio de PROPIEDAD (`ProjectRepository.get_owned`)."""

    def __init__(self, *, owned: bool = True):
        self._owned = owned

    def get_owned(self, project_id: int, owner_id: str) -> _FakeProject | None:
        return _FakeProject() if self._owned else None


class _FakeSpeciesRepo:
    """Repositorio de especies DEL PROYECTO (`ProjectSpeciesRepository.list_species`)."""

    def __init__(self, species: list[tuple[str, int]]):
        self._species = species

    def list_species(self, project_id: int) -> list[tuple[str, int]]:
        return self._species


class _FakeReferenceRepo:
    """Repositorio del referente: version activa + efectos de esa version."""

    def __init__(self, rows: dict[str, _FakeEffect] | None = None, *, active: bool = True):
        self._rows = rows or {}
        self._active = active

    def active_model(self):
        return object() if self._active else None

    def list_species(self) -> list[_FakeEffect]:
        return list(self._rows.values())


def test_species_with_significant_reference_effect_gets_a_narrative():
    project_repo = _FakeProjectRepo()
    species_repo = _FakeSpeciesRepo([("Lafoensia speciosa", 12)])
    reference_repo = _FakeReferenceRepo({
        "Lafoensia speciosa": _FakeEffect(
            species_name="Lafoensia speciosa",
            effect_stall=1.598, se_stall=0.3, or_stall=4.94,
            or_stall_lo=2.71, or_stall_hi=9.02, sig_stall=True,
            effect_mort=0.0, se_mort=0.5, or_mort=1.0,
            or_mort_lo=0.4, or_mort_hi=2.5, sig_mort=False,
            gremio="Tardia",
        ),
    })

    out = contrast_project_species(1, OWNER, project_repo, species_repo, reference_repo)

    assert len(out) == 1
    dto = out[0]
    assert dto.species == "Lafoensia speciosa"
    assert dto.n_trees_in_project == 12
    assert dto.has_reference is True
    assert dto.gremio == "Tardia"
    assert dto.stall_risk.significant is True
    assert dto.stall_risk.odds_ratio == 4.94
    assert "12" in dto.narrative
    assert "Lafoensia speciosa" in dto.narrative


def test_species_absent_from_the_reference_is_marked_not_an_error():
    project_repo = _FakeProjectRepo()
    species_repo = _FakeSpeciesRepo([("Especie inventada", 3)])
    reference_repo = _FakeReferenceRepo({})

    out = contrast_project_species(1, OWNER, project_repo, species_repo, reference_repo)

    assert len(out) == 1
    dto = out[0]
    assert dto.has_reference is False
    assert dto.stall_risk is None
    assert dto.mortality_risk is None
    assert "Sin referencia" in dto.narrative


def test_project_without_trees_returns_an_empty_list():
    out = contrast_project_species(
        1, OWNER, _FakeProjectRepo(), _FakeSpeciesRepo([]), _FakeReferenceRepo({})
    )
    assert out == []


def test_mixes_species_with_and_without_reference():
    project_repo = _FakeProjectRepo()
    species_repo = _FakeSpeciesRepo([
        ("Especie inventada", 1),
        ("Lafoensia speciosa", 5),
    ])
    reference_repo = _FakeReferenceRepo({
        "Lafoensia speciosa": _FakeEffect(species_name="Lafoensia speciosa", or_stall=4.94),
    })

    out = contrast_project_species(1, OWNER, project_repo, species_repo, reference_repo)

    assert [d.has_reference for d in out] == [False, True]


# ── I-2: la propiedad se valida en el caso de uso ──────────────────────────

def test_foreign_project_raises_project_not_found():
    project_repo = _FakeProjectRepo(owned=False)
    species_repo = _FakeSpeciesRepo([("Lafoensia speciosa", 1)])
    reference_repo = _FakeReferenceRepo(
        {"Lafoensia speciosa": _FakeEffect(species_name="Lafoensia speciosa")}
    )

    with pytest.raises(AppError) as exc_info:
        contrast_project_species(1, OWNER, project_repo, species_repo, reference_repo)

    assert exc_info.value.code == "PROJECT_NOT_FOUND"


# ── I-1: sin version activa, el contraste dice que no hay referente ───────

def test_no_active_reference_version_raises_reference_not_loaded():
    project_repo = _FakeProjectRepo()
    species_repo = _FakeSpeciesRepo([("Lafoensia speciosa", 1)])
    reference_repo = _FakeReferenceRepo(active=False)

    with pytest.raises(AppError) as exc_info:
        contrast_project_species(1, OWNER, project_repo, species_repo, reference_repo)

    assert exc_info.value.code == "REFERENCE_NOT_LOADED"


def test_ownership_is_checked_before_reference_not_loaded():
    """Orden explicito del brief: propiedad primero, referente despues."""
    project_repo = _FakeProjectRepo(owned=False)
    species_repo = _FakeSpeciesRepo([])
    reference_repo = _FakeReferenceRepo(active=False)

    with pytest.raises(AppError) as exc_info:
        contrast_project_species(1, OWNER, project_repo, species_repo, reference_repo)

    assert exc_info.value.code == "PROJECT_NOT_FOUND"
