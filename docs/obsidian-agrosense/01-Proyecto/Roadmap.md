---
aliases: [Roadmap, Timeline, Fases]
tags: [proyecto, roadmap]
---

# Roadmap

> [!abstract] Fases y slices de AgroSense v2
> Workflow: 10 fases iterativas (Discovery → Domain → Architecture → Feature Loop)

---

## Fases 1-3: Una sola vez

| Fase | Estado | Descripción |
|---|---|---|
| 1. Discovery | ✅ | Requisitos, usuarios, restricciones + Spike ML |
| 2. Domain | ✅ | DDD ligero: entidades, reglas, casos de uso |
| 3. Architecture | ✅ | Boundaries, modules, dependencies |

---

## Fases 4-7: Loop por Slice

```
Contract → Implement → Verify → Review → Siguiente Slice
```

| Fase | Descripción |
|---|---|
| 4. Contract | API contract, migración DB, ML eval gate |
| 5. Implement | TDD: tests nacen con el código |
| 6. Verify | E2E, lint, types, build, EVIDENCIA |
| 7. Review | Code review + checklist + security scan |

---

## Slices Planificados

### Slice 1: Fundación de Datos ✅

> [[Slice 1 - Fundación de Datos]]

| Aspecto | Estado |
|---|---|
| Ingesta wide→long | ✅ |
| Validación dominio | ✅ |
| 48 tests | ✅ |
| Commits | 63f7d27..95e824f |

### Slice 2: Persistencia + API 🔄

> [[Slice 2 - Persistencia y API]]

| Aspecto | Estado |
|---|---|
| SQLAlchemy models + migración | ✅ |
| Repositories (ingesta idempotente) | ✅ |
| Use cases + DTOs + puerto | ✅ |
| FastAPI routes (6 endpoints) | ✅ |
| 166 tests locales + 4 smoke | ✅ |
| Fase 6 — Verify | ✅ |
| Fase 7 — Review | 🔄 3ª pasada |

> [!warning] Volvió al loop dos veces
> Las revisiones encontraron un 500 en el 2º upload, el nombre de archivo
> eligiendo el status HTTP, un `async def` que congelaba el worker y un
> `.xlsx` de 4.8 KB que costaba 370 MB. Todo corregido; ver la nota del slice.

### Slice 3: Riesgo de Mortalidad ⬜

> [[Slice 3 - Riesgo de Mortalidad]]

| Aspecto | Plan |
|---|---|
| Target | Muerte del árbol |
| Modelo | XGBoost / Random Forest |
| Señal | Estancados ≤5cm → 35x más riesgo |
| Split | GroupKFold por árbol |

### Slice 4: Detección de Estancados ⬜

> [[Slice 4 - Detección de Estancados]]

| Aspecto | Plan |
|---|---|
| Target | Anomalía (estancamiento extremo) |
| Modelo | IsolationForest + regla |
| Regla | Crecimiento ≈ 0 en N campañas |

### Slice 5: Analítica de Crecimiento ⬜

> [[Slice 5 - Analítica de Crecimiento]]

| Aspecto | Plan |
|---|---|
| Target | Tasa crecimiento por especie/sitio |
| Modelo | Regresión + clustering |
| Dashboard | Portado de v1 |

---

## Cronograma Estimado

```
Sep 2026:  Slice 1 ✅ + Slice 2 🔄 (cerrando fase 7)
           Slice 3 (Mortalidad) — descomponer en slices pequeños primero
Pendiente: Slice 4 (Estancados) + Slice 5 (Crecimiento)
           Frontend React + Integración
           Deploy — BLOQUEADO por deuda #G (upload de 81s) y #R6
```

> [!note] Antes del deploy
> `docs/deuda-tecnica.md` #G y #R6 lo bloquean: un request síncrono de 81s
> excede el timeout de proxy de la mayoría de free tiers.

---

## Links

- [[Slice 1 - Fundación de Datos]]
- [[Slice 2 - Persistencia y API]]
- [[Resumen ML]] — Modelos
