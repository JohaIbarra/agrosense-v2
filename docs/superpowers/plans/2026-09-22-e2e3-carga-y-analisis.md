# Plan E2+E3 — Carga desde la ficha y análisis automático de las 7 hojas

Fecha: 2026-09-22. Origen: `docs/04-vision-producto.md` §9 (E2, E3) y la
aclaración de producto del 2026-09-22: **el ingeniero sube solo datos crudos
de campo** (una fila por árbol, como `Monitoreo_4`), un monitoreo a la vez o
acumulado. Las otras 7 hojas del Anexo 1 son trabajo manual que AgroSense
reproduce; se usan como especificación y como verificación.

**Objetivo**: desde la ficha del proyecto, el ingeniero sube su Excel con la
fecha del monitoreo, ve el resultado de la ingesta con sus avisos y, desde el
primer monitoreo, ve las 7 hojas calculadas (tablas ordenables + gráficas) y
descarga un `.xlsx` con todas las salidas. Página y `.xlsx` salen del **mismo
cálculo del backend**.

## Definiciones verificadas contra el Anexo 1

| Hoja | Definición (monitoreo k, anterior k−1) | Verificado |
|---|---|---|
| Composición | Individuos **vivos en Mk** por especie × diseño / × cobertura, por predio | Guayabal DF 171/10/99 = 280; Tres Jotas 176/57/141 = 374 |
| Alturas | Media de la altura de los vivos medidos **en cada monitoreo** (Mk−1 y Mk por separado); crecimiento de celda = media Mk − media Mk−1; CP de la especie = media de sus crecimientos de celda; fila «Crecimiento promedio» = media por columna | Brunellia TJ BG 0,7917 → 1,362; CP TJ cobertura 0,407 |
| Diámetro de copa | Igual que alturas, sobre `Diámetro. Copa` | — |
| Supervivencia | Vivos / (vivos + muertos) con estado registrado en Mk; % por especie, por arreglo (diseño) y por predio | Cavendishia ABB 90 %; ABB Guayabal 82,61 %; predio 80,23 % |
| Estado fito | Conteo Bueno / Regular / Malo de los vivos en Mk; % por especie, diseño y predio | — |
| Edades | Categoría de desarrollo por rango de altura (0,01–0,5 plántula; 0,51–3 juvenil I; 3,1–6 juvenil II) | Guayabal ABB M3: 104 + 80 = 184 |
| DAP | Media del DAP **medido** (> 0) por especie × diseño / cobertura | Montanoa ABB Guayabal M3 2,44; M4 2,9488 |

## Decisiones técnicas

| Decisión | Elección | Por qué |
|---|---|---|
| Forma del resultado | Secciones → **tablas tipadas** (columnas con tipo y decimales) + **gráficas que referencian una tabla** | Un solo cálculo alimenta la página y el `.xlsx`; el frontend solo pinta, nunca recalcula |
| Persistencia | Snapshot JSON en `monitoring_analyses` con `analysis_version` e `input_hash` (ADR-008) | Decisión D2; provenance del análisis |
| Cuándo se calcula | Al terminar cada ingesta, para **todos** los monitoreos del proyecto; en lectura se recalcula si la versión del cálculo cambió | Un archivo nuevo corrige monitoreos anteriores; el cálculo cuesta < 1 s |
| Cola de trabajos | **No en este slice** (ADR-009 queda pendiente) | El análisis es barato; el coste de la carga es #G y se mide y ataca aparte |
| Motor | `adapters/analysis/` con pandas; **definiciones** en `domain/analysis_rules.py` | Vision §7: la regla de negocio no depende de la librería |
| Orquestación | Casos de uso en `application/`, motor y repos inyectados por parámetro | ADR-003: sin puerto donde no hay variación real |
| Fecha del monitoreo | Campo del upload (se asigna al monitoreo más reciente del archivo) + `PATCH` por monitoreo | Un archivo acumulado trae varios; cada uno se fecha |
| Hoja del Excel | La primera hoja que tenga `ID_MUEST` y especie; ya no se exige `Monitoreo_4` | El Excel del M1 se llamará `Monitoreo_1` o como el ingeniero quiera |
| Categorías > 6 m | «Mayor de 6 m» (el Anexo 1 nombra subadulto/adulto sin rangos) | No inventar rangos; decisión de producto registrada |

## Tareas

- **T1** Dominio: `analysis_rules.py` (categorías, estado fito normalizado,
  muestra mínima), invariante de fechas de monitoreo.
- **T2** Motor de análisis (pandas) + test de coincidencia con las hojas.
- **T3** Persistencia: `monitoring_analyses` + migración; repositorio que
  carga el dataset del proyecto como entidades de dominio.
- **T4** Casos de uso: analizar, leer análisis, fechar monitoreo; la carga
  refresca los análisis.
- **T5** Reporte `.xlsx` (una hoja por análisis + datos crudos, formato limpio).
- **T6** API: `monitoring_date` en el upload, `PATCH` monitoreo, `GET`
  análisis, `GET` reporte. Contrato + tests de integración.
- **T7** Frontend: carga desde la ficha, resultado con avisos, página de
  análisis con tablas ordenables y gráficas, botón «Descargar reporte».
- **T8** Verificación: suites, lint, tipos, build, auditorías, navegador;
  `docs/verificacion-e2e3.md`.

## Criterio de salida

Subir el Anexo 1 desde la ficha → ver sus 4 monitoreos → abrir M4 → las cifras
coinciden con las hojas del Anexo 1 (test automatizado) → descargar el `.xlsx`
con las mismas cifras.
