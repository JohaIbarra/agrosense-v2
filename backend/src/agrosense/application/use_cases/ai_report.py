"""UC-IA1/UC-IA2: figuras del snapshot y guardia de numeros para el
borrador de informe con IA de un monitoreo (E9).

AgroSense calcula, el LLM redacta (docs/04-vision-producto.md, principio
2): estas dos funciones son las que hacen cumplir esa regla.

`build_report_figures` recorta el snapshot del monitoreo
(`monitoring_analyses.payload`, ADR-008) a las pocas cifras que puede citar
el modelo: el resumen y el TOTAL de proyecto de la comparacion -- nunca una
fila por arbol ni por especie, porque el modelo es pequeno (qwen2.5:3b, 4 GB
de VRAM) y el prompt debe caber en su contexto.

`find_unverified_numbers` revisa el texto que devolvio el modelo: todo
numero que no aparezca entre esas cifras (con tolerancia para redondeos y
para la coma decimal) se marca como `unverified_numbers` en la respuesta.
Nunca se corrige el texto solo -- el ingeniero decide que hacer con el
aviso.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Protocol

from agrosense.application.dtos import AIReportDTO
from agrosense.application.errors import AppError
from agrosense.application.use_cases.monitoring_analysis import get_monitoring_analysis

# e9.2 (fix wave 2026-09-27, item 7): opciones deterministas de Ollama
# (temperature/seed) cambian que tan variable es la redaccion para las
# MISMAS cifras -- eso es semantica de salida, aunque el texto del prompt
# no cambio una letra. No se guarda por fila (séria redundante con esta
# constante); ver docs/adr/012-ia-local-con-ollama.md.
PROMPT_VERSION = "2026-09-27-e9.2"

SYSTEM_PROMPT = (
    "Eres un asistente que redacta borradores de informes de restauracion "
    "ecologica en español, para un ingeniero forestal colombiano. Reglas "
    "estrictas:\n"
    "1. Usa UNICAMENTE las cifras que se te entregan. No calcules, no "
    "estimes y no inventes ningun numero.\n"
    "2. No hagas recomendaciones que no se desprendan directamente de las "
    "cifras entregadas.\n"
    "3. Escribe en tono tecnico y neutral, en 2 a 4 parrafos cortos.\n"
    "4. Empieza el texto con la frase «Borrador generado por IA: revise "
    "las cifras antes de usarlo.» en su propio parrafo."
)


class LLMClient(Protocol):
    """Puerto hacia el modelo de lenguaje (ADR-003: solo donde hay
    variacion real -- hoy Ollama local, manana otro proveedor, docs/04 §7)."""

    model_name: str

    def generate(self, prompt: str, system: str) -> str: ...


# `(?<!\w)` antes del signo: un "-" solo cuenta como signo si NO esta pegado
# a una letra o digito. Sin esto, "2025-2026" se leia como "2025" y "-2026"
# (un numero negativo inventado) en vez de dos años. Con el signo asi
# acotado, "M3-M4" tampoco produce un falso "-4" (y el "3"/"4" de todas
# formas se descartan aparte, ver `_MONITORING_LABEL_RE`).
# NO se agrega separador de miles (p. ej. "1.234"): las cifras del dominio
# no llegan a los miles (AGENTS.md, item 2 del fix wave 2026-09-27) y
# soportarlo confundiria "1.234" (mil doscientos treinta y cuatro) con
# "1.234" (uno coma dos-tres-cuatro, si algun dia hubiera esa escala).
_NUMBER_RE = re.compile(r"(?<!\w)-?\d+(?:[.,]\d+)?%?")

# Etiquetas de monitoreo ("M1", "M4"...): nunca son una cifra citable, son
# un identificador. Sin esto "M3-M4" marcaba "3" y "4" como no verificados.
_MONITORING_LABEL_RE = re.compile(r"\bM\d+\b")

# Marcador de lista al inicio de linea ("1. ", "2) "): el numero es el
# indice de un item, no una cifra del dominio.
_LIST_MARKER_RE = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)


def _clean_for_numbers(text: str) -> str:
    """Quita del texto lo que NUNCA es una cifra citable antes de buscar
    numeros: marcadores de lista y etiquetas de monitoreo. Se aplica tanto
    al texto generado como a las figuras (valores Y etiquetas), asi ambos
    lados de la comparacion se leen igual."""
    sin_marcadores = _LIST_MARKER_RE.sub("", text)
    return _MONITORING_LABEL_RE.sub("", sin_marcadores)


def _to_float(token: str) -> float:
    """`93,5%` / `93.5` -> 93.5. La coma es el separador decimal en
    español; se asume que no hay separador de miles (las cifras del
    dominio no llegan a los miles)."""
    limpio = token.rstrip("%")
    if "," in limpio and "." not in limpio:
        limpio = limpio.replace(",", ".")
    return float(limpio)


def _decimals(token: str) -> int:
    """Cuantos decimales trae el token, para redondear la cifra conocida a
    esa misma precision antes de comparar (`93.5` escrito como `94` debe
    verificar)."""
    limpio = token.rstrip("%")
    if "," in limpio and "." not in limpio:
        limpio = limpio.replace(",", ".")
    return len(limpio.split(".", 1)[1]) if "." in limpio else 0


def _format_value(kind: str, value, decimals: int | None, unit: str | None) -> str | None:
    if value is None or kind == "text":
        return None
    if kind == "int":
        text = str(int(value))
    elif kind == "percent":
        text = f"{value:.{decimals if decimals is not None else 1}f}%"
    else:  # decimal
        text = f"{value:.{decimals if decimals is not None else 2}f}"
    if unit:
        text = f"{text} {unit}"
    return text


def build_report_figures(payload: dict) -> dict[str, str]:
    """Las cifras que puede citar el LLM: resumen + total de la comparacion.

    Recorre `payload["summary"]` (lista de `SummaryItem`, ya en escala
    0-100 para los porcentajes -- ADR-008) y, si el monitoreo tiene un
    intervalo anterior, la fila "Proyecto" del pie de la tabla
    `comparacion-resumen` de la seccion `id == "comparacion"`. El resto de
    esa seccion (por predio, por especie, por parcela) no entra: son datos
    de detalle, no cifras para un resumen redactado.
    """
    figures: dict[str, str] = {}
    for item in payload.get("summary", []):
        text = _format_value(
            item["kind"], item.get("value"), item.get("decimals"), item.get("unit")
        )
        if text is not None:
            figures[item["label"]] = text

    comparacion = next(
        (s for s in payload.get("sections", []) if s.get("id") == "comparacion"), None
    )
    if comparacion is None:
        return figures
    resumen = next(
        (t for t in comparacion.get("tables", []) if t.get("id") == "comparacion-resumen"),
        None,
    )
    if resumen is None:
        return figures
    total_row = next(
        (f for f in resumen.get("footer", []) if f.get("property") == "Proyecto"), None
    )
    if total_row is None:
        return figures

    columns = {c["key"]: c for c in resumen["columns"]}
    for key, value in total_row.items():
        col = columns.get(key)
        if col is None or value is None or col["kind"] == "text":
            continue
        label = f"{col['label']} ({comparacion['title']})"
        text = _format_value(col["kind"], value, col.get("decimals"), None)
        if text is not None:
            figures[label] = text
    return figures


def find_unverified_numbers(text: str, figures: dict[str, str]) -> list[str]:
    """Numeros del texto generado que NO aparecen entre `figures`.

    Antes de comparar, se descartan del texto las etiquetas de monitoreo
    ("M1", "M4"...) y los marcadores de lista ("1. ", "2) ") -- nunca son
    cifras del dominio, son identificadores y puntuacion (`_clean_for_numbers`).
    Las cifras "conocidas" salen tanto de los VALORES como de las ETIQUETAS
    de `figures` (una etiqueta puede traer un numero real, p. ej. "a los 5
    años"), limpiadas igual.

    La comparacion tolera redondeo: un numero del texto verifica si, al
    redondear alguna cifra conocida a SU MISMA cantidad de decimales,
    coinciden (`93.5` conocido verifica un `94` escrito, porque
    `round(93.5, 0) == 94`; `93,5` con coma decimal tambien). Nunca se
    corrige el texto solo -- el ingeniero decide que hacer con el aviso
    (AGENTS.md: el contenido generado es no confiable por defecto).
    """
    known = [
        _to_float(tok)
        for label, value in figures.items()
        for source in (label, value)
        for tok in _NUMBER_RE.findall(_clean_for_numbers(source))
    ]
    seen: list[str] = []
    for tok in _NUMBER_RE.findall(_clean_for_numbers(text)):
        valor = _to_float(tok)
        decimales = _decimals(tok)
        if not any(round(k, decimales) == valor for k in known) and tok not in seen:
            seen.append(tok)
    return seen


def render_prompt(figures: dict[str, str]) -> str:
    lineas = [f"- {label}: {valor}" for label, valor in figures.items()]
    return (
        "Redacta el borrador del informe con EXACTAMENTE estas cifras "
        "(no agregues ninguna otra):\n" + "\n".join(lineas)
    )


def _figures_fingerprint(analysis_version: str, figures: dict[str, str]) -> str:
    """Ata el borrador a la version del calculo Y a las cifras EXACTAS que
    vio el LLM -- no al `input_hash` del snapshot, que es del PROYECTO
    entero (fix wave 2026-09-27, item 3).

    Antes se usaba `f"{analysis_version}:{snapshot.input_hash}"`: como ese
    hash resume TODO el dataset del proyecto, subir M5 cambiaba el hash de
    M1-M4 tambien y marcaba "stale" borradores cuyas propias cifras (las de
    `build_report_figures`) no habian cambiado en nada. Aqui se recalcula el
    hash SOLO sobre esas cifras, en JSON canonico (`sort_keys=True`, para
    que el orden de insercion del dict no mueva el hash;
    `ensure_ascii=False`, para no tratar una tilde reordenada como un
    cambio) -- un unico punto (esta funcion) usado tanto al generar como al
    leer, para que nunca diverjan.
    """
    canonico = json.dumps(figures, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(canonico.encode("utf-8")).hexdigest()
    return f"{analysis_version}:{digest}"


def _to_dto(project_id: int, number: int, row, stale: bool) -> AIReportDTO:
    return AIReportDTO(
        project_id=project_id,
        monitoring=number,
        model_name=row.model_name,
        prompt_version=row.prompt_version,
        content=row.content,
        unverified_numbers=list(row.unverified_numbers),
        created_at=row.created_at,
        stale=stale,
    )


def get_ai_report(
    project_id: int,
    number: int,
    owner_id: str,
    project_repo,
    analysis_repo,
    report_repo,
    engine,
) -> AIReportDTO:
    """El borrador ya generado del monitoreo `number`.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "MONITORING_NOT_FOUND"): del snapshot
            subyacente (`get_monitoring_analysis`).
        AppError("AI_REPORT_NOT_FOUND"): el monitoreo existe pero todavia
            no se genero ningun borrador.
    """
    analysis = get_monitoring_analysis(
        project_id, number, owner_id, project_repo, analysis_repo, engine
    )
    monitoring = project_repo.get_monitoring(project_id, number)
    row = report_repo.get(monitoring.id)
    if row is None:
        raise AppError(
            "AI_REPORT_NOT_FOUND",
            f"El monitoreo M{number} todavia no tiene un borrador. Generelo primero.",
        )
    figures = build_report_figures(analysis.payload)
    current_key = _figures_fingerprint(analysis.analysis_version, figures)
    return _to_dto(project_id, number, row, stale=row.input_hash != current_key)


def generate_ai_report(
    project_id: int,
    number: int,
    owner_id: str,
    project_repo,
    analysis_repo,
    report_repo,
    engine,
    llm: LLMClient,
) -> AIReportDTO:
    """Genera (o regenera) el borrador del monitoreo `number`.

    AgroSense calcula, el LLM redacta: el prompt SOLO lleva las cifras de
    `build_report_figures`, nunca arboles ni observaciones. La guardia de
    numeros corre sobre lo que devuelve el modelo antes de guardarlo.

    `report_repo.release()` corre DESPUES de leer el snapshot (y de armar
    las figuras, que es trabajo en memoria) y ANTES de `llm.generate`: sin
    esto, la conexion de BD del ingeniero queda reservada en transaccion
    durante los hasta 180 s que puede tardar Ollama (fix wave 2026-09-27,
    item 4) -- con pocas conexiones en el pool, dos generaciones a la vez
    bastarian para agotarlo. No hay escritura pendiente en este punto (el
    snapshot ya se leyo/guardo antes en `get_monitoring_analysis`), asi que
    terminar la transaccion de lectura no pierde nada.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "MONITORING_NOT_FOUND"): del snapshot
            subyacente.
        AppError("LLM_UNAVAILABLE"): el puerto lo lanza si Ollama no responde.
    """
    analysis = get_monitoring_analysis(
        project_id, number, owner_id, project_repo, analysis_repo, engine
    )
    monitoring_id = project_repo.get_monitoring(project_id, number).id
    figures = build_report_figures(analysis.payload)
    analysis_version = analysis.analysis_version
    report_repo.release()
    content = llm.generate(render_prompt(figures), SYSTEM_PROMPT)
    unverified = find_unverified_numbers(content, figures)
    key = _figures_fingerprint(analysis_version, figures)
    row = report_repo.save(
        project_id, monitoring_id, llm.model_name, PROMPT_VERSION, key, content, unverified,
    )
    return _to_dto(project_id, number, row, stale=False)
