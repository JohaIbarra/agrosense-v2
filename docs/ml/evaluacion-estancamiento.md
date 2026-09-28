# Evaluación del modelo de estancamiento — stall-logreg-2026-09-27.1

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
| Commit del código | `a6f8acc0cc0c0b829c06f80822ed35a4e5d1765d` |
| Versiones | Python 3.12.1, scikit-learn 1.5.2, numpy 1.26.4 |
| Semilla | 42 |
| Entrenado | 2026-09-28T01:55:37+00:00 |

## Régimen primario — validación adelantada en el tiempo

Entrena con la ola M2 (etiqueta M2→M3, n = 618, 153 estancados) y prueba con la ola M3 (etiqueta M3→M4, n = 717, 157 estancados, 39 parcelas).

| Modelo | PR-AUC |
|---|---|
| Prevalencia (sin modelo) | 0.219 |
| Persistencia (estancó antes) | 0.331 |
| Tasa media por especie | 0.382 |
| **Regresión logística** | **0.478** (IC 95 % por parcelas 0.37–0.57) |
| Control negativo: etiqueta permutada en todo el conjunto (20 corridas) | 0.227 (rango 0.159–0.327) |
| Control: permutada dentro de cada parcela (solo la tasa de la parcela) | 0.329 (rango 0.244–0.396) |

ROC-AUC 0.738. Con un presupuesto de alertas del 20 %: recall 43.3 %, precisión 47.5 %.

## Régimen secundario — GroupKFold por parcela (diagnóstico)

5 folds agrupados por Codigo de unidad muestreo (parcela): PR-AUC agregado 0.515; por fold 0.584, 0.405, 0.629, 0.651, 0.430.

## Gate

| Criterio | Resultado |
|---|---|
| `pr_auc_at_least_min` | cumple |
| `beats_prevalence` | cumple |
| `beats_persistence` | cumple |
| `permutation_control_near_prevalence` | cumple |
| `beats_within_plot_permutation` | cumple |

## Artefacto servido

Reentrenado con el mismo procedimiento sobre las olas M2, M3 (n = 1335, 310 estancados). Las métricas de arriba evalúan el procedimiento, no este reentrenamiento.

## Lectura honesta

La evidencia de que el modelo supera a una regla de una línea es sugestiva, no concluyente (Protocolo §5): los intervalos de la logística y de la tasa por especie se solapan. La etiqueta mide «crecimiento no detectable por el protocolo», no «crecimiento nulo». La probabilidad es condicional a que el árbol siga vivo.
