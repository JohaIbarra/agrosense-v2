"""Puertos: lo que `application/` necesita del mundo exterior (ADR-003).

Structural typing (`typing.Protocol`), no herencia: el adapter no importa
nada de aqui, solo cumple la forma. Cero coste en runtime.

Por que este puerto SI y no uno por repositorio: ADR-003 admite interfaz
"solo donde hoy hay variacion real". El formato de upload la tiene y esta
documentada — discovery seccion 2 y UC2 (docs/02-domain.md) dicen
**CSV/XLSX**, y hoy solo existe XLSX. Los repositorios siguen inyectandose
por parametro sin interfaz, como decidio el ADR.
"""
from __future__ import annotations

from typing import Protocol

from agrosense.application.dtos import CampaignData


class CampaignSource(Protocol):
    """Traduce el archivo crudo que sube el ingeniero a entidades de dominio.

    El implementador es duenno del formato (Excel, CSV, ...) y de sus
    librerias (pandas vive de ese lado). Tambien es quien valida los
    invariantes de dominio antes de devolver: si la campana es invalida,
    no se devuelve a medias.
    """

    def read(self, content: bytes, filename: str) -> CampaignData:
        """Parsea `content` a una campana canonica.

        Raises:
            ValueError: con prefijo INVALID_FILE si el archivo es ilegible.
            DomainError: si un invariante duro falla (campana rechazada
                completa, sin persistencia parcial — ADR-004).
        """
        ...
