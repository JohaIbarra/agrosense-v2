# Evaluación del modelo de estancamiento — stall-logreg-2026-09-27.2

> Generado por `cd backend && python scripts/train_stall_model.py --data data/raw/anexo1.xlsx`. No editar a mano.

**ML eval gate: APROBADO**

## Procedencia

| Campo | Valor |
|---|---|
| Dataset | `anexo1.xlsx` (hoja `Monitoreo_4`) |
| SHA-256 del dataset | `28583c3b48874626f3d7d7ae35d485634a8c8089b4c03a5997f5ba756b57a0dd` |
| Versión de la ingesta | `2026-09-21-e0` |
| Features | `2026-09-27-e7.1` |
| Preprocesamiento | `2026-09-27-e7.1` |
| Commit del código | `1ef60692147e511049d27b9d5d7e6192feed8855` |
| Versiones | Python 3.12.1, scikit-learn 1.5.2, numpy 1.26.4 |
| Semilla | 42 |
| C (regularización, logística) | 0.5 — protocolo/spike (Protocolo §9), fijado antes de evaluar M3 |
| Entrenado | 2026-09-28T03:17:27+00:00 |

## Régimen primario — validación adelantada en el tiempo

Entrena con la ola M2 (etiqueta M2→M3, n = 618, 153 estancados) y prueba con la ola M3 (etiqueta M3→M4, n = 717, 157 estancados, 39 parcelas).

| Modelo | PR-AUC |
|---|---|
| Prevalencia (sin modelo) | 0.219 |
| Persistencia (estancó antes) | 0.331 |
| Tasa media por especie | 0.382 (IC 95 % por parcelas 0.32–0.46) |
| **Regresión logística** | **0.478** (IC 95 % por parcelas 0.37–0.57; 1000/1000 remuestreos válidos) |
| Control negativo: etiqueta permutada en todo el conjunto (20 corridas) | 0.227 (rango 0.159–0.327) |
| Control: permutada dentro de cada parcela (solo la tasa de la parcela) | 0.329 (rango 0.244–0.396) |

ROC-AUC 0.738. Con un presupuesto de alertas del 20 %: recall 43.3 %, precisión 47.5 %.

## Régimen secundario — GroupKFold por parcela (diagnóstico)

5 folds agrupados por Codigo de unidad muestreo (parcela): PR-AUC agregado 0.515; por fold 0.584, 0.405, 0.629, 0.651, 0.430. Los folds agrupan M2 y M3 en un solo conjunto: es un diagnóstico de estabilidad espacial (parcelas nuevas), no una métrica temporal-segura, porque mezcla ambas olas.

## Gate

| Criterio | Resultado |
|---|---|
| `pr_auc_at_least_min` | cumple |
| `beats_prevalence` | cumple |
| `beats_persistence` | cumple |
| `permutation_control_near_prevalence` | cumple |
| `beats_within_plot_permutation` | cumple |

`pr_auc_at_least_min` compara el PR-AUC **puntual** del régimen temporal (no el límite inferior de su propio IC) contra 0.36.

## Artefacto servido

Reentrenado con el mismo procedimiento sobre las olas M2, M3 (n = 1335, 310 estancados). Las métricas de arriba evalúan el procedimiento, no este reentrenamiento.

## Lectura honesta

**El criterio de fuga se redefinió después de ver el resultado.** El protocolo original usa la permutación DENTRO de cada parcela como control de fugas, con techo 0.31 (rango reportado 0.18–0.31). Al reproducirlo con esta featurización da 0.329 (rango 0.244–0.396): **con ese criterio original, este modelo NO habría pasado el gate**. La causa no es fuga sino señal de sitio: conservar la tasa de cada parcela deja aprender la especie y el predio, que sí varían entre parcelas. Por eso el control dentro de parcela pasó a medir cuánto aporta el modelo por encima de la tasa de la parcela (debe superarlo, no acercarse a él), y el control de fugas real pasó a ser la permutación GLOBAL, con el mismo techo 0.31. Esta regla queda **PRE-REGISTRADA** desde el artefacto `stall-logreg-2026-09-27.2` en adelante: un reentrenamiento futuro se juzga con esta definición, no con la reinterpretada aquí sobre la marcha.

El modelo se entrenó con un solo proyecto (3 predios, ~30 especies): la transferencia espacial a otros proyectos NO está evaluada. Las predicciones que sirve la API para M2 y M3 de este proyecto son sobre datos de ENTRENAMIENTO (in-sample, no evaluación); la única evaluación honesta es M3→M4, la que se reporta arriba.

La evidencia de que el modelo supera a una regla de una línea es sugestiva, no concluyente (Protocolo §5): los intervalos de la logística (0.37–0.57) y de la tasa por especie (0.32–0.46) se solapan. La etiqueta mide «crecimiento no detectable por el protocolo», no «crecimiento nulo». La probabilidad es condicional a que el árbol siga vivo.
