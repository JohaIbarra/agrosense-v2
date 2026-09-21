---
aliases: [Slice 5, Crecimiento, Analítica, Dashboards]
tags: [slice, en-progreso]
status: en-progreso
---

# Slice 5 — Analítica de Crecimiento

> [!abstract] Efectos por especie y parcela de los modelos mixtos
> **Estado**: 🔄 Fase 6 ✅ verificado contra Supabase real | Fase 7 pendiente
> **Estadística**: cerrada, no se re-estima

---

## Objetivo

Publicar en la plataforma los efectos por **especie** y por **parcela** que los
modelos mixtos (`lme4::glmer` binomial) estimaron sobre el dataset de
referencia, de forma que el ingeniero pueda responder dos preguntas distintas:

1. ¿Qué especies conviene plantar y cuáles vigilar? (estancamiento)
2. ¿Dónde hay que mejorar las condiciones? (mortalidad)

> [!important] Este slice NO entrena nada
> La estadística está resuelta y validada. Los CSV de
> `backend/data/processed/` son la **fuente de verdad**; el slice los traduce a
> tablas, API y dashboard. Si un número de la UI no cuadra con el informe, el
> que manda es el CSV.

---

## Los dos hallazgos que el slice debe transmitir

| | Estancamiento | Mortalidad |
|---|---|---|
| Observaciones árbol-intervalo | 1.335 | 1.405 |
| Eventos positivos | 310 (23%) | 70 (5%) |
| Varianza especie / parcela | 0.846 / 0.317 | 0.415 / 0.372 |
| **Razón especie/parcela** | **2.7×** | **1.1×** |
| ICC especie / parcela | 0.190 / 0.071 | 0.102 / 0.091 |
| Rango OR entre especies | 0.24 – 4.94 (**20×**) | 0.35 – 1.97 (5.6×) |
| Especies con IC significativo | 8 de 30 | 1 de 30 |
| Parcelas con IC significativo | 3 de 42 | 0 de 45 |

> [!tip] La lectura estratégica, que es el producto real del slice
> **Estancamiento es un problema de especie**: elegir bien qué plantar cambia
> el resultado por un factor de 20. **Mortalidad es un problema equitativo de
> especie y sitio**: se ataca mejorando condiciones, sobre todo fitosanidad
> (OR 4.64 como efecto fijo).
>
> Los dos forest plots se ven casi iguales. Sin la descomposición de varianza
> al lado, un lector concluye lo mismo de ambos — y se equivoca en uno.

**Se estancan más**: *Lafoensia speciosa* (4.94), *Delostoma integrifolium*
(4.71), *Persea caerulea* (3.82), *Delostoma roseum* (2.98), *Cedrela montana*
(2.29).
**Se estancan menos**: *Verbesina arborea* (0.24), *Heliocarpus popayanensis*
(0.35), *Senna viarum* (0.61).
**Única especie concluyente en mortalidad**: *Inga punctata* (OR 0.35,
protectora). Ninguna especie tiene riesgo de muerte **aumentado** significativo.

---

## Esquema (migración `b1c4a7f20e51`)

```
species_analytics   PK species_name   30 filas
plot_analytics      PK plot_code      45 filas
variance_components UQ (model, grouping)  4 filas
```

> [!note] Por qué no cuelgan de `projects`
> Los efectos se estimaron sobre el dataset completo del programa, no sobre un
> proyecto. Meterles hoy un `project_id` sería inventar una dimensión que el
> modelo estadístico no tiene. Cuando exista multi-proyecto real, eso pide un
> ADR — no una columna.

> [!warning] 45 parcelas, no 42
> El panel de mortalidad cubre 45 parcelas y el de estancamiento 42. Las 3
> extra entran con `effect_stall` en NULL, no se descartan ni se rellenan con
> cero. Por eso todos los merges del loader son OUTER.

---

## API

Todos de **solo lectura**. La carga la hace un script, no un endpoint.

| Endpoint | Devuelve |
|---|---|
| `GET /api/v1/analytics/species` | Ranking de 30 especies (`?gremio=`, `?sort=`) |
| `GET /api/v1/analytics/species/{name}` | Detalle de una especie |
| `GET /api/v1/analytics/species/top-risk-stall` | Top-5 de riesgo, **solo significativas** |
| `GET /api/v1/analytics/species/top-protective` | Protectoras (`?model=stall\|mortality`) |
| `GET /api/v1/analytics/plots` | Efectos por parcela (`?localidad=`) |
| `GET /api/v1/analytics/variance-decomposition` | ICCs + lectura estratégica |

> [!danger] La escala es el error fácil de este slice
> Los efectos se estiman en **log-odds** y se muestran en **odds ratio**.
> El contrato separa las dos escalas por nombre:
>
> - `odds_ratio` y `or_ci95` → **lo que se muestra**. `or_lo = exp(lo)`,
>   `or_hi = exp(hi)`.
> - `ci95_log_odds` → trazabilidad contra el CSV. **Nunca se renderiza.**
>
> *Lafoensia speciosa* tiene OR 4.94 e IC en log-odds [0.81, 2.38]. Publicar
> ese `[0.81, 2.38]` como intervalo del OR da una barra que no contiene a su
> propio punto. Hay tests que lo impiden en el backend y en el frontend.

`significant` es `true` cuando el IC 95% no cruza 0 en log-odds (equivale a no
cruzar 1 en OR). **`false` significa "no distinguible del promedio", no "sin
efecto"** — la interpretación textual la arma `application/`, no la UI, para
que la API y el dashboard no digan cosas distintas del mismo dato.

---

## Carga de datos

```bash
cd backend
alembic upgrade head
python scripts/load_analytics.py --dry-run   # valida sin escribir
python scripts/load_analytics.py             # borra y recarga, en 1 transacción
```

Idempotente: cada corrida reemplaza las tres tablas completas. No es un upsert
fila a fila a propósito — los efectos vienen de un ajuste conjunto sobre todo
el panel, así que mezclar filas de dos corridas daría un ranking que no
corresponde a ningún modelo.

> [!note] `Inga punctata` y el espacio duro
> En los tres CSV la especie llega como `'Inga punctata\xa0'` (NBSP heredado
> del Excel). Sin normalizar, se parte en dos claves, se queda sin gremio y su
> detalle devuelve 404 — justo la única especie concluyente en mortalidad.
> Lo resuelve `normalize_level()`, con test de regresión.

---

## UI (`/analytics`)

| Bloque | Qué resuelve |
|---|---|
| Panel comparativo | Que los dos rankings no se lean como si dijeran lo mismo |
| Forest plot estancamiento | Ranking con IC 95%, eje **logarítmico** |
| Forest plot mortalidad | Mismo formato, para que el contraste sea visible |
| Detalle de especie | Interpretación textual + ambas métricas |
| Filtro por gremio | Inicial / Intermedia / Tardía |

Decisiones de lectura:

- **Eje logarítmico**: el OR es multiplicativo. En eje lineal, "5× menos"
  (0.20) queda aplastado contra el cero y las protectoras desaparecen.
- **Color solo para lo concluyente**: lo que cruza 1 va en gris. Sin eso, un OR
  de 1.9 con IC [0.82, 4.44] se ve tan alarmante como uno de 4.94 con IC
  [2.25, 10.86].
- **Referencia en 1.0**, no en 0.

---

## Tasks

| Task | Estado | Descripción |
|---|---|---|
| Task 1 | ✅ | Migración `b1c4a7f20e51` (3 tablas + índices) |
| Task 2 | ✅ | `adapters/analytics/effects_loader.py` (lectura y normalización) |
| Task 3 | ✅ | `scripts/load_analytics.py` (carga idempotente) |
| Task 4 | ✅ | `application/use_cases/read_analytics.py` (interpretación) |
| Task 5 | ✅ | 6 endpoints + schemas Pydantic |
| Task 6 | ✅ | 52 tests nuevos backend (230 en total) + 28 frontend |
| Task 7 | ✅ | Dashboard React + Recharts |
| Task 8 | ✅ | Fase 6 — Verify contra Supabase real (25 smoke, [[#Fase 6]]) |
| Task 9 | ⬜ | Fase 7 — Review |
| Task 10 | ⬜ | Exponer `efectos_fijos*.csv` (completa el panel comparativo) |

---

## Fase 6 — verificado contra Supabase real (2026-09-21)

Migración aplicada (`b1c4a7f20e51`), datos cargados y 25 smoke en verde contra
PostgreSQL 17.6. Detalle completo en `docs/verificacion-slice5.md`.

> [!warning] Hallazgo con impacto fuera del slice: un pool por request
> `get_engine()` devolvía un engine **nuevo** en cada llamada, y
> `deps.get_session` la llama una vez por request HTTP. Cada petición abría su
> propio pool contra el pooler de Supabase.
>
> Medido: **2.55 s → 0.47 s por request** (~5.4×) tras cachear el engine con
> `lru_cache`. Afecta a **todos** los endpoints, incluidos los del slice 2.
> Regresión en `tests/db/test_session_driver.py`.

> [!note] Hallazgo abierto: `getaddrinfo` intermitente
> 2 de 5 corridas del smoke fallaron al abrir conexión. No reproducible:
> DNS, TCP y 200 resoluciones concurrentes dan 0 fallos. El engine cacheado
> reduce la exposición (3 corridas posteriores: 25/25), pero no es un
> diagnóstico. Un reintento acotado al conectar es la vía siguiente; **no se
> implementó** por ser una decisión de diseño, no de verificación.

> [!note] Advisors de Supabase: sin regresiones
> `rls_enabled_no_policy` (INFO) en las 8 tablas — RLS sin políticas es
> deny-all para el acceso externo, el estado seguro, y las 3 tablas nuevas
> heredan el mismo estado que las del slice 2. Rendimiento: solo
> `ix_species_analytics_or_mort` sin usar, esperado hasta que se ordene por
> mortalidad.

## Limitaciones declaradas

1. Las filas «efecto fijo más fuerte» del informe salen de
   `efectos_fijos*.csv`, que este slice **no persiste ni expone**. El panel
   comparativo las declara pendientes en vez de rellenarlas a mano.
2. Los endpoints nuevos llevan prefijo `/api/v1` y los del slice 2 no.
   Unificar rompería al consumidor existente; se hace cuando haya un cambio de
   contrato que lo justifique.
3. La analítica no está versionada: una recarga sustituye la anterior sin
   historial. Si hace falta comparar campañas, es otro slice.

---

## Links

- [[Slice 4 - Detección de Estancados]] — Siguiente slice de modelo
- [[Slice 3 - Riesgo de Mortalidad]] — Después; el ICC de aquí acota su alcance
- [[Base de Datos]] — Esquema completo
- [[Roadmap]] — Timeline
