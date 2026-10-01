"""Servir el frontend compilado desde el mismo origen que la API (ADR-015).

Solo si `FRONTEND_DIST` apunta a un directorio existente (la imagen Docker);
en desarrollo y en los tests no se monta nada. Las rutas de la API se
registran antes y siempre ganan. Para lo que ninguna ruta atiende: un archivo
real de `dist/` se sirve tal cual, y una navegacion del navegador
(`Accept: text/html`) recibe `index.html` para que el router del SPA la
resuelva. Cualquier otra peticion sin ruta sigue siendo un 404 JSON: un
cliente de la API que se equivoca de URL no recibe HTML con 200.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI) -> None:
    raw = os.environ.get("FRONTEND_DIST", "").strip()
    dist = Path(raw).resolve() if raw else None
    if dist is None or not (dist / "index.html").is_file():
        return
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str, request: Request):
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        if "text/html" in request.headers.get("accept", ""):
            return FileResponse(dist / "index.html")
        return JSONResponse(
            {"detail": {"code": "NOT_FOUND", "message": "Recurso no encontrado."}},
            status_code=404,
        )
