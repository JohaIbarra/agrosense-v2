# Deuda técnica — AgroSense v2

Registro de brechas conocidas entre lo que dicen `AGENTS.md` / los ADR y lo
que hace el código. Nada de esto está "olvidado": está **decidido y fechado**.
La regla es la de AGENTS.md — una deuda sin dueño ni gate es un bug latente.

Última revisión: 2026-09-20 (corrección de los bloqueantes R1-R5 de la fase 7).

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
| 1. Tests pasan | ✅ `pytest` (166 locales) + `pytest -m supabase` (4) |
| 2. Lint pasa | ✅ `ruff check src tests` |
| 3. Type checking pasa | ❌ no hay mypy ni pyright configurado |
| 4. Build pasa | ✅ `pip wheel` en el gate de verificación |
| 5. Security checks | ✅ `pip-audit -r requirements.lock.txt` sobre el cierre |
| 6. Arquitectura consistente | ✅ `tests/architecture/` lo verifica en cada corrida |
| 7. Review | proceso, no herramienta |

Queda **solo el 3**. Los gates 4 y 5 se cerraron en la fase 7 (2026-09-20): el
5 hizo falta cerrarlo de verdad porque auditar solo las raíces daba limpio
mientras el entorno traía `anyio 3.7.1` con dos CVE.

El gate 6 era un ítem manual del plan del slice 2 ("verificar que application/
no importa fastapi ni sqlalchemy") y precisamente por ser manual se nos escapó
una violación. Ahora falla solo.

**Por qué el 3 no se cierra ahora:** añadir mypy a un backend ya escrito
produce un lote de errores que no son el objeto de esta corrección, y
`AGENTS.md` ubica la automatización de gates en la fase 8. Cerrarlo ahí es
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

## G — El upload de una campaña tardaba 79.7s contra Supabase — ✅ CERRADO (2026-09-22)

**Cerrado en E2/E3.** `save_ingest` del dataset de referencia (856 árboles,
3146 observaciones): **91.9s → 4.8s**, dentro del presupuesto de
`docs/03-architecture.md` (<5s para ~1k árboles).

**La causa real no era ninguna de las tres anotadas antes.** Perfilando
sentencia a sentencia contra Supabase: los 856 árboles entraban en **una**
sentencia (0.43s) y las 3146 observaciones se partían en **615** (34.9s +
20.1s + 14.7s + …). El motivo: al pasar los dicts por el `insert()` del ORM,
SQLAlchemy agrupa las filas por el conjunto de columnas **no nulas**, y en
campo cada fila tiene un patrón de nulos distinto (un árbol sin copa, otro sin
estado fitosanitario, otro muerto sin medidas). Cada grupo era un viaje de ida
y vuelta contra el pooler. No era el volumen: era la forma de los datos.

**Arreglo** (`adapters/db/repository.py`): `_bulk_insert` usa
`insert(model.__table__)` en vez del `insert()` del ORM, que emite un único
`executemany` sin importar el patrón de nulos. Observaciones: 615 sentencias →
**1** (3146 filas en 1.11s).

**Regresión:** `tests/db/test_ingest_statements.py` cuenta **sentencias**, no
tiempo — un test de reloj contra una DB remota sería inestable. Exige una
sentencia por tabla al insertar y una al actualizar, con árboles de patrones
de nulos deliberadamente distintos.

**Lo que sigue abierto de aquí:** la causa 2 (un `Engine` y un pool nuevos por
request, `deps.py` → `session.py`) **no se tocó**; sigue costando un handshake
TCP+TLS por llamada y es peligrosa con uploads concurrentes. Anotada como
**#N**. La causa 3 (endpoint `async def`) ya estaba corregida.

## I — Un archivo corregido no elimina lo que ya no trae

**Estado:** deuda aceptada (decisión del 2026-09-20). **Dueño:** épica de UI.

La re-subida corrige valores y atributos descriptivos, pero **nunca borra**.
Si el archivo corregido quita 50 árboles que estaban de más, los 50 siguen en
la base: UC7 los devuelve y los conteos de `campaign_files` dejan de describir
el estado del proyecto (cada fila dice lo que traía *su* archivo, no lo que
hay). No existe endpoint de borrado.

**Por qué no se cierra ahora:** eliminar datos ya cargados es una operación
destructiva sin autenticación en el MVP, y merece su propio diseño (¿borrado
lógico? ¿confirmación explícita? ¿quién puede?). Añadirla al vuelo dentro de
una corrección de bloqueantes sería justo el tipo de decisión que este
proyecto evita.

**Gate para cerrarlo:** antes de que la UI muestre conteos por proyecto, o en
cuanto llegue la épica de auth — lo que ocurra primero. Mientras tanto, los
`campaign_files` son el registro fiel de qué archivo trajo qué.

## H — Errores cuyo mensaje es el propio código — ✅ CERRADO (2026-09-20)

Cerrado por R2: `AppError` lleva código y mensaje separados, y todos los
errores de operación viajan con texto accionable. Se conserva la entrada
porque su redacción original contenía un error de diagnóstico que vale la pena
no repetir.

**Estado:** cerrado. **Dueño:** —

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
(`ValueError("DUPLICATE_NAME: ya existe un proyecto llamado 'X'")`).

> **Corrección (2026-09-20, gate de fase 7).** La redacción anterior decía que
> `errors.py` "ya busca el código por prefijo, así que no hay que tocarlo".
> **Es falso.** `errors.py:31` hace `if code in msg` — subcadena sin anclar,
> sobre un mensaje que incluye el nombre de archivo que manda el usuario. El
> arreglo propuesto aquí no solo no bastaba: **agrandaba la superficie**, al
> meter más texto libre en esos mensajes. El hallazgo real es
> `docs/revision-slice2.md` #R2, que subsume a este #H.

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

---

## Deuda nueva del re-scan de seguridad (2026-09-20)

Hallazgos que los revisores clasificaron como MEDIUM y que se aceptan como
deuda con su motivo, en vez de arreglarse dentro de la corrección de
bloqueantes.

### J — El contenido del archivo se refleja íntegro en los errores 422

`domain/errors.py` interpola valores de celda en el mensaje, y ese mensaje
sale tal cual en el 422. Verificado: una celda con `<script>…</script>` vuelve
literal dentro del JSON. **No es XSS hoy** — la respuesta es `application/json`
y no hay frontend — pero es contenido controlado por quien sube el archivo,
reflejado sin límite de longitud. Lo mismo en el 201 vía `WarningDTO.message`.

**Gate:** el slice que estrene la UI. **Mitigado en E2/E3 (2026-09-22):** la
UI ya existe y los avisos se pintan como texto en React (`{aviso.message}`),
que escapa por construcción — no hay `dangerouslySetInnerHTML` en ninguna
parte. Queda abierto lo otro: **acotar la longitud del valor interpolado** en
`domain/errors.py`, que sigue sin límite.

### K — Dos rutas de error se saltan el envelope `{code, message}`

Un multipart sin boundary devuelve `{"detail":"Missing boundary in multipart."}`
(texto de Starlette) y un multipart malformado devuelve el `422` de validación
de FastAPI. Ninguna es alcanzable desde el contrato que consume el frontend, y
ninguna filtra datos, pero contradicen "todo error sale con la misma forma".

**Gate:** cuando se declaren los `responses=` en el OpenAPI (#R9 de la
revisión), que es cuando el envelope pasa a ser contrato verificable.

### L — `defusedxml` es load-bearing y no está declarado

openpyxl usa `defusedxml` si puede importarlo. Aquí está instalado **solo como
transitiva del extra de desarrollo** (vía `pip-audit`), así que una instalación
de producción no lo tendría. Se verificó que la postura XXE **no** depende de
él (expat de CPython 3.12 rechaza entidades no definidas y corta la expansión),
por eso no es bloqueante — pero es exactamente el mismo argumento por el que se
declaró `lxml`.

**Gate:** al preparar el despliegue, declararlo o dejar constancia de que se
evaluó y se descartó.

### M — La sobrescritura de observaciones no tiene historial ni deshacer

Consecuencia directa y aceptada de la decisión de #R1: quien alcance el
endpoint puede reescribir las mediciones de un proyecto, y sin auth en el MVP
eso es cualquiera. La campaña anterior sobrevive como provenance, pero los
**valores** anteriores no. Añadir auth después no recupera lo ya sobrescrito.

**Gate:** la épica de auth. Registrado aquí como riesgo aceptado explícito y
no como detalle enterrado en un docstring.

### N — Un `Engine` y un pool nuevos en cada request

**Estado:** deuda con gate duro. **Dueño:** fase 9 (deploy). **Origen:** era
la causa 2 de #G; al cerrarse #G por otro motivo, se queda sola.

`deps.py` llama a `session.get_engine()` por request y `session.py` construye
un `Engine` nuevo sin caché ni `dispose()`. Cada llamada paga un handshake
TCP+TLS contra el pooler: por eso un `GET /projects/999999`, que toca una
fila, costó 2.5s en la evidencia del slice 2.

Ahora que los endpoints son síncronos y por tanto concurrentes, es además un
riesgo de agotar el cap de conexiones: N uploads en paralelo son N `Engine`
nuevos.

**Arreglo:** cachear el `Engine` a nivel de módulo (es thread-safe y su pool
existe justo para esto) y cerrarlo en el shutdown de la app.

### O — El bundle del frontend pesa 827 kB

**Estado:** deuda anotada. **Dueño:** épica de mapa (E4), que añadirá otra
librería pesada.

`npm run build` avisa: `index-*.js` 827 kB (237 kB gzip), por encima del
límite de 500 kB de Vite. Casi todo es Recharts, que entra entero aunque la
página de proyectos no dibuje ninguna gráfica.

**Arreglo:** `import()` dinámico de la página de análisis (y luego del mapa),
que es donde vive la visualización. No urge: en local no se nota y el gzip es
razonable, pero con el mapa encima conviene hacerlo antes del deploy.

### P — Inyección de fórmulas en el `.xlsx` — ✅ CERRADO el mismo día (2026-09-22)

Encontrado en la revisión de seguridad de E2/E3 y corregido antes del commit.
openpyxl decide el tipo de celda mirando el valor: una cadena que empiece por
`=` queda marcada como fórmula y **Excel la ejecuta** al abrir el reporte. La
especie, el identificador del árbol y las notas de campo vienen del archivo
que sube el usuario, así que bastaba una celda con `=HYPERLINK(...)` para que
el reporte descargado la ejecutara en la máquina del ingeniero.

**Arreglo:** `_cell()` en `adapters/report/xlsx.py` fuerza `data_type = "s"`
en toda celda de texto; es el único camino de escritura del libro.
**Regresión:** `test_field_text_never_becomes_an_excel_formula` recorre las
nueve hojas y exige cero celdas con `data_type == "f"` (antes: 14).

### Q — `npm audit` señala esbuild y vitest (solo desarrollo)

**Estado:** anotado, sin gate. **Dueño:** el mantenimiento de dependencias.

`npm audit --omit=dev` —el gate de AGENTS.md— da **0 vulnerabilidades**: nada
de esto llega al navegador del ingeniero. Con las de desarrollo incluidas
aparecen esbuild ≤0.24.2 (moderada: el servidor de desarrollo responde a
peticiones de cualquier sitio web) y vitest ≤3.2.5. El arreglo exige
`npm audit fix --force`, que sube Vite de major y puede romper la
construcción; se hace con su propio ciclo, no de paso. Mientras tanto: no
exponer el servidor de desarrollo fuera de `localhost`.

### R — El payload del mapa crece linealmente con los árboles

**Estado:** límite conocido, no deuda. **Dueño:** cuando exista un proyecto
grande de verdad.

`GET /projects/{id}/map` devuelve todos los árboles y todos los monitoreos en
una respuesta: ~330 bytes por árbol (279 KB para los 856 del Anexo). A 10 000
árboles serían ~3 MB, y ahí toca paginar por predio o servir teselas
vectoriales. Está escrito en ADR-009 para que no se descubra en producción.

### S — Una consulta de NDVI larga puede pasar del minuto

**Estado:** límite conocido con tope puesto. **Dueño:** el día que haga falta
barrer años de histórico.

Medido: ~0,8–1,6 s por (escena, predio). Con el tope por defecto (6 escenas ×
3 predios) son ~18 s; con el máximo admitido (24 escenas) pasaría del minuto y
chocaría con el timeout de proxy de un free tier. Por eso `max_scenes` es
explícito, la operación es **idempotente** (lo ya medido no se vuelve a pedir)
y una caída a mitad guarda lo conseguido.

**Arreglo cuando toque:** es el caso de uso que sí justificaría la cola
(ADR-010), junto con la ingesta. Hoy no se paga esa infraestructura por una
consulta que el ingeniero hace de vez en cuando.

