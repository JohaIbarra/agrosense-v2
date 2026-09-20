"""Middleware ASGI: corta el cuerpo de la request antes de que nadie lo parsee.

Por que existe (hallazgo NEW-1 del re-scan de seguridad): el techo de la route
se aplica DEMASIADO TARDE. FastAPI resuelve `UploadFile` llamando a
`request.form()` antes de entrar al endpoint, y el parser de multipart de
Starlette escribe cada parte de archivo en un `SpooledTemporaryFile` que
desborda a disco al pasar 1 MB, sin ningun techo total. Cuando `_read_capped`
corria, el cuerpo entero ya estaba recibido y escrito: un POST de 40 GB se
escribia igual y el 413 llegaba al final.

Aqui se cuenta byte a byte sobre el propio `receive` del protocolo ASGI, que
es el unico punto anterior a todo lo demas.

`_read_capped` en la route se mantiene como defensa en profundidad: si un dia
se despliega detras de algo que ya trocea el cuerpo, el techo sigue existiendo
del lado de la aplicacion.
"""
from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

_DEMASIADO_GRANDE = {
    "code": "FILE_TOO_LARGE",
    "message": "El cuerpo de la peticion supera el limite permitido.",
}


class BodySizeLimitMiddleware:
    """Rechaza con 413 en cuanto el cuerpo supera `max_bytes`.

    ASGI puro y no `BaseHTTPMiddleware` a proposito: hay que envolver
    `receive`, y `BaseHTTPMiddleware` ya lo consume por su cuenta.
    """

    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Atajo para clientes honestos: si declaran de mas, se corta sin leer
        declarado = self._content_length(scope)
        if declarado is not None and declarado > self.max_bytes:
            await self._rechazar(send, scope, f"Content-Length {declarado}")
            return

        leidos = 0
        excedido = False

        async def receive_contado() -> Message:
            nonlocal leidos, excedido
            message = await receive()
            if message["type"] == "http.request":
                leidos += len(message.get("body", b""))
                if leidos > self.max_bytes:
                    excedido = True
                    # Se corta el flujo: el parser ve un cuerpo terminado y no
                    # sigue escribiendo, y el 413 lo emite el wrapper de `send`.
                    return {"type": "http.disconnect"}
            return message

        async def send_o_413(message: Message) -> None:
            if excedido:
                return
            await send(message)

        if declarado is None:
            logger.debug("Request sin Content-Length: se cuenta el cuerpo al vuelo")

        await self.app(scope, receive_contado, send_o_413)

        if excedido:
            await self._rechazar(send, scope, f"cuerpo mayor que {self.max_bytes} bytes")

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for nombre, valor in scope.get("headers", []):
            if nombre == b"content-length":
                try:
                    return int(valor)
                except ValueError:
                    return None
        return None

    async def _rechazar(self, send: Send, scope: Scope, motivo: str) -> None:
        import json

        logger.warning("413 en %s: %s", scope.get("path", "?"), motivo)
        cuerpo = json.dumps({"detail": _DEMASIADO_GRANDE}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(cuerpo)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": cuerpo})
