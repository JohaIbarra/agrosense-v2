---
aliases: [Slice 4, Estancados, Detección]
tags: [slice, pendiente]
status: pendiente
protocolo: "[[Protocolo Estancamiento]]"
---

# Slice 4 — Detección de Estancados/Anómalos

> [!abstract] Regresión logística + regla de negocio (no IsolationForest)
> **Estado**: ⬜ Pendiente | **Protocolo**: [[Protocolo Estancamiento]]
> **Modelo**: Logística (PR-AUC 0.469, interpretable)

---

## Objetivo

Detectar árboles que no crecerán hasta el próximo monitoreo.
**La variable de crecimiento es la altura, no el DAP** (DAP es censura por umbral).

> [!important] Cambio de enfoque
> Originalmente pensábamos en IsolationForest. El [[Protocolo Estancamiento]] demostró que la **regresión logística** es igual de efectiva (PR-AUC empatan) y es interpretable — mejor para una plataforma de decisión.

---

## Datos del protocolo

| Aspecto | Valor |
|---|---|
| Dataset | 856 árboles, 4 monitoreos |
| Variable de crecimiento | Altura total (no DAP) |
| Etiqueta | `altura(t) == altura(t+1)` |
| Validación temporal | Entrena M2→M3, prueba M3→M4 |
| PR-AUC (logística) | 0.469 (IC 95%: 0.36–0.58) |
| Recall@20% | 45% |
| Precision@20% | 50% |
| Prevalencia | 22% |

---

## Enfoque (según protocolo validado)

### Modelo: Regresión Logística

> [[Protocolo Estancamiento#5. Resultados]] para comparación completa

```python
LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)
```

**Por qué logística y no gradient boosting:**
- PR-AUC empatan (0.469 vs 0.454)
- Con 717 árboles, no hay ganancia por complejidad
- Interpretable: el ingeniero de campo puede entender qué variables importan

### Features

| Feature | Tipo | Descripción |
|---|---|---|
| `h_t` | num | Altura actual |
| `copa_t` | num | Diámetro de copa actual |
| `dh_lag` | num | Crecimiento del intervalo anterior |
| `dcopa_lag` | num | Crecimiento de copa anterior |
| `estanco_lag` | num | ¿Estancó en intervalo previo? |
| `h_prev` | num | Altura previa |
| `esbeltez_t` | num | Altura / Copa |
| `fito_empeoro` | num | Cambio fitosanitario |
| `LOCALIDAD` | cat | Localidad |
| `Especie_M1` | cat | Especie |
| `Unidad de monitoreo` | cat | Parcela |
| `fito_t` | cat | Estado fitosanitario actual |

### Regla de negocio (fallback)

```
Si crecimiento altura ≈ 0 en N intervalos:
  → Marcar como estancado
```

### Umbral de operación

Con presupuesto del 20% de árboles para revisión en campo:
- **Recall**: 45% de estancados detectados
- **Precision**: 50% (1 de cada 2 alertas es real)
- **Árboles a revisar**: ~143 de 717

---

## Fugas bloqueadas

> [[Protocolo Estancamiento#4. Las cuatro fugas]] para detalle completo

1. ✅ Ventana de etiqueta: features solo de olas ≤ t
2. ✅ Expectativa: etiqueta no usa expectativa global
3. ✅ Agregados: solo rezagos, no agregados de historia completa
4. ✅ Preprocesamiento: Pipeline de scikit-learn (fit solo en train)

---

## Limitaciones declaradas

> [!warning] Ir a la tesis
> 1. Sin fechas, no se puede anualizar incrementos
> 2. Altura parece corregida contra valor anterior (0 decrementos después de M2)
> 3. 39% de alturas son múltiplos de 5 cm (redondeo vs señal)
> 4. Evidencia "sugestiva, no concluyente" para superar regla simple
> 5. Transferencia espacial no viable (3 localidades, San Antonio = 1 parcela)

---

## Tasks

| Task | Estado | Descripción |
|---|---|---|
| Task 1 | ⬜ | Implementar `build_wave()` + featurización |
| Task 2 | ⬜ | Pipeline logística con ColumnTransformer |
| Task 3 | ⬜ | Validación temporal M3→M4 |
| Task 4 | ⬜ | Bootstrap IC 95% agrupado por parcela |
| Task 5 | ⬜ | Control negativo (permutación) |
| Task 6 | ⬜ | Feature importance + calibration plot |
| Task 7 | ⬜ | Test anti-leakage |
| Task 8 | ⬜ | API + integración con [[Slice 2 - Persistencia y API]] |

---

## Archivos

| Archivo | Contenido |
|---|---|
| `ml/stall_protocol.py` | Protocolo completo (futuro) |
| `ml/preprocessing.py` | Pipeline compartido train/serve (futuro) |
| `ml/model.py` | Inferencia (futuro) |

---

## Links

- [[Protocolo Estancamiento]] — Diseño completo + código + resultados
- [[Slice 3 - Riesgo de Mortalidad]] — Proceso complementario
- [[Slice 5 - Analítica de Crecimiento]] — Siguiente
- [[Resumen ML]] — Visión general
