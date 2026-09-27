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


# ── Regresion: falsos positivos en texto real de qwen2.5:3b (fix wave
# 2026-09-27, item 2) ────────────────────────────────────────────────────


def test_monitoring_labels_are_not_flagged_as_numbers():
    figuras = {"Supervivencia": "93.5%"}
    texto = "Entre M3 y M4 se mantuvo la tendencia observada en M2."
    assert find_unverified_numbers(texto, figuras) == []


def test_a_hyphenated_monitoring_range_does_not_yield_a_negative_number():
    figuras = {"Supervivencia": "93.5%"}
    texto = "La comparación M3-M4 confirma la tendencia."
    assert find_unverified_numbers(texto, figuras) == []


def test_a_hyphenated_year_range_does_not_yield_a_negative_number():
    figuras = {"Inicio": "2025", "Fin": "2026"}
    texto = "El proyecto se ejecuta entre 2025-2026."
    assert find_unverified_numbers(texto, figuras) == []


def test_numbered_list_markers_are_not_flagged_as_numbers():
    figuras = {"Supervivencia": "93.5%"}
    texto = "Recomendaciones:\n1. Revisar las parcelas.\n2) Mantener el monitoreo."
    assert find_unverified_numbers(texto, figuras) == []


def test_a_percent_rounded_to_a_whole_number_verifies_the_known_decimal():
    # 93.5% escrito como 94% (round(93.5, 0) == 94): verificado, no un
    # numero inventado.
    figuras = {"Supervivencia": "93.5%"}
    texto = "La supervivencia fue del 94%."
    assert find_unverified_numbers(texto, figuras) == []


def test_numbers_in_figure_labels_count_as_known():
    figuras = {"Altura promedio a los 5 años (m)": "1.20"}
    texto = "A los 5 años, la altura promedio fue de 1.20 m."
    assert find_unverified_numbers(texto, figuras) == []


def test_an_invented_number_is_still_flagged_alongside_monitoring_labels():
    figuras = {"Supervivencia": "93.5%"}
    texto = "Entre M3 y M4, la supervivencia alcanzó un sorprendente 60%."
    assert find_unverified_numbers(texto, figuras) == ["60%"]


def test_a_realistic_spanish_paragraph_with_only_verified_numbers_yields_nothing():
    figuras = {
        "Árboles registrados en M2": "856",
        "Vivos": "800",
        "Supervivencia": "93.5%",
        "Altura media": "0.85 m",
        "Mortalidad (Comparación M1 → M2)": "4.2%",
        "Crecimiento medio (m) (Comparación M1 → M2)": "0.123",
    }
    texto = (
        "Borrador generado por IA: revise las cifras antes de usarlo.\n\n"
        "En M2 se registraron 856 árboles, de los cuales 800 están vivos: una "
        "supervivencia del 94% (93,5% exacto). La altura media alcanzó 0.85 m.\n\n"
        "Entre M1 y M2 la mortalidad del proyecto fue de 4.2% y el crecimiento "
        "medio de 0.12 m.\n\n"
        "Recomendaciones:\n"
        "1. Revisar las parcelas con mayor mortalidad entre M3-M4.\n"
        "2. Mantener el monitoreo trimestral.\n"
    )
    assert find_unverified_numbers(texto, figuras) == []
