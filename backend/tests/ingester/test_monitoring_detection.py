"""E0 / T4: deteccion de monitoreos y datos de archivo (decision D1).

AgroSense recibe tanto un Excel de UN monitoreo como uno ACUMULADO con varios.
El monitoreo se detecta por las columnas `_M{k}` que traen datos, sin techo.
"""
import pandas as pd

from agrosense.adapters.ingester.ingest import ingest_wide
from agrosense.domain.errors import EventMismatchWarning

BASE = {
    "ID_MUEST": "T1",
    "ID Parcela": 11,
    "LOCALIDAD": "Guayabal",
    "Especie_M1": "Senna viarum",
    "Codigo de unidad muestreo": "GEB/MED-LV/NV/FR/11",
    "Unidad de monitoreo": "Parcela",
    "Diseño floristico": "Rehabilitación vegetal",
    "Cobertura vegetal asociada": "Bosque de galería",
    "Cobertura  donde se establecio el material vegetal": "Vegetación secundaria",
}


def df_of(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame([{**BASE, **r} for r in rows])


def test_accumulated_file_brings_every_monitoring():
    data = ingest_wide(df_of({
        "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
        "Altura total (m)_M2": 0.3, "Sobrevivencia M2": "Vivo",
        "Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo",
        "Altura total (m)_M4": 0.5, "Sobrevivencia M4": "Vivo",
    }))
    assert data.monitorings == [1, 2, 3, 4]


def test_single_monitoring_file():
    """Un Excel con solo las columnas de M3 trae solo el monitoreo 3."""
    data = ingest_wide(df_of({"Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo"}))
    assert data.monitorings == [3]
    assert [o.campaign for o in data.observations] == [3]


def test_columns_present_but_blank_do_not_count_as_a_monitoring():
    """Tener la columna no basta: el monitoreo tiene que traer datos."""
    data = ingest_wide(df_of({
        "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
        "Altura total (m)_M2": None, "Sobrevivencia M2": None,
    }))
    assert data.monitorings == [1]


def test_fifth_monitoring_is_accepted():
    """Hasta E0 el quinto monitoreo se rechazaba por un techo de 4."""
    data = ingest_wide(df_of({
        "Altura total (m)_M4": 0.5, "Sobrevivencia M4": "Vivo",
        "Altura total (m)_M5": 0.6, "Sobrevivencia M5": "Vivo",
    }))
    assert data.monitorings == [4, 5]


def test_tree_carries_its_plot_attributes():
    tree = ingest_wide(df_of({"Altura total (m)_M1": 0.2})).trees[0]
    assert tree.sampling_unit_code == "GEB/MED-LV/NV/FR/11"
    assert tree.monitoring_unit == "Parcela"
    assert tree.floristic_design == "Rehabilitación vegetal"
    assert tree.associated_cover == "Bosque de galería"
    assert tree.establishment_cover == "Vegetación secundaria"


def test_field_notes_go_to_the_latest_observation():
    """`Observa` es la nota de la ultima visita, no de todas."""
    data = ingest_wide(df_of({
        "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
        "Altura total (m)_M2": 0.3, "Sobrevivencia M2": "Vivo",
        "Observa": "Defoliación parcial",
    }))
    notes = {o.campaign: o.field_notes for o in data.observations}
    assert notes == {1: None, 2: "Defoliación parcial"}


def test_file_metadata_is_read_once():
    data = ingest_wide(df_of(
        {"ID_MUEST": "T1", "Altura total (m)_M4": 0.5, "Proyecto": "UPME 04-2014",
         "Evento": "Cuarto monitoreo", "Responsables": "Cuadrilla A", "Anotador": "R. Ibarra"},
        {"ID_MUEST": "T2", "Altura total (m)_M4": 0.6, "Proyecto": "UPME 04-2014",
         "Evento": "Cuarto monitoreo", "Responsables": "Cuadrilla A", "Anotador": "R. Ibarra"},
    ))
    meta = data.file_metadata
    assert meta.project_label == "UPME 04-2014"
    assert meta.event == "Cuarto monitoreo"
    assert meta.field_crew == "Cuadrilla A"
    assert meta.recorder == "R. Ibarra"


def test_conflicting_file_metadata_keeps_every_value():
    """Un archivo con dos cuadrillas no pierde ninguna."""
    data = ingest_wide(df_of(
        {"ID_MUEST": "T1", "Altura total (m)_M1": 0.2, "Responsables": "Cuadrilla A"},
        {"ID_MUEST": "T2", "Altura total (m)_M1": 0.3, "Responsables": "Cuadrilla B"},
    ))
    assert data.file_metadata.field_crew == "Cuadrilla A; Cuadrilla B"


def test_matching_event_does_not_warn():
    data = ingest_wide(df_of({
        "Altura total (m)_M4": 0.5, "Sobrevivencia M4": "Vivo", "Evento": "Cuarto monitoreo",
    }))
    assert not [w for w in data.warnings if isinstance(w, EventMismatchWarning)]


def test_event_that_contradicts_the_data_warns_but_ingests():
    """`Evento` dice M4 pero los datos llegan hasta M3: aviso, no error."""
    data = ingest_wide(df_of({
        "Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo", "Evento": "Cuarto monitoreo",
    }))
    avisos = [w for w in data.warnings if isinstance(w, EventMismatchWarning)]
    assert len(avisos) == 1
    assert avisos[0].declared == 4 and avisos[0].detected_latest == 3
    assert data.observations, "el aviso no debe impedir la ingesta"


def test_unreadable_event_is_ignored():
    data = ingest_wide(df_of({"Altura total (m)_M2": 0.3, "Evento": "Línea base"}))
    assert not [w for w in data.warnings if isinstance(w, EventMismatchWarning)]
