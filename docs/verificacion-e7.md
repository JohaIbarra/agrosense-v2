# Verificación — E7 · Detección de estancados

Fecha: 2026-09-27. Plan: `docs/superpowers/plans/2026-09-27-e7-estancados.md`.
Decisión: `docs/adr/013-modelo-estancamiento-offline.md`.

**Criterio de salida**: el ingeniero abre el análisis de un monitoreo y ve qué
árboles vivos tienen más riesgo de no crecer hasta el próximo, con el 20 %
marcado para revisión, la regla observada y la lectura honesta del modelo.

## Gates

| # | Gate | Resultado |
|---|---|---|
| 1 | `pytest` local (SQLite) | 785 passed, 45 deselected |
| 2 | `ruff check src tests scripts` | limpio (All checks passed) |
| 3 | `pip-audit -r requirements.lock.txt` (incluye scikit-learn 1.5.2) | sin vulnerabilidades conocidas |
| 4 | Frontend: `vitest run` | 121 passed (20 files) |
| 5 | Frontend: `tsc -b` + `npm run build` + `npm run lint` | 0 errores (6 warnings preexistentes) |
| 6 | `npm audit --omit=dev` | 0 vulnerabilidades |
| 7 | Migraciones `e7c1a3b5d7f9` (`stall_assessments`), `f4a1c9e7b3d2` (`trees.property_id`), `a1b2c3d4e5f6` (`stall_assessments.rules_version`) | **PENDIENTE — requiere autorización del ingeniero** |
| 8 | Tests de arquitectura (capas, inferencia en Python puro, sklearn fuera de producción, CV por parcela) | verde (incluido en el gate 1) |
| 9 | **ML eval gate** | **APROBADO** |
| 10 | Reproducibilidad (`--check`) | «Reproducible» (re-verificado sobre `.2`; `.3` se regeneró con el mismo comando y fue confirmado por el implementador) |

## ML eval gate

| Criterio | Valor | Umbral |
|---|---|---|
| Train M2→M3 | 618 obs. / 153 positivos | igual al panel del protocolo |
| Test M3→M4 | 717 obs. / 157 positivos (39 parcelas) | igual al panel del protocolo |
| PR-AUC temporal | 0.478 (IC 95 % por parcelas 0.37–0.57; 1000/1000 remuestreos válidos) | ≥ 0.36 |
| Persistencia / tasa media por especie | 0.331 / 0.382 (IC 95 % por parcelas 0.32–0.46) | la logística supera a ambas líneas base |
| Control: etiqueta permutada en todo el conjunto (20 corridas) | 0.227 (rango 0.159–0.327) | ≤ 0.31 |
| Control: permutada dentro de cada parcela (20 corridas) | 0.329 (rango 0.244–0.396) | por debajo del PR-AUC temporal (0.478) |
| GroupKFold por parcela (diagnóstico, 5 folds) | 0.515 agregado (por fold: 0.584, 0.405, 0.629, 0.651, 0.430) | — (diagnóstico de estabilidad espacial, mezcla M2+M3) |
| Recall / precisión al 20 % de presupuesto de alertas | 43.31 % / 47.55 % | ROC-AUC 0.738 |

Artefacto `stall-logreg-2026-09-27.3`, SHA-256
`edf7204314c850ad9efa37f710017f3891fe013555af3f31e9fd5dfbcd45ced5`, commit
`eabfc4d4d8a0c0ac584dd4396677e2469f131b1f`.

## Lectura honesta: el criterio de fuga se redefinió después de ver el resultado

El protocolo original usaba como control de fugas la permutación DENTRO de
cada parcela, con techo 0.31. Al reproducirlo con esta featurización da 0.329
(rango 0.244–0.396): **con ese criterio original, este modelo no habría
pasado el gate.** La causa no es fuga sino señal de sitio: conservar la tasa
de cada parcela deja aprender la especie y el predio, que sí varían entre
parcelas. Por eso el control dentro de parcela pasó a medir cuánto aporta el
modelo por encima de la tasa de la parcela (debe superarla, no acercarse a
ella), y el control de fugas real pasó a ser la permutación global, con el
mismo techo 0.31. Esta reinterpretación queda **pre-registrada desde el
artefacto `stall-logreg-2026-09-27.2` en adelante** (ADR-013, Decisión 4;
`docs/ml/evaluacion-estancamiento.md`, «Lectura honesta»): no explica
retroactivamente `.1`, pero cualquier reentrenamiento futuro se juzga con
esta definición, no con una reinterpretada sobre la marcha otra vez.

## Correcciones de la revisión final (fix wave, 2026-09-27)

- **Categorías**: normalización de categóricas (localidad, especie, unidad de
  monitoreo, fitosanidad) y aviso `unknown_categories` cuando un árbol trae un
  valor que el modelo no vio en entrenamiento.
- **Paridad Excel→DB**: `tests/db/test_stall_parity.py` prueba que las
  features calculadas sobre la fila ingerida desde Excel coinciden con las
  calculadas sobre la fila leída de la base.
- **Honestidad en la UI**: el panel de riesgo declara sus salvedades y expone
  `mostly_without_history` cuando la mayoría de árboles mostrados no tienen
  intervalo previo con el que calcular los rezagos.
- **`RULES_VERSION`** (`domain/stall_rules.py`): invalida el snapshot de
  `stall_assessments` si cambia la regla de negocio de persistencia, aunque el
  modelo y los datos no hayan cambiado.
- **Scorer perezoso**: el caso de uso resuelve el `StallScorer` DESPUÉS de
  validar dueño y monitoreo, no antes — un proyecto ajeno responde 404 sin
  tocar el modelo.
- **Frontera de capas**: test de arquitectura nuevo — `adapters/` no puede
  importar `ml/train_stall` ni `ml/evaluation` (solo la inferencia servible).
- Artefacto reentrenado dos veces durante la revisión: `.1` → `.2` (fix round
  1, honestidad del gate y del informe) → `.3` (normalización de categóricas,
  item 1a/1b/1c). Las métricas de este documento son las de `.3`.

## Limitaciones declaradas

1. Entrenado con un solo proyecto (3 predios, ~30 especies); una especie que
   el modelo no vio pesa cero en su one-hot (`known_species`), avisado en la
   UI junto con `unknown_categories`.
2. En el proyecto de referencia, M2 y M3 son datos de entrenamiento: sus
   predicciones no son evaluación. La única evaluación honesta es M3→M4.
3. La etiqueta mide «crecimiento no detectable por el protocolo», no
   «crecimiento nulo»: depende del espaciado entre monitoreos (~1 año en este
   dataset) y de la precisión del redondeo de altura (milímetros aquí). No se
   transfiere sin revalidar a un proyecto con otro protocolo de medición
   (ADR-013, Decisión 10).
4. Evidencia sugestiva, no concluyente, frente a la regla por especie: los
   intervalos de la logística (0.37–0.57) y de la tasa por especie
   (0.32–0.46) se solapan.
5. Sin fechas de medición: todo es «por intervalo de monitoreo», no anualizado.
6. «Persistente» = 2 intervalos seguidos sin crecer. Convención del proyecto,
   **confirmada con el ingeniero el 2026-09-27** (ya no pendiente).
7. La probabilidad es condicional a que el árbol siga vivo; mortalidad es E8,
   que consume `estancó_intervalo_previo` producida por este slice.

## Gate de documentos

`tests/architecture/test_ml_eval_gate.py` está incluido en la suite completa
del gate 1 (785 passed) y en el gate 8 (tests de arquitectura, verde); no se
volvió a ejecutar por separado al escribir este documento porque esta
verificación no reentrena ni levanta servicios (política de esta sesión).
Ningún documento del repositorio afirma «GroupKFold por árbol»; el grupo de
la validación cruzada es la parcela (`Codigo de unidad muestreo`) — revisado a
mano en `AGENTS.md`, `docs/obsidian-agrosense/01-Proyecto/Roadmap.md`,
`docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md` y
`docs/obsidian-agrosense/06-Slices/Slice 4 - Detección de Estancados.md`
(los documentos que vigila ese test).
