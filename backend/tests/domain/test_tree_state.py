"""Estado de un arbol en un monitoreo (E6).

Es el dato que colorea cada punto del mapa, pero la regla es de dominio, no
de la pantalla: «el estado fitosanitario de un arbol muerto no cuenta» vale
igual en un informe o en una tabla.
"""
from __future__ import annotations

import pytest

from agrosense.domain.analysis_rules import TREE_STATES, tree_state


@pytest.mark.parametrize(
    "phyto,esperado",
    [("Bueno", "bueno"), ("Regular", "regular"), ("Malo", "malo"),
     ("bueno", "bueno"), ("  MALO ", "malo")],
)
def test_un_arbol_vivo_lleva_su_estado_fitosanitario(phyto, esperado):
    assert tree_state(alive=True, phytosanitary=phyto) == esperado


def test_un_arbol_muerto_es_muerto_aunque_el_archivo_traiga_estado():
    """El estado fitosanitario de un muerto es un residuo de la fila anterior.

    Pintarlo de verde porque la celda dice «Bueno» seria mentir en el mapa.
    """
    assert tree_state(alive=False, phytosanitary="Bueno") == "muerto"


@pytest.mark.parametrize("phyto", [None, "", " ", "Regualr"])
def test_vivo_sin_estado_reconocible_es_sin_dato(phyto):
    assert tree_state(alive=True, phytosanitary=phyto) == "sin_dato"


def test_sin_saber_si_vive_no_se_inventa_un_estado():
    assert tree_state(alive=None, phytosanitary="Bueno") == "sin_dato"


def test_el_vocabulario_es_cerrado_y_ordenado_de_mejor_a_peor():
    assert TREE_STATES == ("bueno", "regular", "malo", "muerto", "sin_dato")
