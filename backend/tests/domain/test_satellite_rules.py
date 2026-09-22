"""Reglas de los índices espectrales (E10a)."""

from datetime import date

import pytest

from agrosense.domain.errors import DomainError
from agrosense.domain.satellite_rules import (
    MAX_RANGE_DAYS,
    MIN_PIXELS_FOR_INDEX,
    is_reliable,
    ndvi_reading,
    validate_index,
    validate_range,
)

HOY = date(2026, 9, 22)


def test_el_indice_se_normaliza():
    assert validate_index("ndvi") == "NDVI"
    assert validate_index("  NDVI ") == "NDVI"


def test_un_indice_que_no_sabemos_interpretar_se_rechaza():
    with pytest.raises(DomainError) as exc:
        validate_index("EVI")
    assert "NDVI" in str(exc.value), "el mensaje debe decir cuáles sí"


def test_una_ventana_normal_es_valida():
    validate_range(date(2024, 1, 1), date(2024, 12, 31), HOY)


@pytest.mark.parametrize(
    "inicio,fin,motivo",
    [
        (date(2024, 12, 31), date(2024, 1, 1), "anterior"),
        (date(2014, 1, 1), date(2015, 1, 1), "2015"),
        (date(2027, 1, 1), date(2027, 2, 1), "futuro"),
    ],
)
def test_ventanas_imposibles(inicio, fin, motivo):
    with pytest.raises(DomainError) as exc:
        validate_range(inicio, fin, HOY)
    assert motivo.lower() in str(exc.value).lower()


def test_una_ventana_demasiado_larga_se_rechaza():
    """Cada escena es una petición al proveedor: la ventana se acota."""
    with pytest.raises(DomainError):
        validate_range(date(2018, 1, 1), date(2018, 1, 1) + __import__("datetime").timedelta(
            days=MAX_RANGE_DAYS + 1
        ), HOY)


def test_un_predio_de_pocos_pixeles_no_es_fiable():
    """Un píxel mide 10 × 10 m: una parcela pequeña es todo borde."""
    assert is_reliable(MIN_PIXELS_FOR_INDEX) is True
    assert is_reliable(MIN_PIXELS_FOR_INDEX - 1) is False
    assert is_reliable(0) is False


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (-0.3, "Sin vegetación"),
        (0.05, "Sin vegetación"),
        (0.25, "escasa"),
        (0.45, "moderada"),
        (0.75, "densa"),
    ],
)
def test_la_lectura_del_ndvi_pone_palabras_al_numero(valor, esperado):
    assert esperado in ndvi_reading(valor)


def test_lo_que_no_se_midio_no_se_interpreta():
    assert ndvi_reading(None) is None
