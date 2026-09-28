---
aliases: [Slice 4, Estancados, Detección]
tags: [slice, hecho]
status: hecho
protocolo: "[[Protocolo Estancamiento]]"
---

# Slice 4 — Detección de Estancados/Anómalos

> [!abstract] Regresión logística + regla de negocio (no IsolationForest)
> **Estado**: ✅ Hecho (2026-09-27) | **Protocolo**: [[Protocolo Estancamiento]]
> **Modelo**: Logística `stall-logreg-2026-09-27.3` (PR-AUC 0.478 en M3→M4, interpretable)
> **Orden**: va ANTES de [[Slice 3 - Riesgo de Mortalidad]] (invertido el 2026-09-21)

> [!important] Este es el primer slice de modelo — y alimenta al de mortalidad
> 1. **Tiene evidencia suficiente**: 153 eventos positivos en el intervalo de
>    prueba (310 en el panel completo, prevalencia 23%) y un protocolo cerrado
>    con PR-AUC 0.469 bajo validación honesta. Mortalidad tiene 33–37 eventos
>    por ola (EPV 4–11) — no alcanza.
> 2. **Produce `estancó_intervalo_previo`**, el predictor más fuerte que
>    tenemos: OR 2.92 dentro del propio modelo de estancamiento y OR 1.70
>    (marginal, p=0.10) en el de mortalidad. El Slice 4 alimenta al 3.

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
| Eventos positivos (panel) | 310 de 1.335 obs árbol-intervalo |

---

## Por qué la especie manda aquí ([[Slice 5 - Analítica de Crecimiento]])

El modelo mixto sobre `panel_estancamiento.csv` dice algo operativamente
distinto a lo del modelo de mortalidad:

| Hallazgo | Valor | Implicación |
|---|---|---|
| Varianza especie / parcela | 0.846 / 0.317 (**razón 2.7×**) | La especie pesa casi el triple que el sitio |
| ICC especie / parcela | 0.190 / 0.071 | El efecto de especie no es ignorable |
| Rango OR entre especies | 0.24 – 4.94 (**factor 20×**) | Elegir bien qué plantar cambia el resultado |
| Especies significativas | 8 de 30 | Señal concreta, no difusa |
| Parcelas significativas | 3 de 42 | El sitio casi no discrimina |
| Efecto fijo más fuerte | Estancó intervalo previo, **OR 2.92** | Justifica que este slice vaya primero |
| Fitosanidad deficiente | OR 2.30 | Segunda palanca |

**Se estancan más**: *Lafoensia speciosa* (OR 4.94), *Delostoma integrifolium*
(4.71), *Persea caerulea* (3.82), *Delostoma roseum* (2.98), *Cedrela montana*
(2.29).
**Se estancan menos**: *Verbesina arborea* (0.24), *Heliocarpus popayanensis*
(0.35), *Senna viarum* (0.61).

> [!tip] Lectura estratégica
> Estancamiento es un problema **dominado por la especie**: se ataca eligiendo
> qué plantar. La especie es, por tanto, una feature de primer orden del modelo.

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
| Task 1 | ✅ | Implementar `build_wave()` + featurización |
| Task 2 | ✅ | Pipeline logística con ColumnTransformer (reimplementado en Python puro, `ml/preprocessing.py`, con test de paridad) |
| Task 3 | ✅ | Validación temporal M3→M4 |
| Task 4 | ✅ | Bootstrap IC 95% agrupado por parcela |
| Task 5 | ✅ | Control negativo (permutación) |
| Task 6 | ✅ | Coeficientes versionados en el artefacto (feature importance). Calibration plot y UI de importancia quedan fuera de alcance — mejora futura (Protocolo §10) |
| Task 7 | ✅ | Test anti-leakage |
| Task 8 | ✅ | API + integración con [[Slice 2 - Persistencia y API]] |
| Task 9 | ✅ | `estancó_intervalo_previo` = `domain.stall_rules.stalled_previous_interval` (derivada, no persistida — ADR-013) |

---

## Archivos

| Archivo | Contenido |
|---|---|
| `backend/src/agrosense/domain/stall_rules.py` | Etiqueta, regla de negocio (`stalled_previous_interval`), `RULES_VERSION` |
| `backend/src/agrosense/ml/stall_features.py` | Featurización relativa a la ola, compartida train/serve |
| `backend/src/agrosense/ml/preprocessing.py` | Preprocesamiento en Python puro (paridad con `SimpleImputer`+`StandardScaler`+`OneHotEncoder`) |
| `backend/src/agrosense/ml/stall_model.py` | Carga y validación del artefacto, inferencia servible |
| `backend/src/agrosense/ml/train_stall.py` | Entrenamiento, evaluación honesta, ML eval gate |
| `backend/scripts/train_stall_model.py` | Comando único de entrenamiento/verificación (`--check`) |

---

> [!warning] Correcciones al implementar (E7, ADR-013)
> - Los **153** estancados son de la ola de **entrenamiento** (M2→M3); la de prueba (M3→M4) tiene **157**.
> - `Unidad de monitoreo` es el **tipo** de unidad (3 niveles), no la parcela. La parcela (`Codigo de unidad muestreo`) no es feature: es la unidad de agrupamiento.
> - La igualdad de alturas se compara en milímetros (0,24 → 0,245 m cuenta como crecimiento).
> - El umbral «≤ 5 cm» es la definición descriptiva de E4, no la etiqueta del modelo.
> - El control negativo que vigila fugas es la permutación **global** de la etiqueta; la permutación dentro de parcela conserva la tasa de cada parcela y puntúa ≈ 0.33 (ADR-013).
> - Fix wave de revisión final: normalización de categóricas + aviso `unknown_categories`, test de paridad Excel→DB, `RULES_VERSION` invalida el snapshot, el scorer se resuelve después de validar dueño/monitoreo, `adapters/` no puede importar `ml/train_stall` ni `ml/evaluation`. Artefacto final: `stall-logreg-2026-09-27.3`.

## Links

- [[Protocolo Estancamiento]] — Diseño completo + código + resultados
- [[Slice 2 - Persistencia y API]] — Anterior (datos y API base)
- [[Slice 3 - Riesgo de Mortalidad]] — **Siguiente**; consume `estancó_intervalo_previo`
- [[Slice 5 - Analítica de Crecimiento]] — Efectos por especie/parcela del modelo mixto
- [[Resumen ML]] — Visión general
