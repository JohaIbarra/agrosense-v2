# Slice 2 — Persistencia + API (UC1/UC2): Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** UC1 (crear proyecto) y UC2 (cargar campaña .xlsx con validación de dominio y errores accionables) de punta a punta: PostgreSQL + FastAPI + Alembic.

**Architecture:** ADR-002 (PostgreSQL Neon) + ADR-003 (adapters/db con SQLAlchemy models + repos; adapters/api FastAPI sin lógica de negocio; application/ orquesta UCs). El ingester del slice 1 es la pieza que la API invoca.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, psycopg3, pytest (con testcontainers NO — Neon branch o SQLite para tests unitarios de repos se evalúa por task).

**Spec:** `docs/02-domain.md` (UC1, UC2, §5 errores), `docs/adr/002-database.md`, `docs/adr/003-arquitectura.md`, contrato del slice (arriba en la conversación + Task 1 lo formaliza).

## Global Constraints

- PostgreSQL Neon desde ya (decisión del usuario 2026-09-14): `DATABASE_URL` SOLO en `backend/.env` (gitignored).
- API sin lógica de negocio (ADR-003): routes parsean → llaman application/ → mapean respuesta.
- Errores de dominio → HTTP 422 con `{code, message, tree_id?, campaign?}` — nunca stack traces.
- Warnings de ingesta NO bloquean: van en la respuesta 201 del upload.
- `agrosense/adapters/db` es el único módulo que toca SQLAlchemy. `application/` recibe repos como dependencia (inyección simple por parámetro, sin framework DI).
- Migración Alembic para TODO cambio de schema (regla AGENTS.md).
- Cada campaign upload guarda: hash SHA256 del archivo crudo + mapping_version + timestamp (provenance, regla AGENTS.md).

---

## File Structure

```
backend/
├── .env                                # DATABASE_URL (gitignored)
├── alembic/                            # migrations env
│   ├── env.py
│   └── versions/
├── src/agrosense/
│   ├── application/
│   │   ├── use_cases/
│   │   │   ├── create_project.py       # UC1
│   │   │   └── upload_campaign.py       # UC2: archivo → ingester → repo → resumen
│   │   └── dtos.py                     # ProjectSummary, CampaignResult, etc.
│   └── adapters/
│       ├── api/
│       │   ├── app.py                  # FastAPI factory + lifespan
│       │   ├── routes/projects.py      # endpoints del contrato
│       │   ├── schemas.py              # pydantic request/response (OpenAPI = contrato)
│       │   └── errors.py               # DomainError → HTTP response mapping
│       └── db/
│           ├── models.py               # SQLAlchemy: Project, CampaignFile, Tree, Observation
│           ├── session.py              # engine/sessionmaker desde DATABASE_URL
│           └── repository.py           # ProjectRepo, CampaignRepo (interface implícita)
└── tests/
    ├── application/test_upload_campaign.py   # UC2 orquestación (ingester+repo fake)
    ├── api/test_projects_api.py               # integration: TestClient + DB real Neon
    └── db/test_repository.py                  # repos contra Neon (o sqlite si se decide)
```

---

### Task 1: Contrato formal (OpenAPI schemas) — TDD del contrato

**Files:**
- Create: `backend/src/agrosense/adapters/api/schemas.py`
- Test: `backend/tests/api/test_contract.py`

**Interfaces:**
- Produces: `ProjectCreate(name: str, locality: str | None, description: str | None)`, `ProjectResponse(id: int, name, locality, description, created_at, campaigns_count)`, `UploadResultResponse(valid: bool, trees: int, observations: int, deaths: int, warnings: list[WarningItem], errors: list[ErrorItem])`, `WarningItem(type, tree_id, message)`, `ErrorItem(code, message, tree_id | None, campaign | None)`.

- [ ] **Step 1: Test fallando** — validaciones del contrato: name requerido (≤200 chars), response shapes, error codes documentados.

```python
# tests/api/test_contract.py
from agrosense.adapters.api.schemas import (
    ErrorItem, ProjectCreate, ProjectResponse, UploadResultResponse, WarningItem,
)

def test_project_create_valid():
    p = ProjectCreate(name="Restauración Guayabal", locality="Guayabal", description="pilot")
    assert p.name == "Restauración Guayabal"

def test_project_create_name_required():
    import pytest
    with pytest.raises(Exception):
        ProjectCreate(name="")

def test_project_create_name_max_200():
    with pytest.raises(Exception):
        ProjectCreate(name="x" * 201)

def test_upload_result_shape():
    r = UploadResultResponse(
        valid=True, trees=856, observations=3146, deaths=340,
        warnings=[WarningItem(type="contraction", tree_id="T1", message="encoge 0.04m")],
        errors=[],
    )
    assert r.valid is True

def test_error_item_has_code_and_message():
    e = ErrorItem(code="DEATH_VIOLATION", message="...", tree_id="T1", campaign=3)
    assert e.code == "DEATH_VIOLATION"
```

- [ ] **Step 2: verificar FAIL → Step 3: implementar schemas.py → Step 4: PASS → Step 5: commit** `feat(api): contrato OpenAPI del slice 2`

### Task 2: Models + migración Alembic inicial

**Files:**
- Create: `src/agrosense/adapters/db/models.py`, `src/agrosense/adapters/db/session.py`
- Create: `alembic/` (init + versión inicial)

**Interfaces:**
- `models.Project(id, name UNIQUE, locality, description, created_at)`
- `models.CampaignFile(id, project_id FK, filename, sha256 UNIQUE por proyecto, mapping_version, ingested_at, stats JSON {trees, observations, deaths})`
- `models.TreeRow(id, project_id FK, tree_id, species, family, common_name, guild, plot_id, locality, coord_x, coord_y, elevation_m)` — UNIQUE(project_id, tree_id)
- `models.ObservationRow(id, tree_row_id FK, campaign, height_m, crown_diameter_m, dap_cm, dap_status, phytosanitary, alive, colonization)` — UNIQUE(tree_row_id, campaign)
- `session.get_engine()` lee `DATABASE_URL` de env.

- [ ] Pasos TDD: test de que los models mapean columnas esperadas (inspección de `__table__`) → `alembic init` → `alembic revision --autogenerate -m "init: projects, campaigns, trees, observations"` → `alembic upgrade head` contra Neon → commit.

### Task 3: Repositories (persistencia de IngestResult)

**Files:**
- Create: `src/agrosense/adapters/db/repository.py`
- Test: `tests/db/test_repository.py` (contra Neon real, con cleanup)

**Interfaces:**
- `ProjectRepository.create(ProjectCreate) -> ProjectResponse` (name duplicado → `ValueError("DUPLICATE_NAME")`)
- `ProjectRepository.list_all() -> list[ProjectResponse]`
- `CampaignRepository.save_ingest(project_id, IngestResult, filename, sha256) -> CampaignFile.stats` — transaccional: si algo falla, rollback completo (sin persistencia parcial, regla ADR-004)
- `TreeRepository.get_trees(project_id, limit, offset)`

- [ ] TDD: crear proyecto → recuperar; ingest real del anexo1 en proyecto demo → 856 trees, 3146 observations; duplicado de campaign sha256 → error claro. Commit.

### Task 4: Use cases UC1 + UC2 (application/)

**Files:**
- Create: `src/agrosense/application/use_cases/create_project.py`, `upload_campaign.py`, `dtos.py`
- Test: `tests/application/test_upload_campaign.py` (repo FAKE in-memory — no DB)

**Interfaces:**
- `CreateProjectUseCase(repo) -> ProjectResponse`
- `UploadCampaignUseCase(campaign_repo, project_repo)` — `execute(project_id, filename, content: bytes) -> UploadResultDTO`: leer xlsx (pandas) → `ingest_wide` → repo.save_ingest → DTO. DomainError sube al caller (API lo mapea). Warnings → DTO.warnings.

- [ ] TDD con fake repo: upload del anexo1 real → DTO con 856/3146/340/19 warnings; proyecto inexistente → ValueError("PROJECT_NOT_FOUND"). Commit.

### Task 5: API routes + error mapping + lifespan

**Files:**
- Create: `src/agrosense/adapters/api/app.py`, `routes/projects.py`, `errors.py`
- Test: `tests/api/test_projects_api.py` (TestClient + Neon real)

**Interfaces:** contrato completo del slice (POST/GET projects, POST campaigns upload, GET trees) con: `400` archivo ilegible, `404` proyecto, `422` DomainError con `{code, message, tree_id, campaign}`. Lifespan crea tablas vía Alembic check (no `create_all` en producción — documentado).

- [ ] TDD: flujo completo via API: crear proyecto → subir anexo1.xlsx real → 201 con stats → GET trees paginado → 404/422 cases. Commit.

### Task 6: Gate de verificación del slice 2

- [ ] `ruff check src tests` → 0 errores
- [ ] `pytest` completo verde (incl. integration contra Neon)
- [ ] Verificación de dependencias: application/ no importa fastapi ni sqlalchemy; adapters/api no importa pandas
- [ ] Demostración: uvicorn + curl del flujo completo, evidencia en consola
- [ ] Commit final + update del README del repo con cómo correr

## Self-Review

- Cobertura: UC1 (Task 1,4,5), UC2 (Tasks 3,4,5), errores accionables 422 (Task 5), provenance sha256 (Task 3), sin persistencia parcial (Task 3 transaccional), migraciones (Task 2). Auth fuera de alcance MVP (discovery §7). Trees paginado GET (Task 5) cubre inicio de UC7.
- Tipos: `IngestResult` del slice 1 se consume directo en Task 3/4; `UploadResultDTO` alimenta `UploadResultResponse` del Task 1 — nombres consistentes.
- DB real desde ya (decisión usuario): los tests de integración requieren `.env` con DATABASE_URL de Neon; se documentan y fallan con mensaje claro si falta.
