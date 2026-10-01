# E8 · Riesgo de mortalidad — Plan de implementación

**Goal:** que el ingeniero abra el análisis de un monitoreo y vea qué árboles vivos tienen más
riesgo de morir antes del próximo monitoreo, en CUALQUIER proyecto: un modelo general (tamaño
relativo, validado en 3 proyectos) para el arranque, y un modelo propio del proyecto que se
reentrena con cada monitoreo y solo se sirve si supera al general en el último intervalo cerrado.

**Spec / evidencia:** `docs/04-vision-producto.md` §9 E8; `docs/spikes/generalizacion_pasos_1_2.md`
(exp_c, exp_d); `docs/spikes/exp_e.py` (LOPO); ADR-013 (patrón de E7); ADR-014 (este plan).

## Decisiones

| # | Decisión | Por qué |
|---|---|---|
| D1 | Etiqueta `died_in_interval(prev, curr)`: población en riesgo = vivo y con altura en t (`is_at_risk`); 1 si `curr.alive is False`, 0 si `True`; `None` (excluido) si no hay dato en t+1. | Misma población que E7. Anexo 1: 31/33/37 muertes en M1→M2/M2→M3/M3→M4. |
| D2 | **Modelo general = 1 variable, `h_pct`** (percentil de altura dentro de la población en riesgo de la ola). Entrenado con Anexo 1 + Werden 2018 + Werden 2020. | exp_e: coeficiente estable (−1.04 a −1.18) en los 3 cortes LOPO y 1.2–2.9× el azar en TODOS los intervalos fuera de muestra. `estanco_lag` cambia de signo entre proyectos: no transfiere. |
| D3 | El modelo general se presenta como **riesgo relativo** (rango y presupuesto de alertas), no como probabilidad. | Las prevalencias van de 5 % a 71 % según proyecto/intervalo; una probabilidad calibrada en otros proyectos sería falsa. |
| D4 | **Modelo propio**: `h_pct, estanco_lag, dh_lag` + `species, fito_t, locality`, logística L2 (C=0.5) en **Python puro** sobre los intervalos cerrados del proyecto (u→u+1 con u+1 ≤ t). | Reabre ADR-013 (que rechazaba entrenar por proyecto): exp_d/Anexo 1 muestran 2.5–3.5× cuando el proyecto tiene historia. Python puro porque scikit-learn no entra a producción (ADR-013 §6). |
| D5 | **Gate automático** (reemplaza la revisión humana solo para el modelo propio): se entrena con los intervalos cerrados menos el último, se compara PR-AUC propio vs general en el último; se sirve el propio (reentrenado con todos) si gana y hay ≥ 10 muertes de entrenamiento y ≥ 5 en la prueba. Si no, el general. La decisión y sus cifras viajan en el snapshot. | Un modelo por proyecto no puede esperar revisión humana; el general sí pasó su gate offline. Con 1 intervalo de prueba la elección es ruidosa: se documenta, no se oculta. |
| D6 | Gate offline del general, **pre-registrado antes de entrenar con datos reales**: en cada proyecto fuera, (mediana del lift por intervalo) / (mediana del lift con sus etiquetas permutadas) ≥ 1.2 y coeficiente negativo. | El test sintético reveló dos fallos del control original antes de usar datos reales: con una sola variable, permutar las etiquetas de entrenamiento es degenerado (el orden solo depende del signo), y el PR-AUC de un orden aleatorio tiene sesgo positivo con pocos eventos (~1.16×), así que el umbral debe compararse con el azar empírico del mismo proyecto. |
| D7 | Artefacto JSON `ml/artifacts/mortality_general.json` + `docs/ml/evaluacion-mortalidad.md`, un comando: `python scripts/train_mortality_general.py --data data/raw/anexo1.xlsx`. Werden se descarga de Zenodo con SHA-256 fijado a `data/external/` (ignorado por git). | Reproducibilidad (AGENTS.md §ML) sin meter datos al repo. |
| D8 | Snapshot `mortality_assessments` (UNIQUE monitoring_id, `model_kind`, `model_version`, `artifact_sha256`, `input_hash`, `rules_version`, payload JSON). `input_hash` = observaciones ≤ t (cubre también los datos de entrenamiento del modelo propio). | Mismo criterio que ADR-008/013: toda predicción trazable. |
| D9 | **Deuda D se cierra aquí**: `campaign_files.content` (binario, nullable para cargas previas) guarda el Excel crudo. | Gate de la deuda D: «antes de la primera épica de ML que entrene con datos subidos por usuarios». |
| D10 | Presupuesto de alertas 20 % con `select_alerts` de E7. | Una sola regla de alertas en el producto. |

## Slices (cada uno TDD, commit propio)

1. **S1 Contrato:** ADR-014; este plan. Tests de arquitectura ya cubren `ml/` (rglob).
2. **S2 Deuda D:** migración `campaign_files.content`; `upload_campaign` guarda los bytes; test de repositorio + test de migración (deriva de esquema ya lo vigila).
3. **S3 Dominio:** `domain/mortality_rules.py` (`died_in_interval`, `MORTALITY_RULES_VERSION`) + tests unitarios (vivo→muerto, vivo→vivo, sin dato, muerto en t excluido).
4. **S4 Logística pura:** `ml/logistic.py` (`fit_logistic_l2` Newton-IRLS con `class_weight` balanceado opcional, `predict_scores`) + test de paridad contra scikit-learn (extra `ml`).
5. **S5 Features:** `ml/mortality_features.py` (`build_mortality_wave(trees, obs, t, labeled)` → filas con `h_pct`, `estanco_lag`, `dh_lag`, `species`, `fito_t`, `locality`; solo usa obs ≤ t para features) + tests de no-fuga (cambiar t+1 no cambia features).
6. **S6 Modelo general:** `ml/mortality_model.py` (`GeneralMortalityModel`, carga validada del artefacto, 503 si versión de features no coincide); `scripts/train_mortality_general.py` (descarga verificada, adaptadores Werden en el script, LOPO, gate D6, artefacto, reporte, `--check`).
7. **S7 Modelo propio + gate:** `ml/mortality_project.py` (`train_project_model`, `choose_model` → decisión con cifras) + `MortalityScorer` compuesto; tests con datasets sintéticos (señal fuerte → propio; pocos eventos → general).
8. **S8 Persistencia + caso de uso:** tabla/migración/repositorio `mortality_assessments`; `application/use_cases/mortality_risk.py` (`get_mortality_assessment`, puerto `MortalityScorer`, dueño antes que scorer como E7).
9. **S9 API:** `GET /projects/{id}/monitorings/{n}/mortality-risk?only_flagged=` (`def`), esquemas pydantic, errores `PROJECT_NOT_FOUND`/`MONITORING_NOT_FOUND`/`MODEL_UNAVAILABLE`; tests de integración (dueño, ajeno 404, M sin siguiente, snapshot reutilizado).
10. **S10 UI:** `api/mortality.ts` + panel «Árboles en riesgo de morir» en el análisis (modelo usado y por qué, tabla con presupuesto 20 %, aviso de riesgo relativo con el general) + tests vitest; E2E: el panel aparece en M3.
11. **S11 Cierre:** suite completa, mypy, ruff, pip-audit, lint/test/build/e2e, `docs/verificacion-e8.md`, roadmap; revisión automática; merge.
