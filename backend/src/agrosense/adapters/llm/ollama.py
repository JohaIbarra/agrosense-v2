"""Cliente de Ollama local (E9, ADR-012): implementa el puerto `LLMClient`
(`application/use_cases/ai_report.py`).

Habla HTTP con `{OLLAMA_URL}/api/generate` (`stream: false`) y traduce
cualquier fallo de red a `AppError("LLM_UNAVAILABLE")`: el ingeniero lee
"vuelva a intentarlo", nunca una excepcion de urllib (mismo patron que
`adapters/satellite/planetary_computer.py`).

Sin reintento (a diferencia de Planetary Computer): una generacion ya
puede tardar hasta 180 s, y reintentarla duplicaria la espera del
ingeniero. Si falla, el boton "Regenerar" del frontend ya cubre el reintento
manual.

Config por variable de entorno (D4, docs/04-vision-producto.md §12):
Ollama corre local hoy; produccion queda abierta hasta conocer el entorno
de despliegue.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from agrosense.application.errors import AppError

logger = logging.getLogger(__name__)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
_TIMEOUT = 180
_USER_AGENT = "AgroSense/2.0 (+restauracion ecologica)"


def _post(url: str, body: dict, timeout: int = _TIMEOUT) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.warning("Ollama no respondio: %s", exc)
        raise AppError(
            "LLM_UNAVAILABLE",
            "El modelo de IA local no está disponible ahora mismo. Verifique que "
            "Ollama esté corriendo (ollama serve) y reintente.",
        ) from exc


class OllamaClient:
    """Implementacion del puerto `LLMClient`."""

    model_name = OLLAMA_MODEL

    def generate(self, prompt: str, system: str) -> str:
        body = {"model": self.model_name, "prompt": prompt, "system": system, "stream": False}
        data = _post(f"{OLLAMA_URL}/api/generate", body)
        texto = (data.get("response") or "").strip()
        if not texto:
            raise AppError(
                "LLM_UNAVAILABLE", "El modelo de IA local devolvió una respuesta vacía."
            )
        return texto
