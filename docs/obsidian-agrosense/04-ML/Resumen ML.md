---
aliases: [ML, Machine Learning, Modelos]
tags: [ml, machine-learning]
---

# Resumen de Machine Learning

> [!abstract] Spike ML y modelos planificados
> Señal validada antes de construir. Preprocessing único compartido train/serve.

---

## Spike ML — Resultados

> [!important] Señal confirmada
> El ML spike demostró que existe señal predictiva real:
> - **Estancados ≤5cm**: 35x más probabilidad de morir
> - **Mortalidad acumulada**: 16%
> - **R² growth prediction**: 0.47 (honesto, sin leakage)

> [!warning] vs v1 (con leakage)
> - v1: R² = 0.968 (falso, tenía `altura_actual` como feature)
> - v2: R² = 0.47 (real, sin leakage)
> - La diferencia confirma que v1 estaba equivocado

---

## Modelos Planificados

### 1. Riesgo de Mortalidad (Slice 3)

> [[Slice 3 - Riesgo de Mortalidad]] para detalle completo

| Aspecto | Valor |
|---|---|
| **Target** | Muerte del árbol (alive pasa a False) |
| **Features** | DAP, altura, crecimiento acumulado, especie, sitio |
| **Algoritmo** | XGBoost / Random Forest |
| **Métrica** | AUC-ROC, Precision-Recall |
| **Split** | Temporal (primario) + group split por parcela |

### 2. Detección de Estancados (Slice 4)

> [[Protocolo Estancamiento]] para diseño completo + código + resultados

| Aspecto | Valor |
|---|---|
| **Target** | Crecimiento no detectable: `altura(t) == altura(t+1)` |
| **Features** | Altura, copa, crecimiento rezagado, fitosanidad, especie, localidad |
| **Algoritmo** | **Regresión logística** (interpretable, empató con boosting) |
| **Métrica** | PR-AUC = **0.469** (IC 95%: 0.36–0.58) |
| **Recall@20%** | 45% de estancados detectados |
| **Variable de crecimiento** | **Altura** (no DAP — DAP es censura por umbral) |
| **Validación** | Temporal: entrena M2→M3, prueba M3→M4 |

### 3. Analítica de Crecimiento (Slice 5)

> [[Slice 5 - Analítica de Crecimiento]] para detalle completo

| Aspecto | Valor |
|---|---|
| **Target** | Tasa de crecimiento por especie/sitio |
| **Features** | DAP, altura, especie, sitio, tiempo |
| **Algoritmo** | Regresión + clustering |
| **Métrica** | R², MAE |
| **Dashboard** | Portado de v1 |

---

## Preprocessing Compartido

> [!important] Regla v2
> **NUNCA** duplicar preprocessing. Un solo módulo que use:
> - Entrenamiento: `ml/preprocessing.py`
> - Inferencia: `ml/preprocessing.py`

```
train_time:  preprocessing.fit(X_train) → transform(X_train)
serve_time:  preprocessing.transform(X_new)  # mismos pasos
```

---

## Leakage que Corregimos

> [!danger] v1 tenía leakage
> ```python
> # MAL (v1):
> features = ["altura_actual", "dap_actual", ...]  # altura_actual = target
> 
> # BIEN (v2):
> features = ["altura_m1", "dap_m1", "crecimiento", ...]  # solo datos pasados
> ```

---

## Split por Parcela

> [!important] Group split — el grupo es la PARCELA, no el árbol
> ```python
> # MAL (v1):
> train_test_split(X, y, test_size=0.2)  # árbol A en train Y test
>
> # MAL (v2, corregido el 2026-09-21):
> GroupKFold(n_splits=5, groups=tree_id)  # deja fuga espacial
>
> # BIEN (v2):
> GroupKFold(n_splits=5, groups=unidad_muestreo)  # `Codigo de unidad muestreo`
> ```

> [!warning] Por qué la parcela y no el árbol
> Los árboles de una misma parcela comparten suelo, pendiente, exposición y
> **cuadrilla de medición**: agrupar por árbol deja que el modelo aprenda la
> parcela en train y la explote en test — fuga espacial.
>
> Además, con validación primaria temporal (M2→M3 entrena, M3→M4 prueba) el
> agrupamiento por árbol es casi irrelevante: las olas ya separan las
> observaciones del mismo individuo. La agrupación que aporta independencia
> real es la **espacial**.
>
> Esto es coherente con la descomposición de varianza: la parcela explica
> ICC 0.07 del estancamiento y 0.09 de la mortalidad — no es ruido
> ignorable. Ver [[Slice 5 - Analítica de Crecimiento]].

---

## Entrenamiento Offline

> [!note] Evolución DL (ADR-003)
> El modelo se entrena offline (scripts, notebooks).
> La inferencia se sirve en el monolito vía `ml/` module.

```
Offline (training):     python -m ml.train
Online (inference):     from ml.model import predict
```

---

## Métricas Documentadas

| Modelo | Métrica | Valor | Estado |
|---|---|---|---|
| Mortalidad | AUC-ROC | Pendiente | Slice 3 |
| **Estancados (logística)** | **PR-AUC** | **0.469** | [[Protocolo Estancamiento]] |
| Estancados (boosting) | PR-AUC | 0.454 | Sin ganancia por complejidad |
| Crecimiento | R² | 0.47 | Spike |

---

## Links

- [[Protocolo Estancamiento]] — Diseño completo de estancamiento
- [[Slice 3 - Riesgo de Mortalidad]] — Próximo
- [[Slice 4 - Detección de Estancados]] — Implementación
- [[Slice 5 - Analítica de Crecimiento]] — Planificado
- [[Modelo de Dominio]] — Entidades del ML
- [[Roadmap]] — Timeline
