# ADR-007 — El Referente científico es independiente del grafo de proyectos (E5)

- **Estado:** Aceptado
- **Fecha:** 2026-09-27
- **Contexto:** El Slice 5 pasó a llamarse **Referente científico**
  (`docs/04-vision-producto.md` §4/§6.7): los efectos por especie y por
  parcela que salen de los modelos mixtos (`lme4::glmer` binomial sobre
  `Monitoreo_4`, 856 árboles, 30 especies) no describen UN proyecto, describen
  el programa completo. UC-AN3 (`GET /projects/{id}/reference-contrast`)
  además necesita cruzar las especies plantadas de un proyecto CUALQUIERA
  contra ese referente, así que el referente tiene que poder leerse sin pasar
  por un proyecto.

  Dos preguntas quedaban abiertas al revisar el slice: si el referente debía
  colgar del grafo de `projects` (FK), y qué pasa cuando se publica una
  versión nueva mientras la vieja sigue citada en algún informe.

- **Opciones consideradas:**
  - *Colgar `reference_species_effects` de un proyecto* (FK a `projects`):
    calzaría con el resto del esquema, pero el referente no es de NINGÚN
    proyecto en particular — es la evidencia del dataset de referencia
    completo. Forzar una FK obligaría a inventar un "proyecto dueño" ficticio
    o a duplicar los efectos por proyecto, ninguna de las dos es cierta.
  - *Publicar reemplazando en el sitio* (como hacía `AnalyticsRepository.replace_all`
    antes de E5): una recarga borraba la versión anterior sin rastro. Rompe
    trazabilidad (AGENTS.md, Data provenance) y un informe que cita un OR deja
    de ser verificable en cuanto alguien vuelve a correr
    `scripts/load_analytics.py`.
  - *Referente versionado, sin FK a proyectos, con exactamente una versión
    activa* (elegida).

- **Decisión:**
  1. **Sin FK hacia `projects`.** `reference_models` (una fila por corrida de
     los modelos mixtos) y las tres tablas de efectos que cuelgan de ella
     (`reference_species_effects`, `reference_plot_effects`,
     `variance_components`, todas por `reference_model_id`) no tienen ninguna
     columna ni constraint que apunte a `projects`. Se protege con un test de
     regresión (`test_reference_tables_have_no_project_foreign_key`,
     `tests/db/` y `tests/smoke/`).
  2. **Publicar siempre añade una versión; nunca borra** (UC-R2,
     `ReferenceRepository.publish_version`). La versión anterior sigue en la
     base, consultable por su `reference_model_id`, fuera de lectura por
     defecto.
  3. **Exactamente una versión activa**, forzado en dos capas: la aplicación
     desactiva con un `UPDATE` masivo (`is_active=False` en todas las filas
     activas) antes de insertar la nueva, y la base lo hace cumplir con un
     índice único parcial —`uq_reference_models_single_active` en
     `reference_models(is_active) WHERE is_active`— para que la garantía no
     dependa solo de que `ReferenceRepository` sea la única puerta de
     escritura. `version` también es única (`uq_reference_models_version`):
     dos corridas no pueden reclamar el mismo identificador.
  4. **Contraste por nombre normalizado, lectura de un solo sentido.**
     UC-AN3 cruza `trees.species` (por proyecto) contra
     `reference_species_effects` de la versión activa, normalizando ambos
     lados con la misma `normalize_level`
     (`adapters/analytics/effects_loader.py`) — la ingesta del proyecto solo
     hace `.strip()`, así que un NBSP interno sobreviviría sin normalizar y
     una especie que sí está en el referente parecería que no. La dependencia
     va en un solo sentido: un proyecto puede leer el referente, el referente
     nunca sabe qué proyectos existen.
  5. **Sin referente publicado, UC-AN3 lo dice explícitamente.** Si no hay
     ninguna versión activa, el caso de uso levanta
     `AppError("REFERENCE_NOT_LOADED")` (404) en vez de responder que ninguna
     especie tiene referencia — esas son afirmaciones distintas: la primera
     es "el referente no existe todavía", la segunda sería "el referente
     existe y no cubre esta especie".

- **Consecuencias:**
  - El referente puede evolucionar (nuevas corridas del modelo mixto) sin
    tocar ni un proyecto, y un proyecto puede consultarlo sin saber cómo se
    calculó.
  - Cualquier informe que cite un efecto puede anclarse a su
    `reference_model_id`: la versión que lo produjo sigue en la base aunque
    se publique una nueva.
  - Pendiente (fuera de alcance de E5):
    - La API no expone todavía la versión activa en sus respuestas
      (`reference_models.version`/`.id`); un informe hoy no puede citar CUÁL
      versión leyó sin consultar la base directamente.
    - `normalize_level` vive en `adapters/analytics/effects_loader.py`, junto
      al loader del referente, no en `domain/`. Debería moverse al dominio y
      aplicarse en la ingesta (`wide_to_long.py`) para que
      `ProjectSpeciesRepository` no tenga que normalizar en el momento de
      leer.
