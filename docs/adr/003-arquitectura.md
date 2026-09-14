# ADR-003 — Arquitectura: monolito modular con capas por dependencia

- **Estado:** Aceptado
- **Fecha:** 2026-09-14

## Contexto

App CRUD+ML de tamaño pequeño (1 dev + agente). Regla del AGENTS.md: carpetas
no son arquitectura; separación solo por dominio/responsabilidad/dependencia;
DDD pragmático sin aggregates/events/CQRS.

## Opciones consideradas

1. **Monolito modular: `domain/` → `application/` → `adapters/`, con
   `ml/` como módulo de análisis separado** ✅
2. Clean Architecture estricta con ports/adapters para todo (interfaces
   abstractas por repositorio, use cases inyectados)
3. Microservicios (API + servicio ML)

## Decisión

Monolito modular con UNA regla de dependencia (flechas hacia adentro):

```
backend/
├── domain/            # entidades, invariantes, errores de dominio. CERO imports de infra
│   ├── entities.py    # Project, Tree, Observation (+ StatusSemantic)
│   └── rules.py       # invariantes (muerto no revive, contracción ≤1cm, ...)
├── application/       # casos de uso UC1-UC7: orquestan dominio, sin HTTP ni SQL
│   └── use_cases/     # upload_campaign, assess_mortality, detect_stagnant, ...
├── ml/                # análisis: features + train + inferencia (comparten
│   │                  # preprocessing.py ÚNICO — regla anti-v1)
│   ├── features.py
│   ├── preprocessing.py
│   ├── train.py
│   └── inference.py
├── adapters/          # TODO lo que toca el mundo exterior
│   ├── api/           # FastAPI: parse → use case → response. CERO lógica de negocio
│   ├── db/            # SQLAlchemy models + repos + Alembic migrations
│   └── storage/       # archivo crudo subido (adjunto versionado)
└── tests/
```

Motivo contra la opción 2 (Clean estricta): el sistema tiene 2 persistence
needs (DB y files) y 1 delivery (HTTP). Interfaz abstracta por repositorio
para 1 sola implementación real es un seam hipotético — regla de la skill
codebase-design: "un adapter = seam hipotético; dos = seam real". Se usa
interfaz SOLO donde hoy hay variación real: almacenamiento de archivos
(local vs S3-compatible en free tier).

Motivo contra la opción 3 (microservicios): dataset pequeño; el pipeline ML
toma <5s. Un segundo servicio duplicaría deploy/observabilidad sin beneficio
medible. Si un día el análisis pesa, el módulo `ml/` ya tiene su seam.

Motivo de `ml/` fuera de domain: el modelo no es regla de negocio — es
análisis estadístico versionado que consume el dominio (Observation ya
validada). El riesgo de v1 fue mezclar las capas; aquí el ingester valida
invariantes ANTES de que ML vea los datos.

## Consecuencias

- Tests de dominio/application corren sin DB ni HTTP (puros).
- El contrato de API nace en `adapters/api/schemas.py` (OpenAPI) y de ahí
  se generan los tipos del frontend.
- Módulo `ml/` no puede importar `adapters/` — solo `domain/` (features
  sobre Observations válidas).
