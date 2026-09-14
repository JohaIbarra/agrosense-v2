# AgroSense Engineering Rules

Proyecto: AgroSense AI v2 — plataforma de análisis de restauración ecológica
(predicción de riesgo de mortalidad, detección de árboles estancados/anómalos,
analítica de crecimiento por especie y sitio).

Fuente de datos: `Anexo 1 Base de datos 4 MONITOREO.xlsx` (hoja `Monitoreo_4`,
856 árboles, M1-M4). Las demás hojas son tablas dinámicas resumen y NO son
fuente de datos: todo se recalcula desde `Monitoreo_4`.

## General

- Do not start implementation before understanding the requirement.
- Do not modify architecture accidentally while implementing a feature.
- Prefer simple designs over unnecessary abstractions.
- Every architectural decision must have a documented reason.
- Folder structure is NOT architecture by itself. Module separation must
  exist for a domain, responsibility or dependency reason — never to satisfy
  a visual pattern (layers/`utils/`/`services/` folders alone prove nothing).
- Architecture is evolutionary, not frozen: phases 1-3 produce the INITIAL
  architecture. A slice may reopen domain or architecture when it reveals an
  unforeseen requirement, but the change requires justification, an ADR, and
  an impact review on existing slices.

## Domain

- Business logic belongs to the domain/application layers.
- Domain code must not depend on FastAPI, React, PostgreSQL, SQLAlchemy,
  Prisma or other infrastructure details.
- Every significant business capability must be represented by a use case.
- Validate business invariants inside the domain/application layer.
- Use DDD pragmatically: no Aggregates, Domain Events, CQRS or Event
  Sourcing unless a demonstrable domain need exists. YAGNI > pattern fashion.

## Database

- Database schema must be derived from the domain model.
- Every schema change must use a migration.
- Never modify production schema manually.
- Define constraints and indexes intentionally.
- Do not use the database as a substitute for business logic.

## API

- API contracts are defined first and are the source of truth. A contract
  must specify: request, response, errors, validations, auth,
  pagination/filters/sorting where applicable.
- The frontend consumes the contract; it never invents its own structure.
- Use consistent request/response schemas.
- Never expose internal exceptions or stack traces.
- Validate all external input.
- API must not contain business logic.

## Frontend

- Components should have one clear responsibility.
- Business rules must not be duplicated in the frontend.
- API communication belongs in dedicated data-access layers.
- Avoid giant components and unnecessary state.

## ML

- Training and inference must share preprocessing logic.
- Never use information unavailable at prediction time.
- Never allow target leakage.
- Train/validation/test splits must respect temporal structure when applicable
  (and group structure: the same tree must never appear in both train and test).
- Every production model must have reproducible training and evaluation.
- Model artifacts must be versioned.
- Metrics must be documented.
- A model is only reproducible if it can be rebuilt from code + config +
  data version + pinned dependencies. Random seeds are controlled.
  Evaluation is repeatable via one documented command (no .pkl black boxes).

## Data provenance

- Every dataset, feature set, model, prediction and analysis must be
  traceable to its source data and transformation version. Record at least:
  source dataset version, ingestion script version, preprocessing version,
  feature definitions, model version, training/eval configuration, timestamp.

## Testing

- New behavior starts with a test.
- Bugs require a regression test.
- Domain rules must have unit tests.
- Critical API flows require integration tests.
- Critical user journeys require E2E tests.

## Security

- Secrets never enter source control.
- Authentication and authorization are explicit.
- User-controlled input is untrusted.
- File uploads are validated.
- External errors are sanitized.
- Dependencies must be checked for known vulnerabilities.

## Completion

A feature is NOT complete until:

1. Tests pass.
2. Lint passes.
3. Type checking passes.
4. Build passes.
5. Security checks pass.
6. Architecture remains consistent.
7. Changes are reviewed.
8. Verification evidence exists.

---

## Workflow — AgroSense V2

Estructura: fases 1-3 se ejecutan UNA vez (ejercicio de pensamiento, días no
semanas). Fases 4-7 son un LOOP que se repite por cada slice vertical de
feature. Fases 8-9 cierran el ciclo.

### Lecciones de v1 que este workflow debe prevenir

- v1 entrenó un modelo con leakage (`altura_actual` contiene al target) y con
  split aleatorio que puso el mismo árbol en train y test. Nadie validó la
  señal antes de construir. → Por eso el spike ML es obligatorio en Discovery.
- v1 duplicó el preprocesamiento (train vs serve) y ya divergieron. → Por eso
  preprocessing único compartido.
- v1 ejecutó todo el pipeline ML síncrono en un endpoint `async`. → Por eso
  contract-first por slice.

### Diagrama

```
     ╔══════════════════ FASES 1-3: UNA SOLA VEZ ══════════════════╗

           ┌─────────────────┐
           │ 1. DISCOVERY     │  requisitos, usuarios, restricciones
           │                  │  + SPIKE ML OBLIGATORIO:
           │                  │    calidad de datos y señal real
           │                  │    del modelo ANTES de construir
           └────────┬────────┘
                    ▼
           ┌─────────────────┐
           │ 2. DOMAIN       │  DDD LIGERO: entidades, reglas,
           │                  │  casos de uso. SIN aggregates,
           │                  │  domain events ni CQRS.
           └────────┬────────┘
                    ▼
           ┌─────────────────┐
           │ 3. ARCHITECTURE │  boundaries, modules, dependencies
           │                  │  Database | API | Frontend
           │                  │  (contratos definidos primero)
           └────────┬────────┘
                    │
     ╠═════════════╪════ LOOP POR SLICE VERTICAL (4-7) ══════════════╣
                    ▼
           ┌─────────────────┐
           │ 4. CONTRACT      │  API contract del slice,
           │                  │  migración DB si aplica,
           │                  │  ML EVAL GATE si hay modelo
           └────────┬────────┘
                    ▼
           ┌─────────────────┐
           │ 5. IMPLEMENT    │  TDD: los tests nacen CON el
           │                  │  código, feature by feature
           └────────┬────────┘
                    ▼
           ┌─────────────────┐
           │ 6. VERIFY        │  E2E de journeys críticos,
           │                  │  lint + types + build,
           │                  │  EVIDENCIA de verificación
           └────────┬────────┘
                    ▼
           ┌─────────────────┐
           │ 7. REVIEW        │  UN solo gate: code review +
           │                  │  checklist de arquitectura +
           │                  │  security scan
           └────────┬────────┘
                    │  slice verificado y revisado
                    ↺  siguiente slice (vuelve a 4)

     ╚════════════════ CIERRE DEL CICLO (8-9) ═══════════════════════╝
                    ▼
           ┌─────────────────┐
           │ 8. CI/CD        │  automatizar los gates del loop
           └────────┬────────┘
                    ▼
           ┌─────────────────┐
           │ 9. DEPLOY       │  + monitoreo y feedback
           └────────┬────────┘  (el feedback alimenta Discovery)
```

### Reglas del loop (fases 4-7)

- Un slice vertical = una feature completa de punta a punta (DB → API →
  frontend), demostrable por sí sola.
- Ningún slice sale del loop sin pasar los TRES gates: verify (6), review (7)
  y, si tiene modelo, el ML eval gate (4).
- ML eval gate (para slices con modelo): evaluación honesta (group split por
  árbol + split temporal donde aplique, cero leakage), métricas documentadas,
  artefacto versionado, y preprocessing compartido train/serve.
- Un bug encontrado → regresión test → vuelve a entrar al loop en 5.
- Si un slice revela un requisito de dominio o arquitectura no contemplado,
  el flujo es: justificar → ADR → actualizar documentación → revisar impacto
  en slices existentes → continuar el loop.

### Slices planificados de AgroSense v2 (orden propuesto)

Los elementos de esta lista son épicas/macro-features. Cada una debe
descomponerse en slices verticales pequeños (ej: mortalidad = labeling
temporal → baseline → evaluación → versionado → inferencia → API → UI)
antes de comenzar su implementación, usando writing-plans.

1. **Fundación de datos**: ingesta de `Monitoreo_4` → formato long limpio y
   reproducible (script versionado), validaciones de dominio (alturas no
   negativas, árboles muertos no reviven ni crecen).
2. **Riesgo de mortalidad**: predicción de muerte por árbol (señal validada:
   estancados ≤5cm tienen ~35x más riesgo; mortalidad 16% acumulada).
3. **Detección de estancados/anómalos**: IsolationForest + regla de negocio
   (crecimiento ≈ 0).
4. **Analítica de crecimiento por especie/sitio**: dashboards (lo que ya
   funciona de v1, portado).

## Skills to use per phase

| Fase | Skills |
|---|---|
| 1. Discovery (+ spike ML) | brainstorming, writing-plans, machine-learning |
| 2. Domain | domain-modeling |
| 3. Architecture | architecture-patterns, codebase-design, database-design, api-and-interface-design |
| 4. Contract | api-and-interface-design, database-design |
| 5. Implement | test-driven-development, executing-plans, machine-learning |
| 6. Verify | verification-before-completion |
| 7. Review | requesting-code-review, receiving-code-review, security-review, secure-code-review |
| 8. CI/CD | ci-cd-and-automation, ci-cd-security |
| 9. Deploy | finishing-a-development-branch, verification-before-completion |
