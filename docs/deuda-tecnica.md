# Deuda técnica — AgroSense v2

Registro de brechas conocidas entre lo que dicen `AGENTS.md` / los ADR y lo
que hace el código. Nada de esto está "olvidado": está **decidido y fechado**.
La regla es la de AGENTS.md — una deuda sin dueño ni gate es un bug latente.

Última revisión: 2026-09-20 (cierre de las correcciones A/B/C del slice 2).

## Cerrado en el slice 2

| # | Hallazgo | Resolución |
|---|---|---|
| A | `application/` importaba `adapters/` (violación de ADR-003) | DTOs propios en `application/dtos.py`, `CampaignData` movido a la capa interna, puerto `CampaignSource` con el adapter Excel afuera. Gate ejecutable: `tests/architecture/test_layer_dependencies.py` |
| B | `pytest` sin argumentos golpeaba Supabase y se colgaba | Repos contra SQLite en memoria (corren siempre), marker `supabase` + `addopts` para el smoke explícito. Guard: `tests/architecture/test_no_remote_db_by_default.py` |
| C | `pyproject.toml` traía psycopg2, ADR-002 dice psycopg3 | `psycopg[binary]` único driver; `session.normalize_database_url()` fuerza `postgresql+psycopg://` en un solo punto |
| F | `deaths` es ambiguo en el contrato | Semántica documentada en el OpenAPI (`schemas._DEATHS_DESC`) + test de contrato. Ver #F1 abajo para lo que queda |

---

## D — El archivo crudo de la campaña no se guarda

**Estado:** deuda aceptada. **Dueño:** épica de storage / ADR-005 si aplica.

ADR-004 §5 exige "cada archivo crudo se guarda versionado + hash", y
`AGENTS.md` (Data provenance) pide poder trazar cada análisis a su dataset
origen. Hoy se persiste **solo el sha256**: `upload_campaign` calcula el hash
de los bytes y los descarta. `adapters/storage/` (previsto en ADR-003) no existe.

**Consecuencia real:** el sha256 no es verificable contra nada. Si alguien
cuestiona una ingesta, no se puede recomputar desde el archivo original. Y
docs/02-domain.md §6 dice que los errores se corrigen "re-subiendo la campaña
(auditable)" — la auditoría es parcial sin el crudo.

**Por qué no se cierra ahora:** ningún caso de uso del slice 2 consume el
archivo crudo, y la decisión de destino (disco del servicio vs bucket
S3-compatible de Supabase Storage) es justamente el seam que ADR-003 dejó
abierto. Abrirlo aquí sería ampliar el alcance de una corrección de
dependencias.

**Gate para cerrarlo:** antes de la primera épica de ML que entrene con datos
subidos por usuarios. Un modelo versionado cuyo dataset de origen no se puede
recuperar incumple la regla de reproducibilidad de `AGENTS.md`.

## E — Tres de los siete gates de "Completion" no son ejecutables

**Estado:** parcialmente cerrado. **Dueño:** fase 8 (CI/CD).

`AGENTS.md` §Completion exige 7 checks. Situación:

| Gate | Estado |
|---|---|
| 1. Tests pasan | ✅ `pytest` (133 locales) + `pytest -m supabase` (4) |
| 2. Lint pasa | ✅ `ruff check src tests` |
| 3. Type checking pasa | ❌ no hay mypy ni pyright configurado |
| 4. Build pasa | ❌ no se construye el paquete en ningún gate |
| 5. Security checks | ❌ no hay escaneo de dependencias (pip-audit) |
| 6. Arquitectura consistente | ✅ **nuevo**: `tests/architecture/` lo verifica en cada corrida |
| 7. Review | proceso, no herramienta |

El gate 6 era un ítem manual del plan del slice 2 ("verificar que application/
no importa fastapi ni sqlalchemy") y precisamente por ser manual se nos escapó
una violación. Ahora falla solo.

**Por qué 3/4/5 no se cierran ahora:** añadir mypy a un backend ya escrito
produce un lote de errores que no son el objeto de esta corrección, y
`AGENTS.md` ubica la automatización de gates en la fase 8. Cerrarlos ahí es
seguir el workflow, no postergarlo.

**Nota puntual para cuando entre mypy:** `routes/projects.py` tiene un
`# type: ignore[arg-type]` en el registro del handler y dos endpoints que
terminan sin `return` explícito tras `raise_for_value_error` (que siempre
lanza, pero el type checker no lo sabe — se resuelve tipándolo `NoReturn`).

## F1 — Falta una métrica de mortalidad por árbol

**Estado:** deuda acotada. **Dueño:** épica 2 (riesgo de mortalidad).

`deaths` ya declara su semántica en el OpenAPI, pero sigue siendo un conteo de
**observaciones** con estado muerto (340 en el dataset de referencia), no de
árboles distintos (138, el 16% que documenta discovery §6). Los dos números son
correctos y miden cosas distintas.

**Qué falta:** cuando la épica 2 necesite mortalidad por árbol, el conteo se
deriva en su capa (`ml/features.py` o una query de analítica), **no** se agrega
un campo más al upload. La ingesta reporta lo que ingirió; la analítica calcula.

**Riesgo si se ignora:** alguien grafica "340 muertes de 856 árboles" (40%) y
contradice el 16% del discovery en la misma pantalla.

## G — El upload de una campaña tarda 79.7s contra Supabase

**Estado:** deuda con gate duro. **Dueño:** fase 9 (deploy) — bloquea.

Medido en la demostración de Task 6 (`docs/verificacion-slice2.md`): subir el
dataset de referencia (856 árboles, 3146 observaciones) por la API real tardó
**79.7s**. `docs/03-architecture.md` fija el presupuesto en **<5s para ~1k
árboles**; son 16x.

**Causa:** no es el parseo — el mismo ingest sobre SQLite corre en ~2s. Son
~900 round-trips al session pooler, porque `bulk_save_objects(...,
return_defaults=True)` necesita el id de cada árbol para enlazar sus
observaciones.

**Por qué no se cierra ahora:** el flujo es funcionalmente correcto y el gate
del slice 2 es de comportamiento, no de rendimiento. Optimizar la escritura es
un cambio con su propio ciclo TDD.

**Gate para cerrarlo:** antes del deploy. Un request síncrono de 80s excede el
timeout de proxy de la mayoría de free tiers, así que esto **rompe el producto
desplegado**, no solo lo hace lento. Dos salidas:

1. Insertar los árboles en una sola sentencia y resolver los ids con un
   `SELECT` por `tree_id` (barato, no cambia arquitectura).
2. Mover la ingesta a job asíncrono — es el "job queue (requisito futuro, ADR
   nuevo)" que `docs/03-architecture.md` ya anticipó. Sería ADR-005.

Empezar por (1): si baja de 5s, (2) no hace falta y el ADR no se escribe.

## H — Errores cuyo mensaje es el propio código

**Estado:** deuda menor. **Dueño:** cierre de la épica de UI, o antes si molesta.

`AGENTS.md` pide mensajes accionables para un ingeniero de campo sin ayuda
técnica. Se cumple a medias:

```json
{"detail": {"code": "PROJECT_NOT_FOUND", "message": "Proyecto 999999 no existe"}}   ← route, bien
{"detail": {"code": "DUPLICATE_NAME",    "message": "DUPLICATE_NAME"}}              ← ValueError, mal
```

Los errores que nacen como `ValueError("CODIGO")` en repos y use cases llegan
al cliente con el código repetido como mensaje. Afecta a `DUPLICATE_NAME`,
`DUPLICATE_FILE` y al `PROJECT_NOT_FOUND` que lanza UC2.

**Arreglo:** que el `ValueError` lleve el texto accionable
(`ValueError("DUPLICATE_NAME: ya existe un proyecto llamado 'X'")`) — el mapeo
de `errors.py` ya busca el código por prefijo, así que no hay que tocarlo.

---

## Desalineaciones de documentación

Resueltas en el gate de Task 6 (2026-09-20):

- ~~`README.md` decía "Fase 1 (Discovery) completada"~~ → estado real por slice
  y sección "Cómo correr".
- ~~`docs/briefing_opus.md` listaba como commiteado lo que no lo estaba~~ →
  reescrito contra el repo real.

Pendientes (no bloquean código):

- `docs/superpowers/plans/2026-09-14-slice2-persistencia-api.md` dice "Neon" en
  todo el texto; ADR-002 fue revisado a Supabase **después** de escribirlo. El
  plan ya se ejecutó, así que es un documento histórico: corregirlo reescribiría
  el registro de lo que se decidió entonces. Se deja como está, anotado aquí.
- `ProjectRepository.list_all()` existe sin endpoint `GET /projects` que lo
  exponga: la futura pantalla de proyectos no tiene de dónde listar. Se resuelve
  en el slice que estrene la UI de proyectos, con su test de contrato.
