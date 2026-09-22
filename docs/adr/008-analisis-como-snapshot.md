# ADR-008 — El análisis exploratorio es un snapshot versionado (E3)

- **Estado:** Aceptado
- **Fecha:** 2026-09-22
- **Contexto:** El ingeniero sube **solo datos crudos de campo** (una fila por
  árbol, como la hoja `Monitoreo_4`). Las otras siete hojas del Anexo 1
  —Composición, Alturas, Diámetro de copa, Supervivencia, Estado fito, Edades
  y DAP— son el análisis que hoy hace a mano, y AgroSense debe reproducirlas
  desde el primer monitoreo, con sus tablas y sus gráficas, y poder
  descargarlas en un `.xlsx`.

  Dos preguntas quedaban abiertas: **dónde vive el resultado** y **quién lo
  calcula**. La segunda tiene una respuesta obligada por `AGENTS.md`
  («business rules must not be duplicated in the frontend»): si la página
  calculara sus propias cifras, el `.xlsx` y la pantalla podrían discrepar —
  exactamente el error de v1 con el preprocesamiento duplicado.

- **Opciones consideradas:**
  - *Calcular al vuelo en cada lectura.* Siempre coherente con los datos, sin
    tabla nueva. Pero un informe que cita «en M3 la supervivencia era 82 %»
    deja de ser verificable en cuanto alguien recarga un archivo, y no hay
    dónde anclar la trazabilidad que pide `AGENTS.md` (Data provenance).
  - *Guardar el análisis normalizado en tablas.* Consultable con SQL, pero el
    análisis no se consulta por dentro: se calcula entero y se consume entero.
    Serían ~15 tablas para reconstruir un objeto que ya viene hecho.
  - *Snapshot JSON versionado* (elegida).

- **Decisión:**
  1. **`monitoring_analyses`**: un snapshot por monitoreo (`UNIQUE(monitoring_id)`)
     con `payload` JSONB, `analysis_version` e `input_hash` (SHA-256 de los
     árboles y observaciones que lo produjeron). Recalcular reemplaza.
  2. **Quién calcula**: `adapters/analysis/` (pandas). Las *definiciones* —qué
     es una plántula, qué estados fitosanitarios existen, desde cuántos
     árboles un porcentaje dice algo— viven en `domain/analysis_rules.py`,
     puras y testeables. La agregación no contamina el dominio y la regla de
     negocio no depende de pandas.
  3. **Forma del payload (contrato interno)**: secciones → **tablas tipadas**
     (cada columna declara `kind` text/int/decimal/percent y sus decimales) y
     **gráficas que referencian una tabla por su id**. La página y el `.xlsx`
     se construyen de ahí: **ninguno de los dos calcula nada**, solo presentan.
     Los porcentajes viajan en escala 0–100 en ambos destinos.
  4. **Cuándo se calcula**: al terminar cada ingesta, para *todos* los
     monitoreos del proyecto (un archivo nuevo corrige monitoreos anteriores, y
     el análisis de Mk depende de Mk−1). En lectura, un snapshot de otra
     `analysis_version` se recalcula antes de responder: nunca se sirve un
     resultado de una definición vieja.
  5. **Sin cola de trabajos.** ADR-009 queda pendiente: medido contra Supabase,
     el análisis de los cuatro monitoreos del dataset de referencia cuesta
     ~7 s y guardar sus snapshots ~2 s, sobre una carga que ahora tarda ~5 s
     (era 92 s, ver #G). Con ~18 s de request completa no hace falta
     infraestructura nueva; cuando un proyecto la necesite, el caso de uso ya
     está aislado y solo cambia quién lo invoca.

- **Consecuencias:**
  - Un informe (E9) puede citar un snapshot y seguir siendo cierto, porque el
    `input_hash` dice de qué datos salió.
  - Cambiar cualquier definición obliga a subir `ANALYSIS_VERSION`; los
    snapshots viejos se recalculan solos al abrirlos.
  - El payload del dataset de referencia pesa ~220 KB por monitoreo: cómodo
    para JSONB y para una respuesta HTTP, pero no es un formato para crecer
    sin control. Si una sección futura lo multiplicara, se pagina por sección.
  - El motor **no** lleva puerto (ADR-003: interfaz solo donde hay variación
    real). Se inyecta por parámetro, como los repositorios.
