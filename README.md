# AgroSense AI v2

Plataforma de análisis de restauración ecológica para ingenieros de campo:
riesgo de mortalidad por árbol, detección de estancados/anómalos y analítica
de crecimiento por especie y sitio.

> Predecesor histórico: [agrosense-ai (v1)](https://github.com/JohaIbarra/agrosense-ai) —
> archivado como referencia. Sus lecciones (leakage ML, preprocessing duplicado)
> están documentadas en `AGENTS.md`.

## Estado

Fases 1-3 (discovery + spike ML, dominio, arquitectura) completadas. El
desarrollo sigue el loop por slices verticales definido en `AGENTS.md`.

| Slice | Alcance | Estado |
|---|---|---|
| 1 — Fundación de datos | ingesta ancho→long + invariantes de dominio | ✅ cerrado |
| 2 — Persistencia + API | UC1 (crear proyecto), UC2 (cargar campaña), lecturas | ✅ verificado ([evidencia](docs/verificacion-slice2.md)) |
| 3 — Riesgo de mortalidad | modelo + eval gate | ⬜ pendiente |
| 4 — Estancados/anómalos | IsolationForest + regla de negocio | ⬜ pendiente |
| 5 — Analítica por especie/sitio | dashboards | ⬜ pendiente |

Frontend (React TS): aún no empezado. Deuda conocida en
[`docs/deuda-tecnica.md`](docs/deuda-tecnica.md) — léelo antes de desplegar.

## Cómo correr

Requiere Python 3.12.

```bash
cd backend
pip install -e ".[dev]"
```

Crea `backend/.env` con la URL de PostgreSQL (nunca se commitea):

```
DATABASE_URL=postgresql://usuario:password@host:5432/postgres
```

El sufijo del driver no hace falta: `adapters/db/session.py` normaliza la URL
a `postgresql+psycopg://` (ADR-002, un solo driver).

### Migraciones

El esquema **solo** cambia por migración; la app nunca hace `create_all`.

```bash
cd backend
alembic upgrade head      # aplicar
alembic current           # revisión aplicada
```

### API

```bash
cd backend
uvicorn "agrosense.adapters.api.app:create_app" --factory --reload --port 8000
```

- Documentación interactiva: http://127.0.0.1:8000/docs
- Contrato OpenAPI (fuente de los tipos del frontend): http://127.0.0.1:8000/openapi.json

Flujo mínimo:

```bash
# crear proyecto
curl -X POST http://127.0.0.1:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"Restauración Guayabal","locality":"Guayabal"}'

# subir una campaña (formato ancho de campo, hoja Monitoreo_4)
curl -X POST http://127.0.0.1:8000/projects/1/campaigns \
  -F "file=@data/raw/anexo1.xlsx"

# leer lo ingerido
curl http://127.0.0.1:8000/projects/1/campaigns
curl "http://127.0.0.1:8000/projects/1/trees?limit=10"
curl http://127.0.0.1:8000/projects/1/trees/1/observations
```

> El upload del dataset de referencia tarda ~80s contra una DB remota. Es
> deuda conocida (#G) y **bloquea el deploy**, no el desarrollo local.

### CLI del ingester (sin DB)

```bash
cd backend
python -m agrosense.adapters.ingester.cli data/raw/anexo1.xlsx
```

### Tests

```bash
cd backend
pytest                    # 134 tests locales, sin red (SQLite en memoria)
pytest -m supabase        # 4 smoke contra la DB real, requiere DATABASE_URL
ruff check src tests
```

`pytest` a secas **nunca** toca la red: los repositorios se prueban contra
SQLite y un test de arquitectura falla si alguien agrega un test que abra la
conexión real sin el marker `supabase`.

## Estructura

```
backend/src/agrosense/
├── domain/        entidades, invariantes, errores. Cero imports de infra
├── application/   casos de uso, DTOs y puertos. Importa solo domain
└── adapters/      api (FastAPI) · db (SQLAlchemy + Alembic) · ingester (pandas)
```

Una sola regla de dependencia, hacia adentro (ADR-003). No es una convención
de carpetas: `backend/tests/architecture/` la verifica en cada corrida.

## Documentación

- `AGENTS.md` — reglas de ingeniería y workflow (leer primero)
- `docs/01-discovery.md` — requisitos, usuarios, spike ML (Go)
- `docs/02-domain.md` — entidades, invariantes, casos de uso
- `docs/03-architecture.md` — estructura y evolución prevista
- `docs/adr/` — decisiones arquitectónicas
- `docs/deuda-tecnica.md` — brechas conocidas, con dueño y gate
- `docs/verificacion-slice2.md` — evidencia del gate del slice 2
