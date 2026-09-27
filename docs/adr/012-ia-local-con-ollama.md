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
  6. **Provenance.** `ai_reports.input_hash` guarda
     `f"{analysis_version}:{snapshot.input_hash}"`: si el snapshot cambia,
     el borrador guardado se sigue sirviendo pero marcado `stale`, nunca se
     regenera solo.

- **Consecuencias:**
  - Un informe nunca puede citar una cifra que AgroSense no calculó: el
    peor caso es un número inventado marcado como no verificado, no una
    cifra falsa sin aviso.
  - El prompt es deliberadamente pequeño: cabe en el contexto de un modelo
    de 3B sin necesidad de recortar información a mitad de generación.
  - Deuda explícita: sin cola de trabajos (ADR-010) y sin fine-tuning. Un
    fine-tuning solo se justifica cuando existan suficientes informes
    reales para evaluarlo — hoy no hay ninguno.
  - Producción de Ollama sigue abierta (D4): si el entorno de despliegue no
    puede correr un LLM local, el puerto `LLMClient` es el único punto que
    cambia.
