# Briefing para Claude Code — AgroSense v2

Estado a **2026-09-20**, tras el cierre del gate del slice 2 (Task 6).
Este documento describe el estado real y commiteado; si algo aquí no coincide
con el repo, gana el repo.

## Proyecto
Plataforma de análisis de restauración ecológica para ingenieros de campo:
subir datasets de monitoreo, detectar riesgo de mortalidad, estancamiento/anomalías,
analítica de crecimiento por especie/sitio.

## Stack
- Backend: FastAPI + Python 3.12
- DB: Supabase PostgreSQL (sa-east-1, session pooler), driver psycopg3
- ORM: SQLAlchemy 2.0 + Alembic
- ML: scikit-learn + pandas (aún sin implementar)
- Frontend: React TypeScript (futuro, no implementado)

## Arquitectura
Monolito modular (ADR-003), una sola regla de dependencia hacia adentro:
```
domain/ ← application/ ← adapters/(api|db|ingester)
```
- `domain/`: entidades, reglas, invariantes (sin dependencias externas)
- `application/`: casos de uso + DTOs + puertos. Importa **solo** domain
- `adapters/api/`: FastAPI routes + schemas (contrato OpenAPI)
- `adapters/db/`: SQLAlchemy models + repositories + Alembic
- `adapters/ingester/`: wide→long (pandas), implementa el puerto `CampaignSource`

La regla no es una convención: `tests/architecture/` la verifica en cada corrida.

## Lo que está commiteado en master

### Slice 1 — Fundación de datos ✅
- `domain/entities.py` — Observation, Tree, StatusSemantic (pydantic)
- `domain/errors.py` — errores duros + 3 warnings de ingesta
- `domain/rules.py` — validate_tree_observations, growth_between
- `adapters/ingester/` — column_mapping, wide_to_long, ingest, cli

### Slice 2 — Persistencia + API ✅ (gate cerrado, Task 6)
- `adapters/api/schemas.py` — contrato OpenAPI del slice
- `adapters/api/app.py` — factory + handler DomainError→422
- `adapters/api/deps.py` — inyección de sesión
- `adapters/api/errors.py` — ValueError→HTTP, sin stack traces
- `adapters/api/routes/projects.py` — 6 endpoints
- `adapters/db/models.py` — 4 tablas + migración aplicada en Supabase
- `adapters/db/repository.py` — ProjectRepo + CampaignRepo (transaccional)
- `adapters/db/session.py` — engine + normalización del driver
- `application/dtos.py`, `application/ports.py` — DTOs y puerto CampaignSource
- `application/use_cases/` — UC1 (create_project), UC2 (upload_campaign)

Commits relevantes:
- `a3e11be` feat(api): task 5 — rutas FastAPI del slice 2
- `3b93209` fix(arch): invierte la dependencia de application/, saca los tests
  de Supabase y unifica el driver

## Verificación (evidencia en `docs/verificacion-slice2.md`)

```
ruff check src tests    → All checks passed
pytest                  → 134 passed, 4 deselected (~12s, sin red)
pytest -m supabase      → 4 passed (~19s, Supabase real)
alembic current         → a8888efd3ae8 (head)
build                   → agrosense-0.1.0-py3-none-any.whl
E2E uvicorn + curl      → 14/14 llamadas con el código HTTP esperado
```

## Estrategia de testing

| Nivel | Backend | Cuándo |
|---|---|---|
| Unit (domain, ingester) | sin DB | siempre |
| Use cases | fake repos + fake source en memoria | siempre |
| API routes | SQLite en memoria (dependency_overrides) | siempre |
| Repositories | SQLite en memoria (FKs activas) | siempre |
| Arquitectura | AST de los imports | siempre |
| Smoke | Supabase real | `pytest -m supabase` |

**`pytest` a secas no toca la red.** Esto es un invariante con guard:
`tests/architecture/test_no_remote_db_by_default.py` falla si un test llama
`get_engine`/`get_session_factory` sin el marker `supabase`. Fue el error que
costó 5 horas; ahora no puede repetirse en silencio.

## Deuda abierta — leer antes de continuar

`docs/deuda-tecnica.md` tiene el detalle, con dueño y gate. Lo que condiciona
los próximos slices:

| # | Qué | Bloquea |
|---|---|---|
| G | El upload tarda 79.7s contra Supabase (presupuesto: <5s) | **el deploy**, fase 9 |
| D | El archivo crudo de la campaña no se guarda (ADR-004 §5) | la primera épica de ML |
| E | Falta type checking, build y escaneo de dependencias en los gates | fase 8 (CI/CD) |
| F1 | `deaths` cuenta observaciones, no árboles distintos | épica 2 (mortalidad) |
| H | Varios errores llevan el código como mensaje | UX de campo |

## Qué sigue

Slice 3 — riesgo de mortalidad. Antes de implementar, descomponerlo en slices
verticales pequeños (labeling temporal → baseline → evaluación → versionado →
inferencia → API → UI), como exige `AGENTS.md`.

Tiene **ML eval gate** obligatorio (fase 4): evaluación honesta, cero leakage,
métricas documentadas, artefacto versionado y preprocessing compartido
train/serve. La regla de splits de `AGENTS.md` (sección ML) es la corregida:
el mismo árbol puede estar en train y test en tiempos distintos; la misma
observación (árbol + tiempo) nunca. Para grouped CV se agrupa por parcela.

Señal validada en discovery §6: estancados (≤5cm) tienen ~35x más riesgo de
muerte; mortalidad acumulada 16% (138/856).

## ML — Protocolo de estancamiento (ya validado externamente)
- Variable de crecimiento: **altura** (no DAP — es censura por umbral)
- Etiqueta: `altura(t) == altura(t+1)`
- Modelo: regresión logística (PR-AUC 0.469, interpretable)
- Validación temporal: entrena M2→M3, prueba M3→M4

## Datos del entorno
- Windows, Python 3.12.1 global
- DNS intermitente con el pooler de Supabase — reintentar si falla
- Dataset: `backend/data/raw/anexo1.xlsx` (hoja Monitoreo_4, 856 árboles, M1-M4)
- repo: `C:\Users\ASUS\Documents\agrosense-v2`
- GitHub: `https://github.com/JohaIbarra/agrosense-v2`
- Skills del workflow: `C:\Users\ASUS\.agents\skills` (Claude Code lee
  `~/.claude/skills`, así que hoy no las carga solo — hay que leerlas a mano
  o enlazar el directorio)

## Estado de la DB
Limpia: 0 proyectos. Esquema aplicado (revisión `a8888efd3ae8`).

## Tags de checkpoint
- `checkpoint-antes-de-opus` — antes de empezar con Opus
