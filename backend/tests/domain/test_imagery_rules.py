"""Reglas de una capa de imagen del proyecto (E6b).

La plantilla de teselas la escribe el ingeniero y la CARGA SU NAVEGADOR: cada
tesela es una peticion a un tercero. Por eso lo que se acepta es estrecho a
proposito.
"""
from __future__ import annotations

import pytest

from agrosense.domain.errors import DomainError
from agrosense.domain.imagery_rules import (
    MAX_URL_LENGTH,
    normalize_opacity,
    validate_tile_template,
)

VALIDA = "https://tiles.openaerialmap.org/abc/0/def/{z}/{x}/{y}.png"


def test_una_plantilla_xyz_sobre_https_es_valida():
    assert validate_tile_template(VALIDA) == VALIDA


def test_se_recortan_los_espacios_de_pegar_desde_el_navegador():
    assert validate_tile_template(f"  {VALIDA}\n") == VALIDA


@pytest.mark.parametrize(
    "template,motivo",
    [
        ("http://tiles.example.org/{z}/{x}/{y}.png", "https"),
        ("javascript:alert(1)", "https"),
        ("data:image/png;base64,AAAA", "https"),
        ("//tiles.example.org/{z}/{x}/{y}.png", "https"),
    ],
)
def test_solo_https(template, motivo):
    """http mezclado en una pagina https lo bloquea el navegador, y
    `javascript:`/`data:` no son fuentes de teselas: son inyeccion."""
    with pytest.raises(DomainError) as exc:
        validate_tile_template(template)
    assert motivo in str(exc.value).lower()


@pytest.mark.parametrize(
    "template",
    [
        "https://tiles.example.org/{z}/{x}.png",
        "https://tiles.example.org/tiles.png",
        "https://tiles.example.org/{z}/{y}.png",
    ],
)
def test_la_plantilla_debe_traer_z_x_e_y(template):
    with pytest.raises(DomainError) as exc:
        validate_tile_template(template)
    assert "{z}" in str(exc.value)


def test_una_url_absurdamente_larga_se_rechaza():
    with pytest.raises(DomainError):
        validate_tile_template("https://t.example.org/" + "a" * MAX_URL_LENGTH + "/{z}/{x}/{y}.png")


def test_se_admite_el_esquema_invertido_de_algunos_servidores():
    """Hay servidores TMS que ponen {y} antes de {x}: es igual de valido."""
    t = "https://t.example.org/{z}/{y}/{x}.png"
    assert validate_tile_template(t) == t


def test_las_llaves_deben_ser_las_de_leaflet():
    """`{s}` (subdominio) obligaria a configurar subdominios: no se acepta."""
    with pytest.raises(DomainError) as exc:
        validate_tile_template("https://{s}.example.org/{z}/{x}/{y}.png")
    assert "{s}" in str(exc.value)


@pytest.mark.parametrize(
    "entrada,esperado", [(None, 1.0), (0.0, 0.0), (0.5, 0.5), (1, 1.0), (0.333, 0.33)]
)
def test_la_opacidad_se_normaliza(entrada, esperado):
    assert normalize_opacity(entrada) == esperado


@pytest.mark.parametrize("entrada", [-0.1, 1.5, 2])
def test_una_opacidad_fuera_de_rango_se_rechaza(entrada):
    with pytest.raises(DomainError):
        normalize_opacity(entrada)
