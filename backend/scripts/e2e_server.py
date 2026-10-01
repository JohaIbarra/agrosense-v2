"""Backend para las pruebas E2E del frontend (frontend/e2e). Nunca en produccion.

Arranca la API real contra una base SQLite NUEVA (migrada con Alembic, igual
que produccion) y verificando sesiones contra el Supabase Auth falso de
`frontend/e2e/fake-auth.mjs`. Antes escribe el Excel de campo que suben las
pruebas, para que el fixture no dependa del Anexo 1 (que no se commitea).

Uso (lo lanza Playwright): python scripts/e2e_server.py
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TMP = BACKEND.parent / "frontend" / "e2e" / ".tmp"
DB = TMP / "e2e.db"
PORT = int(os.environ.get("E2E_API_PORT", "8000"))

# Antes de importar agrosense: session.py lee DATABASE_URL al importarse y
# load_dotenv() no pisa variables ya definidas, asi que backend/.env no entra.
os.environ["DATABASE_URL"] = f"sqlite:///{DB.as_posix()}"
os.environ["SUPABASE_URL"] = os.environ.get("E2E_AUTH_URL", "http://127.0.0.1:54321")


def write_fixture(path: Path) -> None:
    """Excel de campo con 3 monitoreos: 2 predios, 4 parcelas, 40 arboles."""
    from openpyxl import Workbook

    rng = random.Random(42)
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_1"
    headers = ["LOCALIDAD", "Codigo de unidad muestreo", "ID Parcela", "Diseño floristico",
               "Cobertura vegetal asociada", "ID_MUEST", "Especie_M1", "Familia"]
    for n in (1, 2, 3):
        headers += [f"Altura total (m)_M{n}", f"Sobrevivencia M{n}", f"Estado Fitosanitario_M{n}"]
    ws.append(headers)
    species = [("Senna viarum", "Fabaceae"), ("Inga punctata", "Fabaceae"),
               ("Cecropia peltata", "Urticaceae"), ("Guazuma ulmifolia", "Malvaceae")]
    for i in range(40):
        locality = "Guayabal" if i < 20 else "San Antonio"
        unit = f"U{i // 10 + 1}"
        sp, fam = species[i % 4]
        row = [locality, unit, i // 10 + 1, "Rehabilitación vegetal", "Bosque de galería",
               f"T_{i + 1}", sp, fam]
        h, alive = 0.3 + rng.random() * 0.3, True
        for n in (1, 2, 3):
            if n > 1 and alive and rng.random() < 0.1:
                alive = False
            if alive and n > 1:
                h += 0.0 if rng.random() < 0.25 else rng.random() * 0.3
            row += [round(h, 2) if alive else None, "Vivo" if alive else "Muerto",
                    "Bueno" if alive else None]
        ws.append(row)
    wb.save(path)


def main() -> None:
    TMP.mkdir(parents=True, exist_ok=True)
    DB.unlink(missing_ok=True)
    write_fixture(TMP / "campo.xlsx")

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")

    import uvicorn

    uvicorn.run("agrosense.adapters.api.app:create_app", factory=True,
                host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    sys.exit(main())
