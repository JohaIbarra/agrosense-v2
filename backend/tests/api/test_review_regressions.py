"""Regresiones de los bloqueantes de la fase 7 (docs/revision-slice2.md).

Regla de AGENTS.md: "Bugs require a regression test". Cada test de aqui
reproduce un bloqueante que el gate de revision encontro, al nivel donde se
encontro: HTTP. Si alguno vuelve a pasar, estos fallan.
"""
from __future__ import annotations

import functools
import inspect
import io
import zipfile
from pathlib import Path

import pytest

DATASET = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"


def _xlsx_bytes() -> bytes:
    if not DATASET.exists():
        pytest.skip("dataset de referencia local ausente")
    return DATASET.read_bytes()


def _zip_bomb(entry_bytes: int = 40_000_000) -> bytes:
    """Un .xlsx sintetico con ratio de compresion absurdo.

    `.xlsx` ES un zip, asi que la bomba de descompresion es el caso normal,
    no el exotico: unos cientos de KB expanden a decenas de MB de XML.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", b"<c r='A1'/>" * (entry_bytes // 11))
    return buf.getvalue()


# ── R1: el segundo upload al mismo proyecto ────────────────────────────────

class TestSecondUpload:
    """Decision de producto (2026-09-20): mismo sha -> 409 sin crear campana;
    sha distinto -> campana nueva, la anterior intacta, y las observaciones
    del archivo mas reciente mandan."""

    def test_same_file_twice_is_409_and_creates_no_campaign(self, client):
        content = _xlsx_bytes()
        pid = client.post("/projects", json={"name": "P"}).json()["id"]

        assert client.post(
            f"/projects/{pid}/campaigns", files={"file": ("a.xlsx", content)}
        ).status_code == 201
        r = client.post(f"/projects/{pid}/campaigns", files={"file": ("a.xlsx", content)})
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "DUPLICATE_FILE"

        assert len(client.get(f"/projects/{pid}/campaigns").json()) == 1

    def test_corrected_file_creates_a_second_campaign(self, client):
        """El bloqueante R1: esto devolvia 500."""
        content = _xlsx_bytes()
        pid = client.post("/projects", json={"name": "P"}).json()["id"]

        client.post(f"/projects/{pid}/campaigns", files={"file": ("v1.xlsx", content)})
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": ("v2.xlsx", content + b"\x00")}
        )
        assert r.status_code == 201, f"R1 reabierto: {r.status_code}"
        assert r.json()["trees"] == 856

    def test_previous_campaign_is_neither_modified_nor_deleted(self, client):
        content = _xlsx_bytes()
        pid = client.post("/projects", json={"name": "P"}).json()["id"]

        client.post(f"/projects/{pid}/campaigns", files={"file": ("v1.xlsx", content)})
        before = client.get(f"/projects/{pid}/campaigns").json()[0]

        client.post(
            f"/projects/{pid}/campaigns", files={"file": ("v2.xlsx", content + b"\x00")}
        )
        campaigns = client.get(f"/projects/{pid}/campaigns").json()

        assert len(campaigns) == 2
        assert campaigns[0] == before, "la campana anterior cambio"
        assert campaigns[0]["filename"] == "v1.xlsx"
        assert campaigns[1]["filename"] == "v2.xlsx"
        assert campaigns[0]["id"] != campaigns[1]["id"]

    def test_trees_are_not_duplicated(self, client):
        """La identidad del arbol persiste entre campanas (docs/02-domain.md §2.4)."""
        content = _xlsx_bytes()
        pid = client.post("/projects", json={"name": "P"}).json()["id"]

        client.post(f"/projects/{pid}/campaigns", files={"file": ("v1.xlsx", content)})
        client.post(
            f"/projects/{pid}/campaigns", files={"file": ("v2.xlsx", content + b"\x00")}
        )

        trees = client.get(f"/projects/{pid}/trees?limit=500").json()
        trees += client.get(f"/projects/{pid}/trees?limit=500&offset=500").json()
        ids = [t["tree_id"] for t in trees]
        assert len(ids) == 856
        assert len(set(ids)) == 856, "hay arboles duplicados tras el segundo upload"

    def test_observations_are_not_duplicated(self, client):
        content = _xlsx_bytes()
        pid = client.post("/projects", json={"name": "P"}).json()["id"]

        client.post(f"/projects/{pid}/campaigns", files={"file": ("v1.xlsx", content)})
        tree = client.get(f"/projects/{pid}/trees?limit=1").json()[0]
        before = client.get(f"/projects/{pid}/trees/{tree['id']}/observations").json()

        client.post(
            f"/projects/{pid}/campaigns", files={"file": ("v2.xlsx", content + b"\x00")}
        )
        after = client.get(f"/projects/{pid}/trees/{tree['id']}/observations").json()

        assert len(after) == len(before), "UC7 devolveria filas duplicadas"
        assert [o["campaign"] for o in after] == [o["campaign"] for o in before]


# ── R2: el nombre de archivo no puede elegir el status ─────────────────────

class TestFilenameCannotChooseStatus:
    @pytest.mark.parametrize(
        "filename",
        [
            "bad.xlsx",
            "DUPLICATE_FILE.xlsx",
            "PROJECT_NOT_FOUND.xlsx",
            "TREE_NOT_FOUND.xlsx",
            "DUPLICATE_NAME.xlsx",
            "INVALID_FILE_PROJECT_NOT_FOUND.xlsx",
        ],
    )
    def test_unreadable_file_is_always_400_invalid_file(self, client, filename):
        """R2: `if code in msg` dejaba que el filename eligiera el status."""
        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": (filename, b"no soy excel")}
        )
        assert r.status_code == 400, f"{filename} eligio el status {r.status_code}"
        assert r.json()["detail"]["code"] == "INVALID_FILE"

    def test_parser_exception_is_not_echoed_to_the_client(self, client):
        """AGENTS.md: 'External errors are sanitized'."""
        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": ("x.xlsx", b"no soy excel")}
        )
        msg = r.json()["detail"]["message"]
        for leak in ("Traceback", "openpyxl", "pandas", "you must specify an engine"):
            assert leak not in msg, f"se filtro '{leak}' al cliente: {msg!r}"

    def test_filename_is_not_reflected_verbatim(self, client):
        """Un filename hostil no vuelve al cliente ni entra a la DB tal cual."""
        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        hostile = "<img src=x onerror=alert(1)>.xlsx"
        r = client.post(f"/projects/{pid}/campaigns", files={"file": (hostile, b"nope")})
        assert "onerror" not in r.text


# ── R3: el upload no puede bloquear el event loop ──────────────────────────

def test_upload_endpoint_is_not_a_coroutine():
    """AGENTS.md:132 — la tercera leccion de v1.

    Un `async def` cuyo unico `await` es `file.read()` corre TODO el parseo y
    las escrituras en el event loop: durante los ~80s del upload el worker no
    atiende ninguna otra request. FastAPI solo manda al threadpool los `def`.
    """
    from agrosense.adapters.api.routes import projects

    assert not inspect.iscoroutinefunction(projects.upload_campaign_endpoint), (
        "el endpoint de upload volvio a ser async def: bloquea el event loop"
    )


# Nota: la consecuencia (que la API siga atendiendo durante un upload) no se
# testea aqui. TestClient serializa las requests por un unico portal, asi que
# un test de concurrencia contra el seria teatro. La forma SI es verificable y
# es lo que causa el bloqueo, por eso el test de arriba mira la corrutina.


# ── R4: el upload se valida (tamano, tipo, bomba zip) ──────────────────────

class TestUploadIsValidated:
    def test_oversized_upload_is_rejected(self, client):
        """AGENTS.md, Security: 'File uploads are validated'."""
        from agrosense.adapters.api.routes.projects import MAX_UPLOAD_BYTES

        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        payload = b"PK\x03\x04" + b"0" * (MAX_UPLOAD_BYTES + 1)
        r = client.post(f"/projects/{pid}/campaigns", files={"file": ("big.xlsx", payload)})
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"

    def test_non_zip_bytes_are_rejected_before_parsing(self, client):
        """Un .xlsx es un zip: sin la firma PK no se le entrega a pandas."""
        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": ("x.xlsx", b"%PDF-1.4 nope")}
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_FILE"

    def test_zip_bomb_is_rejected(self, client):
        """CWE-409: ratio de descompresion acotado antes de abrir el XML."""
        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        bomb = _zip_bomb()
        assert len(bomb) < 1_000_000, "la bomba deberia ser pequena comprimida"
        r = client.post(f"/projects/{pid}/campaigns", files={"file": ("bomb.xlsx", bomb)})
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_FILE"

    def test_valid_dataset_still_passes_all_guards(self, client):
        """Las defensas no pueden romper el caso real."""
        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": ("anexo1.xlsx", _xlsx_bytes())}
        )
        assert r.status_code == 201
        assert r.json()["trees"] == 856


# ── Ninguna excepcion interna llega cruda al cliente ───────────────────────

def test_unmapped_exception_returns_a_structured_error(lenient_client):
    """AGENTS.md: 'Never expose internal exceptions or stack traces'.

    R1 fallaba como 500 sin cuerpo estructurado; el contrato dice que todo
    error lleva {code, message}.
    """
    from agrosense.adapters.api import routes

    def _boom(*a, **k):
        raise RuntimeError("secreto interno: postgresql://user:pass@host/db")

    pid = lenient_client.post("/projects", json={"name": "P"}).json()["id"]
    original = routes.projects.ProjectRepository.campaigns_count
    routes.projects.ProjectRepository.campaigns_count = _boom
    try:
        r = lenient_client.get(f"/projects/{pid}")
    finally:
        routes.projects.ProjectRepository.campaigns_count = original

    assert r.status_code == 500
    assert r.json()["detail"]["code"] == "INTERNAL"
    assert "secreto interno" not in r.text
    assert "postgresql://" not in r.text


# ── NEW-2: el coste de la hoja, no solo el del contenedor ──────────────────

def _sparse_xlsx(last_row: int = 60_000, last_col: int = 200) -> bytes:
    """Un .xlsx diminuto que declara una hoja enorme.

    Tres celdas sueltas: openpyxl rellena los huecos y pandas materializa el
    rectangulo completo. Las guardas de contenedor no ven nada raro porque el
    archivo NO esta comprimido de forma sospechosa — el coste esta en la
    dimension declarada.
    """
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    buf = io.BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_4"
    ws["A1"] = "ID_MUEST"
    ws[f"{get_column_letter(last_col)}1"] = "x"
    ws[f"A{last_row}"] = "y"
    wb.save(buf)
    return buf.getvalue()


def _strip_dimension(xlsx: bytes) -> bytes:
    """El mismo archivo sin el elemento <dimension>.

    Es el bypass que derribo la primera guarda: pandas llama
    `reset_dimensions()` y deriva el rectangulo de los atributos `r=` reales,
    asi que validar la declaracion no valida nada. Bastaba borrarla.
    """
    import re as _re

    salida = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(xlsx)) as zin, zipfile.ZipFile(
        salida, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for entrada in zin.infolist():
            datos = zin.read(entrada.filename)
            if entrada.filename.startswith("xl/worksheets/"):
                datos = _re.sub(rb"<dimension[^>]*/>", b"", datos)
            zout.writestr(entrada, datos)
    return salida.getvalue()


class TestSheetCostIsBounded:
    def test_huge_declared_sheet_is_rejected(self, client):
        payload = _sparse_xlsx()
        assert len(payload) < 50_000, "el archivo hostil debe ser diminuto"

        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": ("sparse.xlsx", payload)}
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_FILE"

    def test_rejection_is_cheap(self):
        """La guarda tiene que cortar ANTES de materializar el rectangulo.

        Sin ella esto costaba ~12s y ~370 MB; el limite de 3s deja margen de
        sobra para la lectura de la dimension y falla si alguien la quita.
        """
        import time

        from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

        payload = _sparse_xlsx()
        t0 = time.monotonic()
        with pytest.raises(ValueError):
            ExcelCampaignSource().read(payload, "sparse.xlsx")
        assert time.monotonic() - t0 < 3.0, "la guarda no corto antes de parsear"

    @pytest.mark.parametrize("mutar", [lambda b: b, _strip_dimension])
    def test_guard_holds_without_a_declared_dimension(self, client, mutar):
        """La guarda no puede depender de lo que el atacante declara."""
        payload = mutar(_sparse_xlsx())
        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": ("x.xlsx", payload)}
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_FILE"

    def test_rejection_is_cheap_without_dimension(self):
        """Sin declaracion, la guarda tiene que cortar igual de pronto."""
        import time

        from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

        payload = _strip_dimension(_sparse_xlsx(last_row=200_000, last_col=500))
        t0 = time.monotonic()
        with pytest.raises(ValueError):
            ExcelCampaignSource().read(payload, "x.xlsx")
        transcurrido = time.monotonic() - t0
        assert transcurrido < 5.0, f"tardo {transcurrido:.1f}s: la guarda no corto"

    def test_real_dataset_is_well_inside_the_budget(self, client):
        """El presupuesto no puede estorbar al caso real (858 x 42)."""
        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": ("anexo1.xlsx", _xlsx_bytes())}
        )
        assert r.status_code == 201


# ── NEW-3 y NEW-4: las guardas del contenedor, a fondo ─────────────────────

class TestContainerGuards:
    def test_ratio_is_measured_against_the_real_upload(self):
        """NEW-3: `compress_size` lo escribe quien sube el archivo.

        Declarando compress_size == file_size el ratio da 1.00 y la guarda
        vieja lo dejaba pasar. El tamano real subido no es metadato.
        """
        from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("xl/worksheets/sheet1.xml", b"<c r='A1'/>" * 400_000)
        raw = bytearray(buf.getvalue())

        # mentir en el directorio central: compress_size := file_size
        pos = raw.find(b"PK\x01\x02")
        assert pos >= 0
        file_size = int.from_bytes(raw[pos + 24 : pos + 28], "little")
        raw[pos + 20 : pos + 24] = file_size.to_bytes(4, "little")

        # Directamente contra la guarda: si se llamara a read() el test pasaria
        # igual sin la guarda, porque pandas falla despues por otro motivo.
        with pytest.raises(ValueError):
            ExcelCampaignSource()._check_container(bytes(raw))

    def test_unsupported_zip_version_is_a_client_error_not_a_500(self, client):
        """NEW-4: zipfile lanza NotImplementedError, que no es BadZipFile."""
        payload = bytearray(_xlsx_bytes())
        pos = 0
        while True:
            pos = payload.find(b"PK\x01\x02", pos)
            if pos < 0:
                break
            payload[pos + 6] = 0xA7
            pos += 4

        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": ("raro.xlsx", bytes(payload))}
        )
        assert r.status_code == 400, "un zip ilegible no es culpa del servidor"
        assert r.json()["detail"]["code"] == "INVALID_FILE"

    def test_bomb_guard_actually_fires(self):
        """El test anterior pasaba igual sin la guarda (fallaba por otro motivo).

        Este llama a la guarda directamente: si desaparece, no hay excepcion.
        """
        from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

        with pytest.raises(ValueError):
            ExcelCampaignSource()._check_container(_zip_bomb())


# ── El mensaje accionable vuelve al cliente ────────────────────────────────

class TestActionableIngestErrors:
    def _xlsx_with(self, df) -> bytes:
        import pandas as pd  # noqa: F401  (solo para construir el fixture)

        buf = io.BytesIO()
        df.to_excel(buf, sheet_name="Monitoreo_4", index=False)
        return buf.getvalue()

    def test_wrong_columns_explain_what_is_missing(self, client):
        """Sanear la salida no puede borrar el texto que escribimos nosotros.

        Es el fallo mas comun de campo: el ingeniero necesita saber QUE falta.
        """
        import pandas as pd

        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        payload = self._xlsx_with(pd.DataFrame({"columna_equivocada": [1, 2]}))
        r = client.post(f"/projects/{pid}/campaigns", files={"file": ("x.xlsx", payload)})

        assert r.status_code == 400
        detalle = r.json()["detail"]
        assert detalle["code"] == "INVALID_FILE"
        assert "ID_MUEST" in detalle["message"], (
            f"el mensaje no dice que falta: {detalle['message']!r}"
        )


# ── R1 (2a parte): la identidad del arbol se rechaza, no se descarta ───────

# Los tests de identidad son por arbol: 20 filas prueban exactamente lo mismo
# que 856 y bajan la suite ~20s. El dataset completo se sigue usando donde el
# volumen ES la conducta (los conteos de TestSecondUpload).
_IDENTITY_ROWS = 20


@functools.cache
def _base_dataset() -> bytes:
    """Las primeras filas del dataset real, sin modificar."""
    import pandas as pd

    df = pd.read_excel(io.BytesIO(_xlsx_bytes()), sheet_name="Monitoreo_4").head(
        _IDENTITY_ROWS
    )
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name="Monitoreo_4", index=False)
    return buf.getvalue()


@functools.cache
def _corrected_dataset_cached(cambios: tuple[tuple[str, object], ...]) -> bytes:
    """El dataset real con celdas cambiadas en su primera fila.

    Cacheado: reescribir las 856 filas con pandas cuesta ~10s, y varios tests
    piden la misma variante. Una suite lenta es una suite que se deja de
    correr, que es justo lo que el hallazgo B vino a arreglar.
    """
    import pandas as pd

    df = pd.read_excel(io.BytesIO(_xlsx_bytes()), sheet_name="Monitoreo_4")
    df = df.head(_IDENTITY_ROWS)
    cambios_dict = dict(cambios)
    for fragmento, valor in cambios_dict.items():
        col = next(c for c in df.columns if fragmento.lower() in str(c).lower())
        df.loc[0, col] = valor
    buf = io.BytesIO()
    df.to_excel(buf, sheet_name="Monitoreo_4", index=False)
    return buf.getvalue()


def _corrected_dataset(**cambios) -> bytes:
    return _corrected_dataset_cached(tuple(sorted(cambios.items())))


class TestTreeIdentityOnReupload:
    """Decision de producto (2026-09-20): si un archivo corregido cambia la
    IDENTIDAD de un arbol, se rechaza la carga con DomainError. Antes se
    aceptaba con 201 y se descartaba en silencio."""

    def _project_with_v1(self, client) -> int:
        pid = client.post("/projects", json={"name": "P"}).json()["id"]
        r = client.post(
            f"/projects/{pid}/campaigns", files={"file": ("v1.xlsx", _base_dataset())}
        )
        assert r.status_code == 201
        return pid

    def test_species_change_is_rejected(self, client):
        pid = self._project_with_v1(client)
        r = client.post(
            f"/projects/{pid}/campaigns",
            files={"file": ("v2.xlsx", _corrected_dataset(especie="OTRA ESPECIE"))},
        )
        assert r.status_code == 422, "un cambio de especie no puede pasar en silencio"
        assert r.json()["detail"]["code"] == "SPECIES_MISMATCH"

    def test_coordinate_change_is_rejected(self, client):
        pid = self._project_with_v1(client)
        r = client.post(
            f"/projects/{pid}/campaigns",
            files={"file": ("v2.xlsx", _corrected_dataset(coord_x=99.9))},
        )
        assert r.status_code == 422
        detalle = r.json()["detail"]
        assert detalle["code"] == "TREE_IDENTITY_MISMATCH"
        assert "coord_x" in detalle["message"]

    def test_rejected_upload_persists_nothing(self, client):
        """Sin persistencia parcial (ADR-004): la campana se rechaza entera."""
        pid = self._project_with_v1(client)
        antes = client.get(f"/projects/{pid}/campaigns").json()

        client.post(
            f"/projects/{pid}/campaigns",
            files={"file": ("v2.xlsx", _corrected_dataset(especie="OTRA"))},
        )

        assert client.get(f"/projects/{pid}/campaigns").json() == antes

    def test_descriptive_attributes_are_corrected(self, client):
        """Lo descriptivo SI se corrige: es lo que hace util re-subir."""
        pid = self._project_with_v1(client)
        antes = client.get(f"/projects/{pid}/trees?limit=1").json()[0]
        assert antes["common_name"] != "NOMBRE CORREGIDO"

        r = client.post(
            f"/projects/{pid}/campaigns",
            files={"file": ("v2.xlsx", _corrected_dataset(nombcom="NOMBRE CORREGIDO"))},
        )
        assert r.status_code == 201

        despues = client.get(f"/projects/{pid}/trees?limit=1").json()[0]
        assert despues["common_name"] == "NOMBRE CORREGIDO", (
            "la correccion descriptiva se descarto en silencio"
        )


# ── NEW-1: el cuerpo se corta antes de que nadie lo parsee ────────────────

class TestBodySizeMiddleware:
    def test_oversized_body_is_cut_before_parsing(self, client):
        """Se prueba contra /projects (JSON), que NO usa multipart.

        Si el techo viviera solo en `_read_capped` del upload, esta request
        llegaria a FastAPI y devolveria 422 de validacion. El 413 demuestra
        que el corte ocurre en el middleware, antes del parseo.
        """
        from agrosense.adapters.api.routes.projects import MAX_UPLOAD_BYTES

        r = client.post(
            "/projects",
            content=b'{"name": "' + b"x" * (MAX_UPLOAD_BYTES + 1) + b'"}',
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 413
        assert r.json()["detail"]["code"] == "FILE_TOO_LARGE"

    def test_normal_requests_are_untouched(self, client):
        r = client.post("/projects", json={"name": "normal"})
        assert r.status_code == 201
