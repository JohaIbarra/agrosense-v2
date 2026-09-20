# Verificación — Slice 2 (Persistencia + API), Task 6

Gate de la fase 6 del workflow de `AGENTS.md`. Evidencia ejecutada el
**2026-09-20**, commits `a3e11be` (Task 5) y `3b93209` (correcciones A/B/C).

Regla aplicada (skill `verification-before-completion`): ninguna afirmación
de este documento se escribió sin correr el comando que la respalda.

## Checklist del plan del slice 2

| # | Ítem del plan | Resultado |
|---|---|---|
| 1 | `ruff check src tests` → 0 errores | ✅ `All checks passed!` (exit 0) |
| 2 | `pytest` completo verde | ✅ 134 passed, 4 deselected (12s) |
| 2b | Integración contra la DB real | ✅ `pytest -m supabase` → 4 passed (19s) |
| 3 | `application/` no importa fastapi ni sqlalchemy | ✅ `tests/architecture` → 6 passed |
| 3b | `adapters/api` no importa pandas | ✅ sin ocurrencias |
| 4 | Demostración uvicorn + curl del flujo completo | ✅ 14/14 llamadas, abajo |
| 5 | README con cómo correr + commit final | ✅ este commit |

Extras del briefing de handoff:

| Ítem | Resultado |
|---|---|
| Sin imports circulares | ✅ 28 módulos del paquete importados sin fallo |
| Dependencias completas en `pyproject.toml` | ✅ el paquete construye e importa |
| Build | ✅ `agrosense-0.1.0-py3-none-any.whl` |

## Comandos y salida

```
$ python -m ruff check src tests
All checks passed!
exit=0

$ python -m pytest -q
134 passed, 4 deselected, 16 warnings in 12.08s

$ python -m pytest -m supabase -q
4 passed, 134 deselected in 18.50s

$ python -m pytest tests/architecture -q
6 passed in 0.06s

$ python -m pip wheel . --no-deps -w dist/
agrosense-0.1.0-py3-none-any.whl
```

## Demostración E2E (uvicorn + curl contra Supabase real)

```
$ python -m uvicorn "agrosense.adapters.api.app:create_app" --factory --port 8011
```

Las 14 llamadas del flujo, con el código HTTP observado:

| # | Llamada | Esperado | Obtenido | Tiempo |
|---|---|---|---|---|
| 1 | `POST /projects` | 201 | **201** | 3.27s |
| 2 | `POST /projects` (nombre repetido) | 409 | **409** `DUPLICATE_NAME` | 2.47s |
| 3 | `POST /projects` (nombre vacío) | 422 | **422** validación pydantic | 0.003s |
| 4 | `GET /projects/{id}` | 200 | **200** | 2.63s |
| 5 | `GET /projects/999999` | 404 | **404** `PROJECT_NOT_FOUND` | 2.49s |
| 6 | `POST .../campaigns` (archivo ilegible) | 400 | **400** `INVALID_FILE` | 2.53s |
| 7 | `POST /projects/999999/campaigns` | 404 | **404** `PROJECT_NOT_FOUND` | 2.50s |
| 8 | `POST .../campaigns` (anexo1.xlsx) | 201 | **201** | **79.70s** ⚠ |
| 9 | `POST .../campaigns` (mismo archivo) | 409 | **409** `DUPLICATE_FILE` | 3.08s |
| 10 | `GET .../campaigns` | 200 | **200** | 2.65s |
| 11 | `GET .../trees?limit=2` | 200 | **200** | 2.65s |
| 12 | `GET .../trees/{id}/observations` | 200 | **200** | 2.62s |
| 13 | `GET .../trees/999999/observations` | 404 | **404** `TREE_NOT_FOUND` | 2.56s |
| 14 | `GET /projects/{id}` (campaigns_count) | 200 | **200**, `campaigns_count: 1` | 2.61s |

Respuesta del upload (UC2) con el dataset de referencia:

```json
{
  "valid": true,
  "campaign_id": 13,
  "trees": 856,
  "observations": 3146,
  "deaths": 340,
  "warnings": [
    {"type": "contraction", "tree_id": "FR_1_22",
     "message": "Arbol FR_1_22 'encoge' 0.040 m hasta campana 2 (...)"},
    {"type": "revival", "tree_id": "FR_1_24",
     "message": "Arbol FR_1_24 figura 'Muerto' en campana 2 y 'Vivo' en 3 (...)"},
    {"type": "census_gap", "tree_id": "FR_1_44",
     "message": "Arbol FR_1_44 con censo no contiguo: [1, 4] (...)"}
  ]
}
```

Coincide con el E2E del slice 1 (856 / 3146 / 340) y con la provenance
persistida (`mapping_version: 2026-09-anexo1`, sha256 del archivo crudo).

Traza de árbol (UC7), `GET /projects/49/trees/3434/observations`:

```json
[{"campaign": 1, "height_m": 0.28, "dap_status": "bajo_umbral_dap",
  "phytosanitary": "Bueno", "alive": true},
 {"campaign": 2, "height_m": 0.32, "dap_status": "bajo_umbral_dap",
  "phytosanitary": "Bueno", "alive": true}, ...]
```

`StatusSemantic` llega intacto hasta la respuesta HTTP: `bajo_umbral_dap` no
se imputó a 0 en ningún punto del recorrido.

**Limpieza:** el proyecto de demostración se borró al terminar; la DB quedó en
0 proyectos (verificado por conteo).

## Hallazgo del gate: el upload tarda 79.7s contra Supabase

`docs/03-architecture.md` fija la restricción operativa: *"Pipeline de análisis
síncrono acotado (<5s para ~1k árboles — validado en spike). Si crece: job
queue (requisito futuro, ADR nuevo)"*. El upload de 856 árboles tardó **79.7s**,
16x por encima del presupuesto.

La causa no es el parseo (el mismo ingest sobre SQLite corre en ~2s): son
~900 round-trips al session pooler de Supabase, porque
`bulk_save_objects(..., return_defaults=True)` necesita los ids de cada árbol
para enlazar sus observaciones.

No bloquea el cierre del slice 2 — el flujo es correcto y el dataset de
referencia es el caso grande — pero **sí bloquea el deploy** (fase 9): un
request síncrono de 80s excede el timeout de proxy de la mayoría de free tiers.
Registrado como **#G** en `docs/deuda-tecnica.md` con dos salidas posibles
(insertar árboles con una sola sentencia y resolver los ids por `tree_id`, o
mover la ingesta a job asíncrono vía ADR-005).

## Hallazgo menor: mensajes de error sin contexto

`DUPLICATE_NAME`, `DUPLICATE_FILE` y `PROJECT_NOT_FOUND` viajan al cliente con
`message` igual al código:

```json
{"detail": {"code": "DUPLICATE_NAME", "message": "DUPLICATE_NAME"}}
```

`AGENTS.md` pide errores accionables para un ingeniero de campo. Los errores
que nacen en las routes sí lo cumplen (`"Proyecto 999999 no existe"`); los que
nacen como `ValueError(codigo)` en repos y use cases, no. Registrado como **#H**.
