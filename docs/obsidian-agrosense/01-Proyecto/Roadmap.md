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

> [!important] Orden invertido el 2026-09-21: Estancados va ANTES que Mortalidad
> Los números conservan su nombre (Slice 3 = Mortalidad, Slice 4 = Estancados),
> pero el **orden de ejecución** se invierte. Tres razones:
>
> 1. **Evidencia disponible.** Estancamiento tiene 153 eventos positivos y un
>    protocolo cerrado con PR-AUC 0.47 bajo validación honesta. Mortalidad
>    tiene 33–37 eventos por ola: con ~8 predictores eso es un EPV de 4–11,
>    por debajo del mínimo habitual de 10–20. Un modelo de mortalidad hoy
>    sería un modelo de ruido.
> 2. **Dependencia de features.** `estancó_intervalo_previo` es el predictor
>    individual más fuerte que tenemos (OR 2.92 en estancamiento, OR 1.70
>    marginal en mortalidad) y lo **produce** el slice de estancados. El
>    Slice 4 alimenta al 3, no al revés.
> 3. **Riesgo de gate.** Construir mortalidad primero obliga a improvisar esa
>    feature y a pasarle el ML eval gate dos veces.

### Slice 4: Detección de Estancados ⬜ ← siguiente

> [[Slice 4 - Detección de Estancados]]

| Aspecto | Plan |
|---|---|
| Target | Altura no crece en el intervalo (t, t+1] |
| Modelo | Regresión logística + regla de negocio |
| Evidencia | 153 eventos positivos, PR-AUC 0.469 (IC 95% 0.36–0.58) |
| Split | Temporal M2→M3 / M3→M4 + GroupKFold por **parcela** |
| Produce | `estancó_intervalo_previo` — feature de entrada del Slice 3 |

### Slice 3: Riesgo de Mortalidad ⬜ ← después de Estancados

> [[Slice 3 - Riesgo de Mortalidad]]

| Aspecto | Plan |
|---|---|
| Target | Muerte del árbol |
| Modelo | XGBoost / Random Forest |
| Señal | Estancados ≤5cm → 35x más riesgo |
| Limitante | 33–37 eventos por ola (EPV 4–11): descomponer y acotar el alcance |
| Depende de | `estancó_intervalo_previo` ([[Slice 4 - Detección de Estancados]]) |
| Split | Temporal M2→M3 / M3→M4 + GroupKFold por **parcela** |

### Slice 5: Analítica de Crecimiento 🔄

> [[Slice 5 - Analítica de Crecimiento]]

| Aspecto | Estado |
|---|---|
| Migración + 3 tablas analíticas | ✅ |
| Loader idempotente (`scripts/load_analytics.py`) | ✅ |
| 6 endpoints `/api/v1/analytics` | ✅ |
| Dashboard React + Recharts | ✅ |
| 52 tests nuevos backend (230 total) + 28 frontend | ✅ |
| Fase 6 — Verify contra Supabase real | ✅ 25 smoke |
| Fase 7 — Review | ⬜ |

> [!note] No entrena nada
> La estadística está cerrada: los CSV de `backend/data/processed/` son la
> fuente de verdad y el slice los traduce a tablas, API y UI.

### E5: Referente científico + contraste ✅ (2026-09-27)

> Plan: `docs/superpowers/plans/2026-09-27-e5-referente-cientifico.md`.
> El Slice 5 pasa a ser el **Referente científico** (`docs/04-vision-producto.md` §4).
> Decisión de arquitectura: `docs/adr/007-separacion-proyecto-referente.md`.

| Aspecto | Estado |
|---|---|
| `reference_models` versionado (`is_active`, único activo forzado por índice parcial); publicar ya no borra la versión anterior (UC-R2) | ✅ |
| Tablas `reference_species_effects` / `reference_plot_effects` / `variance_components` por versión | ✅ |
| Contrato `/api/v1/analytics` → `/api/v1/reference` | ✅ |
| UC-AN3: `GET /projects/{id}/reference-contrast` + página «Contraste con el referente» | ✅ |
| Especies del proyecto normalizadas igual que las del referente (NBSP, NFC) | ✅ |
| Tests: 596 backend + 101 frontend | ✅ |

> [!warning] Operación tras aplicar la migración
> `alembic upgrade head` deja las tablas del referente vacías (lo único que
> se pierde es el referente, que es regenerable). Hay que re-publicarlo con
> `python scripts/load_analytics.py` antes de que UC-AN3 y el ranking del
> referente vuelvan a responder.

> [!info] Diferido, no resuelto en E5
> Discrepancia de `comparacion_estancamiento_mortalidad.csv` (0 vs 1 de 45
> parcelas significativas en mortalidad, doc 04 §14) — diferida.

### E9: IA con Ollama ✅ (2026-09-27)

> Plan: `docs/superpowers/plans/2026-09-27-e9-ia-ollama.md`.
> Decisión de arquitectura: `docs/adr/012-ia-local-con-ollama.md`.

| Aspecto | Estado |
|---|---|
| Tabla `ai_reports` (un borrador por monitoreo, `input_hash` atado al snapshot) | ✅ |
| Puerto `LLMClient` + adaptador `OllamaClient` (urllib, `qwen2.5:3b` por defecto) | ✅ |
| Guardia de números: marca cifras del texto que no estaban en el snapshot | ✅ |
| `GET/POST /projects/{id}/monitorings/{n}/ai-report` (404 `AI_REPORT_NOT_FOUND`, 503 `LLM_UNAVAILABLE`) | ✅ |
| Panel en la página de análisis + descarga `.md` (UC-IA3) + aviso de borrador desactualizado | ✅ |
| Tests: 652 backend + 110 frontend | ✅ |

> [!info] Limitaciones conocidas
> Sin cola de trabajos (ADR-010 pendiente): la generación es una llamada
> síncrona de hasta 180 s. La guardia no distingue unidades ni rangos de
> años («2025-2026»). Requiere Ollama corriendo en local.

Siguiente según `docs/04-vision-producto.md` §11: **E7 · Estancados** (primer modelo de ML).

---

## Cronograma Estimado

```
Sep 2026:  Slice 1 ✅ + Slice 2 🔄 (cerrando fase 7)
           Slice 5 (Analítica) — estadística ya resuelta, solo DB/API/UI
Siguiente: Slice 4 (Estancados) — protocolo cerrado, produce
             `estancó_intervalo_previo`
Después:   Slice 3 (Mortalidad) — descomponer en slices pequeños primero;
             consume la feature del Slice 4
           Deploy — BLOQUEADO por deuda #G (upload de 81s) y #R6
```

> [!note] Antes del deploy
> `docs/deuda-tecnica.md` #G y #R6 lo bloquean: un request síncrono de 81s
> excede el timeout de proxy de la mayoría de free tiers.

---

## Links

- [[Slice 1 - Fundación de Datos]]
- [[Slice 2 - Persistencia y API]]
- [[Slice 5 - Analítica de Crecimiento]]
- [[Slice 4 - Detección de Estancados]]
- [[Slice 3 - Riesgo de Mortalidad]]
- [[Resumen ML]] — Modelos
