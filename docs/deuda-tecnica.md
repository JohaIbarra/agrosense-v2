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

---

## Desalineaciones de documentación (pendientes, no bloquean código)

- `docs/superpowers/plans/2026-09-14-slice2-persistencia-api.md` dice "Neon" en
  todo el texto; ADR-002 fue revisado a Supabase **después** de escribirlo.
- `docs/briefing_opus.md` lista bajo "commiteado en master" archivos de la
  Task 5 que siguen sin commitear, y reporta "92 tests en 12s" (hoy son 133
  locales en ~45s).
- `README.md` sigue diciendo que el estado es "Fase 1 (Discovery) completada";
  van dos slices. Actualizarlo es parte del gate de Task 6.
- `ProjectRepository.list_all()` existe sin endpoint `GET /projects` que lo
  exponga: la futura pantalla de proyectos no tiene de dónde listar.
