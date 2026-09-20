"""Adapter de ingesta desde Excel: implementa `application.ports.CampaignSource`.

Aqui vive TODO lo que sabe de archivos: pandas, openpyxl, el nombre de la
hoja de campo. `application/` solo ve el puerto (ADR-003).

Cuando llegue el upload de CSV (discovery seccion 2 / UC2), sera otra
implementacion del mismo puerto — sin tocar el caso de uso.
"""
from __future__ import annotations

import io

import pandas as pd

from agrosense.adapters.ingester.ingest import ingest_wide
from agrosense.application.dtos import CampaignData

# Hoja del dataset de campo (ADR-004 + AGENTS.md)
SHEET_NAME = "Monitoreo_4"


class ExcelCampaignSource:
    """Lee el formato ancho de campo en .xlsx y lo valida contra el dominio."""

    def __init__(self, sheet_name: str = SHEET_NAME):
        self._sheet_name = sheet_name

    def read(self, content: bytes, filename: str) -> CampaignData:
        """Parsea los bytes del .xlsx a una campana canonica.

        Raises:
            ValueError: INVALID_FILE si no es un Excel legible o falta la hoja.
            DomainError: si un invariante duro falla (campana rechazada entera).
        """
        try:
            df = pd.read_excel(io.BytesIO(content), sheet_name=self._sheet_name)
        except Exception as exc:
            # Mensaje accionable, sin stack trace (AGENTS.md / Security)
            raise ValueError(
                f"INVALID_FILE: no se pudo leer '{filename}' como Excel "
                f"(hoja '{self._sheet_name}'): {exc}"
            ) from exc

        return ingest_wide(df)
