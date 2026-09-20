"""Errores de aplicacion con codigo transportado FUERA del mensaje.

Por que existe (hallazgo R2 del gate de fase 7): antes el codigo viajaba
DENTRO del texto y `adapters/api/errors.py` lo recuperaba con `if code in msg`
— una subcadena sin anclar sobre un mensaje que interpolaba el nombre de
archivo que manda el usuario. Un archivo llamado `PROJECT_NOT_FOUND.xlsx`
elegia el status de la respuesta. Cuando llegue la epica de auth, ese mismo
mecanismo dejaria que un nombre de archivo eligiera el resultado de
autorizacion.

`AppError` hereda de `ValueError` a proposito: los callers que ya hacen
`except ValueError` siguen funcionando sin cambios.

Vive en `application/` porque la usan los casos de uso y los adapters que
traducen hacia ellos (adapters -> application es hacia adentro, ADR-003).
Los errores de INVARIANTE de dominio siguen siendo `DomainError`
(`domain/errors.py`): esto es otra cosa, son fallos de operacion.
"""
from __future__ import annotations


class AppError(ValueError):
    """Fallo de operacion con un codigo estable del contrato.

    `code` es vocabulario cerrado (ver `adapters/api/errors._CODE_HTTP`);
    `message` es el texto accionable para el ingeniero de campo y NUNCA
    debe contener excepciones de librerias ni datos crudos del usuario.
    """

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
