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

## Evolución ML prevista (deep learning)

Escenario roadmap: modelos DL (p.ej. visión por computador con imágenes de
dron/satélite). Cubierto por diseño, sin cambios presentes:

- **Entrenamiento SIEMPRE offline** (local/Colab/GPU puntual): el cómputo
  va a los datos, no al revés. Solo inferencia vive en el monolito (CPU,
  ms para dataset pequeño).
- `ml/` es agnóstico al framework: sklearn hoy, PyTorch/ONNX mañana, la
  misma interfaz de inferencia y el mismo ML eval gate (group split por
  árbol, cero leakage, artefacto versionado, preprocessing compartido).
- Extracción de `ml/` como servicio independiente SOLO si la inferencia
  deja de ser acotada (lotes de imágenes): sería ADR-005, escrito cuando
  exista el requisito real, no antes.
- Con los datos tabulares actuales (856 árboles, 4 monitoreos), DL de
  series temporales no es viable (insuficientes puntos por árbol); el
  escenario DL realista es nueva modalidad de datos (imágenes).
