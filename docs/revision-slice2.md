# Revisión — Slice 2, fase 7 (gate único)

`AGENTS.md` define la fase 7 como **un solo gate**: code review + checklist de
arquitectura + security scan. Ejecutado el **2026-09-20** sobre el rango
`a871601..88347e5`.

**Veredicto de la primera pasada: NO PASA.** Ambos revisores independientes
concluyeron "with fixes", y el bloqueante principal fue el mismo desde los dos
ángulos. Según `AGENTS.md` ("ningún slice sale del loop sin pasar los TRES
gates"), el slice 2 volvió al loop en la fase 5.

---

## Segunda pasada (2026-09-20) — estado de los bloqueantes

R1-R5 se corrigieron y se volvió a pasar el gate completo: code review y
security scan independientes sobre el diff de arreglos.

| | Estado | Cómo se cerró |
|---|---|---|
| **R1** | ✅ | Ingesta idempotente. Mismo SHA → 409; SHA distinto → campaña nueva y la anterior intacta. La identidad del árbol que diverge **rechaza la carga** con `SPECIES_MISMATCH` / `TREE_IDENTITY_MISMATCH` en vez de descartarse en silencio; lo descriptivo sí se corrige. Lo que no se borra queda como deuda #I |
| **R2** | ✅ | `AppError` lleva el código como atributo. 391 cuerpos mutados → mensaje constante, cero texto de librería |
| **R3** | ✅ | `def` en vez de `async def`, con test de forma |
| **R4** | ✅ | Presupuesto de **celdas de hoja** (lo que acota el coste), ratio contra los bytes reales, `except` ancho, y middleware ASGI que corta el cuerpo antes del parseo |
| **R5** | ✅ | `requirements.lock.txt` con el cierre completo (64 paquetes) auditado por `pip-audit`: sin avisos |

La segunda pasada encontró cuatro defectos **en los propios arreglos** —el más
grave, un `.xlsx` de 4.8 KB que pasaba las guardas de contenedor y costaba
11.8s y 370 MB porque declaraba una hoja enorme con tres celdas sueltas—
además de una regresión introducida al sanear los errores: el fallo más común
de campo (columnas equivocadas) había quedado como `BAD_REQUEST` genérico.
Todos corregidos, todos con test que muerde al revertir.

**R6-R11 y los menores siguen abiertos**, registrados en `docs/deuda-tecnica.md`.

### Tercera pasada — cierre

Revisión independiente acotada a R1-R5 y al middleware. Veredicto: R1, R2, R3
y R5 resisten el ataque; **R4 no**. La guarda de coste validaba el elemento
`<dimension>` declarado, y pandas llama `reset_dimensions()`: la declaración es
decorativa y el coste no. Bastaba **borrarla** para pasar la guarda y seguir
costando decenas de segundos (medido por el revisor: 200000×500 → 21.7s
end-to-end desde 4.8 KB).

Corregido sustituyendo `pd.read_excel` por un lector que **cuenta celdas
mientras las materializa** y aborta al pasar `MAX_SHEET_CELLS`. Ya no se lee
ninguna declaración del atacante, así que las cinco variantes de bypass
colapsan en el mismo camino. Verificado sobre cuatro de ellas:

```
original (declara enorme)      4864B  rechazado  0.06s
sin <dimension>                4849B  rechazado  0.06s
<dimension> mentirosa A1:B2    4862B  rechazado  0.05s
<dimension ref="A1">           4856B  rechazado  0.05s
```

Efecto colateral: el lector acotado es **3x más rápido** que el de pandas
(0.39s vs 1.19s sobre el dataset real), y la suite bajó de 81s a 25s.

## Cómo se ejecutó

| Parte | Quién | Método |
|---|---|---|
| Code review | reviewer independiente (skill `requesting-code-review`) | contexto acotado + diff, sin historial de sesión |
| Security scan | reviewer independiente (skills `security-review` + `secure-code-review`) | ASVS 4.0.3 / CWE, con exploits ejecutados |
| Checklist de arquitectura | esta sesión | reglas de `AGENTS.md` + `alembic check` |

Ninguno de los dos revisores trabajó sobre el otro. Los hallazgos que aparecen
en ambas columnas se descubrieron por separado.

Todo lo marcado **verificado aquí** se reprodujo en esta sesión, no se aceptó
por el informe.

---

## Bloqueantes

### R1 — El segundo upload a un proyecto devuelve 500
`adapters/db/repository.py:111-128` · `models.py:76-78` · `routes/projects.py:135`

Reportado por los dos revisores (code review Crítico #1, security SCR-001).
**Verificado aquí:**

```
upload 1 -> 201
upload 2 -> 500
```

`save_ingest` siempre inserta `TreeRow` nuevos. El segundo archivo choca contra
`UNIQUE(project_id, tree_id)`; el `IntegrityError` no es `ValueError`, así que
`routes/projects.py:135` no lo atrapa y nadie lo mapea.

Por qué bloquea: `docs/02-domain.md` §6 promete que los errores de datos se
corrigen **re-subiendo la campaña**, y `CampaignFile` tiene clave única
`(project_id, sha256)` precisamente para admitir varios archivos por proyecto.
El modelo promete N campañas y el escritor soporta una. El flujo de corrección
documentado es inalcanzable hoy, y falla como 500 sin `{code, message}`.

El revisor de seguridad añadió el ángulo de abuso: sin auth, un archivo de
<10 KB con un `tree_id` cualquiera **bloquea permanentemente** la carga real de
ese proyecto, y no hay endpoint de borrado (`DELETE /projects/1` → 405) para
deshacerlo. Daño irreversible, que es peor que "CRUD sin autenticar".

**Decisión pendiente (dominio, no técnica):** qué significa un segundo upload.
El archivo ancho contiene M1-M4 completo, así que "otra campaña" y "corrección
del mismo dato" son el mismo gesto físico. Opciones: reemplazar la campaña
anterior, coexistir versionadas, o rechazar con código accionable.

### R2 — El nombre de archivo elige el código de estado HTTP
`adapters/api/errors.py:29-35` · `adapters/ingester/excel_source.py:39-42`

Reportado por los dos (code review #2, security SCR-005, CWE-807 / ASVS V7.4.1).
**Verificado aquí:**

```
bad.xlsx                 -> 400  INVALID_FILE
DUPLICATE_FILE.xlsx      -> 409  DUPLICATE_FILE
PROJECT_NOT_FOUND.xlsx   -> 404  PROJECT_NOT_FOUND
TREE_NOT_FOUND.xlsx      -> 404  TREE_NOT_FOUND
```

`if code in msg` es una subcadena sin anclar sobre un mensaje que interpola el
filename crudo. Además el cuerpo devuelve la excepción literal de pandas/openpyxl,
contra la regla "external errors are sanitized" de `AGENTS.md`.

Por qué bloquea ahora y no después: hoy el daño es un status mentiroso. Cuando
llegue la épica de auth, cualquier `ValueError("FORBIDDEN")` entra a la misma
tabla de subcadenas y **el nombre de archivo elegiría el resultado de
autorización**. Arreglarlo ahora es casi gratis; después obliga a auditar cada
código del diccionario.

Este hallazgo **subsume el #H del registro de deuda**, cuyo arreglo propuesto
partía de una premisa falsa (ver la corrección en `deuda-tecnica.md`).

### R3 — El endpoint de upload es `async def` y congela el worker
`routes/projects.py:118-138` (security SCR-003, CWE-400)

**Verificado aquí:** es el único `async def` de los seis endpoints, y su único
`await` es `file.read()`. Todo lo demás — `pd.read_excel`, `wide_to_long`, la
construcción de entidades y cada round-trip bloqueante de `save_ingest` — corre
en el event loop. FastAPI no descarga una corrutina al threadpool.

Durante los 79.7s del upload, el worker **no atiende ninguna otra request**.

Esto es, literalmente, la tercera lección de v1 escrita en `AGENTS.md:132`:
*"v1 ejecutó todo el pipeline ML síncrono en un endpoint `async`"*. La regla
existe en el repo y el slice 2 la repitió.

Arreglo: una línea (`async def` → `def`, `file.file.read()`).

### R4 — Upload sin límite de tamaño ni validación de tipo
`routes/projects.py:123` · `excel_source.py:36` (security SCR-002, CWE-770/409,
ASVS V12.1.1 y V12.1.2)

**Verificado aquí:** no existe ningún límite en el backend (`grep` de
`max_size`/`content-length`/`MAX_*` → solo `MAX_CONTRACTION_M`, que es de dominio).
No hay middleware ni configuración de despliegue en el repo que lo acote aguas
arriba.

El revisor midió la amplificación: un `.xlsx` de 279.8 KB expande a 31.4 MB de
XML (110x) y consume 24.3s de CPU. `.xlsx` es un ZIP, así que la bomba de
descompresión es el caso normal, no el exótico. `AGENTS.md` pide explícitamente
"file uploads are validated".

### R5 — Dependencias con CVE conocido en la superficie de upload
`pyproject.toml`

**Verificado aquí** (versiones instaladas y el tope que impone FastAPI):

| Paquete | Instalado | Situación |
|---|---|---|
| `starlette` | 0.37.2 | CVE-2024-47874 (DoS por multipart sin acotar). Corregido en 0.40.0 |
| `python-multipart` | 0.0.9 | CVE-2024-53981 (DoS de CPU por boundary malformado). Corregido en 0.0.18 |
| `fastapi` | 0.115.0 | declara `starlette<0.39.0,>=0.37.2` → **el arreglo de starlette es inalcanzable sin subir FastAPI** |

Las dos CVE caen exactamente sobre el único endpoint de upload del slice. No se
corrió `pip-audit` (no está instalado y no se instaló nada durante la revisión):
la tabla sale de las versiones inspeccionadas, y debe confirmarse con un escaneo
real — que es justamente el gate 5 de `AGENTS.md` que `deuda-tecnica.md` #E
registra como no ejecutable.

---

## Importantes (no bloquean el gate, sí el cierre ordenado)

- **R6 — Un `Engine` y un pool nuevos por request.** `deps.py:17` → `session.py:54`.
  **Verificado aquí:** 3 requests → 3 llamadas a `create_engine()`. Anula el
  pooling y el `pool_pre_ping`, agota el cap de conexiones del pooler bajo
  concurrencia, y explica los 2.5s de los GET triviales en la evidencia de
  Task 6. Incorporado como segunda causa de #G.
- **R7 — El envelope de error 422 no tiene tests ni los campos del contrato.**
  El plan (Task 5) especifica `{code, message, tree_id, campaign}`; el handler
  emite solo `{code, message}`, porque las subclases de `DomainError` entierran
  árbol y campaña dentro del string (las clases de *warning* sí los guardan como
  atributos). Y ningún test ejercita `domain_error_handler`: los tres 422 del
  suite son validación de pydantic, otro camino. Es la única parte del slice sin
  cobertura, y es la conducta central de UC2.
- **R8 — `test_upload_result_invalid_shape` documenta una respuesta que no existe.**
  `tests/api/test_contract.py:86-94` afirma un 422 con `valid=False` + `errors`;
  la API devuelve `{"detail": {code, message}}`. `UploadResultResponse.valid` está
  hardcodeado a `True` y `.errors` a `[]`: ambos campos son código muerto.
- **R9 — Los errores no aparecen en el OpenAPI.** Ninguna route declara
  `responses=`, así que 400/404/409 son invisibles en el contrato. `AGENTS.md`
  exige que el contrato especifique los errores, y que el frontend no invente
  estructura: hoy no le queda otra.
- **R10 — `alembic upgrade head` revienta si la password lleva `%`.**
  `alembic/env.py:17` pasa la URL por ConfigParser. **Verificado aquí:**
  `ValueError: invalid interpolation syntax`. Es el paso uno del README para
  cualquier entorno nuevo. Lo afila el propio slice: `test_session_driver.py:47`
  afirma que una URL con `p%40ss` sobrevive la normalización — cierto, y su único
  consumidor real se atraganta con ella.
- **R11 — Cuatro de los seis endpoints saltan `application/`.** Hallazgo del
  checklist de arquitectura. `routes/projects.py:94,147,178,211` llaman al
  repositorio directo: UC3 (ver historial) y UC7 (traza de árbol) existen en
  `docs/02-domain.md` pero no como casos de uso. No es la flecha invertida que
  corregimos — `adapters` puede usar `adapters` — pero deja lógica de lectura en
  el adapter y le quita a UC3/UC7 el lugar donde vivirán sus reglas.

## Menores

Registrados sin desarrollar: truncamiento silencioso de `VARCHAR` que SQLite no
detecta (el único punto donde el paso a SQLite sí perdió cobertura, y está sobre
la ruta de entrada del usuario); `save_ingest` devuelve un `dict` sin tipo que
`application/` consume por claves; el Protocol `CampaignSource` no lo verifica
nadie hasta que exista mypy; los dos guards de arquitectura ignoran imports
relativos y `create_engine` directo; `colonization` es columna `JSON` para un
campo `str | None`; `bulk_save_objects` es legacy en SQLAlchemy 2.x;
`ObservationResponse` entró sin test de contrato; `lxml` está instalado pero no
declarado (openpyxl cambia de backend XML según si puede importarlo, así que el
parser probado no es necesariamente el de producción); `psycopg2-binary` sigue
instalado pese a ADR-002.

---

## Checklist de arquitectura (`AGENTS.md`)

| Regla | Estado |
|---|---|
| Lógica de negocio en domain/application | ✅ |
| Domain sin dependencias de infra | ✅ verificado por AST en cada corrida |
| Toda capacidad de negocio es un caso de uso | ⚠️ R11: UC3 y UC7 no existen |
| Esquema derivado del dominio | ⚠️ menor: `colonization` JSON vs `str` |
| Todo cambio de esquema por migración | ✅ `alembic check`: sin operaciones pendientes |
| La DB no sustituye lógica de negocio | ✅ |
| Contrato primero, con errores especificados | ❌ R9: los errores no están en el OpenAPI |
| La API no contiene lógica de negocio | ⚠️ R11 |
| Nunca exponer excepciones internas | ❌ R2: se devuelve la excepción de pandas |
| Validar toda entrada externa | ❌ R4: el upload no valida tamaño ni tipo |
| Reglas de dominio con tests unitarios | ✅ |
| Flujos críticos de API con tests de integración | ⚠️ R7: falta el de rechazo 422 |
| Secretos fuera del control de versiones | ✅ auditado sobre todas las refs |
| Errores externos saneados | ❌ R2 |
| Dependencias sin vulnerabilidades conocidas | ❌ R5 |

## Lo que la revisión confirmó que está bien

Vale registrarlo, porque el gate no es solo una lista de defectos:

- **Cero sinks de inyección.** Todas las queries son `select()` de SQLAlchemy 2.0
  con parámetros ligados: ni f-strings, ni `text()`, ni `.raw()`. Sin `eval`,
  `exec`, `pickle`, `yaml.load`, `subprocess` ni `shell=True` en el backend.
- **XXE bloqueado, comprobado con exploit**, no asumido: un `sheet1.xml` con
  `<!ENTITY xxe SYSTEM "file:///...">` devolvió `400 INVALID_FILE: undefined
  entity`. Las bombas de expansión de entidades las corta expat de CPython.
- **El filename nunca toca una API de rutas**: `../../../../etc/passwd` como
  nombre es inerte. Sin traversal.
- **El scoping por proyecto es correcto aun sin auth**: `get_tree_row` filtra por
  `project_id` *y* `tree_row_id`, así que no hay IDOR entre proyectos adivinando
  ids. Es la forma correcta para cuando llegue la autenticación.
- **Sin mass assignment**, lecturas acotadas (`limit` ≤ 500), y `response_model`
  explícito campo a campo.
- **Sin secretos en el historial**: `git log --diff-filter=A` sobre todas las refs
  no encuentra ningún `.env`; la cadena de conexión nunca llega a una respuesta.
- **La inversión de dependencia es real**, no un movimiento de archivos: el
  revisor comprobó la dirección, no los ficheros.
- **La documentación es honesta**: el gate de Task 6 publicó el fallo de 79.7s en
  vez de enterrarlo.
