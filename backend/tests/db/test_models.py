"""Tests de schema: las tablas mapean el modelo de dominio (ADR-002/003).

Verifica columnas, constraints UNIQUE y FKs ANTES de la migracion: la
migracion debe derivarse de estos models (schema derivado del dominio).
"""
from agrosense.adapters.db import models


def unique_groups(table) -> list[tuple[str, ...]]:
    """Columnas de cada UniqueConstraint de la tabla."""
    from sqlalchemy import UniqueConstraint

    groups = []
    for con in table.constraints:
        if isinstance(con, UniqueConstraint):
            groups.append(tuple(sorted(c.name for c in con.columns)))
    return groups


def test_project_table():
    t = models.Project.__table__
    cols = {c.name for c in t.columns}
    assert {"id", "name", "locality", "description", "created_at"} <= cols
    # E1: propietario, codigo interno y los campos de D7
    assert {
        "owner_id", "project_code", "contract_code", "objective", "executing_org",
        "contracting_entity", "department", "municipality", "intervention_type",
        "area_ha", "planted_individuals", "planting_density", "establishment_date",
        "start_date", "end_date", "legal_framework", "environmental_authority",
        "status", "coordinate_srid",
    } <= cols
    # el nombre es unico POR INGENIERO, no global
    assert ("name", "owner_id") in unique_groups(t)
    assert ("name",) not in unique_groups(t)


def test_engineer_table():
    t = models.Engineer.__table__
    assert {"id", "email", "full_name", "professional_license", "organization"} <= {
        c.name for c in t.columns
    }


def test_campaign_file_table():
    t = models.CampaignFile.__table__
    cols = {c.name for c in t.columns}
    assert cols == {
        "id", "project_id", "filename", "sha256", "mapping_version",
        "ingested_at", "trees", "observations", "deaths",
        # E0: lo que el archivo dice de si mismo
        "source_project_label", "source_event", "source_field_crew", "source_recorder",
    }
    # provenance: mismo archivo no se ingesta 2 veces al mismo proyecto
    assert ("project_id", "sha256") in unique_groups(t)


def test_tree_table():
    t = models.TreeRow.__table__
    cols = {c.name for c in t.columns}
    assert {
        "id", "project_id", "tree_id", "species", "family", "common_name",
        "guild", "plot_row_id", "coord_x", "coord_y", "elevation_m",
    } <= cols
    # E0: la parcela y el predio viven en `plots` / `properties`
    assert "plot_id" not in cols and "locality" not in cols
    assert ("project_id", "tree_id") in unique_groups(t)


def test_observation_table():
    t = models.ObservationRow.__table__
    cols = {c.name for c in t.columns}
    assert {
        "id", "tree_row_id", "monitoring_id", "height_m", "crown_diameter_m",
        "dap_cm", "dap_status", "phytosanitary", "alive", "colonization",
        "field_notes",
    } <= cols
    assert "campaign" not in cols, "E0: el numero de monitoreo vive en `monitorings`"
    # una observacion por (arbol, monitoreo)
    assert ("monitoring_id", "tree_row_id") in unique_groups(t)


def test_fk_cascades():
    """Borrar proyecto borra su arbolada en cascada (sin huerfanos)."""
    obs_fk = models.ObservationRow.__table__.c.tree_row_id
    assert obs_fk.foreign_keys and "CASCADE" in str(list(obs_fk.foreign_keys)[0].ondelete)
    tree_fk = models.TreeRow.__table__.c.project_id
    assert tree_fk.foreign_keys and "CASCADE" in str(list(tree_fk.foreign_keys)[0].ondelete)


def test_observation_dap_status_is_enum_string():
    """dap_status persiste el valor del enum de dominio como string."""
    from agrosense.domain.entities import StatusSemantic

    assert {s.value for s in StatusSemantic} == {"sin_censo", "bajo_umbral_dap", "medido"}


# ── E0: territorio y monitoreos ─────────────────────────────────────────────

def test_property_table():
    t = models.PropertyRow.__table__
    assert {"id", "project_id", "name", "vereda"} <= {c.name for c in t.columns}
    assert ("name", "project_id") in unique_groups(t)


def test_plot_table():
    t = models.PlotRow.__table__
    assert {
        "id", "project_id", "property_id", "code", "sampling_unit_code", "plot_label",
        "monitoring_unit", "floristic_design", "associated_cover", "establishment_cover",
    } <= {c.name for c in t.columns}
    # la unicidad de la parcela es por PROYECTO, no por predio
    assert ("code", "project_id") in unique_groups(t)


def test_monitoring_table():
    t = models.MonitoringRow.__table__
    assert {
        "id", "project_id", "number", "monitoring_date", "field_crew", "recorder", "notes",
    } <= {c.name for c in t.columns}
    assert ("number", "project_id") in unique_groups(t)


def test_campaign_file_to_monitoring_is_many_to_many():
    """Un archivo acumulado trae varios monitoreos (decision D1)."""
    t = models.campaign_file_monitorings
    assert {c.name for c in t.columns} == {"campaign_file_id", "monitoring_id"}
    assert {c.name for c in t.primary_key.columns} == {"campaign_file_id", "monitoring_id"}


def test_new_tables_cascade_from_the_project():
    for model in (models.PropertyRow, models.PlotRow, models.MonitoringRow):
        fk = model.__table__.c.project_id
        assert "CASCADE" in str(list(fk.foreign_keys)[0].ondelete), model.__name__
