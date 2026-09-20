---
aliases: [Slice 3, Mortalidad, Riesgo]
tags: [slice, pendiente]
status: pendiente
---

# Slice 3 — Riesgo de Mortalidad

> [!abstract] Predicción de muerte por árbol
> **Estado**: ⬜ Pendiente | **Señal**: Estancados ≤5cm → 35x más riesgo

---

## Objetivo

Predecir la probabilidad de muerte de cada árbol basado en
características de crecimiento, especie y sitio.

---

## Señal Validada (Spike ML)

| Métrica | Valor |
|---|---|
| Mortalidad acumulada | 16% |
| Odds ratio (estancados) | 35x |
| R² growth (honesto) | 0.47 |

---

## Plan

### Features

- DAP inicial, altura inicial
- Crecimiento acumulado DAP
- Crecimiento acumulado altura
- Número de campañas
- Especie (one-hot)
- Sitio (one-hot)
- StatusSemantic

### Modelo

| Aspecto | Elección |
|---|---|
| Algoritmo | XGBoost / Random Forest |
| Target | alive = False |
| Split | GroupKFold (por árbol) |
| Métrica | AUC-ROC, Precision-Recall |

### Evaluación

> [!important] ML Eval Gate
> - Split temporal (M1-M3 train, M4 test)
> - Group split (mismo árbol no en ambos)
> - Cero leakage
> - Métricas documentadas

---

## Tasks

| Task | Estado | Descripción |
|---|---|---|
| Task 1 | ⬜ | Labeling temporal (definir target) |
| Task 2 | ⬜ | Feature engineering |
| Task 3 | ⬜ | Baseline model |
| Task 4 | ⬜ | Evaluación honesta |
| Task 5 | ⬜ | Versionado de modelo |
| Task 6 | ⬜ | Inferencia + API |

---

## Links

- [[Resumen ML]] — Modelos
- [[Slice 2 - Persistencia y API]] — Anterior
- [[Slice 4 - Detección de Estancados]] — Siguiente
- [[Roadmap]] — Timeline
