# Architecture — AgroSense AI v2

Estado: COMPLETADO (2026-09-14) · Decisiones en `docs/adr/001-004`.

## Resumen de decisiones

| ADR | Decisión |
|---|---|
| 001 | FastAPI + React **TypeScript** (stack de v1, tipos como contrato) |
| 002 | PostgreSQL managed free tier (Neon/Supabase) + Alembic |
| 003 | Monolito modular: domain → application → ml / adapters (una regla de dependencia) |
| 004 | Upload en formato ancho de campo → ingester único → long canónico + invariantes |

## Visión de dependencias (la única regla que importa)

```
        ┌────────────┐
        │  domain/   │  entidades + invariantes. No importa NADA de fuera
        └─────┬──────┘
              ▲
        ┌─────┴──────┐
        │application/│  casos de uso UC1-UC7. Importa solo domain
        └─────┬──────┘
              ▲                    ▲
   ┌──────────┴────┐        ┌──────┴────────┐
   │     ml/      │        │   adapters/   │  api (FastAPI) · db (SQLAlchemy,
   │ train+infer  │        │               │  Alembic) · storage · ingester
   │ preprocessing│        │  traducen mundo exterior ← → dominio
   │   ÚNICO     │        └───────────────┘
   └─────────────┘
```

## Estructura del repo (nace con el primer slice, no antes)

```
agrosense-v2/
├── AGENTS.md · README.md · docs/ (esto)
├── backend/
│   ├── domain/ application/ ml/ adapters/ tests/
│   ├── pyproject.toml (deps pineadas)
│   └── alembic/
├── frontend/
│   ├── src/api/ (tipos generados de OpenAPI — data access layer)
│   ├── src/pages/ src/components/
│   └── package.json
└── .github/workflows/ (fase 8)
```

## Frontend

- React + TS + Vite. Comunicación SOLO vía `src/api/` con tipos generados
  del OpenAPI de FastAPI (`openapi-typescript`). El frontend nunca inventa
  estructura (regla AGENTS.md).
- Pages por caso de uso: Proyectos → Campaña (upload+errores) → Análisis
  (riesgo, estancados, analítica) → Traza de árbol.

## Restricciones operativas (free tier)

- Pipeline de análisis síncrono acotado (<5s para ~1k árboles — validado
  en spike). Si crece: job queue (requisito futuro, ADR nuevo).
- Archivos crudos: storage local del servicio → S3-compatible si el
  proveedor lo exige (seam: interfaces de storage).
