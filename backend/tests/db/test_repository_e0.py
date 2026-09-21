"""E0 / T6: el repositorio normaliza predios, parcelas y monitoreos.

Contra SQLite local (fixture `session`), como el resto de tests de repositorio.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from agrosense.adapters.db.models import (
    CampaignFile,
    MonitoringRow,
    ObservationRow,
    PlotRow,
    PropertyRow,
    TreeRow,
)
from agrosense.adapters.db.repository import CampaignRepository, ProjectRepository
from agrosense.application.dtos import CampaignData, FileMetadata
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.errors import ProjectLabelMismatchWarning


def _tree(tree_id: str, unit: str, plot: str, predio: str, **extra) -> Tree:
    return Tree(
        tree_id=tree_id,
        species="Senna viarum",
        plot_id=plot,
        locality=predio,
        sampling_unit_code=unit,
        monitoring_unit="Parcela",
        floristic_design=extra.get("design", "Rehabilitación vegetal"),
        associated_cover="Bosque de galería",
        establishment_cover="Vegetación secundaria",
    )


def _obs(tree_id: str, campaign: int, height: float = 0.3, notes: str | None = None):
    return Observation(
        tree_id=tree_id,
        campaign=campaign,
        height_m=height,
        crown_diameter_m=0.2,
        dap_cm=None,
        dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary="Bueno",
        alive=True,
        colonization=None,
        field_notes=notes,
    )


def _campaign(
    monitorings=(1, 2), project_label: str | None = "UPME 04-2014", design=None
) -> CampaignData:
    trees = [
        _tree("T1", "GEB/FR/11", "11", "Guayabal", **({"design": design} if design else {})),
        _tree("T2", "GEB/FR/11", "11", "Guayabal"),
        _tree("T3", "GEB/FR/12", "12", "Tres Jotas"),
    ]
    obs = [_obs(t.tree_id, m) for t in trees for m in monitorings]
    return CampaignData(
        trees=trees,
        observations=obs,
        mapping_version="test-e0",
        file_metadata=FileMetadata(
            project_label=project_label,
            event="Segundo monitoreo",
            field_crew="Cuadrilla A",
            recorder="R. Ibarra",
        ),
    )


@pytest.fixture()
def project(session):
    return ProjectRepository(session).create(name="E0", locality=None, description=None)


def _count(session, model) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_ingest_creates_properties_plots_and_monitorings(session, project):
    stats = CampaignRepository(session).save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)

    assert stats["monitorings"] == [1, 2]
    assert sorted(p.name for p in session.scalars(select(PropertyRow))) == [
        "Guayabal", "Tres Jotas",
    ]
    plots = {p.code: p for p in session.scalars(select(PlotRow))}
    assert set(plots) == {"GEB/FR/11", "GEB/FR/12"}
    assert plots["GEB/FR/11"].floristic_design == "Rehabilitación vegetal"
    assert plots["GEB/FR/11"].associated_cover == "Bosque de galería"
    assert plots["GEB/FR/11"].property.name == "Guayabal"
    assert sorted(m.number for m in session.scalars(select(MonitoringRow))) == [1, 2]


def test_trees_still_expose_plot_and_property(session, project):
    """El contrato de lectura no cambia: `plot_id` y `locality` siguen ahi."""
    CampaignRepository(session).save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)
    t1 = session.scalar(select(TreeRow).where(TreeRow.tree_id == "T1"))
    assert t1.plot_id == "11"
    assert t1.locality == "Guayabal"
    assert t1.sampling_unit_code == "GEB/FR/11"
    assert t1.floristic_design == "Rehabilitación vegetal"


def test_observations_still_expose_the_monitoring_number(session, project):
    CampaignRepository(session).save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)
    numeros = sorted(o.campaign for o in session.scalars(select(ObservationRow)))
    assert numeros == [1, 1, 1, 2, 2, 2]


def test_reupload_does_not_duplicate_territory_or_monitorings(session, project):
    """Idempotencia: otro archivo con los mismos datos no duplica nada."""
    repo = CampaignRepository(session)
    repo.save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)
    repo.save_ingest(project.id, _campaign(), "a-v2.xlsx", "b" * 64)

    assert _count(session, PropertyRow) == 2
    assert _count(session, PlotRow) == 2
    assert _count(session, MonitoringRow) == 2
    assert _count(session, ObservationRow) == 6


def test_new_file_adds_only_the_new_monitoring(session, project):
    repo = CampaignRepository(session)
    repo.save_ingest(project.id, _campaign(monitorings=(1, 2)), "m2.xlsx", "a" * 64)
    stats = repo.save_ingest(project.id, _campaign(monitorings=(3,)), "m3.xlsx", "b" * 64)

    assert stats["monitorings"] == [3]
    assert sorted(m.number for m in session.scalars(select(MonitoringRow))) == [1, 2, 3]
    assert _count(session, ObservationRow) == 9


def test_plot_attributes_follow_the_latest_file(session, project):
    repo = CampaignRepository(session)
    repo.save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)
    repo.save_ingest(project.id, _campaign(design="Enriquecimiento"), "b.xlsx", "b" * 64)
    plot = session.scalar(select(PlotRow).where(PlotRow.code == "GEB/FR/11"))
    assert plot.floristic_design == "Enriquecimiento"


def test_field_crew_goes_to_the_latest_monitoring_only(session, project):
    """`Responsables` es de todo el archivo; lo midio la cuadrilla del ultimo."""
    CampaignRepository(session).save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)
    mons = {m.number: m for m in session.scalars(select(MonitoringRow))}
    assert mons[2].field_crew == "Cuadrilla A" and mons[2].recorder == "R. Ibarra"
    assert mons[1].field_crew is None


def test_campaign_file_records_its_metadata_and_monitorings(session, project):
    CampaignRepository(session).save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)
    cf = session.scalar(select(CampaignFile))
    assert cf.source_project_label == "UPME 04-2014"
    assert cf.source_event == "Segundo monitoreo"
    assert sorted(m.number for m in cf.monitorings) == [1, 2]


def test_field_notes_are_persisted(session, project):
    data = _campaign(monitorings=(1,))
    data.observations[0] = _obs("T1", 1, notes="Defoliación parcial")
    CampaignRepository(session).save_ingest(project.id, data, "a.xlsx", "a" * 64)
    notas = [o.field_notes for o in session.scalars(select(ObservationRow)) if o.field_notes]
    assert notas == ["Defoliación parcial"]


def test_file_from_another_project_warns(session, project):
    repo = CampaignRepository(session)
    first = repo.save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)
    assert first["extra_warnings"] == []

    second = repo.save_ingest(
        project.id, _campaign(project_label="OTRO CONTRATO"), "b.xlsx", "b" * 64
    )
    avisos = second["extra_warnings"]
    assert len(avisos) == 1 and isinstance(avisos[0], ProjectLabelMismatchWarning)
    # es aviso, no error: la carga entra igual
    assert _count(session, CampaignFile) == 2


def test_file_without_project_label_does_not_warn(session, project):
    repo = CampaignRepository(session)
    repo.save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)
    stats = repo.save_ingest(project.id, _campaign(project_label=None), "b.xlsx", "b" * 64)
    assert stats["extra_warnings"] == []


def test_same_plot_code_in_two_projects_are_different_plots(session):
    """La unicidad de la parcela es por proyecto."""
    prepo = ProjectRepository(session)
    p1 = prepo.create(name="P1", locality=None, description=None)
    p2 = prepo.create(name="P2", locality=None, description=None)
    repo = CampaignRepository(session)
    repo.save_ingest(p1.id, _campaign(), "a.xlsx", "a" * 64)
    repo.save_ingest(p2.id, _campaign(), "a.xlsx", "a" * 64)
    assert _count(session, PlotRow) == 4
    assert _count(session, MonitoringRow) == 4


def test_deleting_the_project_cascades_to_the_new_tables(session, project):
    CampaignRepository(session).save_ingest(project.id, _campaign(), "a.xlsx", "a" * 64)
    session.delete(project)
    session.commit()
    for model in (PropertyRow, PlotRow, MonitoringRow, ObservationRow, TreeRow):
        assert _count(session, model) == 0, model.__name__


def test_get_monitorings_lists_them_with_their_observation_counts(session, project):
    repo = CampaignRepository(session)
    repo.save_ingest(project.id, _campaign(monitorings=(1, 2)), "a.xlsx", "a" * 64)
    filas = ProjectRepository(session).get_monitorings(project.id)
    assert [(m.number, n) for m, n in filas] == [(1, 3), (2, 3)]
