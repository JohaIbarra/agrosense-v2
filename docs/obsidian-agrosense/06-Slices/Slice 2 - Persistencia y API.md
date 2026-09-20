---
aliases: [Slice 2, Persistencia, API, FastAPI]
tags: [slice, completado]
status: completado
fecha: 2026-09-20
---

# Slice 2 — Persistencia y API

> [!abstract] Repositories + FastAPI routes + tests locales
> **Estado**: fases 4-7 ✅ — slice cerrado
> **Tests**: 169 locales + 4 smoke

---

## Objetivo

Persistir datos en PostgreSQL vía SQLAlchemy y exponerlos por API REST con
FastAPI, sin tocar Supabase en los tests.

---

## Tasks del Slice

| Task | Estado | Descripción |
|---|---|---|
| Task 1: Contrato | ✅ | Schemas pydantic (8 schemas, 12 tests) |
| Task 2: Models | ✅ | SQLAlchemy 4 tablas + migración Alembic |
| Task 3: Repositories | ✅ | ProjectRepo + CampaignRepo |
| Task 4: Use Cases | ✅ | create_project + upload_campaign |
| Task 5: Routes | ✅ | FastAPI 6 endpoints |
| Task 6: Gate verify | ✅ | [[#Evidencia de verificación]] |
| Fase 7: Review | ✅ | 3 pasadas; la 3ª derribó la guarda de R4 y se rehízo |

---

## Lo que cambió tras las revisiones

> [!warning] El slice volvió al loop dos veces
> Cada pasada de review encontró defectos reales. Esto es el registro corto;
> el detalle vive en `docs/revision-slice2.md`.

### Antes del gate (hallazgos A/B/C)

| # | Problema | Arreglo |
|---|---|---|
| A | `application/` importaba `adapters/` | DTOs propios + puerto `CampaignSource` |
| B | `pytest` golpeaba Supabase y colgaba | SQLite local + marker `supabase` |
| C | pyproject traía psycopg2, ADR-002 dice psycopg3 | driver único + normalización de URL |

### Fase 7, primera pasada (R1-R5)

| # | Problema | Arreglo |
|---|---|---|
| R1 | 2º upload al mismo proyecto → **500** | Ingesta idempotente |
| R2 | El **nombre de archivo elegía el status HTTP** | `AppError` lleva el código aparte |
| R3 | Upload `async def` congelaba el worker ~80s | Pasó a `def` (threadpool) |
| R4 | Upload sin límite de tamaño ni tipo | Middleware ASGI + guardas de contenedor |
| R5 | Dependencias con CVE en la ruta de upload | `requirements.lock.txt` + `pip-audit` |

### Fase 7, segunda pasada (defectos en los arreglos)

| Problema | Arreglo |
|---|---|
| `.xlsx` de 4.8 KB → 11.8s y 370 MB (hoja enorme declarada) | Presupuesto de celdas leyendo `<dimension>` |
| Ratio de compresión calculado desde metadatos del atacante | Ratio contra los bytes reales |
| `NotImplementedError` de zipfile escapaba como 500 | `except` ancho en la guarda |
| El saneado de R2 borró los mensajes útiles | Textos accionables como `AppError` |

### Fase 7, tercera pasada

| Problema | Arreglo |
|---|---|
| La guarda de coste validaba el `<dimension>` **declarado**, que pandas ignora: bastaba borrarlo | Lector propio que cuenta celdas mientras las materializa |

---

## Semántica de la re-subida

> [!important] Decisión de producto del 2026-09-20
> Ver [[Modelo de Dominio#Re-subida de una campaña]]

| Caso | Resultado |
|---|---|
| Mismo archivo (mismo SHA-256) | `409 DUPLICATE_FILE`, no se crea campaña |
| Archivo distinto | Campaña **nueva**; la anterior no se toca |
| Valores de observación | Se corrigen: manda el más reciente |
| Atributos descriptivos del árbol | Se corrigen |
| Identidad (especie, parcela, coords) | **Rechaza la carga entera** → 422 |
| Filas que desaparecen | No se borran — deuda #I |

---

## Endpoints

| Método | Ruta | Status |
|---|---|---|
| POST | `/projects` | 201 · 409 · 422 |
| GET | `/projects/{id}` | 200 · 404 |
| POST | `/projects/{id}/campaigns` | 201 · 400 · 404 · 409 · 413 · 422 |
| GET | `/projects/{id}/campaigns` | 200 · 404 |
| GET | `/projects/{id}/trees` | 200 · 404 |
| GET | `/projects/{id}/trees/{id}/observations` | 200 · 404 |

---

## Error Mapping

Todos con la forma `{"detail": {"code", "message"}}`.

| Código | HTTP | Nace en |
|---|---|---|
| `DUPLICATE_NAME` | 409 | repositorio |
| `DUPLICATE_FILE` | 409 | repositorio |
| `DUPLICATE_TREE` | 409 | constraint de DB |
| `PROJECT_NOT_FOUND` | 404 | use case / route |
| `TREE_NOT_FOUND` | 404 | route |
| `INVALID_FILE` | 400 | adapter de Excel |
| `FILE_TOO_LARGE` | 413 | middleware |
| `SPECIES_MISMATCH` · `TREE_IDENTITY_MISMATCH` · … | 422 | dominio |
| `INTERNAL` | 500 | red de seguridad |

> [!danger] La lección de R2
> El código **nunca** se busca dentro del mensaje. Antes se hacía
> `if code in msg` sobre un texto que incluía el nombre de archivo del
> usuario, así que `PROJECT_NOT_FOUND.xlsx` devolvía 404.

---

## Testing Strategy

> [!important] `pytest` a secas nunca toca la red
> Hay un test de arquitectura que falla si alguien añade un test que abra
> la conexión real sin el marker `supabase`.

| Suite | Backend |
|---|---|
| `tests/domain/` · `tests/ingester/` | sin DB |
| `tests/application/` | fakes en memoria |
| `tests/api/` | SQLite en memoria |
| `tests/db/` | SQLite en memoria |
| `tests/architecture/` | AST de los imports |
| `tests/smoke/` | Supabase real (`-m supabase`) |

---

## Evidencia de verificación

```
ruff check src tests                → All checks passed
pytest                              → 169 passed, 4 deselected (25s)
pytest -m supabase                  → 4 passed (26s)
pip-audit -r requirements.lock.txt  → No known vulnerabilities (64 paquetes)
pip wheel .                         → agrosense-0.1.0-py3-none-any.whl
alembic check                       → No new upgrade operations detected
```

E2E contra Supabase real: ciclo de corrección completo, identidad divergente
rechazada con 422, hoja de 12M celdas → 400, cuerpo de 11 MB → 413 en 6 ms.

Detalle: `docs/verificacion-slice2.md`.

---

## Archivos Clave

| Archivo | Contenido |
|---|---|
| `adapters/api/app.py` | Factory + handlers + middleware |
| `adapters/api/middleware.py` | Techo de cuerpo antes del parseo |
| `adapters/api/errors.py` | Código → HTTP, sin adivinar |
| `adapters/api/routes/projects.py` | 6 endpoints |
| `adapters/db/repository.py` | Ingesta idempotente |
| `adapters/ingester/excel_source.py` | Guardas de contenedor y de hoja |
| `application/dtos.py` · `ports.py` · `errors.py` | Capa interna |
| `domain/rules.py` | `validate_tree_identity` |
| `tests/api/test_review_regressions.py` | Regresiones de la fase 7 |
| `requirements.lock.txt` | Cierre auditado |

---

## Commits

```
88347e5 chore(slice-2): gate de verificacion (task 6) + docs
3b93209 fix(arch): invierte la dependencia de application/
a3e11be feat(api): task 5 - rutas FastAPI del slice 2
```

Más el commit de cierre de la fase 7 con las correcciones R1-R5, el middleware
y el lockfile de dependencias.

---

## Deuda que deja este slice

Ver `docs/deuda-tecnica.md`. Lo que condiciona lo siguiente:

| # | Qué | Bloquea |
|---|---|---|
| G | Primer upload ~81s contra Supabase (presupuesto <5s) | **deploy** |
| D | El archivo crudo no se guarda | 1ª épica de ML |
| I | La re-subida no borra lo que ya no trae | UI / auth |
| R6 | Un `Engine` nuevo por request | deploy |

---

## Links

- [[Slice 1 - Fundación de Datos]] — Anterior
- [[Slice 3 - Riesgo de Mortalidad]] — Siguiente
- [[Modelo de Dominio]] · [[Base de Datos]] · [[Sistema]]
