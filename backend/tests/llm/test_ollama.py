"""Adaptador de Ollama (E9), SIN salir a la red.

Se sustituye `_post`, el unico punto que habla HTTP -- mismo patron que
`tests/satellite/test_planetary_computer.py`.
"""
from __future__ import annotations

import pytest

from agrosense.adapters.llm import ollama
from agrosense.application.errors import AppError


@pytest.fixture()
def llamadas(monkeypatch):
    registro: list[tuple[str, dict]] = []
    respuestas: list[dict] = []

    def _post(url, body, timeout=None):
        registro.append((url, body))
        return respuestas.pop(0)

    monkeypatch.setattr(ollama, "_post", _post)
    return registro, respuestas


def test_generate_pide_el_modelo_el_prompt_y_el_sistema_sin_streaming(llamadas):
    registro, respuestas = llamadas
    respuestas.append({"response": "  Borrador generado por IA...  "})

    texto = ollama.OllamaClient().generate("cifras: 1", "eres un asistente")

    url, cuerpo = registro[0]
    assert url == f"{ollama.OLLAMA_URL}/api/generate"
    assert cuerpo["model"] == ollama.OLLAMA_MODEL
    assert cuerpo["prompt"] == "cifras: 1"
    assert cuerpo["system"] == "eres un asistente"
    assert cuerpo["stream"] is False
    assert texto == "Borrador generado por IA..."  # recortado


def test_una_respuesta_vacia_es_un_error_de_operacion(llamadas):
    _, respuestas = llamadas
    respuestas.append({"response": ""})
    with pytest.raises(AppError) as exc:
        ollama.OllamaClient().generate("x", "y")
    assert exc.value.code == "LLM_UNAVAILABLE"


def test_un_fallo_de_red_sale_como_error_de_operacion_no_como_excepcion(monkeypatch):
    import urllib.error

    def _urlopen(request, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(ollama.urllib.request, "urlopen", _urlopen)

    with pytest.raises(AppError) as exc:
        ollama.OllamaClient().generate("x", "y")
    assert exc.value.code == "LLM_UNAVAILABLE"
    assert "Ollama" in exc.value.message


def test_el_nombre_del_modelo_es_el_configurado():
    assert ollama.OllamaClient().model_name == ollama.OLLAMA_MODEL
