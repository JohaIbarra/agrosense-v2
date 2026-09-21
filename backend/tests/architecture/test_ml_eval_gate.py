"""Gate ejecutable del ML eval gate: la validacion cruzada agrupa por PARCELA.

Por que existe como test y no como item de checklist: el repositorio ya
afirmaba en cuatro documentos que el `GroupKFold` era por arbol, y nadie lo
noto hasta la auditoria del 2026-09-21. Un chequeo humano que ya se escapo
una vez se convierte en test (misma razon que `test_layer_dependencies.py`).

Que agrupar por arbol esta mal, en corto:

  - **Fuga espacial.** Los arboles de una parcela comparten suelo, pendiente,
    exposicion y cuadrilla de medicion. Con folds por arbol, la misma parcela
    aparece en train y en test, y el modelo puntua mejor de lo que rendira en
    una parcela nueva.
  - **No aporta nada bajo split temporal.** El regimen primario entrena en
    M2->M3 y prueba en M3->M4: las olas ya separan las observaciones del mismo
    individuo. Lo que falta es independencia ESPACIAL, no temporal.
  - **La parcela no es ruido.** El modelo mixto le atribuye ICC 0.07 en
    estancamiento y 0.09 en mortalidad.

AGENTS.md lo permite explicitamente: el mismo arbol puede aparecer en train y
test en olas distintas; la misma observacion (arbol + ola) nunca.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).parents[3]
BACKEND = REPO / "backend"

# El identificador de parcela en el dataset de campo.
GROUPING_UNIT = "Codigo de unidad muestreo"

# Como se nombra el grupo correcto en codigo y en prosa.
_GRUPOS_OK = (
    "unidad_muestreo",
    "unidad de muestreo",
    "unidad muestreo",
    "parcela",
    "plot",
)

# Lo que NO puede ser el grupo.
_GRUPOS_MAL = ("tree_id", "arbol", "árbol", "id_muest")

_DOCS_CON_CV = (
    REPO / "AGENTS.md",
    REPO / "docs" / "01-discovery.md",
    REPO / "docs" / "03-architecture.md",
    REPO / "docs" / "obsidian-agrosense" / "01-Proyecto" / "Roadmap.md",
    REPO / "docs" / "obsidian-agrosense" / "04-ML" / "Resumen ML.md",
    REPO / "docs" / "obsidian-agrosense" / "04-ML" / "Protocolo Estancamiento.md",
    REPO / "docs" / "obsidian-agrosense" / "06-Slices" / "Slice 3 - Riesgo de Mortalidad.md",
    REPO / "docs" / "obsidian-agrosense" / "06-Slices" / "Slice 4 - Detección de Estancados.md",
)


def _ml_sources() -> list[Path]:
    """Codigo del pipeline ML. Hoy `ml/` no existe todavia (va en el slice 4)."""
    roots = [BACKEND / "src" / "agrosense" / "ml", BACKEND / "ml", REPO / "ml"]
    out: list[Path] = []
    for root in roots:
        if root.exists():
            out.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    out.extend(
        p
        for p in (BACKEND / "scripts").rglob("*.py")
        if "__pycache__" not in p.parts
    )
    return out


def test_groupkfold_uses_plot() -> None:
    """Toda CV agrupada del pipeline ML usa la parcela como grupo, no el arbol.

    Se salta (no se aprueba en falso) mientras no exista codigo ML: el gate
    empieza a morder en cuanto el slice 4 escriba el primer `GroupKFold`.
    """
    fuentes = [p for p in _ml_sources() if "group" in p.read_text(encoding="utf-8").lower()]
    if not fuentes:
        pytest.skip("aun no hay codigo de CV agrupada (llega con el slice 4)")

    violaciones: list[str] = []
    for path in fuentes:
        for i, linea in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            bajo = linea.lower()
            if "groups" not in bajo and "group_kfold" not in bajo:
                continue
            if any(mal in bajo for mal in _GRUPOS_MAL) and not any(
                ok in bajo for ok in _GRUPOS_OK
            ):
                violaciones.append(
                    f"{path.relative_to(REPO)}:{i} agrupa por arbol: {linea.strip()}"
                )
    assert not violaciones, (
        "La CV agrupada debe usar `" + GROUPING_UNIT + "` (parcela), no el arbol:\n"
        + "\n".join(violaciones)
    )


def test_docs_do_not_claim_grouping_by_tree() -> None:
    """Ningun documento vigente puede seguir diciendo "GroupKFold por arbol".

    La documentacion es el contrato del ML eval gate: si dice el grupo
    equivocado, quien implemente el slice 4 lo implementara mal.
    """
    # "MAL (...)": bloques que muestran el antipatron a proposito.
    patron = re.compile(
        r"(groupkfold\s*(por|by)\s*[áa]rbol"
        r"|group\s*split\s*(por|by)\s*[áa]rbol"
        r"|groups\s*=\s*tree_id)",
        re.IGNORECASE,
    )
    violaciones: list[str] = []
    for path in _DOCS_CON_CV:
        if not path.exists():
            continue
        lineas = path.read_text(encoding="utf-8").splitlines()
        for i, linea in enumerate(lineas, 1):
            if not patron.search(linea):
                continue
            # Un ejemplo marcado como incorrecto en las 3 lineas previas es
            # documentacion del error, no una afirmacion.
            contexto = "\n".join(lineas[max(0, i - 4) : i]).upper()
            if "MAL" in contexto or "FUGA" in contexto:
                continue
            violaciones.append(f"{path.relative_to(REPO)}:{i}: {linea.strip()}")
    assert not violaciones, (
        "Documentos que aun afirman agrupar por arbol:\n" + "\n".join(violaciones)
    )


def test_agents_md_states_the_plot_as_grouping_unit() -> None:
    """AGENTS.md es la fuente de la regla: debe nombrar la parcela."""
    texto = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert GROUPING_UNIT in texto, (
        "AGENTS.md debe nombrar `" + GROUPING_UNIT + "` como unidad de agrupamiento"
    )
    assert "sampling plot, not individual tree" in texto
