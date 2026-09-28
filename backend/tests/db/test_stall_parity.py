"""Paridad Excel -> DB -> load_dataset para el modelo de estancamiento (E7).

Fix wave (item 2). El entrenamiento (`scripts/train_stall_model.py`) featuriza
entidades que salen DIRECTO de `ExcelCampaignSource`. El servicio (la API)
featuriza entidades que salen de `ProjectAnalysisRepository.load_dataset`,
tras pasar por la normalizacion de predios/parcelas de la base (E0). Si esas
dos rutas no coinciden, el modelo servido ve datos distintos de los que
evaluo el ML eval gate — silenciosamente.

Este test ingesta el MISMO archivo por las dos rutas y compara las features y
la huella de `ml/stall_features.build_wave`/`fingerprint`.
"""
from __future__ import annotations

import hashlib
import io

from openpyxl import Workbook

from agrosense.adapters.db.repository import (
    CampaignRepository,
    ProjectAnalysisRepository,
    ProjectRepository,
)
from agrosense.adapters.ingester.excel_source import ExcelCampaignSource
from agrosense.ml.stall_features import build_wave, fingerprint
from tests.auth.keys import ENGINEER_A as OWNER

HEADERS = [
    "LOCALIDAD", "Codigo de unidad muestreo", "ID Parcela", "Diseño floristico",
    "Cobertura vegetal asociada", "ID_MUEST", "Especie_M1", "Familia", "Coord_X", "Coord_Y",
    "Altura total (m)_M1", "Diámetro. Copa (m)_M1", "Sobrevivencia M1", "Estado Fitosanitario_M1",
    "Altura total (m)_M2", "Diámetro. Copa (m)_M2", "Sobrevivencia M2", "Estado Fitosanitario_M2",
]
X0, Y0 = 4735700.0, 2199400.0

# (locality, sampling_unit_code, plot_id, tree_id, species)
FILAS = [
    ("Guayabal", "U1", "1", "G_1", "Senna viarum"),
    ("Guayabal", "U1", "1", "G_2", "Senna viarum"),
    # Sin `Codigo de unidad muestreo` NI `ID Parcela`, pero CON `LOCALIDAD`:
    # domain.rules.plot_key devuelve None (E0 solo liga el predio a la
    # parcela). El hallazgo del item 2: la locality de este arbol se pierde
    # al servir desde la base si el mapeo no se corrige.
    ("Tres Jotas", None, None, "G_3", "Cedrela montana"),
]


def _excel() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_2"
    ws.append(HEADERS)
    for i, (loc, unit, plot, tid, sp) in enumerate(FILAS):
        ws.append(
            [
                loc, unit, plot, "Rehabilitación vegetal", "Bosque de galería",
                tid, sp, "Fabaceae", X0 + 30 * i, Y0 + 30 * i,
                0.5, 0.3, "Vivo", "Bueno",
                0.5, 0.3, "Vivo", "Bueno",
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_served_dataset_matches_the_direct_excel_source_for_every_wave(session):
    content = _excel()
    direct = ExcelCampaignSource().read(content, "m.xlsx")

    project = ProjectRepository(session).create(owner_id=OWNER, name="Paridad E7")
    CampaignRepository(session).save_ingest(
        project.id, direct, "m.xlsx", hashlib.sha256(content).hexdigest()
    )

    served_trees, served_obs = ProjectAnalysisRepository(session).load_dataset(project.id)
    assert {t.tree_id for t in served_trees} == {t.tree_id for t in direct.trees}

    for t in (1, 2):
        direct_rows = {
            r.tree_id: r.features for r in build_wave(direct.trees, direct.observations, t, labeled=False)
        }
        served_rows = {
            r.tree_id: r.features for r in build_wave(served_trees, served_obs, t, labeled=False)
        }
        assert served_rows == direct_rows, f"ola {t}: features distintas entre servido y directo"
        assert fingerprint(served_trees, served_obs, t) == fingerprint(
            direct.trees, direct.observations, t
        ), f"ola {t}: huella distinta entre servido y directo"


def test_locality_of_a_tree_without_a_plot_key_is_not_lost_when_served(session):
    """Caso puntual del hallazgo: G_3 no tiene parcela pero si predio."""
    content = _excel()
    direct = ExcelCampaignSource().read(content, "m.xlsx")
    directa = {t.tree_id: t for t in direct.trees}
    assert directa["G_3"].locality == "Tres Jotas"  # la ruta directa la conserva

    project = ProjectRepository(session).create(owner_id=OWNER, name="Paridad E7 (locality)")
    CampaignRepository(session).save_ingest(
        project.id, direct, "m.xlsx", hashlib.sha256(content).hexdigest()
    )
    served_trees, _ = ProjectAnalysisRepository(session).load_dataset(project.id)
    servida = {t.tree_id: t for t in served_trees}
    assert servida["G_3"].locality == "Tres Jotas"
