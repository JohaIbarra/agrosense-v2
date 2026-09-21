# Verificación — E0 · Fundación de datos completa

Fecha: 2026-09-21. Plan: `docs/superpowers/plans/2026-09-21-e0-fundacion-datos.md`.
Decisión: `docs/adr/005-territorio-y-monitoreos.md`.

**Criterio de salida**: el dataset de referencia se reingiere sin perder
ninguna dimensión de las 7 hojas del Excel, y nada de lo construido se rompe.
**Cumplido.**

---

## Gates

| # | Gate | Resultado |
|---|---|---|
| 1 | `pytest` local | ✅ **291 passed** (eran 230; +61 de E0) |
| 2 | `pytest -m supabase` | ✅ **31 passed** (eran 25; +6 de E0) |
| 3 | `ruff check src tests` | ✅ limpio |
| 4 | Migración aplicada en Supabase | ✅ `c2d8e41f6a07 (head)` |
| 5 | Advisors de seguridad | ✅ sin regresión (las 4 tablas nuevas con RLS, como las demás) |
| 6 | Contratos del Slice 2 | ✅ ningún test de API ni de repositorio existente modificado |
| 7 | Review (fase 7) | ⬜ pendiente |

---

## 1. Las dimensiones del ingeniero llegan hasta la base

Reingesta del Excel real: **856 árboles, 3 146 observaciones, monitoreos
[1, 2, 3, 4], 3 predios, 54 parcelas — las 54 con código de unidad de
muestreo.**

La prueba de que no se pierde nada es **recalcular desde la base las cifras
que el ingeniero hizo a mano en el Excel**. Coinciden exactamente:

| Hoja del Excel | Valor en la hoja | Recalculado desde la base |
|---|---|---|
| Supervivencia — árboles en Guayabal | 349 | **349** |
| Supervivencia — Guayabal, Ampliación de borde de bosque | 207 | **207** |
| Alturas — Tres Jotas, Bosque de galería (M4, vivos) | 0,7345 | **0,7345** |
| Alturas — Tres Jotas, Mosaico de pastos (M4, vivos) | 0,6824 | **0,6824** |

Con el modelo anterior estos cortes eran imposibles: cobertura y diseño no se
guardaban.

## 2. Ninguna columna se descarta en silencio

`test_real_file_header_is_fully_classified` lee la cabecera del archivo real
y exige que cada una de sus 42 columnas esté mapeada o ignorada con motivo.

La primera versión de la lista de prueba se copió mal («Colonización» en vez
de la forma truncada **«Colonizació»** que trae el archivo) y solo el test
contra el archivo real lo detectó. Por eso existen los dos.

## 3. Monitoreos (decisión D1)

- Un Excel acumulado (M1–M4) y uno de un solo monitoreo se leen igual.
- Sin techo: M5, M6… se aceptan (antes el dominio rechazaba el quinto).
- `Evento` («Cuarto monitoreo») solo verifica: si contradice los datos se
  emite `event_mismatch`, un aviso que no bloquea la carga. El archivo real no
  lo dispara.
- `Responsables` y `Anotador` se atribuyen al monitoreo más reciente del
  archivo; `Observa`, a la última observación de cada árbol.

## 4. Migración sin pérdida

`tests/db/test_e0_migration.py` construye una base en la revisión anterior
con datos del Slice 2 (incluido el caso de un mismo `ID Parcela` en dos
predios) y comprueba:

- el upgrade traslada predios, parcelas y monitoreos sin perder una
  observación;
- el downgrade devuelve exactamente la forma vieja;
- subir, bajar y volver a subir es estable;
- tras migrar a head, **todas** las tablas coinciden columna a columna con los
  modelos.

En Supabase se revisó el SQL con `--sql` antes de aplicarlo y se confirmó que
las tablas afectadas tenían 0 filas.

## 5. Postgres real (smoke)

`tests/smoke/test_e0_smoke.py`: tablas y restricciones con nombre presentes,
`monitoring_date` es `DATE` e ida y vuelta correcta, **Postgres rechaza un
monitoreo número 0** (el CHECK vive en la base, no solo en el dominio), y la
cascada desde el proyecto alcanza las tablas nuevas.

## 6. Sistema de coordenadas

Proyección inversa de EPSG:9377 (Transverse Mercator, GRS80, λ₀ = 73° O,
φ₀ = 4° N, k₀ = 0,9992, FE = 5 000 000, FN = 2 000 000):

| Predio | Latitud | Longitud | Elevación registrada |
|---|---|---|---|
| Guayabal | 5,8017° N | 75,3852° O | 2 746 m |
| San Antonio | 5,8013° N | 75,3876° O | 2 790 m |
| Tres Jotas | 5,8054° N | 75,3850° O | 2 794 m |

Extensión conjunta: 646 × 907 m.

**Confirmado con alta confianza**: es el único sistema colombiano con ese
falso origen, y el resultado cae en la cordillera, coherente con la elevación
del propio archivo.

**No confirmado**: que el sitio esté en el corredor de la línea Medellín – La
Virginia. Queda ~30 km al este de la recta entre ambas, lo cual es posible en
una compensación ambiental pero no se puede verificar desde los datos.

---

## Desviaciones respecto al plan

| Plan | Hecho | Por qué |
|---|---|---|
| `trees.srid` | No se añade | El sistema de coordenadas es del proyecto, no del árbol; va a `projects` en E1 con 9377 por defecto |
| `trees.plot_fk` | `trees.plot_row_id` | Convención existente (`tree_row_id`) |
| Unicidad de parcela «a decidir» | `plots.project_id` + `UNIQUE(project_id, code)` | El predio es opcional; la unicidad debe ser por proyecto |
| — | Se quitó el techo de 4 monitoreos | Hallazgo durante T2: validador del dominio y mapeo cortaban en M4 |
| — | Mapeo tolerante a tildes, mayúsculas y espacios | Cada proyecto trae su propio Excel (D6) |

## Limitaciones declaradas

1. Un proyecto que mezcle archivos con y sin código de unidad de muestreo
   recibe dos claves para la misma parcela.
2. Un árbol con predio pero sin parcela no conserva el predio.
3. Los archivos cargados antes de E0 no quedan enlazados a monitoreos.
4. La fecha del monitoreo queda vacía hasta que el ingeniero la registre (E2).
