# Plan E0 — Fundación de datos completa

Fecha: 2026-09-21. Estado: **implementado y verificado** — evidencia en
`docs/verificacion-e0.md`; desviaciones del plan documentadas ahí.
Origen: `docs/04-vision-producto.md` §9 (E0) y hallazgos H2, H3 y H4.

**Objetivo**: que la ingesta conserve todas las dimensiones que usa el análisis
del ingeniero, y que el monitoreo sea una entidad con fecha — **sin romper
nada de lo construido**.

**Criterio de salida**: el dataset de referencia se reingiere y ninguna
dimensión de las 7 hojas del Excel se pierde; los 230 tests locales y los 25
smoke siguen verdes (ajustados solo donde el cambio es intencional).

---

## 1. Estado actual (verificado)

**Base de datos en Supabase** — revisión `b1c4a7f20e51`:

| Tabla | Filas | ¿La toca E0? |
|---|---|---|
| `projects`, `campaign_files`, `trees`, `observations` | **0** | Sí |
| `species_analytics`, `plot_analytics`, `variance_components` | 30 / 45 / 4 | **No** — es el referente |

Las tablas que E0 modifica **están vacías en producción**. Es el mejor momento
posible para migrar: no hay datos de ingenieros que preservar.

**Qué depende del modelo actual**:

- `Observation.campaign: int` y `Tree.plot_id` / `Tree.locality` aparecen en 7
  módulos de `src/` y en 13 archivos de tests.
- La palabra *campaign* tiene hoy **dos significados**: el número de monitoreo
  (`Observation.campaign`, 1–4) y el archivo subido (`CampaignFile`,
  `POST /projects/{id}/campaigns`). E0 separa los conceptos en la base de
  datos, pero **no renombra nada visible** (ver §3).

---

## 2. Hallazgos de datos que fijan el modelo

Verificados sobre `anexo1.xlsx`, hoja `Monitoreo_4`:

| Columna | Valores distintos | Constante dentro de la unidad de muestreo | Pertenece a |
|---|---|---|---|
| `Codigo de unidad muestreo` | 54 | — (es la clave) | **Parcela** |
| `ID Parcela` | 54 (1:1 con el código) | sí | Parcela |
| `LOCALIDAD` | 3 | sí | **Predio** |
| `Unidad de monitoreo` | 3 | sí | Parcela |
| `Diseño florístico` | 4 | sí | Parcela |
| `Cobertura vegetal asociada` | 4 | sí | Parcela |
| `Cobertura donde se estableció…` | 2 | sí | Parcela |
| `Proyecto` | 1 | sí | **Archivo** |
| `Evento` | 1 («Cuarto monitoreo») | sí | **Archivo** |

- Diseño y coberturas **no varían por árbol**: viven en `plots`, no en `trees`.
  Así se reproducen los cortes de las hojas sin duplicar datos.
- El dataset crudo tiene **54** unidades de muestreo; los modelos mixtos usan
  42–45 porque solo cuentan las que tienen intervalos. No es una
  contradicción.
- **Coordenadas**: X ∈ [4 735 663, 4 736 310], Y ∈ [2 199 355, 2 200 262], sin
  nulos. Encajan con **MAGNA-SIRGAS / Origen Nacional (EPSG:9377)** para el
  corredor Medellín – La Virginia. Inferencia fuerte, **no confirmada**: se
  guarda el SRID como dato y se valida en T8.
- **Pendiente de verificar en T1**: si `Responsables`, `Anotador` y `Observa`
  son constantes por archivo (→ `monitorings`) o varían por fila
  (→ `observations`). **No se asume.**

---

## 3. Principio de la migración: nada visible se rompe

| Contrato | Qué pasa en E0 |
|---|---|
| `Observation.campaign: int` (dominio) | **Se conserva** como el *número* de monitoreo. El repositorio lo traduce a `monitoring_id` |
| `ObservationResponse.campaign` (API) | **Se conserva**. Sigue siendo el número |
| `POST /projects/{id}/campaigns` | **Se conserva** el path |
| `CampaignFile` / `campaign_files` | **No se renombra** en E0. Pasar a `Upload` es cosmético y rompe tests y contrato; se hace en E2, cuando la UI lo consuma |
| `TreeRowResponse` | Solo **se añaden** campos (cambio aditivo) |
| `validate_tree_identity` | **Sin cambios**: `TreeRow` expone `plot_id` y `locality` como propiedades desde la relación con `plots` |
| `WarningItem.type` | Se **añade** un valor (`project_mismatch`); los existentes no cambian |

E0 **no toca**: el referente científico, autenticación, cola de trabajos, UI,
campos nuevos de `projects` (son de E1).

---

## 4. Modelo objetivo de E0

```
projects ──┬── properties (predio)  ── plots (unidad de muestreo) ── trees ── observations
           │                                                                     │
           └── monitorings (M1, M2…, con fecha) ────────────────────────────────┘
           └── campaign_files (archivo) ──N:N── monitorings
```

### Tablas nuevas

**`properties`** — `id`, `project_id` FK, `name`, `vereda` (null),
`UNIQUE (project_id, name)`.

**`plots`** — `id`, `property_id` FK, `sampling_unit_code`, `plot_label`,
`monitoring_unit`, `floristic_design`, `associated_cover`,
`establishment_cover`, `UNIQUE (property_id, sampling_unit_code)`.

> La unicidad de `sampling_unit_code` debe ser **por proyecto**, no solo por
> predio. Como `plots` no tiene `project_id`, se añade redundante con un
> `CHECK` de coherencia, o se valida en el repositorio. **Decisión en T3.**

**`monitorings`** — `id`, `project_id` FK, `number`, `monitoring_date` (null
hasta que el ingeniero la registre en E2), `field_crew`, `recorder`, `notes`,
`UNIQUE (project_id, number)`.

**`campaign_file_monitorings`** — tabla puente N:N (un archivo acumulado trae
varios monitoreos).

### Cambios en tablas existentes

| Tabla | Cambio |
|---|---|
| `trees` | `+ plot_fk` → `plots` · `- plot_id` · `- locality` (pasan a la relación) · `+ srid` |
| `observations` | `+ monitoring_id` → `monitorings` · `- campaign` · `UNIQUE (tree_row_id, monitoring_id)` · `+ field_notes` |
| `campaign_files` | `+ source_project_label` (columna `Proyecto` del archivo) · `+ source_event` (`Evento`) |

---

## 5. Tareas

Cada tarea deja la suite en verde antes de la siguiente (TDD, AGENTS.md).

### T1 · Verificación previa (sin código)
- Comprobar si `Responsables`, `Anotador` y `Observa` son constantes por
  archivo o por fila, y decidir su tabla.
- Revisar las columnas de un Excel de **un solo monitoreo** (D1): si no hay
  uno real, construir el fixture a partir del acumulado quitando columnas.

### T2 · Dominio
- `Tree` gana los atributos de parcela como **portador de la ingesta**
  (`sampling_unit_code`, `floristic_design`, `associated_cover`,
  `establishment_cover`, `monitoring_unit`). La normalización a `plots` es
  trabajo del repositorio, no del dominio.
- `CampaignData` gana `file_metadata` (proyecto, evento) y `monitorings`
  (números detectados).
- Invariante nueva: los números de monitoreo de un proyecto son enteros ≥ 1.
- Tests primero.

### T3 · Mapeo de columnas
- Añadir las 9 columnas a `column_mapping.py`.
- Subir `MAPPING_VERSION` a `2026-09-21-e0`: cambiar el mapeo cambia la
  provenance (ADR-004).
- Test: ninguna de las 42 columnas del Excel queda sin clasificar (mapeada o
  explícitamente ignorada con motivo).

### T4 · Detección de monitoreos (D1)
- Un monitoreo está presente si alguna de sus columnas `_M{k}` trae datos.
- `Evento` se usa como **verificación cruzada**, no como fuente.
- Tests con el acumulado (M1–M4) y con un archivo de un solo monitoreo.

### T5 · Modelos y migración Alembic
- Nueva revisión sobre `b1c4a7f20e51`.
- Orden dentro de la migración: crear tablas → **backfill** desde las
  columnas viejas → añadir FKs y `NOT NULL` → eliminar columnas viejas.
- El backfill se escribe aunque producción esté vacía: cualquier base local
  con datos debe migrar sin pérdida.
- `downgrade` restaura las columnas y reconstruye sus valores.
- Tests (patrón de `test_analytics_migration.py`): migrar una base con datos
  del Slice 2 y comprobar que no se pierde nada; subir, bajar y volver a subir.

### T6 · Repositorio
- `save_ingest` crea o reutiliza predios, parcelas y monitoreos **en la misma
  transacción** (ADR-004: todo o nada).
- Traduce `Observation.campaign` ↔ `monitoring_id`.
- `TreeRow.plot_id` / `TreeRow.locality` como propiedades de solo lectura.
- Si la columna `Proyecto` del archivo no coincide con el proyecto destino:
  **aviso**, no error (`project_mismatch`).
- Idempotencia: resubir el mismo archivo no duplica predios, parcelas ni
  monitoreos.

### T7 · API (solo aditiva)
- `TreeRowResponse` + atributos de parcela.
- `GET /projects/{id}/monitorings` — lista con número, fecha y estado.
- Tests de contrato: los campos existentes no cambian.

### T8 · Verificación con datos reales
- Reingerir el dataset de referencia (SQLite local y smoke en Supabase).
- Comprobar que se pueden reproducir los cortes de las 7 hojas: especie ×
  predio × cobertura × diseño × monitoreo.
- **Confirmar el SRID** de las coordenadas (proyectar un árbol y verificar que
  cae en el corredor Medellín – La Virginia).
- Evidencia en `docs/verificacion-e0.md`.

### T9 · Documentación
- ADR-009 (datos geoespaciales y SRID).
- Actualizar `docs/02-domain.md` y la nota *Modelo de Dominio* del vault.

---

## 6. Tests que cambian (intencionalmente)

| Archivo | Por qué |
|---|---|
| `tests/db/test_models.py`, `test_repository.py` | Nuevas tablas y relaciones |
| `tests/ingester/test_column_mapping.py` | Nuevas columnas y versión |
| `tests/ingester/test_ingest_real.py` | Verifica que se conservan las dimensiones |
| `tests/smoke/test_supabase_smoke.py` | El esquema real incluye las tablas nuevas |

Los tests que construyen `Observation(campaign=…)` **no cambian**: el dominio
conserva el número. Si alguno de los demás falla, es una regresión, no un
ajuste.

---

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| El backfill falla en una base con datos | Test de migración con datos del Slice 2 antes de tocar Supabase |
| La unicidad de parcela por proyecto queda sin garantía en la base | Decidirlo explícitamente en T3, con test |
| El SRID inferido es incorrecto | Se guarda como dato, no como constante en el código; se confirma en T8 |
| Un archivo de un solo monitoreo tiene columnas distintas | T1 lo verifica antes de escribir la detección |
| Aplicar la migración en Supabase | Mismo protocolo que la fase 6: revisar el SQL con `--sql`, confirmar tablas vacías, aplicar |
