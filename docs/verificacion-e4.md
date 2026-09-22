# Verificación — E4 · Comparación entre monitoreos

Fecha: 2026-09-22. Decisión: sin ADR nuevo — la comparación es **una sección
más del análisis** que ya existe (ADR-008), no un artefacto aparte.

**Criterio de salida**: el ingeniero abre el análisis de Mk y ve qué pasó
entre Mk−1 y Mk —quién murió, quién creció, quién se quedó igual— por predio,
por especie y por parcela, y eso mismo baja en el `.xlsx`. **Cumplido y
probado.**

## La decisión de diseño

`docs/04-vision-producto.md` §6.5 preveía una tabla `comparison_analyses`
propia. No se creó, y la razón es la misma que llevó a ADR-008: el análisis de
Mk **ya se calcula contra Mk−1** (las secciones de alturas y copa traen su
columna de crecimiento desde E3) y ya se guarda como snapshot versionado. Una
tabla aparte habría duplicado el disparador, el versionado y la invalidación
para responder la misma pregunta con los mismos datos.

La comparación entra entonces como la **sección `comparacion`** del payload, y
con eso hereda gratis: el recálculo al subir un archivo, la hoja del `.xlsx`,
la pestaña de la página y la trazabilidad por `input_hash`.

**Consecuencia asumida:** subir `ANALYSIS_VERSION` a `2026-09-22-e4.1`
invalida los snapshots anteriores, que se recalculan solos al abrirlos. Es
exactamente el mecanismo que ADR-008 dejó previsto.

## El cambio que sí tocó el contrato: las fechas

El crecimiento anualizado necesita saber cuánto duró el intervalo, así que
`engine.analyze` y `engine.fingerprint` reciben ahora las fechas de los
monitoreos, y **las fechas entran en el `input_hash`**: corregir la fecha de un
monitoreo recalcula el análisis igual que corregir una altura. Sin fechas no
se anualiza y la tabla lo dice en una nota — un crecimiento de 30 cm en seis
meses y otro en dos años no son el mismo dato, y **inventar el denominador
sería peor que no darlo**.

## Qué se publica

| Tabla | Qué responde |
|---|---|
| `comparacion-resumen` | Por predio (+ proyecto en el pie): vivos al inicio, muertos, mortalidad, medidos en ambos, estancados, % estancados, contracciones, crecimiento medio y anualizado |
| `comparacion-especie-{predio}` | Lo mismo por especie, dentro de cada predio: es donde se decide qué replantar |
| `comparacion-parcela` | Lo mismo por parcela: separa el problema del sitio del problema de la especie |
| `comparacion-estado` | Matriz de transición fitosanitaria: de cada estado en Mk−1, a dónde llegó en Mk (incluido «Muerto») |

Cuatro gráficas, todas apuntando a una de esas tablas. El resumen general del
monitoreo gana tres indicadores: mortalidad del intervalo, crecimiento medio y
crecimiento anualizado.

**Definiciones** (las del dominio, no inventadas aquí): estancado = creció 5 cm
o menos (`STAGNATION_THRESHOLD_M`); contracción = perdió más de 5 cm
(`MAX_CONTRACTION_M`). Solo entran los árboles **vivos en Mk−1 y censados en
Mk**: quien ya estaba muerto no puede volver a morir ni crecer.

## Gates

| # | Gate | Resultado |
|---|---|---|
| 1 | `pytest` local | ✅ 523 passed, 43 deselected (118 s) |
| 2 | `pytest -m supabase` | ✅ 43 passed (176 s) |
| 3 | `ruff check src tests` | ✅ limpio |
| 4 | Frontend: `vitest run` | ✅ 82 passed |
| 5 | `tsc -b` + `npm run build` + `npm run lint` | ✅ 0 errores (6 avisos previos de `any`) |
| 6 | `pip-audit` · `npm audit --omit=dev` | ✅ sin vulnerabilidades |
| 7 | Migración | — ninguna: la comparación vive en el snapshot que ya existe |

`tests/analysis/test_comparison.py` (**12 tests**) comprueba cada cifra a mano
sobre un caso construido: un árbol que crece 50 cm, otro que se estanca en
3 cm, uno que muere y otro que se contrae 10 cm. Incluye que medio año duplica
el anualizado, que sin fechas no aparece la columna, y que el primer monitoreo
devuelve la sección con una nota en vez de tablas vacías.

## Contra los datos reales

Con el Anexo completo y fechas plausibles:

| Intervalo | Vivos al inicio | Muertos | Estancados | Contracciones | Crecimiento |
|---|---|---|---|---|---|
| M1 → M2 | 682 | 31 (4,5 %) | 236 (36,3 %) | **8** | 0,140 m |
| M2 → M3 | 651 | 33 (5,1 %) | 244 (39,5 %) | 0 | 0,189 m |
| M3 → M4 | 754 | 37 (4,9 %) | 275 (38,4 %) | 0 | 0,191 m |

Dos lecturas que confirman lo ya documentado:

- **33–37 muertes por ola**, que es exactamente el número que el Discovery dio
  como limitante del modelo de mortalidad (EPV 4–11).
- **Las contracciones solo existen en M1 → M2.** Cero en los dos intervalos
  siguientes es biológicamente inverosímil y ya estaba anotado en
  `domain/rules.py`: es la huella de que la cuadrilla «arregló» las alturas
  hasta dejarlas monótonas. El producto ahora lo muestra en vez de esconderlo.

**Aviso de lectura, anotado para que nadie lo confunda:** los 236–275
«estancados» de esta tabla son un conteo descriptivo (creció ≤ 5 cm en el
intervalo). No son los 153 eventos positivos del protocolo de estancamiento de
E7, que se define sobre otra ventana y excluye casos. Son dos cosas con el
mismo nombre y no deben compararse.

## Pendiente del ingeniero

1. Revisar en pantalla la pestaña «Comparación» del análisis de M4 y la hoja
   del mismo nombre en el `.xlsx`.
2. **Registrar las fechas reales de M1–M4.** Sin ellas no hay anualización, y
   con intervalos de 6 y 12 meses mezclados el crecimiento por intervalo no es
   comparable entre olas. Es un dato que solo usted tiene.
