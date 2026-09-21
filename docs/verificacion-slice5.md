# Verificación — Slice 5 (Analítica) + tres correcciones prioritarias

Fecha: 2026-09-21. Evidencia de la fase 6 del loop (AGENTS.md).

**Alcance**: tres correcciones al código y la documentación existentes, más la
implementación completa del slice 5 (migración → carga → API → dashboard).
**No se re-estimó nada**: los modelos mixtos ya estaban ajustados y sus CSV son
la fuente de verdad.

---

## Resumen de gates

| # | Gate | Resultado |
|---|---|---|
| 1 | `pytest` backend | ✅ 230 passed, 25 deselected (eran 172 antes del slice) |
| 2 | `ruff check src tests` | ✅ `All checks passed!` |
| 3 | Regla de dependencia (ADR-003) | ✅ 9 tests de `tests/architecture/` |
| 4 | Migración = modelo de dominio | ✅ 10 tests, Alembic aplicado sobre SQLite |
| 5 | `npm test` frontend | ✅ 28 passed (4 archivos) |
| 6 | `npm run build` (tsc strict + vite) | ✅ built in 10.81s |
| 7 | `npm run lint` | ✅ 0 errores (4 warnings de `any` en render props de Recharts) |
| 8 | `pytest -m supabase` (Postgres real) | ✅ 25 passed — ver «Fase 6» abajo |
| 9 | Advisors de seguridad y rendimiento | ✅ sin hallazgos nuevos (solo INFO) |
| 10 | Review (fase 7) | ⬜ pendiente |

> El gate 10 queda abierto a propósito: este documento cierra la fase 6, no el
> slice.

---

## Corrección 1 — regla de contracción de altura

### Qué estaba mal

`MAX_CONTRACTION_M = 0.01` emitía `SuspiciousContractionWarning` ante cualquier
bajada de altura mayor a 1 cm. Dos problemas, uno numérico y otro de redacción:

- **El umbral.** El único intervalo sin corregir del dataset (M1→M2) tiene 13
  contracciones reales de 1 a 20 cm. Con 1 cm se marcaban 12 de 13.
- **El nombre y el texto.** «Sospechosa» + «error de medición de campo
  documentado» le dice a la cuadrilla que arregle el dato. Eso ya ocurrió:
  M2→M3 y M3→M4 tienen **0 % de contracciones**, lo cual es biológicamente
  inverosímil. Es monotonización artificial, y se lleva por delante justo la
  señal que busca el modelo de estancamiento.

### Qué se cambió

| Antes | Ahora |
|---|---|
| `SuspiciousContractionWarning` | `LargeContractionNoted` |
| `MAX_CONTRACTION_M = 0.01` | `MAX_CONTRACTION_M = 0.05` |
| «encoge … error de medición documentado» | «decrece … **NO corregir el dato original**» |

El mensaje nuevo nombra las causas reales (daño físico, poda, ramoneo, cambio
del punto de referencia). El `type` del contrato sigue siendo `contraction`:
es vocabulario estable de la API y no había razón para romperlo.

### Efecto medido sobre el dataset real

```
$ python -m agrosense.adapters.ingester.cli data/raw/anexo1.xlsx   (equivalente)
total warnings: 14
Counter({'LargeContractionNoted': 7, 'SuspiciousRevivalWarning': 6, 'CensusGapWarning': 1})
contracciones anotadas (m): [0.07, 0.09, 0.1, 0.1, 0.13, 0.18, 0.2]
```

De 13 contracciones, ahora se anotan **7** (las de ≥7 cm). Las de 1–5 cm —
ruido de cinta — pasan sin aviso. Es exactamente el efecto buscado: se anota
lo que merece una visita, no lo que invita a reescribir el dato.

### Tests

`backend/tests/domain/test_rules.py`:

- `test_contraction_threshold` — gate: `MAX_CONTRACTION_M >= 0.05`.
- `test_field_scale_contractions_are_not_flagged` — 1, 2, 3 y 4 cm no generan aviso.
- `test_contraction_at_tolerance_boundary_is_not_warning` — 5 cm exactos tampoco.
- `test_contraction_note_does_not_ask_to_correct_the_datum` — el texto contiene
  «no corregir» y **no** contiene «sospechos». Es la mitad del arreglo: sin
  esto, alguien puede revertir la redacción sin que nada falle.

`backend/tests/ingester/test_ingest_real.py::test_real_annex_ingests` fija el
desglose exacto (7 / 6 / 1) contra el dataset real.

---

## Corrección 2 — el grupo de la validación cruzada es la PARCELA

### Qué estaba mal

Cuatro documentos afirmaban que el `GroupKFold` agrupaba **por árbol**.
Agrupar por árbol:

1. **Deja fuga espacial.** Los árboles de una parcela comparten suelo,
   pendiente, exposición y cuadrilla de medición. Con folds por árbol, la misma
   parcela está en train y en test.
2. **No aporta nada bajo split temporal.** El régimen primario entrena M2→M3 y
   prueba M3→M4: las olas ya separan las observaciones del mismo individuo.
3. **Ignora que la parcela no es ruido**: ICC 0.07 en estancamiento, 0.09 en
   mortalidad.

### Archivos corregidos

| Archivo | Cambio |
|---|---|
| `AGENTS.md` | ML eval gate del workflow: «group split por árbol» → por parcela, con el porqué |
| `docs/01-discovery.md` | Metodología del spike ML |
| `docs/03-architecture.md` | ML eval gate de `ml/` |
| `04-ML/Resumen ML.md` | Sección «Split por Árbol» → «Split por Parcela», con el antipatrón marcado como MAL |
| `01-Proyecto/Roadmap.md` | Fila Split del slice de mortalidad |
| `06-Slices/Slice 3 - …md` | Fila Split + ML Eval Gate completo |

`04-ML/Protocolo Estancamiento.md` ya decía «agrupado por unidad de muestreo»:
no se tocó.

### Test

`backend/tests/architecture/test_ml_eval_gate.py` (3 tests):

- `test_groupkfold_uses_plot` — recorre el código ML y falla si un `groups=`
  usa el árbol. Hace **skip** mientras `ml/` no exista (llega con el slice 4);
  empieza a morder con el primer `GroupKFold` que se escriba.
- `test_docs_do_not_claim_grouping_by_tree` — ningún documento vigente puede
  afirmarlo. Ignora los bloques marcados como «MAL», que documentan el error a
  propósito.
- `test_agents_md_states_the_plot_as_grouping_unit` — AGENTS.md debe nombrar
  `Codigo de unidad muestreo`.

**Verificación de que el gate muerde** (no pasa por vacío):

```
$ # revirtiendo la fila del Roadmap a "GroupKFold por árbol"
E   AssertionError: Documentos que aun afirman agrupar por arbol:
E     docs\obsidian-agrosense\01-Proyecto\Roadmap.md:95: | Split | GroupKFold por árbol |
1 failed, 2 passed
$ # restaurado
3 passed
```

---

## Corrección 3 — orden invertido: Estancados (4) antes que Mortalidad (3)

Se mantienen los números y los nombres de archivo (renombrarlos rompería todos
los wikilinks del vault); lo que cambia es el **orden de ejecución** y la
dependencia declarada.

| Razón | Dato |
|---|---|
| Evidencia disponible | Estancamiento: 153 eventos positivos, PR-AUC 0.469 con validación honesta. Mortalidad: 33–37 por ola ⇒ **EPV 4–11**, bajo el mínimo de 10–20 |
| Dependencia de features | `estancó_intervalo_previo` lo **produce** el slice 4 y es el predictor más fuerte (OR 2.92 en estancamiento, 1.70 marginal en mortalidad) |
| Riesgo de gate | Hacer mortalidad primero obliga a improvisar esa feature y a pasar el ML eval gate dos veces |

Archivos actualizados: `Roadmap.md` (secciones reordenadas + cronograma),
`Slice 3` (aviso de dependencia + hallazgos del modelo mixto de mortalidad),
`Slice 4` (marcado como primero + tarea 9 para entregar la feature),
`AGENTS.md` (épicas 2 y 3 intercambiadas), `README.md`.

---

## Slice 5 — implementación

### Esquema (migración `b1c4a7f20e51`)

```
species_analytics    PK species_name         30 filas
plot_analytics       PK plot_code            45 filas
variance_components  UQ (model, grouping)     4 filas
```

Sin FK hacia `projects`: los efectos se estimaron sobre el dataset completo del
programa, no sobre un proyecto. Hay un test que lo verifica
(`test_analytics_tables_have_no_project_foreign_key`) para que nadie añada esa
columna sin ADR.

**`alembic/env.py` se modificó** para aceptar una conexión inyectada vía
`config.attributes["connection"]` (patrón estándar de Alembic). Sin eso, las
migraciones solo podían probarse contra Supabase real, lo que viola
`test_no_remote_db_by_default`.

### Carga

```
$ python scripts/load_analytics.py --dry-run
Especies:  30
Parcelas:  45
Varianza:  4 filas

Especies con IC significativo (estancamiento): 8
  Lafoensia speciosa           OR  4.94 [2.25, 10.86]  se estanca mas
  Delostoma integrifolium      OR  4.71 [2.81, 7.90]  se estanca mas
  Persea caerulea              OR  3.82 [2.14, 6.81]  se estanca mas
  Delostoma roseum             OR  2.98 [1.38, 6.45]  se estanca mas
  Cedrela montana              OR  2.29 [1.19, 4.39]  se estanca mas
  Senna viarum                 OR  0.61 [0.38, 0.97]  se estanca menos
  Heliocarpus popayanensis     OR  0.35 [0.13, 0.93]  se estanca menos
  Verbesina arborea            OR  0.24 [0.12, 0.52]  se estanca menos

Especies con IC significativo (mortalidad): 1
  Inga punctata                OR  0.35 [0.16, 0.80]

  stall      parcela  var=0.317 ICC=0.071  (310/1335 eventos)
  stall      especie  var=0.846 ICC=0.190  (310/1335 eventos)
  mortality  parcela  var=0.372 ICC=0.091  (70/1405 eventos)
  mortality  especie  var=0.415 ICC=0.102  (70/1405 eventos)
```

Coincide con los informes del 2026-09-21 en los 12 valores comprobables.

### Dos hallazgos de datos durante la implementación

**1. `Inga punctata` trae un NBSP.** En los tres CSV la especie llega como
`'Inga punctata\xa0'`. Sin normalizar: la PK la acepta como dos taxones
distintos, el join con el panel no casa (se queda sin gremio ni conteos) y
`GET /analytics/species/Inga punctata` devuelve 404 — justo para la **única**
especie con efecto significativo en mortalidad. Lo resuelve `normalize_level()`
y lo fija `test_species_with_nbsp_in_the_source_is_reachable`.

**2. El encoding de los paneles se verificó, no se asumió.** La primera lectura
sugería cp1252 (el terminal mostraba `Rehabilitaci?n`). La inspección de bytes
mostró `C3 B3` — UTF-8 correcto; el `?` era del terminal. Declarar cp1252
habría metido mojibake en la base **sin fallar**.

### API

Seis endpoints de solo lectura bajo `/api/v1/analytics`. Verificados contra el
OpenAPI generado:

```
['get'] /api/v1/analytics/plots
['get'] /api/v1/analytics/species
['get'] /api/v1/analytics/species/top-protective
['get'] /api/v1/analytics/species/top-risk-stall
['get'] /api/v1/analytics/species/{name}
['get'] /api/v1/analytics/variance-decomposition
```

Las rutas fijas se declaran **antes** de `/{name}`; hay un test
(`test_top_risk_route_is_not_swallowed_by_the_name_parameter`) porque el orden
es invisible al leer el archivo.

### La escala, que es el error fácil de este slice

Los efectos se estiman en **log-odds** y se publican en **odds ratio**. El
contrato separa las dos escalas por nombre:

| Campo | Escala | Uso |
|---|---|---|
| `odds_ratio`, `or_ci95` | odds ratio | **lo que se muestra** |
| `ci95_log_odds` | log-odds | trazabilidad contra el CSV, **nunca se renderiza** |

> **Desviación deliberada del ejemplo del prompt.** El ejemplo traía `ci95:
> [0.81, 2.38]` junto a `or: 4.94` — esos valores son log-odds, y un lector
> razonable los tomaría por el intervalo del OR (que es [2.25, 10.86]). El
> campo se renombró a `ci95_log_odds` y se añadió `or_ci95`. Mismo dato, sin
> ambigüedad posible.

Tests que lo protegen, en los dos lados:

- Backend: `test_confidence_intervals_are_exponentiated_for_the_ui` verifica
  `log(or_lo) == ci95_log_odds[0]` para las 30 especies.
- Frontend: `ForestPlot.test.tsx` (los valores que entran al gráfico) y
  `SpeciesDetail.test.tsx` (los que se renderizan como texto).

**Prueba de mutación**: cambiando `or_ci95` por `ci95_log_odds` en los dos
componentes, **4 tests fallan**. Restaurado, 28 pasan. Los tests miden lo que
dicen medir.

> Nota metodológica: el primer test de escala que escribí comprobaba el DOM de
> la página completa y pasaba **por vacío** — en jsdom el SVG se renderiza con
> tamaño 0 y no emite texto. Se detectó con una sonda y se reemplazó por los
> dos tests de arriba, que sí ejercitan el código.

### Interpretación: en `application/`, no en la UI

Decidir que un IC que cruza 1 **no es un hallazgo** es una regla de negocio. Si
viviera en el frontend, la API y el dashboard dirían cosas distintas del mismo
dato (AGENTS.md: «business rules must not be duplicated in the frontend»).

`test_interpretation_never_claims_an_effect_when_ci_crosses_one` lo fija: toda
especie no significativa debe leerse como «sin efecto significativo … cruza 1»,
aunque su OR puntual se vea alto.

---

## Fase 6 — Verify contra Supabase real

Ejecutada el 2026-09-21 contra el proyecto real (PostgreSQL 17.6, session
pooler `aws-0-sa-east-1`). Estado previo: revisión `a8888efd3ae8`, las cuatro
tablas del slice 2 **vacías** (0 filas), ningún dato en riesgo.

### Migración

El SQL se revisó antes de aplicarlo (`alembic upgrade --sql`): tres
`CREATE TABLE` y cuatro `CREATE INDEX`, **ningún `ALTER` ni `DROP`** sobre lo
existente. Aplicada:

```
$ alembic upgrade head
Running upgrade a8888efd3ae8 -> b1c4a7f20e51, slice 5: species_analytics, …
$ alembic current
b1c4a7f20e51 (head)
```

### Carga

`python scripts/load_analytics.py` → 30 especies, 45 parcelas, 4 componentes.
Los 12 valores comprobables del informe coinciden.

### Lo que SQLite no podía verificar, y aquí sí

| Verificación | Resultado |
|---|---|
| `sig_*` es BOOLEAN real | ✅ `True`/`False`, no 0/1. `WHERE sig_stall` → 8; `WHERE sig_mort` → 1 |
| `updated_at` es TIMESTAMPTZ | ✅ `2026-09-21 15:39:43.703903+00:00` |
| NULL ≠ 0 en las 3 parcelas solo-mortalidad | ✅ `or_stall IS NULL`; cero filas con `or_stall = 0` |
| UTF-8 de punta a punta | ✅ `Tardía` = U+00ED (no mojibake); `Inga punctata` sin NBSP, len 13 |
| UNIQUE `(model, grouping)` existe en la DB | ✅ |
| Índices creados | ✅ 4 |
| Sin FK hacia `projects` | ✅ |
| Recarga idempotente | ✅ 30/45/4 otra vez, mismos valores |

> El `Tardía` se verificó por **codepoints**, no leyendo la consola: el
> terminal de Git Bash muestra `Tard?a` aunque el dato esté bien. Ya me había
> engañado una vez con el encoding de los CSV.

### Smoke nuevo

`backend/tests/smoke/test_analytics_smoke.py` — 21 tests marcados `supabase`,
incluidos 6 que ejercitan la API contra Postgres (no contra SQLite en
memoria). Hacen **skip** con motivo si la analítica no está cargada: el smoke
informa, no miente.

```
$ pytest -m supabase -q
25 passed, 230 deselected in 52.68s
```

### E2E con uvicorn real

Servidor levantado de verdad (no `TestClient`):

| Caso | Resultado |
|---|---|
| `/variance-decomposition` | ratios 2.67 (stall) y 1.12 (mortality) + lectura estratégica |
| `/species/top-risk-stall` | las 5 esperadas, todas con `significant: true` |
| `/species/Lafoensia%20speciosa` | `or_ci95: [2.25, 10.86]` y `ci95_log_odds: [0.81, 2.38]` — **escalas separadas y correctas** |
| `?gremio=Tard%C3%ADa` | 12 especies; el acento sobrevive a URL → Postgres → JSON |
| `/species/Ficus inventada` | 404 `{"detail":{"code":"SPECIES_NOT_FOUND",…}}` |
| `?sort=drop table` | 422, rechazado en el borde |
| `/plots` | 45, con 3 `odds_ratio: null` serializados como `null` |

---

## Hallazgo de la fase 6: un engine (y un pool) POR REQUEST

**El problema.** `api/deps.get_session` llama a `get_session_factory()` una vez
por request HTTP, y `get_engine()` devolvía un engine **nuevo** en cada
llamada. Verificado:

```
engines creados para 5 'requests': 5
ids distintos: 5
```

Es decir: cada petición construía su propio pool, con resolución DNS,
handshake TCP y TLS contra el pooler de Supabase, y el pool anterior quedaba
sin `dispose()` hasta el recolector. Un pool que nunca reutiliza una conexión
no es un pool.

**El coste, medido.** Mismo endpoint, mismo servidor, 6 peticiones seguidas:

| | req 1 | req 2-6 (mediana) |
|---|---|---|
| Sin caché de engine | 3.37 s | **2.55 s** |
| Con caché de engine | 0.50 s | **0.47 s** |

**~5.4× más rápido**; ~2,1 s de handshake desperdiciados en cada petición. La
suite de smoke bajó de 113 s a 52 s.

**El arreglo.** `@lru_cache(maxsize=1)` sobre `get_engine()`, más
`reset_engine_cache()` para soltar el pool. Sigue siendo **perezoso**:
importar el módulo no conecta, que es lo que permite que `pytest` corra
offline.

**Regresión.** `tests/db/test_session_driver.py::TestEngineIsReusedAcrossRequests`
(5 tests, sobre SQLite). Prueba de mutación: quitando el `lru_cache`, **3
fallan**; restaurado, 14 pasan.

**Efecto colateral en un gate.** Esos tests llaman a `get_engine()`, lo que
disparó `test_no_remote_db_by_default`. El gate tenía razón en avisar, pero
era un falso positivo: apuntan `DATABASE_URL` a SQLite. Se abrió una excepción
**acotada** que exige las dos marcas a la vez (parchear la variable *y*
apuntar a sqlite), con un test propio —
`test_the_sqlite_exception_is_not_a_blank_cheque` — que verifica que la
excepción no se convierta en un cheque en blanco.

> Este hallazgo es independiente del slice 5: afecta a **todos** los endpoints,
> incluidos los del slice 2. Puede explicar parte de la deuda #G (upload de
> ~81 s), aunque no lo he medido.

---

## Hallazgo abierto: `getaddrinfo` intermitente

Durante la fase 6, **2 de 5** corridas del smoke fallaron con
`psycopg.OperationalError: [Errno 11001] getaddrinfo failed` al abrir una
conexión nueva. Siempre al conectar, nunca en una consulta sobre una conexión
ya establecida.

Lo que descarté con medición:

| Prueba | Resultado |
|---|---|
| `nslookup` del host | resuelve (CNAME → ELB de AWS) |
| `socket.gethostbyname` desde Python | resuelve |
| TCP a 5432 y 6543 | abierto |
| 60 `getaddrinfo` seguidos | 0 fallos |
| 200 `getaddrinfo` con 8 y 32 hilos | 0 fallos |

**No es reproducible bajo demanda y no le atribuyo causa.** El engine cacheado
reduce mucho la exposición (una resolución por proceso en vez de una por
request) y las tres corridas posteriores dieron 25/25, pero eso es mitigación,
no diagnóstico.

Si vuelve a aparecer en uso real, la vía siguiente es un reintento acotado al
abrir conexión. **No lo he implementado**: añadir reintentos es una decisión de
diseño que puede enmascarar fallos reales, y corresponde decidirla, no
colarla en un gate de verificación.

---

## Advisors de Supabase

**Seguridad** — un aviso, nivel `INFO`: `rls_enabled_no_policy` en las 8 tablas
del esquema `public`, incluidas las 3 nuevas.

Interpretación: RLS **habilitado sin políticas** significa deny-all para el
acceso externo (anon key / PostgREST). Es el estado *seguro*; lo peligroso
sería lo contrario. El backend no pasa por ahí: conecta con el rol propietario
por el pooler. Las tablas nuevas **heredan exactamente el mismo estado** que
las del slice 2, así que el slice no introduce ninguna regresión.

> Sigue siendo deuda: si algún día se expone la anon key, hará falta decidir
> políticas explícitas de lectura para la analítica (que es información
> pública del programa, no dato sensible). No es trabajo de este slice.

**Rendimiento** — un aviso, nivel `INFO`: `ix_species_analytics_or_mort` sin
usar. Es esperado: el smoke y la vista por defecto ordenan por `or_stall`; ese
índice entra con `?sort=mortality_risk`. Los otros tres **no** aparecen como
no usados, lo que confirma que están bien elegidos. No se elimina.

---

## Estado de la base de datos tras la fase 6

| Tabla | Filas |
|---|---|
| `projects`, `campaign_files`, `trees`, `observations` | 0 (sin cambios) |
| `species_analytics` | 30 |
| `plot_analytics` | 45 |
| `variance_components` | 4 |

Revisión de Alembic: `b1c4a7f20e51 (head)`.

---

## Limitaciones declaradas

1. **Panel comparativo incompleto.** Las filas «efecto fijo más fuerte» del CSV
   de comparación salen de `efectos_fijos*.csv`, que este slice no persiste ni
   expone. Se declaran pendientes en la UI en vez de escribirlas a mano — un
   número hardcodeado en el frontend deja de cuadrar con la base en la primera
   recarga y nadie se entera. Queda como Task 10.
2. **Prefijo de rutas inconsistente.** Los endpoints nuevos llevan `/api/v1` y
   los del slice 2 no. Versionar los existentes rompe a su consumidor; se
   unifica con el próximo cambio de contrato, no de paso.
3. **Sin versionado de analítica.** Una recarga sustituye la anterior sin
   historial.
4. **Los CSV no están en el repo** (`.gitignore` excluye `data/processed/` y
   `*.csv`). Los tests que los necesitan hacen **skip**, igual que
   `test_ingest_real.py` con el `.xlsx`. Verificado moviendo la carpeta:

   ```
   $ mv data/processed data/_processed_tmp && pytest -q
   187 passed, 37 skipped, 4 deselected
   ```

   Es decir: en una máquina sin los datos la suite **no falla**, avisa.

---

## Comandos de reproducción

```bash
cd backend
pip install -e ".[dev]"
alembic upgrade head
python scripts/load_analytics.py --dry-run   # valida sin escribir
python scripts/load_analytics.py             # carga real
pytest -q                                    # 230, offline
pytest -m supabase -q                         # 25, contra Postgres real
ruff check src tests

cd ../frontend
npm install
npm test
npm run build
npm run lint
```

---

## Cierre de la fase 6

La fase 6 queda **cerrada**. Lo verificado está arriba; lo que queda abierto
está declarado, no olvidado:

| Abierto | Decisión |
|---|---|
| `getaddrinfo` intermitente | Se documenta y **no se investiga más ni se añaden reintentos** (decisión del 2026-09-21). El engine cacheado reduce la exposición; un reintento al conectar es una decisión de diseño, no de verificación |
| RLS sin políticas | Deuda heredada del slice 2, sin regresión. Se decide cuando se exponga la anon key |
| `efectos_fijos*.csv` | Task 10, fuera del alcance acordado de este slice |
| Fase 7 — Review | Siguiente paso |

Nada de lo anterior bloquea la revisión.
