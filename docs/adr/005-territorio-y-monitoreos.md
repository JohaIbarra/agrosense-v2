# ADR-005 — Territorio y monitoreo como entidades (E0)

- **Estado:** Aceptado
- **Fecha:** 2026-09-21
- **Contexto:** `docs/04-vision-producto.md` convierte AgroSense en una
  plataforma donde cada ingeniero sube los Excel de sus propios proyectos, y
  el análisis exploratorio reproduce lo que hoy hace a mano en las 7 hojas
  del Anexo 1. Tres hallazgos lo impedían con el modelo del Slice 2:

  1. **La ingesta descartaba nueve columnas**, entre ellas las dimensiones de
     esas hojas (diseño florístico, coberturas) y `Codigo de unidad muestreo`,
     la unidad por la que el ML eval gate agrupa la validación cruzada.
  2. **El monitoreo no era una entidad** (`observations.campaign: int`): no
     había dónde guardar su fecha, que el protocolo de estancamiento declara
     como su limitación nº 1.
  3. **El número de monitoreo tenía techo en 4** (validador del dominio y
     mapeo de columnas): el quinto monitoreo de cualquier proyecto se habría
     rechazado.

  Verificado sobre el dataset: diseño, coberturas, unidad de monitoreo y
  predio son **constantes dentro de cada unidad de muestreo** (54 unidades).

- **Opciones consideradas:**
  - *Añadir las columnas a `trees`.* Mínimo cambio, pero repite el mismo
    valor en cada árbol de la parcela y deja sin respuesta dónde vive la fecha
    del monitoreo.
  - *Normalizar territorio y monitoreo* (elegida).
  - *Renombrar además `campaign_files`/`campaign` a `uploads`/`monitoring` en
    todo el código y la API.* Más limpio, pero rompe el contrato y los tests
    del Slice 2 sin ganancia funcional.

- **Decisión:**
  - Tablas `properties` (predio), `plots` (unidad de muestreo, con diseño y
    coberturas), `monitorings` (número, fecha, cuadrilla) y la puente
    `campaign_file_monitorings` (un archivo acumulado trae varios monitoreos).
  - `observations.campaign` → `observations.monitoring_id`;
    `trees.plot_id` / `trees.locality` → `trees.plot_row_id`.
  - **Identidad de la parcela** en el dominio (`domain.rules.plot_key`): el
    código de unidad de muestreo, o `predio/ID Parcela` si el archivo no lo
    trae. La unicidad es **por proyecto**.
  - **Ningún contrato visible cambia**: el dominio sigue viendo
    `Observation.campaign` como número de monitoreo, `TreeRow` expone
    `plot_id` y `locality` como propiedades, y la API solo añade campos.
  - **Mapeo de columnas con cuatro papeles** (fija por árbol, por monitoreo,
    de archivo, ignorada con motivo). Una columna que no cae en ninguno se
    reporta; ya no se descarta en silencio. Las cabeceras se comparan
    normalizadas (sin tildes, mayúsculas ni espacios de más).
  - **Coordenadas**: se guardan tal como vienen. En el dataset de referencia
    son **MAGNA-SIRGAS / Origen Nacional (EPSG:9377)** — es el único sistema
    colombiano con falso origen en ~5 000 000 / 2 000 000, y la proyección
    inversa cae en la cordillera (5,80° N, 75,39° O), coherente con la
    elevación registrada (~2 770 m). El SRID es propiedad del **proyecto**, no
    del árbol: se añade a `projects` en E1, con 9377 por defecto.

- **Consecuencias:**
  - Se pueden reproducir los cortes de las hojas: verificado que la base
    recalcula exactamente los valores del Excel (ver `docs/verificacion-e0.md`).
  - El monitoreo tiene dónde guardar su fecha (la registra el ingeniero en E2).
  - El Slice 4 puede agrupar por parcela en su ML eval gate.
  - **Limitación declarada**: si un proyecto mezcla archivos con y sin código
    de unidad de muestreo, la misma parcela física recibe dos claves.
  - **Limitación declarada**: un árbol con predio pero sin parcela no conserva
    el predio (el formato de campo real siempre trae la parcela).
  - Los archivos cargados antes de E0 no quedan enlazados a monitoreos: no se
    registraba qué monitoreos traía cada uno, y enlazarlos sería inventar
    provenance.
  - El renombrado visible (`campaign_files` → `uploads`) queda para E2, cuando
    la UI consuma esos endpoints.
