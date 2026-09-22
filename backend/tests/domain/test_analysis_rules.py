"""Definiciones del analisis exploratorio (E3): lo que el ingeniero hacia a mano
en las hojas del Anexo 1, escrito como reglas puras del dominio."""

from datetime import date

import pytest

from agrosense.domain.analysis_rules import (
    DEVELOPMENT_CLASSES,
    MIN_SAMPLE_FOR_PERCENT,
    PHYTOSANITARY_STATES,
    development_class,
    is_low_sample,
    normalize_phytosanitary,
    validate_monitoring_date,
)
from agrosense.domain.errors import DomainError

# ── Categoria de desarrollo (hoja «Edades», «ELABORACIÓN DEL RANGO») ─────────


@pytest.mark.parametrize(
    ("height", "expected"),
    [
        (0.01, "Plántula"),
        (0.2, "Plántula"),
        (0.5, "Plántula"),
        # El Anexo 1 escribe los rangos con dos decimales (0,01-0,5 / 0,51-3):
        # entre 0,50 y 0,51 no hay hueco, el limite superior es inclusivo.
        (0.505, "Juvenil I"),
        (0.51, "Juvenil I"),
        (3.0, "Juvenil I"),
        (3.05, "Juvenil II"),
        (6.0, "Juvenil II"),
        (6.01, "Mayor de 6 m"),
    ],
)
def test_development_class_by_height(height, expected):
    assert development_class(height) == expected


def test_development_class_without_height_is_none():
    assert development_class(None) is None
    # 0 m no es una altura de un arbol vivo: el Anexo lo trata como «Muertos»
    assert development_class(0) is None


def test_development_classes_are_ordered():
    assert [c.name for c in DEVELOPMENT_CLASSES] == [
        "Plántula",
        "Juvenil I",
        "Juvenil II",
        "Mayor de 6 m",
    ]


# ── Estado fitosanitario ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Bueno", "Bueno"),
        (" bueno ", "Bueno"),
        ("REGULAR", "Regular"),
        ("Malo", "Malo"),
        (" ", None),  # blanco de campo que trae el M2 real
        (None, None),
        ("Excelente", None),
    ],
)
def test_normalize_phytosanitary(raw, expected):
    assert normalize_phytosanitary(raw) == expected


def test_phytosanitary_vocabulary():
    assert PHYTOSANITARY_STATES == ("Bueno", "Regular", "Malo")


# ── Tamano minimo de muestra ─────────────────────────────────────────────────


def test_low_sample_flag():
    assert is_low_sample(MIN_SAMPLE_FOR_PERCENT - 1)
    assert not is_low_sample(MIN_SAMPLE_FOR_PERCENT)
    assert is_low_sample(0)


# ── Fechas de monitoreo ──────────────────────────────────────────────────────


def test_monitoring_date_must_follow_previous_and_precede_next():
    fechas = {1: date(2024, 1, 10), 3: date(2025, 1, 10)}
    validate_monitoring_date(2, date(2024, 6, 1), fechas, today=date(2026, 1, 1))
    with pytest.raises(DomainError) as exc:
        validate_monitoring_date(2, date(2023, 12, 1), fechas, today=date(2026, 1, 1))
    assert exc.value.code == "INVALID_MONITORING_DATE"
    with pytest.raises(DomainError):
        validate_monitoring_date(2, date(2025, 1, 10), fechas, today=date(2026, 1, 1))


def test_monitoring_date_cannot_be_in_the_future():
    with pytest.raises(DomainError) as exc:
        validate_monitoring_date(1, date(2027, 1, 1), {}, today=date(2026, 1, 1))
    assert "futuro" in exc.value.message


def test_monitoring_date_ignores_its_own_previous_value():
    fechas = {1: date(2024, 1, 10), 2: date(2024, 6, 1)}
    validate_monitoring_date(2, date(2024, 7, 1), fechas, today=date(2026, 1, 1))
