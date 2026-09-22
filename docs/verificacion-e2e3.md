# Verificación — E2/E3 · Carga de datos crudos y análisis exploratorio

Fecha: 2026-09-22. Plan: `docs/superpowers/plans/2026-09-22-e2e3-carga-y-analisis.md`.
Decisión: `docs/adr/008-analisis-como-snapshot.md`.

**Criterio de salida**: el ingeniero sube **solo la hoja de campo** (una fila
por árbol) con la fecha del monitoreo, y AgroSense reproduce las **siete hojas
de análisis** que hoy arma a mano —Composición, Alturas, Diámetro de copa,
Supervivencia, Estado fitosanitario, Edades (clases de desarrollo) y DAP—,
las muestra en pantalla con sus tablas y gráficas, y las entrega en un `.xlsx`
descargable. **Cumplido y probado**; las cifras se comparan contra el Anexo 1
celda a celda. El recorrido en navegador con una cuenta real sigue pendiente
del ingeniero (ver abajo).

## Gates

| # | Gate | Resultado |
|---|---|---|
| 1 | `pytest` local (SQLite) | ✅ 436 passed, 39 deselected (102 s) |
| 2 | `pytest -m supabase` (Postgres real) | ✅ 39 passed (33 de E0/E1 + 6 nuevos de E2/E3) |
| 3 | `ruff check src tests` | ✅ limpio |
| 4 | Frontend: `vitest run` | ✅ 58 passed (9 archivos) |
| 5 | Frontend: `tsc -b` + `npm run build` + `npm run lint` | ✅ 0 errores (4 avisos previos de `any` en Recharts) |
| 6 | `pip-audit -r requirements.lock.txt` | ✅ sin vulnerabilidades conocidas |
| 7 | `npm audit --omit=dev` | ✅ 0 vulnerabilidades |
| 8 | Migración `e5f1a2b3c4d6` en Supabase | ✅ aplicada (head) |
| 9 | Test de arquitectura (capas) | ✅ `domain`/`application` siguen sin importar adapters, FastAPI, SQLAlchemy ni pandas |

## Contra el Anexo 1: las cifras coinciden

`tests/analysis/test_engine_vs_annex.py` — **20 tests**, ejecutados con el
archivo real (`data/raw/anexo1.xlsx`, 856 árboles, M1–M4; el test se salta
solo si el archivo no está). Compara el resultado del motor contra las hojas
que el ingeniero llenó a mano: totales por especie y diseño florístico,
alturas y diámetros de copa promedio por especie/predio/monitoreo,
supervivencia por predio y acumulada, reparto de estados fitosanitarios,
clases de desarrollo y el conteo de DAP medidos.

Dos diferencias encontradas, ambas **del archivo, no del cálculo**, y ambas
documentadas dentro del test:

1. *Cavendishia / Guayabal / ABB / M3*: la hoja dice 0.52 y el motor calcula
   0.5244 — esa columna está escrita a mano con dos decimales. Se compara con
   tolerancia 0.005.
2. *Cedrela / Guayabal / CP*: la hoja escribe 0.23 para EEN-M4, pero los dos
   árboles vivos de ese grupo miden 0.20 en los datos crudos. Es un error de
   transcripción de la hoja; el test afirma sobre las celdas individuales.

Que el motor detecte una errata del trabajo manual es, justamente, la razón
de calcularlo desde los datos crudos.

## Una sola fuente de cifras

Regla de `AGENTS.md`: las reglas de negocio no se duplican en el frontend.
Aquí eso se traduce en que **el backend calcula una vez** y la pantalla y el
`.xlsx` solo presentan:

- `tests/api/test_e2e3_api.py` (**11 tests**) incluye la comprobación clave:
  un valor del `payload` que devuelve `GET …/analysis` aparece **idéntico** en
  la celda correspondiente del libro que devuelve `GET …/report.xlsx`.
- `tests/analysis/test_report_xlsx.py` (**9 tests**): una hoja por análisis más
  `Resumen` y `Datos crudos`, formatos numéricos por tipo de columna,
  cabeceras agrupadas, gráficas nativas de Excel, y **la hoja de datos crudos
  vuelve a ser ingerible** (se reingiere en el test y produce lo mismo).
- El frontend no hace ninguna cuenta: `DataTable` y `AnalysisBarChart` se
  dibujan desde el contrato tipado (cada columna declara `kind` y decimales).

## Reparto de responsabilidades

- `domain/analysis_rules.py` (**23 tests**) — las *definiciones*: qué es una
  plántula, qué estados fitosanitarios existen, desde cuántos árboles un
  porcentaje significa algo (`MIN_SAMPLE_FOR_PERCENT = 5`), y la validación de
  la fecha del monitoreo (ni futura ni fuera de orden → 422).
- `adapters/analysis/engine.py` (**13 tests**) — la agregación con pandas.
  Fuera del dominio: el dominio no depende de pandas.
- `application/use_cases/monitoring_analysis.py` (**8 tests**) — cuándo se
  calcula y quién puede leerlo.

## Base de datos

- Migración `e5f1a2b3c4d6`: tabla `monitoring_analyses` con
  `UNIQUE(monitoring_id)`, `analysis_version`, `input_hash` (SHA-256 de los
  árboles y observaciones que lo produjeron) y `payload` JSONB.
- `tests/smoke/test_e2e3_smoke.py` (**6 tests contra Supabase**): la carga
  deja un snapshot por monitoreo con el mismo `input_hash`; el `payload`
  vuelve de JSONB con su forma (listas, nulos, decimales); un archivo
  corregido **reemplaza** el snapshot en vez de acumular filas; la fecha llega
  a la columna `DATE`; el `.xlsx` sale del mismo snapshot que la pantalla; y
  borrar el proyecto se lleva los snapshots por cascada de la propia DB.

## Rendimiento: deuda #G cerrada

Perfilando la carga del dataset de referencia contra Supabase apareció el
motivo real de los 92 s: las 3146 observaciones entraban en **615 sentencias**.
No es el volumen — al pasar los dicts por el `insert()` del ORM, las filas se
agrupan por el conjunto de columnas **no nulas**, y en campo cada fila tiene un
patrón de nulos distinto (un árbol sin copa, otro sin estado fitosanitario,
otro muerto sin medidas). Cada grupo era un viaje contra el pooler.

`_bulk_insert` usa `insert(model.__table__)` y emite un único `executemany`:

| | antes | después |
|---|---|---|
| `save_ingest` (856 árboles, 3146 obs.) | 91.9 s | **4.8 s** |
| sentencias para observaciones | 615 | **1** (3146 filas, 1.11 s) |

La regresión se vigila contando **sentencias**, no tiempo (un test de reloj
sería inestable): `tests/db/test_ingest_statements.py` (**2 tests**) exige una
sentencia por tabla en la inserción y una en la actualización.

Con eso, la carga completa del Anexo mide ≈18 s de punta a punta: parseo 2.2 s
+ guardado 4.8 s + lectura 1.6 s + análisis de los cuatro monitoreos 7.4 s +
snapshots 2.1 s. Por eso ADR-008 decide **no** montar todavía la cola de
trabajos (ADR-009 sigue pendiente).

## Errores y seguridad

- Fecha futura o fuera de orden → 422 `INVALID_MONITORING_DATE`, validada
  **antes** de persistir nada.
- Monitoreo inexistente → 404 `MONITORING_NOT_FOUND`; proyecto de otro
  ingeniero → 404 en las tres rutas nuevas; sin token → 401 (verificado
  también contra el servidor real: `GET /projects/138/monitorings/1/analysis`
  sin token devuelve `401 UNAUTHENTICATED`).
- Un fallo del análisis **no** tumba una carga válida: se registra con
  `logger.exception` y la respuesta informa qué monitoreos se analizaron.
- El `.xlsx` se sirve con `Content-Disposition: attachment` y
  `Cache-Control: no-store`.
- Los avisos del archivo se muestran como texto escapado por React; no se
  interpreta HTML venido del Excel (mitigación de #J).
- **Hallazgo de esta revisión, corregido**: openpyxl marca como *fórmula*
  cualquier cadena que empiece por `=`, y Excel la ejecuta al abrir el
  archivo. Como la especie, el identificador del árbol y las notas de campo
  salen del Excel que sube el usuario, el reporte era un vector de inyección
  de fórmulas. `_cell()` fuerza el tipo texto en toda celda escrita, y
  `test_field_text_never_becomes_an_excel_formula` recorre el libro entero
  exigiendo **cero** celdas ejecutables (antes salían 14).

## Pendiente del ingeniero

1. **Recorrido en navegador con una cuenta real**: subir el Anexo desde la
   ficha del proyecto, abrir el análisis de M4, cambiar de hoja y de predio, y
   descargar el reporte. La extensión de Chrome no está conectada en esta
   máquina, así que la revisión visual no pudo hacerse desde aquí (igual que
   en E1).
2. Confirmar que el `.xlsx` descargado se abre bien en su Excel (las gráficas
   son nativas, no imágenes).
