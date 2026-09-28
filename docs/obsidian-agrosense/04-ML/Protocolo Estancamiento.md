---
aliases: [Protocolo Estancamiento, Detección Estancados, Stall Protocol]
tags: [ml, protocolo, estancamiento]
status: validado
fecha: 2024-09-19
fuente: auditoría externa del dataset
---

# Protocolo a Prueba de Fugas — Detección de Crecimiento Estancado

> [!abstract] Diseño ML para detectar árboles que no crecen
> **Estado**: ✅ Validado | **Modelo**: Logística (PR-AUC 0.469) | **Dataset**: 856 árboles, 4 monitoreos
> **Fuente**: Auditoría externa del dataset `Monitoreo_4`

---

## 1. Qué contiene realmente la base

> [!important] Datos crudos
> - 856 individuos, 4 eventos de monitoreo, formato ancho
> - 30 especies, 54 unidades de muestreo, 3 localidades
> - 2675–2827 m s.n.m.

### Cinco hechos que condicionan todo el diseño

> [!warning] Limitaciones críticas del dataset

1. **No hay fechas.** Ninguna hoja contiene fecha de monitoreo ni de siembra. No se puede anualizar incrementos, modelar edad, ni tratar la duración del intervalo como covariable. Todo queda en unidades de "por intervalo de monitoreo".

2. **DAP no es utilizable como variable de crecimiento.** Solo 83/856 árboles tienen DAP en M4 (9.7%) y 27 en M3 (3.2%). Es censura por umbral, no dato faltante aleatorio. Un DAP vacío significa "por debajo del umbral". La variable de crecimiento del protocolo es la **altura total**.

3. **Cohorte de 139 árboles entra en M3** (70 en Tres Jotas, 69 de San Antonio). No tienen historia previa. En la ola de prueba, 126 de 717 árboles en riesgo carecen de incremento rezagado.

4. **Altura nunca decrece después de M2.** M1→M2 tiene 13 incrementos negativos; M2→M3 y M3→M4 tienen **cero** en 619 y 718 observaciones. La altura parece revisarse contra el valor anterior. Consecuencia: no se puede estimar error de medición, y "no creció" incluye una porción desconocida de error de medición redondeado a cero.

5. **Apilamiento de dígitos.** 39% de las alturas son múltiplos de 5 cm. Con incremento mediano de 9 cm por intervalo, el redondeo es del mismo orden que la señal.

### Auditoría de datos

> Ver `auditoria_datos.csv` para el CSV completo con hallazgos cuantificados

| Métrica | Valor |
|---|---|
| Individuos | 856 |
| Monitoreos | 4 |
| Especies | 30 |
| Unidades de muestreo | 54 |
| Localidades | 3 |
| Fechas de monitoreo | **NINGUNA** |
| Cohorte sin historia (M3) | 139 |
| DAP con dato M4 / total | 83 / 856 (9.7%) |
| Altura mediana M1→M4 | 0.24 → 0.60 m |
| Inc. negativos altura M1→M2 | 13 de 652 |
| Inc. negativos altura M2→M3 | 0 de 619 |
| Inc. negativos altura M3→M4 | 0 de 718 |
| Alturas múltiplos de 5 cm | 39.2% |
| Prevalencia Δaltura=0 por intervalo | 0.172 / 0.248 / 0.219 |
| Árboles con 3 intervalos estancados | 24 de 592 |
| Secuencias inconsistentes (resurrección) | 5 árboles |
| Árboles Muertos en las 4 olas | 42 |

---

## 2. Definición de la etiqueta

> [!important] Estancado(i, t) = 1 si la altura no cambió entre t y t+1

```
Estancado(i, t) = 1  si  altura(i, t) == altura(i, t+1)
                   y árbol vivo en ambos
```

### Prevalencia por intervalo

| Intervalo | Prevalencia |
|---|---|
| M1→M2 | 0.172 |
| M2→M3 | 0.248 |
| M3→M4 | 0.219 |

### Por qué esta definición

> [!note] Ventajas de esta definición
> 1. **No requiere estimar una expectativa** → elimina la fuga por expectativa
> 2. **Es directamente auditable** en campo
> 3. **La masa exacta en cero** (~22%) es un rasgo real, no artefacto

### Debilidad declarada

> [!warning] Limitación de la etiqueta
> Con resolución de 1 cm y redondeo a 5 cm, parte de los ceros son árboles que crecieron 1–3 cm. La etiqueta mide **"crecimiento no detectable por el protocolo"**, no "crecimiento nulo".

### Población en riesgo

Solo árboles **vivos en t y en t+1**, con altura medida en ambos. Los que mueren se excluyen — mortalidad y estancamiento son procesos distintos. La mortalidad merece su propio modelo.

---

## 3. Diseño de validación

### Régimen primario — Validación adelantada en el tiempo

| | Entrenamiento | Prueba |
|---|---|---|
| **Instante de predicción** | M2 | M3 |
| **Features** | registros ≤ M2 | registros ≤ M3 |
| **Etiqueta** | intervalo M2→M3 | intervalo M3→M4 |
| **n en riesgo** | 618 | 717 |
| **Prevalencia** | 0.248 | 0.219 |

> [!important] Es el único que responde la pregunta de despliegue
> ¿Puede la plataforma señalar hoy qué árboles no crecerán hasta el próximo monitoreo?

### Régimen secundario — Validación cruzada agrupada

- **GroupKFold**, 5 folds, agrupado por unidad de muestreo
- Sirve como diagnóstico: la diferencia con el régimen primario cuantifica cuánto del desempeño aparente es interpolación dentro de la misma ola

### Lo que NO es viable

> [!danger] No hacer
> Validación espacial dejando una localidad fuera. Son 3 localidades, San Antonio es una sola parcela que entra en M3. Con 2 folds efectivos no hay estimación de transferencia espacial defendible. **Declarar como limitación, no inventar.**

### Featurización relativa a la ola

Las variables se llaman `altura_t`, `incremento_rezagado`, `estancó_intervalo_previo` — NO `altura_M3`. Así la matriz de entrenamiento y prueba tienen la misma semánica, y el modelo es aplicable a la ola M5 sin reentrenar.

---

## 4. Las cuatro fugas y cómo se bloquean

### 4.1 Fuga por ventana de etiqueta

> [!danger] Cualquier variable medida en t+1 está dentro del intervalo que define la etiqueta
> **Sospechosos**: Estado Fitosanitario_M4, Diámetro Copa_M4, Sobrevivencia M4
> **Bloqueo**: `build_wave(lg, t)` construye features solo desde olas ≤ t

### 4.2 Fuga por expectativa

> [!danger] Si "estancado" se definiera contra crecimiento esperado por especie/sitio
> **Bloqueo**: la etiqueta adoptada no usa expectativa. Si se quiere la versión "por debajo de lo esperado", la referencia debe ajustarse **dentro de cada fold** y aplicarse al fold retenido

### 4.3 Fuga por agregados de historia completa

> [!danger] media de crecimiento del árbol, crecimiento total, altura final, Categoría M4
> **Bloqueo**: solo rezagos, nunca agregados que crucen el instante de predicción

### 4.4 Fuga por preprocesamiento

> [!danger] Estandarización, imputación, codificación de especie por tasa media, binning por cuantiles
> **Bloqueo**: todo dentro de un `Pipeline` de scikit-learn que se ajusta solo con datos de entrenamiento

---

## 5. Resultados

### Comparación de desempeño

> [!note] Métrica principal: PR-AUC
> Clase positiva minoritaria (22%), exactitud engañosa con 78% negativos.
> Intervalos al 95% por bootstrap agrupado por parcela.

| Modelo | PR-AUC | IC 95% | ROC-AUC | Recall@20% | Precision@20% |
|---|---|---|---|---|---|
| Prevalencia (sin modelo) | 0.219 | 0.18–0.26 | 0.500 | 0.22 | — |
| Persistencia (estancó antes) | 0.350 | 0.24–0.46 | 0.660 | 0.43 | 0.47 |
| Tasa media por especie | 0.382 | 0.32–0.46 | 0.697 | 0.41 | 0.45 |
| **Regresión logística** | **0.469** | **0.36–0.58** | **0.735** | **0.45** | **0.50** |
| Gradient boosting | 0.454 | 0.34–0.55 | 0.735 | 0.43 | 0.48 |
| Control negativo (permutado) | 0.238 | 0.18–0.31 | 0.513 | 0.21 | 0.23 |

### Lectura honesta

> [!important] La frase que debe ir en la tesis
> El modelo duplica la tasa base y supera claramente a la regla de persistencia, pero los intervalos de confianza de la logística (0.36–0.58) y de la regla por especie (0.32–0.46) se solapan. Con 717 árboles en ~39 parcelas, **la evidencia de que el modelo supera a una regla de una línea es sugestiva, no concluyente**.

> [!note] La regresión logística y el gradient boosting empatan
> No hay ganancia por complejidad, lo que es esperable con este tamaño muestral y argumenta a favor del **modelo interpretable** para una plataforma de decisión.

### El control negativo funciona

Permutando etiquetas dentro de cada parcela, el desempeño cae a 0.238, indistinguible de la prevalencia. **Prueba de que el pipeline no tiene fugas.**

### Cuánto infla cada fuga

| Variante con fuga | PR-AUC | Inflación sobre honesto |
|---|---|---|
| Añadir fitosanidad de cierre | 0.485 | +7% |
| Añadir crecimiento medio de 4 olas | 0.610 | **+34%** |
| CV aleatoria por fila | 0.566 | **+25%** |

> [!warning] La fuga más peligrosa es la tercera
> Basta usar `train_test_split` o `KFold` sin `groups` sobre la tabla apilada para que el mismo árbol quede a ambos lados. Es el error más común en datos de panel.

---

## 6. Umbral de operación

> [!important] El modelo entrega probabilidad, no una decisión
> Fija un **presupuesto de alertas**, no un umbral de 0.5.

| Presupuesto | Recall | Precision | Árboles a revisar |
|---|---|---|---|
| 10% | ~30% | ~65% | ~72 |
| **20%** | **45%** | **50%** | **~143** |
| 30% | ~55% | ~40% | ~215 |

Con el 20% de árboles marcados para revisión en campo, la regresión logística recupera el 45% de los estancados con 50% de precisión. **Ese es el número accionable para un equipo de campo con tiempo limitado.**

> [!warning] Reglas para el umbral
> - Recalibrar por localidad si las tasas base difieren
> - **Nunca** elegir maximizando métrica sobre la ola de prueba (eso vuelve a ser fuga)

### Agregado: Curva de costos (futuro)

> [!todo] Por implementar
> Definir costo de revisar un árbol vs costo de no detectar estancamiento.
> Con esos costos, encontrar el umbral que minimiza el costo total.
> Esto es más accionable que un presupuesto arbitrario del 20%.

---

## 7. Qué pedir en el próximo monitoreo

> [!important] Recomendaciones por orden de impacto

1. **Fecha de cada medición, por árbol.** Habilita anualizar incrementos, modelar edad, tratar duración del intervalo como covariable. La mejora individual más grande.

2. **No corregir la altura contra el valor anterior.** Registrar la medición cruda, incluso si baja. Los decrementos permiten estimar error de medición.

3. **Doble medición en submuestra (~30 árboles).** Estima repetibilidad y cuántos "estancados" son ruido.

4. **Registrar DAP siempre**, con umbral anotado explícitamente, o marcar "bajo umbral" en vez de dejar celda vacía.

5. **Conservar árboles muertos y resiembras** con identificador propio. Hay 5 con supervivencia inconsistente y 42 registrados como muertos en las 4 olas.

---

## 8. Sentinel-2

> [!warning] Regla operativa para NDVI/EVI/NDMI
> La fecha de la imagen debe ser **estrictamente anterior** a la visita t.
> La composición temporal (mediana de los últimos N días) no puede incluir fechas posteriores.

> [!note] Limitación de resolución
> Con parcelas de ~69 árboles y píxeles Sentinel-2 de 10 m, varios árboles comparten píxel. El índice es una **variable de parcela**, no de árbol. Refuerza agrupar por parcela en validación.

---

## 9. Implementación (código)

> Ver `agrosense_stall_protocol.py` para el script completo

### Features del modelo

| Feature | Tipo | Descripción |
|---|---|---|
| `h_t` | num | Altura actual |
| `copa_t` | num | Diámetro de copa actual |
| `dh_lag` | num | Crecimiento del intervalo anterior |
| `dcopa_lag` | num | Crecimiento de copa anterior |
| `estanco_lag` | num | ¿Estancó en intervalo previo? (0/1) |
| `h_prev` | num | Altura previa |
| `esbeltez_t` | num | Altura / Copa |
| `fito_empeoro` | num | Cambio en estado fitosanitario |
| `LOCALIDAD` | cat | Localidad |
| `Especie_M1` | cat | Especie |
| `Unidad de monitoreo` | cat | Parcela |
| `fito_t` | cat | Estado fitosanitario actual |

> [!warning] Correcciones al implementar (E7, ADR-013)
> - `Unidad de monitoreo` es el **tipo** de unidad (3 niveles), no la parcela. La parcela (`Codigo de unidad muestreo`) no es feature: es la unidad de agrupamiento.
> - La igualdad de alturas se compara en milímetros (0,24 → 0,245 m cuenta como crecimiento).
> - El control negativo que vigila fugas es la permutación **global** de la etiqueta; la permutación dentro de parcela conserva la tasa de cada parcela y puntúa ≈ 0.33 (ADR-013).

### Pipeline

```python
Pipeline([
    ("pre", ColumnTransformer([
        ("num", [Imputer(median) + Scaler], NUM),
        ("cat", [Imputer(most_frequent) + OneHot], CAT),
    ])),
    ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)),
])
```

### Validación

```python
# Temporal (primaria)
train: ola ≤ t, test: intervalo (t, t+1]
# GroupKFold (secundaria)
GroupKFold(n_splits=5, groups=unidad_muestreo)
```

---

## 10. Agregados (mejoras propuestas)

### Feature importance

> [!todo] Por implementar
> Extraer coeficientes de la logística para identificar qué variables impulsan la predicción.
> Relevante para interpretabilidad y para decidir qué medir en el futuro.

### Calibration plot

> [!todo] Por implementar
> Graficar probabilidad predicha vs frecuencia observada.
> Necesario para fijar umbrales con confianza.

### Análisis por subgrupo

> [!todo] Por implementar
> Descomponer desempeño por localidad y especie.
> Puede revelar donde el modelo funciona bien y donde no.

### Test de smoke anti-leakage

> [!todo] Por implementar
> Assert automático: features de test no contienen información de t+1.
```python
def test_no_leakage(X_test, t):
    assert not any(col.endswith(f"_M{t+1}") for col in X_test.columns)
```

### Threshold por localidad

> [!todo] Por implementar
> Si las tasas base difieren entre localidades, calibrar umbral por localidad.
> Implementar como función que recibe prevalencia local y devuelve umbral óptimo.

---

## Links

- [[Slice 4 - Detección de Estancados]] — Feature del proyecto
- [[Resumen ML]] — Visión general ML
- [[Modelo de Dominio]] — Entidades
- [[ADR-004 - Ingesta de Datos]] — Preprocessing
- [[Slice 3 - Riesgo de Mortalidad]] — Proceso complementario
