# Briefing para Opus 4.6 — AgroSense v2

## Proyecto
Plataforma de análisis de restauración ecológica para ingenieros de campo:
subir datasets de monitoreo, detectar riesgo de mortalidad, estancamiento/anomalías,
analítica de crecimiento por especie/sitio.

## Stack
- Backend: FastAPI + Python 3.12
- DB: Supabase PostgreSQL (sa-east-1, session pooler)
- ORM: SQLAlchemy 2.0 + Alembic
- ML: scikit-learn + pandas
- Frontend: React TypeScript (futuro, no implementado aún)

## Arquitectura
Monolito modular (ADR-003):
```
domain/ → application/ → adapters/(api|db|ingester)
```
- `domain/`: entidades, reglas, invariantes (sin dependencias externas)
- `application/`: casos de uso
- `adapters/api/`: FastAPI routes + schemas
- `adapters/db/`: SQLAlchemy models + repositories
- `adapters/ingester/`: wide→long transform (pandas)

## Lo que ya está listo (commiteado en master)

### Slice 1 — Fundación de datos ✅
48 tests pasando, 4 commits:
- `domain/entities.py` — Observation, Tree, StatusSemantic (pydantic)
- `domain/errors.py` — DeathViolation, CensusGap, SuspiciousRevival
- `domain/rules.py` — validate_tree_observations, growth_between
- `adapters/ingester/column_mapping.py` — field name mapping (typos, truncados)
- `adapters/ingester/wide_to_long.py` — wide→long transform
- `adapters/ingester/ingest.py` — IngestResult orchestration
- `adapters/ingester/cli.py` — CLI demo

E2E verificado: 856 árboles, 3146 observaciones, 340 muertes, 19 warnings.

### Slice 2 — Persistencia + API (parcial)
- ✅ `adapters/api/schemas.py` — 11 contract tests (pydantic request/response)
- ✅ `adapters/db/models.py` — 4 tablas SQLAlchemy (projects, campaign_files, trees, observations)
- ✅ Migración aplicada a Supabase (Alembic, 2 revisions)
- ✅ `adapters/db/repository.py` — ProjectRepository + CampaignRepository (bulk insert)
- ✅ `adapters/db/session.py` — engine from DATABASE_URL
- ⚠️ 6 tests de repositorio: 5 pasan, 1 requiere revisión (dataset completo vs pooler lento)
- ⬜ `application/use_cases/create_project.py`
- ⬜ `application/use_cases/upload_campaign.py`
- ⬜ `adapters/api/routes.py` — FastAPI routes + lifespan + error mapping
- ⬜ Gate verification final

### Documentación
- `AGENTS.md` — reglas de ingeniería + workflow 10 fases
- `docs/01-discovery.md` — requisitos, ML spike (señal validada)
- `docs/02-domain.md` — entidades, invariantes, StatusSemantic
- `docs/03-architecture.md` — estructura + evolución DL
- `docs/adr/001-004` — stack, database, arquitectura, ingesta

## DB state
Limpia: 0 proyectos, 0 tablas con datos. Esquema listo (4 tablas + constraints).
La migración de Alembic ya está aplicada.

## El error que NO debes repetir
**NO testes contra Supabase remoto en cada corrida de pytest.** El session pooler
tiene ~200ms RTT. 4000 inserts individuales = 13+ min = timeouts = procesos muertos
= estado sucio. Eso nos costó 5 horas.

## Estrategia de testing (corregida)

| Nivel | Qué | Backend | Cuándo |
|---|---|---|---|
| Unit | dominio, ingester, repos con fakes | SQLite en memoria | cada commit |
| Integración | repos reales, cascades | SQLite en archivo | pre-merge |
| Smoke | 1 test E2E completo | Supabase real | solo a demanda, manual |

Configurar SQLite como backend de tests en `conftest.py` (el esquema SQLAlchemy
es idéntico, solo cambia el dialecto). Los 856+3146 inserts en SQLite tardan <2s.

## Dataset
`backend/data/raw/anexo1.xlsx` (sheet Monitoreo_4, 856 árboles, M1-M4, 42 columnas).
Referencia: `C:\Users\ASUS\Documents\Semillero_INNOVASIC\ruben\Anexo 1 Base de datos 4 MONITOREO.xlsx`

## Archivos clave para continuar

```
backend/
  pyproject.toml                    # deps: pandas, pydantic, fastapi, sqlalchemy, alembic
  .env                              # DATABASE_URL (Supabase, gitignored)
  src/agrosense/
    domain/
      entities.py                   # Observation, Tree, StatusSemantic
      errors.py                     # DomainError hierarchy
      rules.py                      # temporal invariants
    application/
      use_cases/                    # VACÍO — crear create_project.py, upload_campaign.py
    adapters/
      api/
        schemas.py                  # pydantic contract (request/response)
        routes.py                   # NO EXISTE — crear: FastAPI routes + lifespan
      db/
        models.py                   # SQLAlchemy 4 tablas
        session.py                  # engine from DATABASE_URL
        repository.py               # ProjectRepository + CampaignRepository
      ingester/
        column_mapping.py           # field name mapping
        wide_to_long.py             # wide→long transform
        ingest.py                   # IngestResult + ingest_wide
  tests/
    conftest.py                     # load_dotenv
    domain/                         # 21 tests (entities + rules)
    ingester/                       # 23 tests (mapping + ingest + E2E + CLI + seam)
    api/                            # 11 tests (contract schemas)
    db/                             # 12 tests (models + repository)
```

## Lo que falta (slice 2)

### 1. Use cases
```python
# application/use_cases/create_project.py
def create_project(repo, name, locality, description) -> ProjectRead

# application/use_cases/upload_campaign.py
def upload_campaign(project_id, file_bytes, filename, project_repo, campaign_repo) -> CampaignRead
  - lee Excel con pandas
  - ingesta wide→long
  - persiste via campaign_repo.save_ingest()
```

### 2. FastAPI routes
```python
# adapters/api/routes.py
POST /projects                  → ProjectRead
GET  /projects/{id}             → ProjectRead
POST /projects/{id}/campaigns   → CampaignRead
GET  /projects/{id}/campaigns   → list[CampaignRead]
GET  /projects/{id}/trees       → list[TreeRead]
GET  /projects/{id}/trees/{id}/observations → list[ObservationRead]
```
Incluir lifespan (create engine on startup), error mapping (DomainError → 400/404/409).

### 3. Gate verification
- ruff check backend/src backend/tests — 0 warnings
- pytest tests/ — todos pasando
- sin imports circulares
- sin dependencias faltantes

## Decisiones de arquitectura (ADRs)
- ADR-001: FastAPI + React TS (no Django, no Streamlit)
- ADR-002: Supabase (no Neon) — auth + storage resuelven 2 seams futuros
- ADR-003: Monolito modular (no microservicios)
- ADR-004: wide→long en ingesta (no directo a DB)

## Datos del entorno
- Windows, Python 3.12.1 global
- DNS intermitente con el pooler de Supabase (a veces falla resolución) — reintento
- working directory para opencode: `C:\Users\ASUS\Documents\Default Project`
- repo: `C:\Users\ASUS\Documents\agrosense-v2`
- v1 repo (referencia archivada): `https://github.com/JohaIbarra/agrosense-ai.git`
