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
