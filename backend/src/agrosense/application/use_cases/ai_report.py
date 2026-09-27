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

import re
from typing import Protocol

from agrosense.application.dtos import AIReportDTO
from agrosense.application.errors import AppError
from agrosense.application.use_cases.monitoring_analysis import get_monitoring_analysis

PROMPT_VERSION = "2026-09-27-e9.1"

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


_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?%?")


def _to_float(token: str) -> float:
    """`93,5%` / `93.5` -> 93.5. La coma es el separador decimal en
    español; se asume que no hay separador de miles (las cifras del
    dominio no llegan a los miles)."""
    limpio = token.rstrip("%")
    if "," in limpio and "." not in limpio:
        limpio = limpio.replace(",", ".")
    return float(limpio)


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

    Compara con una tolerancia de 0.05 (el modelo puede redondear una cifra
    al escribirla) y normaliza la coma decimal. Puede marcar como
    "no verificado" un numero que en realidad es correcto pero no viene de
    una figura (un numero de monitoreo como "M4", por ejemplo): es un falso
    positivo aceptable -- la funcion nunca corrige el texto sola, solo
    avisa (AGENTS.md: el contenido generado es no confiable por defecto).
    """
    known = [_to_float(tok) for value in figures.values() for tok in _NUMBER_RE.findall(value)]
    seen: list[str] = []
    for tok in _NUMBER_RE.findall(text):
        valor = _to_float(tok)
        if not any(abs(valor - k) <= 0.05 for k in known) and tok not in seen:
            seen.append(tok)
    return seen


def render_prompt(figures: dict[str, str]) -> str:
    lineas = [f"- {label}: {valor}" for label, valor in figures.items()]
    return (
        "Redacta el borrador del informe con EXACTAMENTE estas cifras "
        "(no agregues ninguna otra):\n" + "\n".join(lineas)
    )


def _snapshot_key(analysis_version: str, input_hash: str) -> str:
    """Ata el borrador a la version Y a los datos exactos del snapshot."""
    return f"{analysis_version}:{input_hash}"


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
    current_key = _snapshot_key(analysis.analysis_version, analysis.input_hash)
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

    Raises:
        AppError("PROJECT_NOT_FOUND" | "MONITORING_NOT_FOUND"): del snapshot
            subyacente.
        AppError("LLM_UNAVAILABLE"): el puerto lo lanza si Ollama no responde.
    """
    analysis = get_monitoring_analysis(
        project_id, number, owner_id, project_repo, analysis_repo, engine
    )
    monitoring = project_repo.get_monitoring(project_id, number)
    figures = build_report_figures(analysis.payload)
    content = llm.generate(render_prompt(figures), SYSTEM_PROMPT)
    unverified = find_unverified_numbers(content, figures)
    key = _snapshot_key(analysis.analysis_version, analysis.input_hash)
    row = report_repo.save(
        project_id, monitoring.id, llm.model_name, PROMPT_VERSION, key, content, unverified,
    )
    return _to_dto(project_id, number, row, stale=False)
