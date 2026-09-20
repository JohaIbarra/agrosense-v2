"""Adapter de ingesta desde Excel: implementa `application.ports.CampaignSource`.

Aqui vive TODO lo que sabe de archivos: pandas, openpyxl, el nombre de la
hoja de campo, y las guardas de formato. `application/` solo ve el puerto
(ADR-003).

Guardas antes de parsear (hallazgo R4 del gate de fase 7). Un `.xlsx` ES un
zip, asi que la bomba de descompresion es el caso normal, no el exotico:
unos cientos de KB expanden a decenas de MB de XML. `pd.read_excel` no ofrece
ningun punto donde interceptar eso, asi que se valida sobre los bytes crudos.

Cuando llegue el upload de CSV (discovery seccion 2 / UC2), sera otra
implementacion del mismo puerto — con SUS propias guardas.
"""
from __future__ import annotations

import io
import logging
import zipfile

import pandas as pd
from openpyxl import load_workbook

from agrosense.adapters.ingester.ingest import ingest_wide
from agrosense.application.dtos import CampaignData
from agrosense.application.errors import AppError

logger = logging.getLogger(__name__)

# Hoja del dataset de campo (ADR-004 + AGENTS.md)
SHEET_NAME = "Monitoreo_4"

# Firma de un contenedor ZIP (todo .xlsx/.xlsm lo es)
_ZIP_MAGIC = b"PK\x03\x04"

# Techo de expansion. El dataset de referencia (858 filas x 42 columnas)
# descomprime a ~4 MB; 15 MB deja margen de 4x sin regalar CPU a un atacante.
MAX_UNCOMPRESSED_BYTES = 15 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100

# Techo de CELDAS que se materializan al leer la hoja. Acota el COSTE, que
# es distinto de acotar el contenedor: un .xlsx de 5 KB puede hacer que
# openpyxl+pandas materialicen un rectangulo enorme con tres celdas sueltas
# (medido: 4.8 KB -> 11.8s y 370 MB). El dataset real son 36.036 celdas;
# 2 millones dejan 55x de margen.
MAX_SHEET_CELLS = 2_000_000

# Mensaje unico hacia el cliente: accionable y sin internals (AGENTS.md).
_UNREADABLE = (
    "No se pudo leer el archivo como Excel. Verifique que sea un .xlsx valido "
    f"y que contenga la hoja '{SHEET_NAME}'."
)


def _reject(reason: str, exc: Exception | None = None) -> AppError:
    """Registra el detalle del lado del servidor y devuelve el error del contrato."""
    logger.warning("Upload rechazado: %s", reason, exc_info=exc)
    return AppError("INVALID_FILE", _UNREADABLE)


class ExcelCampaignSource:
    """Lee el formato ancho de campo en .xlsx y lo valida contra el dominio."""

    def __init__(self, sheet_name: str = SHEET_NAME):
        self._sheet_name = sheet_name

    def _check_container(self, content: bytes) -> None:
        """Valida el ZIP antes de que openpyxl abra un solo byte de XML."""
        if not content.startswith(_ZIP_MAGIC):
            raise _reject("no empieza con la firma ZIP de un .xlsx")

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                entries = zf.infolist()
        except Exception as exc:
            # No solo BadZipFile: zipfile lanza NotImplementedError para una
            # "version needed to extract" alta, y esa escapaba hasta el 500.
            # El trabajo de esta funcion es decidir si el contenedor es de
            # fiar; cualquier fallo aqui significa que no.
            raise _reject(f"contenedor ilegible ({type(exc).__name__})", exc) from exc

        uncompressed = sum(e.file_size for e in entries)
        if uncompressed > MAX_UNCOMPRESSED_BYTES:
            raise _reject(
                f"descomprime a {uncompressed} bytes, sobre el techo de "
                f"{MAX_UNCOMPRESSED_BYTES}"
            )

        # El ratio se mide contra los bytes que REALMENTE llegaron. `compress_size`
        # sale del directorio central, que lo escribe quien sube el archivo:
        # declarando compress_size == file_size el ratio daba 1.00 y pasaba todo.
        ratio = uncompressed / max(len(content), 1)
        if ratio > MAX_COMPRESSION_RATIO:
            raise _reject(f"ratio de compresion {ratio:.0f}:1 (bomba de descompresion)")

    def _read_sheet_bounded(self, content: bytes) -> pd.DataFrame:
        """Lee la hoja contando celdas y abortando al pasar el presupuesto.

        Sustituye a `pd.read_excel`, que no ofrece ningun punto donde cortar.

        Por que NO basta mirar el `<dimension>` declarado (intento anterior,
        derribado en revision): pandas llama `reset_dimensions()` y deriva el
        rectangulo de los atributos `r=` reales, asi que la declaracion es
        decorativa y el coste no. Bastaba **borrar** el elemento para pasar la
        guarda y seguir costando decenas de segundos. Lo unico que acota el
        coste de verdad es contar lo que se materializa, mientras se
        materializa.
        """
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise _reject(f"no se pudo abrir el libro ({type(exc).__name__})", exc) from exc

        try:
            if self._sheet_name not in wb.sheetnames:
                raise _reject(f"el libro no tiene la hoja '{self._sheet_name}'")
            ws = wb[self._sheet_name]
            # Igual que pandas: la extension real la fijan las celdas, no la
            # cabecera. Con esto un <dimension> mentiroso no trunca datos.
            ws.reset_dimensions()

            filas: list[tuple] = []
            celdas = 0
            ancho = 0
            for fila in ws.iter_rows(values_only=True):
                celdas += len(fila)
                if celdas > MAX_SHEET_CELLS:
                    raise _reject(
                        f"la hoja supera el techo de {MAX_SHEET_CELLS} celdas"
                    )
                ancho = max(ancho, len(fila))
                filas.append(fila)
        finally:
            wb.close()

        # Las hojas suelen acabar con filas vacias de relleno; `pd.read_excel`
        # las descarta y aqui hay que hacer lo mismo o el ingester las toma
        # por arboles sin ID.
        while filas and all(v is None for v in filas[-1]):
            filas.pop()

        if not filas:
            raise _reject("la hoja esta vacia")
        if len(filas) * ancho > MAX_SHEET_CELLS:
            raise _reject(f"la hoja supera el techo de {MAX_SHEET_CELLS} celdas")

        # Filas ragged -> rectangulo, como hace el lector de pandas
        cabecera = filas[0] + (None,) * (ancho - len(filas[0]))
        cuerpo = [f + (None,) * (ancho - len(f)) for f in filas[1:]]
        return pd.DataFrame(cuerpo, columns=list(cabecera))

    def read(self, content: bytes, filename: str) -> CampaignData:
        """Parsea los bytes del .xlsx a una campana canonica.

        `filename` solo se usa para el registro del servidor: no vuelve al
        cliente ni decide nada (hallazgo R2).

        Raises:
            AppError("INVALID_FILE"): contenedor invalido, bomba, o Excel ilegible.
            DomainError: si un invariante duro falla (campana rechazada entera).
        """
        self._check_container(content)
        df = self._read_sheet_bounded(content)
        return ingest_wide(df)
