## 012 — IA local con Ollama, snapshot como única entrada

- **Estado:** Aceptado
- **Fecha:** 2026-09-27
- **Contexto:** E9 (docs/04-vision-producto.md §9) pide un borrador de
  informe por monitoreo (UC-IA1 resumen, UC-IA2 comparativo, UC-IA3
  exportar). AGENTS.md exige que la lógica de negocio no dependa de
  infraestructura y que el LLM nunca calcule una métrica (docs/04,
  principio 2: "AgroSense calcula, el LLM redacta"). D4 (docs/04 §12) dejó
  resuelto que Ollama corre local en desarrollo, tras un puerto, con
  producción abierta hasta conocer el entorno de despliegue.

- **Opciones consideradas:**
  - *Mandarle al LLM los datos crudos (árboles, observaciones) y que
    calcule las cifras del informe.* Más "inteligente" en apariencia, pero
    viola el principio 2 directamente y reintroduce el riesgo de v1: un
    modelo de lenguaje no es un motor estadístico confiable, y una cifra
    mal calculada en un informe técnico es un riesgo real.
  - *Una tabla `comparison_analyses` con su propio informe.* Rechazada:
    ADR-008 ya estableció que la comparación es una SECCIÓN del snapshot de
    `monitoring_analyses`, no una entidad aparte. Un informe por monitoreo
    ya cubre ambas (UC-IA1 + UC-IA2).
  - **Snapshot como única entrada + guardia de números** (elegida).

- **Decisión:**
  1. **Entrada del LLM = figuras, no datos.** `build_report_figures`
     recorta `monitoring_analyses.payload` (ya calculado, ADR-008) a los
     ítems del resumen y al total de proyecto de la comparación. El modelo
     nunca ve una fila de árbol.
  2. **Guardia de números.** `find_unverified_numbers` revisa el texto
     generado contra esas figuras y devuelve `unverified_numbers`; el
     frontend lo muestra como aviso. Nunca se corrige el texto solo.
  3. **Modelo: `qwen2.5:3b`.** El hardware de desarrollo es una RTX 3050 de
     4 GB de VRAM con 7.7 GB de RAM: un modelo de 3B en cuantización Q4
     cabe en la GPU sin desbordar a RAM compartida, con una latencia
     aceptable para un borrador que el ingeniero pide una vez por
     monitoreo. Un modelo mayor (8B+) se evaluará cuando haya hardware de
     despliegue conocido.
  4. **Puerto `LLMClient`** (`application/use_cases/ai_report.py`):
     `generate(prompt, system) -> str` + `model_name`. Adaptador
     `adapters/llm/ollama.py` habla HTTP con `urllib` (sin dependencia
     nueva, mismo patrón que `adapters/satellite/planetary_computer.py`).
     Mañana, otro proveedor implementa el mismo puerto sin tocar el caso de
     uso.
  5. **Endpoints síncronos, sin cola.** La generación es una llamada
     bloqueante de hasta 180 s; los endpoints son `def` (no `async def`)
     para que FastAPI la mande al threadpool (lección de v1, AGENTS.md).
     ADR-010 (cola de trabajos) sigue pendiente: con un ingeniero generando
     un borrador a la vez, esto no agota el threadpool. Se revisa si algún
     día hay generación concurrente real.
  6. **Provenance, por monitoreo.** `ai_reports.input_hash` guarda
     `f"{analysis_version}:{sha256(JSON canónico de build_report_figures)}"`
     (`application/use_cases/ai_report.py: _figures_fingerprint`) — NO el
     `input_hash` del snapshot, que resume el dataset del PROYECTO entero.
     Con esa versión anterior, subir un monitoreo nuevo (p. ej. M5) volvía
     "stale" los borradores de M1-M4 aunque sus propias cifras no hubieran
     cambiado un dígito: el fingerprint se ata a lo que el LLM realmente
     vio, no a todo lo que cambió en el proyecto. Un único helper calcula
     el fingerprint tanto al generar como al leer, para que nunca diverjan.
  7. **La conexión de BD se libera antes de llamar al LLM.** La generación
     bloquea hasta 180 s; sin este paso, esa conexión quedaba reservada en
     transacción todo ese tiempo. `AIReportRepository.release()` hace
     `rollback()` (no hay escritura pendiente en ese punto: el snapshot ya
     se leyó/guardó antes) y `generate_ai_report` lo llama después de leer
     el snapshot y armar las figuras, antes de `llm.generate`. La capa de
     aplicación sigue sin importar SQLAlchemy: `release()` es un método más
     del puerto del repositorio, igual que `get`/`save`.
  8. **Opciones deterministas.** La petición a Ollama fija
     `options: {temperature: 0.2, seed: 42}` (constantes del módulo,
     `adapters/llm/ollama.py`): un borrador técnico debe ser reproducible
     con las mismas cifras, no variar en cada "Regenerar". No se guardan
     por fila — sería redundante con las constantes ya fijas en el código —
     sino que su presencia se registra subiendo `PROMPT_VERSION` a
     `2026-09-27-e9.2`: el contrato de provenance es "misma versión de
     prompt implica mismo comportamiento de generación", y ese
     comportamiento cambió aunque el texto del prompt no.
  9. **Desvío de `docs/04-vision-producto.md` §6.10.** Allí `ai_reports`
     era genérica (`subject_type` + `subject_id`). Aquí lleva
     `project_id` + `monitoring_id` con `UNIQUE(monitoring_id)` y claves
     foráneas reales: el único sujeto que existe es el monitoreo (ADR-008,
     no hay `comparison_analyses`). Si aparece otro sujeto, se añade con una
     migración.

- **Consecuencias:**
  - La guardia de números AVISA, no impide: un borrador puede llegar a
    citar una cifra que AgroSense no calculó, pero queda marcada como
    `unverified_numbers` para que el ingeniero decida qué hacer — nunca se
    corrige ni se bloquea sola.
  - El prompt es deliberadamente pequeño: cabe en el contexto de un modelo
    de 3B sin necesidad de recortar información a mitad de generación.
  - Deuda explícita: sin cola de trabajos (ADR-010) y sin fine-tuning. Un
    fine-tuning solo se justifica cuando existan suficientes informes
    reales para evaluarlo — hoy no hay ninguno.
  - Un proxy inverso con timeout de 60 s (frecuente en despliegues
    detrás de Nginx/Cloudflare) cortaría la respuesta al ingeniero antes de
    los 180 s que puede tardar Ollama, aunque el backend siga trabajando y
    termine guardando el borrador igual — el ingeniero vería un error de
    conexión y tendría que refrescar para verlo. Solución pendiente:
    ADR-010 (endpoint `202` + polling), que además resolvería el límite del
    threadpool si algún día hay generación concurrente real. Hoy queda
    como deuda documentada, no bloqueante para este slice.
  - Producción de Ollama sigue abierta (D4): si el entorno de despliegue no
    puede correr un LLM local, el puerto `LLMClient` es el único punto que
    cambia.
