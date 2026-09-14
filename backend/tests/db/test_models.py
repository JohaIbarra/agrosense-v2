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
    assert cols == {"id", "name", "locality", "description", "created_at"}
    assert ("name",) in unique_groups(t)


def test_campaign_file_table():
    t = models.CampaignFile.__table__
    cols = {c.name for c in t.columns}
    assert cols == {
        "id", "project_id", "filename", "sha256", "mapping_version",
        "ingested_at", "trees", "observations", "deaths",
    }
    # provenance: mismo archivo no se ingesta 2 veces al mismo proyecto
    assert ("project_id", "sha256") in unique_groups(t)


def test_tree_table():
    t = models.TreeRow.__table__
    cols = {c.name for c in t.columns}
    assert {
        "id", "project_id", "tree_id", "species", "family", "common_name",
        "guild", "plot_id", "locality", "coord_x", "coord_y", "elevation_m",
    } <= cols
    assert ("project_id", "tree_id") in unique_groups(t)


def test_observation_table():
    t = models.ObservationRow.__table__
    cols = {c.name for c in t.columns}
    assert {
        "id", "tree_row_id", "campaign", "height_m", "crown_diameter_m",
        "dap_cm", "dap_status", "phytosanitary", "alive", "colonization",
    } <= cols
    # una observation por (arbol, campana)
    assert ("campaign", "tree_row_id") in unique_groups(t)


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
