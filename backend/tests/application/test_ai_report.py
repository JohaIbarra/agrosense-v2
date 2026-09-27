"""Figuras compactas del snapshot y guardia de numeros para el borrador de
IA (E9). Funciones puras: se prueban con un payload de mentira, con la
misma forma que devuelve el motor de analisis (ADR-008) -- nada de ORM ni
de red.
"""
from __future__ import annotations

from agrosense.application.use_cases.ai_report import (
    build_report_figures,
    find_unverified_numbers,
)

PAYLOAD_M1 = {
    "summary": [
        {"key": "trees", "label": "Árboles registrados en M1", "kind": "int", "value": 856},
        {"key": "alive", "label": "Vivos", "kind": "int", "value": 800},
        {
            "key": "survival", "label": "Supervivencia", "kind": "percent",
            "decimals": 1, "value": 93.5,
        },
        {
            "key": "height", "label": "Altura media", "kind": "decimal",
            "decimals": 2, "unit": "m", "value": 0.85,
        },
    ],
    "sections": [
        {
            "id": "comparacion", "title": "Comparación M1 → M2",
            "tables": [], "charts": [], "notes": ["Primer monitoreo: sin comparación"],
        }
    ],
}

PAYLOAD_M2 = {
    "summary": PAYLOAD_M1["summary"],
    "sections": [
        {
            "id": "comparacion", "title": "Comparación M1 → M2",
            "tables": [
                {
                    "id": "comparacion-resumen",
                    "title": "Qué pasó entre M1 y M2, por predio",
                    "columns": [
                        {"key": "property", "label": "Predio", "kind": "text"},
                        {
                            "key": "mortality", "label": "Mortalidad", "kind": "percent",
                            "decimals": 1,
                        },
                        {
                            "key": "growth", "label": "Crecimiento medio (m)",
                            "kind": "decimal", "decimals": 3,
                        },
                    ],
                    "rows": [],
                    "footer": [{"property": "Proyecto", "mortality": 4.2, "growth": 0.123}],
                    "notes": [],
                }
            ],
            "charts": [],
        }
    ],
}


def test_summary_items_become_readable_figures():
    figuras = build_report_figures(PAYLOAD_M1)
    assert figuras["Árboles registrados en M1"] == "856"
    assert figuras["Supervivencia"] == "93.5%"
    assert figuras["Altura media"] == "0.85 m"


def test_a_value_of_none_is_not_a_figure():
    payload = {
        "summary": [{"key": "x", "label": "X", "kind": "int", "value": None}],
        "sections": [],
    }
    assert build_report_figures(payload) == {}


def test_the_comparison_project_total_is_added_when_there_is_an_interval():
    figuras = build_report_figures(PAYLOAD_M2)
    assert figuras["Mortalidad (Comparación M1 → M2)"] == "4.2%"
    assert figuras["Crecimiento medio (m) (Comparación M1 → M2)"] == "0.123"


def test_first_monitoring_has_no_comparison_totals():
    figuras = build_report_figures(PAYLOAD_M1)
    assert not [k for k in figuras if "Comparación" in k]


def test_a_number_that_is_among_the_figures_is_verified():
    figuras = {"Supervivencia": "93.5%", "Árboles": "856"}
    texto = "La supervivencia fue de 93.5% sobre 856 árboles registrados."
    assert find_unverified_numbers(texto, figuras) == []


def test_a_comma_decimal_matches_the_same_dot_decimal_figure():
    figuras = {"Supervivencia": "93.5%"}
    texto = "La supervivencia fue del 93,5%."
    assert find_unverified_numbers(texto, figuras) == []


def test_a_rounded_number_within_tolerance_is_verified():
    figuras = {"Crecimiento medio": "0.123 m"}
    texto = "El crecimiento medio fue de 0.12 m."
    assert find_unverified_numbers(texto, figuras) == []


def test_an_invented_number_is_flagged():
    figuras = {"Supervivencia": "93.5%"}
    texto = "La supervivencia fue del 99%, muy por encima de lo esperado."
    assert find_unverified_numbers(texto, figuras) == ["99%"]


def test_the_same_invented_number_is_only_reported_once():
    figuras = {"Supervivencia": "93.5%"}
    texto = "La cifra 99 aparece dos veces: 99."
    assert find_unverified_numbers(texto, figuras) == ["99"]
