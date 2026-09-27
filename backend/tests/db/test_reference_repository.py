"""ReferenceRepository: publicar una version nueva no borra la anterior (E5).

Antes de E5, `AnalyticsRepository.replace_all` borraba las tres tablas en
cada carga (docs/04-vision-producto.md §6.7: "una recarga borra la anterior
sin rastro"). Esto prueba que ya no es asi.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import (
    Base,
    ReferenceModel,
    ReferenceSpeciesEffect,
)
from agrosense.adapters.db.repository import ReferenceRepository


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


def _model(version: str) -> ReferenceModel:
    return ReferenceModel(
        version=version, source_dataset="data/raw/anexo1.xlsx",
        method="lme4::glmer binomial", n_observations=100,
    )


def test_publish_first_version_activates_it(session):
    repo = ReferenceRepository(session)
    m = repo.publish_version(
        _model("v1"),
        [ReferenceSpeciesEffect(species_name="Lafoensia speciosa", or_stall=4.94)],
        [], [],
    )
    assert m.is_active is True
    assert repo.active_model().version == "v1"
    assert len(repo.list_species()) == 1


def test_publish_second_version_deactivates_the_first_but_keeps_its_rows(session):
    repo = ReferenceRepository(session)
    v1 = repo.publish_version(
        _model("v1"),
        [ReferenceSpeciesEffect(species_name="Lafoensia speciosa", or_stall=4.94)],
        [], [],
    )
    v2 = repo.publish_version(
        _model("v2"),
        [ReferenceSpeciesEffect(species_name="Lafoensia speciosa", or_stall=5.10)],
        [], [],
    )

    session.refresh(v1)
    assert v1.is_active is False
    assert v2.is_active is True
    assert repo.active_model().version == "v2"

    # Solo la version activa se lee por defecto...
    activos = repo.list_species()
    assert len(activos) == 1
    assert activos[0].or_stall == pytest.approx(5.10)

    # ...pero la fila de v1 sigue en la base, no se borro.
    todas = session.query(ReferenceSpeciesEffect).all()
    assert len(todas) == 2


def test_get_species_reads_only_the_active_version(session):
    repo = ReferenceRepository(session)
    repo.publish_version(
        _model("v1"), [ReferenceSpeciesEffect(species_name="X", or_stall=1.0)], [], [],
    )
    repo.publish_version(
        _model("v2"), [ReferenceSpeciesEffect(species_name="X", or_stall=2.0)], [], [],
    )
    assert repo.get_species("X").or_stall == pytest.approx(2.0)


def test_no_active_model_yet_reads_are_empty_not_an_error(session):
    repo = ReferenceRepository(session)
    assert repo.active_model() is None
    assert repo.list_species() == []
    assert repo.list_plots() == []
    assert repo.list_variance() == []
    assert repo.get_species("X") is None


def test_publish_is_all_or_nothing(session):
    """Una version con una PK compuesta duplicada no queda a medias.

    Nota de diseno (ruling del controlador, reemplaza el test original del
    brief): meter un string en una columna Float no sirve como fallo real
    porque SQLite tiene "type affinity" y lo acepta sin quejarse. El fallo
    de integridad real y reproducible es una PK compuesta duplicada: dos
    `ReferenceSpeciesEffect` con el mismo `species_name` dentro de la MISMA
    version violan `(reference_model_id, species_name)` al hacer flush.
    """
    repo = ReferenceRepository(session)
    dup_a = ReferenceSpeciesEffect(species_name="X", or_stall=1.0)
    dup_b = ReferenceSpeciesEffect(species_name="X", or_stall=2.0)

    with pytest.raises(IntegrityError):
        repo.publish_version(_model("v1"), [dup_a, dup_b], [], [])

    assert repo.active_model() is None
    assert session.query(ReferenceModel).count() == 0


def test_failed_publish_leaves_the_previous_active_version_untouched(session):
    """Si v2 falla al publicarse, v1 sigue activa (todo o nada, ADR-004)."""
    repo = ReferenceRepository(session)
    repo.publish_version(
        _model("v1"),
        [ReferenceSpeciesEffect(species_name="Lafoensia speciosa", or_stall=4.94)],
        [], [],
    )

    dup_a = ReferenceSpeciesEffect(species_name="X", or_stall=1.0)
    dup_b = ReferenceSpeciesEffect(species_name="X", or_stall=2.0)
    with pytest.raises(IntegrityError):
        repo.publish_version(_model("v2"), [dup_a, dup_b], [], [])

    activo = repo.active_model()
    assert activo is not None
    assert activo.version == "v1"
    assert session.query(ReferenceModel).filter(ReferenceModel.is_active.is_(True)).count() == 1
