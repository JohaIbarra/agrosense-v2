---
aliases: [Slice 3, Mortalidad, Riesgo]
tags: [slice, pendiente]
status: pendiente
---

# Slice 3 — Riesgo de Mortalidad

> [!abstract] Predicción de muerte por árbol
> **Estado**: ⬜ Pendiente | **Señal**: Estancados ≤5cm → 35x más riesgo
> **Orden**: va DESPUÉS de [[Slice 4 - Detección de Estancados]] (invertido el 2026-09-21)

> [!warning] Este slice depende del Slice 4 — no empezarlo antes
> `estancó_intervalo_previo` lo **produce** el slice de estancados y es el
> predictor más fuerte del que disponemos (OR 2.92 en estancamiento, OR 1.70
> —marginal, p=0.10— en mortalidad). Construir mortalidad primero obliga a
> improvisar esa feature y a pasar el ML eval gate dos veces.
>
> **Además, el poder estadístico es el limitante real:** solo 70 muertes en
> 1.405 observaciones árbol-intervalo (prevalencia 5%), unos 33–37 eventos por
> ola. Con ~8 predictores eso es un EPV de 4–11, por debajo del mínimo
> habitual de 10–20. Cualquier alcance que no lo tenga en cuenta produce un
> modelo de ruido.

---

## Objetivo

Predecir la probabilidad de muerte de cada árbol basado en
características de crecimiento, especie y sitio.

---

## Lo que ya sabemos del modelo mixto ([[Slice 5 - Analítica de Crecimiento]])

La descomposición de varianza sobre `panel_mortalidad.csv` acota qué puede y
qué no puede hacer este slice:

| Hallazgo | Valor | Implicación para el modelo |
|---|---|---|
| Varianza especie / parcela | 0.415 / 0.372 (razón 1.1×) | Especie y **sitio pesan casi igual**: no basta con elegir especie |
| ICC especie / parcela | 0.102 / 0.091 | Ambos efectos aleatorios son necesarios |
| Rango OR entre especies | 0.35 – 1.97 (factor 5.6×) | Señal por especie real pero **modesta** |
| Especies significativas | 1 de 30 (*Inga punctata*, OR 0.35) | Ninguna especie con riesgo aumentado significativo |
| Efecto fijo más fuerte | Fitosanidad deficiente, OR 4.64 | **La palanca accionable es la condición, no la especie** |
| Gremio intermedio | OR 3.33 | Candidato a feature |
| log(altura)ᶻ | OR 0.53 | Los árboles grandes mueren menos |

> [!tip] Lectura estratégica
> Mortalidad es un problema **equitativo de especie + sitio**: se ataca
> mejorando condiciones (sobre todo fitosanidad) que re-seleccionando especies.
> Estancamiento es lo contrario — ahí sí domina la especie.

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
| Split | Temporal M2→M3 / M3→M4 + GroupKFold por parcela |
| Métrica | AUC-ROC, Precision-Recall |

### Evaluación

> [!important] ML Eval Gate
> - Split temporal primario (entrena M2→M3, prueba M3→M4)
> - Group split por **parcela** (`Codigo de unidad muestreo`), no por árbol:
>   los árboles de una parcela comparten suelo, pendiente, exposición y
>   cuadrilla; agrupar por árbol deja fuga espacial. Con split temporal el
>   mismo árbol PUEDE aparecer en train y test en olas distintas — lo que
>   nunca puede repetirse es la misma observación (árbol + ola)
> - Bootstrap del IC 95% agrupado por parcela
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

- [[Slice 4 - Detección de Estancados]] — **Anterior** (produce `estancó_intervalo_previo`)
- [[Slice 5 - Analítica de Crecimiento]] — Efectos por especie/parcela del modelo mixto
- [[Resumen ML]] — Modelos
- [[Roadmap]] — Timeline
