# Discovery — AgroSense AI v2

Estado: COMPLETADO (2026-09-14) · Documenta los requisitos previos al dominio.

## 1. Propósito del producto

Herramienta de campo real para ingenieros que ejecutan proyectos de
restauración ecológica. Después de cada jornada de monitoreo, el ingeniero
carga los datos recolectados (CSV/XLSX) y la plataforma analiza:

- riesgo de mortalidad por árbol (priorización de intervención/replanteo),
- detección de árboles estancados/anómalos,
- analítica de crecimiento por especie y sitio.

## 2. Usuarios y modelo de uso

**Usuario primario:** ingeniero de campo, no analista de datos.
- Maneja varios proyectos de restauración simultáneos (sitios distintos).
- Flujo central: recolectar → armar CSV → subir → ver análisis.
- La herramienta debe ahorrarle el trabajo manual que hoy hace en Excel
  (tablas dinámicas por monitoreo — ver hojas 2-8 del Anexo 1).

**Dataset de referencia:** `Anexo 1 Base de datos 4 MONITOREO.xlsx`
(hoja `Monitoreo_4`) = proyecto ejemplo/demuestra, no la app en sí.

## 3. Decisiones de producto (confirmadas)

| Tema | Decisión | Razón |
|---|---|---|
| Modelo de datos | Multi-proyecto: cada restauración es un Proyecto con sus monitoreos | Los ingenieros trabajan varios sitios |
| Flujo de datos | Upload CSV/XLSX como operación central (no dataset precargado) | Es el flujo real de campo |
| Deploy | Cloud gratuito (Render/Railway/Fly) | Accesible por link sin infra propia |
| Auth | Sin login en MVP; diseñado para añadirse después | Simplifica el alcance inicial |

## 4. Restricciones conocidas

- Datos reales: 856 árboles, M1-M4, 3 localidades — pequeño pero real.
- El MAE honesto del modelo de crecimiento (~11 cm) no sostiene forecasts
  por árbol; el producto se ancla en mortalidad/anomalías/analítica.
- Cloud gratuito ⇒ límites de RAM/CPU/ejectución síncrona: los pipelines
  deben ser acotados y rápidos (dataset pequeño lo permite).

## 5. Fuente de verdad de datos

- Formato de entrada esperado: estructura de la hoja `Monitoreo_4`
  (una fila por árbol, columnas M1..M4 anidadas) — a definir el contrato
  exacto de columnas en la épica 1.
- Todo análisis se recalcula desde los datos crudos subidos; nada se
  precalcula a mano (las hojas dinámicas del Anexo no son fuente).

## 6. Spike ML — evidencia de viabilidad (ya ejecutado)

**Metodología:** evaluación honesta (GroupKFold por árbol, sin variables
derivadas del target) sobre el dataset de referencia.

| Resultado | Valor | Implicación |
|---|---|---|
| Señal estancado→muerte | crecimiento ≤5cm ⇒ 10.7% muere en M4 vs 0.3% (>5cm) — **riesgo 35x** | Feature estrella: riesgo de mortalidad |
| Mortalidad acumulada | 16% (138/856), por especie 0%–87.5% | Hay target binario real con varianza por especie |
| Crecimiento (regresión honesta) | R²≈0.46–0.49, MAE≈0.11m vs mediana 0.09m | NO vender forecast por árbol; usar como score de salud |
| Señal por especie | medias 0.043–0.465m (rango 10x) | Ranking especie/sitio válido |
| Datos M1 recuperables | +652 transiciones M1→M2 | Incluir M1 en ingesta |
| v1 (con leakage) | R²=0.968 con `altura_actual` como feature | Confirmado: era la resta disfrazada, no ML |

**Go/No-Go: GO** — existe señal predictiva real para mortalidad y anomalías;
la regresión de crecimiento se posiciona como scoring, no forecast exacto.

## 7. Fuera de alcance (MVP)

- Login/usuarios (épica futura)
- Forecast preciso por árbol (señal insuficiente)
- App móvil offline (el CSV se arma en Excel por ahora)
