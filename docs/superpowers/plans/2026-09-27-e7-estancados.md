# E7 · Detección de estancados — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el ingeniero abra el análisis de un monitoreo y vea qué árboles vivos tienen más probabilidad de no crecer hasta el próximo monitoreo (UC-AN4), con un modelo de regresión logística entrenado y evaluado sin fugas, versionado y trazable, y con la regla de negocio que produce `estancó_intervalo_previo` para E8.

**Architecture:** La etiqueta y la regla de negocio viven en `domain/stall_rules.py` (puras). La featurización relativa a la ola y el preprocesamiento son un único módulo en Python puro dentro de `ml/`, compartido por entrenamiento e inferencia. El entrenamiento es **offline** (un script, un comando, scikit-learn solo como extra `ml`) y produce un artefacto JSON versionado en git con coeficientes, parámetros de preprocesamiento, métricas del ML eval gate y procedencia. La API sirve la inferencia en un endpoint síncrono (`def`) que guarda un snapshot por monitoreo (`stall_assessments`, mismo criterio que ADR-008) y el frontend lo muestra en un panel de la página de análisis.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, pydantic 2; scikit-learn 1.5.2 + numpy 1.26.4 (solo entrenamiento); React 18 + TypeScript + Vitest.

**Spec:** `docs/04-vision-producto.md` (§9 E7, §8 UC-AN4, §10 dependencias); `docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md` (autoridad del modelo); `docs/obsidian-agrosense/06-Slices/Slice 4 - Detección de Estancados.md`; `docs/obsidian-agrosense/04-ML/Resumen ML.md`; `docs/obsidian-agrosense/01-Proyecto/Roadmap.md`; `AGENTS.md` (§ML, §Data provenance, ML eval gate); ADR-003, ADR-008, ADR-012.

## Global Constraints

Valores copiados literalmente de la fuente; todas las tareas los cumplen implícitamente.

- **Etiqueta (Protocolo §2):** `Estancado(i, t) = 1  si  altura(i, t) == altura(i, t+1) y árbol vivo en ambos`.
- **Población en riesgo (Protocolo §2):** «Solo árboles **vivos en t y en t+1**, con altura medida en ambos. Los que mueren se excluyen — mortalidad y estancamiento son procesos distintos.»
- **Resolución de la igualdad (decisión de este plan, ADR-013):** se compara en milímetros, `round(h * 1000)`. Con esa regla el dataset de referencia da 618 en riesgo / 153 estancados (M2→M3) y 717 / 157 (M3→M4), idéntico a `backend/data/processed/panel_estancamiento.csv`. Comparar en centímetros fusiona 0,24 y 0,245 m (árbol `FR_1_31`) y da 158.
- **Validación primaria (Protocolo §3):** «Entrena M2→M3, prueba M3→M4» — instante de predicción M2 para entrenar, M3 para probar.
- **Validación secundaria (AGENTS.md):** «group split por **parcela** — `Codigo de unidad muestreo`, NO por árbol»; `GroupKFold(n_splits=5, groups=unidad_muestreo)`.
- **AGENTS.md (ML):** «Training and inference must share preprocessing logic.» «Never use information unavailable at prediction time.» «Never allow target leakage.» «The same observation (same tree + same monitoring time) must never appear in both train and test.» «Model artifacts must be versioned.» «Metrics must be documented.» «A model is only reproducible if it can be rebuilt from code + config + data version + pinned dependencies. Random seeds are controlled. Evaluation is repeatable via one documented command (no .pkl black boxes).»
- **AGENTS.md (Data provenance):** «Record at least: source dataset version, ingestion script version, preprocessing version, feature definitions, model version, training/eval configuration, timestamp.»
- **Modelo (Protocolo §9):** `LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)`; preprocesamiento `Imputer(median) + Scaler` para numéricas y `Imputer(most_frequent) + OneHot` para categóricas, ajustado solo con entrenamiento.
- **Métrica principal (Protocolo §5):** PR-AUC; «Intervalos al 95% por bootstrap agrupado por parcela». Referencia honesta: logística 0.469 (IC 95% 0.36–0.58); control negativo permutado 0.238 (0.18–0.31). El gate usa 0.36 y 0.31 como umbrales (ver D8 para el control).
- **Umbral de operación (Protocolo §6):** «Fija un **presupuesto de alertas**, no un umbral de 0.5.» Presupuesto 20 %. «**Nunca** elegir maximizando métrica sobre la ola de prueba (eso vuelve a ser fuga)».
- **Dataset versionado:** `backend/data/raw/anexo1.xlsx`, hoja `Monitoreo_4`, SHA-256 `28583c3b48874626f3d7d7ae35d485634a8c8089b4c03a5997f5ba756b57a0dd`. Los datos NUNCA entran al repo (`.gitignore`: `data/raw/`, `*.xlsx`, `*.pkl`, `*.joblib`).
- **Dependencias:** `scikit-learn==1.5.2` y `numpy==1.26.4` solo en `[project.optional-dependencies].ml`; ninguna dependencia nueva de producción. `pip-audit -r requirements.lock.txt` limpio.
- **Capas (ADR-003):** `domain ← application ← adapters | ml`; `ml/` solo importa `domain/`; `application/` no importa `ml/`, `adapters/`, `pandas`, `sqlalchemy`, `fastapi`.
- **API:** endpoints `def` (no `async def`) — lección de v1; errores con la forma `{"detail": {"code", "message"}}`; proyecto ajeno responde igual que inexistente (`PROJECT_NOT_FOUND`); los porcentajes viajan en escala 0–100 (ADR-008).
- **Idioma:** textos de UI y documentos en español con tildes; identificadores en inglés; docstrings del backend en español sin tildes (convención del código existente).
- **Commits:** terminar cada mensaje con `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **RAM baja en la máquina de desarrollo:** durante las tareas se ejecutan solo los tests indicados; la suite completa se corre una vez, en la Task 15.

---

## Decisiones que este plan toma (y conflictos con la documentación)

| # | Tema | Documentación | Decisión | Por qué |
|---|---|---|---|---|
| D1 | Umbral de la etiqueta | Roadmap/Resumen ML hablan de «estancados ≤5cm» (spike de mortalidad) y `domain/rules.py` tiene `STAGNATION_THRESHOLD_M = 0.05` (E4) | La etiqueta del modelo es la **igualdad** del Protocolo; el umbral de 5 cm sigue siendo la definición descriptiva de E4 y no se toca | Las métricas validadas (PR-AUC 0.469) y los 153/157 eventos solo valen para la igualdad; se verificó contra el panel |
| D2 | «153 eventos en el intervalo de prueba» (Slice 4, AGENTS.md) | — | 153 son los estancados de **entrenamiento** (M2→M3); la prueba (M3→M4) tiene **157** | Recontado desde `Monitoreo_4` y coincide con `panel_estancamiento.csv` |
| D3 | Feature `Unidad de monitoreo` = «Parcela» (Protocolo §9) | — | Es `Tree.monitoring_unit`, el **tipo** de unidad (3 niveles: Parcela, Árboles aislados, Unidad de muestreo tipo X). La parcela (`sampling_unit_code`, 54 niveles) **no es feature**: es solo la unidad de agrupamiento | Con la parcela como feature, el modelo memoriza sitios que no existen en otro proyecto; reproducido: PR-AUC 0.478 con esta definición |
| D4 | Dónde se entrena | Resumen ML: `python -m ml.train` | Script offline `backend/scripts/train_stall_model.py` (composition root que lee el Excel con el adapter de ingesta) | `ml/` no puede importar `adapters/` (ADR-003); entrenar en un endpoint repetiría el pipeline ML síncrono de v1 |
| D5 | Artefacto | «sin .pkl» | JSON en `backend/src/agrosense/ml/artifacts/stall_logreg.json`, en git | Legible, auditable, sin ejecución de código al cargar; `.gitignore` ya prohíbe pickle |
| D6 | `estancó_intervalo_previo` persistida (Slice 4, Task 9) | — | No es columna: es la función de dominio `stalled_previous_interval`, y además viaja en el snapshot | Se deriva en microsegundos de las observaciones; guardarla duplicaría una verdad que puede divergir |
| D7 | Regla «≈0 en N intervalos» sin N | Slice 4 | `PERSISTENT_STALL_INTERVALS = 2`, declarado como convención del proyecto pendiente de confirmar con el ingeniero | 1 intervalo ya es `stalled_last_interval`; 2 es el mínimo que merece «persistente» |
| D8 | Control negativo «permutando dentro de cada parcela» = 0.238 (Protocolo §5) | — | Dos controles: permutación **global** ≤ 0.31 vigila fugas; permutación **dentro de parcela** debe quedar por debajo del modelo | Reproducido en este plan: la permutación dentro de parcela da ≈ 0.33 (conserva la tasa de la parcela, que especie y predio permiten aprender: señal de sitio, no fuga); la global da ≈ 0.227 ≈ prevalencia |

---

## Mapa de archivos

| Archivo | Responsabilidad | Tarea |
|---|---|---|
| `docs/adr/013-modelo-estancamiento-offline.md` | Decisión de arquitectura del primer modelo | 1 |
| `backend/pyproject.toml`, `backend/requirements.lock.txt` | Extra `ml`, package-data del artefacto | 1 |
| `backend/tests/architecture/test_layer_dependencies.py` | Reglas de capa para `ml/` y pureza de la ruta de inferencia | 1 |
| `backend/tests/architecture/test_ml_dependencies.py` | scikit-learn fuera de producción | 1 |
| `backend/src/agrosense/domain/stall_rules.py` | Etiqueta, regla de negocio, presupuesto de alertas | 2 |
| `backend/tests/ml/builders.py` | Constructores de entidades y panel sintético para tests | 2, 5 |
| `backend/src/agrosense/ml/__init__.py` | Paquete vacío (no importa sklearn) | 3 |
| `backend/src/agrosense/ml/stall_features.py` | Featurización relativa a la ola + huella de datos (Python puro) | 3 |
| `backend/src/agrosense/ml/preprocessing.py` | Imputación, escalado y one-hot compartidos (Python puro) | 4 |
| `backend/src/agrosense/ml/stall_model.py` | Formato del artefacto, carga validada, scoring (Python puro) | 5 |
| `backend/src/agrosense/ml/evaluation.py` | PR-AUC, ROC-AUC, bootstrap por parcela, líneas base (numpy/sklearn) | 6 |
| `backend/src/agrosense/ml/train_stall.py` | Entrenamiento, evaluación, gate, artefacto, informe (numpy/sklearn) | 7 |
| `backend/scripts/train_stall_model.py` | El comando único de entrenamiento/reproducción | 8 |
| `backend/src/agrosense/ml/artifacts/stall_logreg.json` | Artefacto versionado (generado) | 8 |
| `docs/ml/evaluacion-estancamiento.md` | Métricas documentadas (generado) | 8 |
| `backend/src/agrosense/adapters/db/models.py`, `repository.py`, `alembic/versions/e7c1a3b5d7f9_e7_stall_assessments.py` | Snapshot `stall_assessments` | 9 |
| `backend/src/agrosense/application/dtos.py`, `application/use_cases/stall_detection.py` | UC-AN4 | 10 |
| `backend/src/agrosense/adapters/api/schemas.py`, `errors.py` | Contrato del endpoint | 11 |
| `backend/src/agrosense/adapters/api/routes/stall.py`, `app.py` | Endpoint | 12 |
| `frontend/src/api/types.ts`, `frontend/src/api/stall.ts` | Acceso a datos | 13 |
| `frontend/src/components/StallPanel.tsx`, `pages/MonitoringAnalysisPage.tsx` | UI | 14 |
| `docs/verificacion-e7.md` + notas del vault | Evidencia y documentación | 15 |

## Slices

| Slice | Qué se puede demostrar al cerrarlo | Tareas |
|---|---|---|
| S1 · Contrato del épico | ADR-013 aceptado; `pip install -e ".[dev,ml]"` funciona; tests de arquitectura muerden | 1 |
| S2 · Etiqueta y regla de negocio | `pytest tests/domain/test_stall_rules.py tests/ml/test_stall_labels_real.py` reproduce 618/153 y 717/157 | 2 |
| S3 · Features y preprocesamiento compartidos | Tests anti-fuga y paridad con scikit-learn en verde | 3, 4 |
| S4 · Modelo servible | Un artefacto JSON se carga, se valida y puntúa árboles en Python puro | 5 |
| S5 · Entrenamiento + ML eval gate | `python scripts/train_stall_model.py --data data/raw/anexo1.xlsx` escribe artefacto + informe; `--check` reproduce | 6, 7, 8 |
| S6 · Persistencia y caso de uso | UC-AN4 devuelve y guarda el snapshot, y lo reutiliza | 9, 10 |
| S7 · API | `GET /projects/{id}/monitorings/{n}/stall-assessment` con contrato y errores | 11, 12 |
| S8 · UI | Panel «Árboles en riesgo de estancarse» en el análisis del monitoreo + journey E2E | 13, 14 |
| S9 · Cierre (verify + review) | `docs/verificacion-e7.md` con evidencia de los gates | 15 |

---

## S1 · Contrato del épico

### Task 1: ADR-013, extra `ml` y reglas de arquitectura

**Files:**
- Create: `docs/adr/013-modelo-estancamiento-offline.md`
- Create: `backend/tests/architecture/test_ml_dependencies.py`
- Modify: `backend/tests/architecture/test_layer_dependencies.py` (bloque `FORBIDDEN` y un test nuevo al final)
- Modify: `backend/pyproject.toml` (`[project.optional-dependencies]`, nueva sección `[tool.setuptools.package-data]`)
- Modify: `backend/requirements.lock.txt`

**Interfaces:**
- Consumes: nada.
- Produces: extra `ml` instalable; capa `ml` con reglas `FORBIDDEN["ml"]`; constante de test `ML_SERVING_MODULES = ("ml/__init__.py", "ml/stall_features.py", "ml/preprocessing.py", "ml/stall_model.py")` — esos módulos no pueden importar `numpy`, `sklearn`, `pandas`, `scipy`, `joblib` ni `pickle`.

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/architecture/test_ml_dependencies.py`:

```python
"""ADR-013: scikit-learn es herramienta de ENTRENAMIENTO, no de servicio.

La inferencia del modelo de estancamiento es Python puro sobre un artefacto
JSON. Si scikit-learn se colara en las dependencias de produccion, la API
cargaria una libreria que no usa y cada aviso de seguridad de sklearn (y de
scipy/joblib) pasaria a ser nuestro.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).parents[2] / "pyproject.toml"


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]


def _name(requirement: str) -> str:
    return requirement.split("==")[0].split("[")[0].strip().lower()


def test_sklearn_is_not_a_production_dependency():
    assert "scikit-learn" not in {_name(d) for d in _project()["dependencies"]}


def test_ml_extra_pins_exact_versions():
    extra = _project()["optional-dependencies"]["ml"]
    assert {"scikit-learn", "numpy"} <= {_name(d) for d in extra}
    assert all("==" in d for d in extra), f"versiones sin fijar: {extra}"
```

En `backend/tests/architecture/test_layer_dependencies.py`, reemplazar el diccionario `FORBIDDEN` completo por:

```python
FORBIDDEN: dict[str, tuple[str, ...]] = {
    "domain": (
        "agrosense.application",
        "agrosense.adapters",
        "agrosense.ml",
        "fastapi",
        "sqlalchemy",
        "pandas",
    ),
    "application": (
        "agrosense.adapters",
        # ADR-003/ADR-013: ml/ es capa exterior; el caso de uso recibe el
        # modelo inyectado, no lo importa.
        "agrosense.ml",
        "fastapi",
        "sqlalchemy",
        "pandas",
    ),
    # ADR-003: "Modulo ml/ no puede importar adapters/ — solo domain/".
    "ml": (
        "agrosense.application",
        "agrosense.adapters",
        "fastapi",
        "sqlalchemy",
    ),
    # Regla del plan de slice 2: la API no parsea datos, delega en el ingester.
    "adapters/api": ("pandas",),
}
```

y añadir al final del archivo:

```python
# ADR-013: la ruta de INFERENCIA corre en cada peticion de la API y debe ser
# Python puro. numpy/sklearn solo existen en el extra `ml` (entrenamiento).
ML_SERVING_MODULES = (
    "ml/__init__.py",
    "ml/stall_features.py",
    "ml/preprocessing.py",
    "ml/stall_model.py",
)
ML_SERVING_FORBIDDEN = ("numpy", "sklearn", "pandas", "scipy", "joblib", "pickle")


def test_ml_serving_path_is_pure_python() -> None:
    presentes = [SRC / m for m in ML_SERVING_MODULES if (SRC / m).exists()]
    if not presentes:
        pytest.skip("la ruta de inferencia de ml/ aun no existe (E7)")
    malos = []
    for py in presentes:
        for module, lineno in _imports_of(py):
            raiz = module.split(".")[0]
            if raiz in ML_SERVING_FORBIDDEN:
                malos.append(f"{py.relative_to(SRC.parent)}:{lineno} importa {module!r}")
    assert not malos, "La inferencia debe ser Python puro (ADR-013):\n" + "\n".join(malos)
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/architecture/test_ml_dependencies.py tests/architecture/test_layer_dependencies.py -v`
Expected: `test_ml_extra_pins_exact_versions` FAIL con `KeyError: 'ml'`; `test_layer_does_not_import_outwards[ml]` y `test_ml_serving_path_is_pure_python` SKIPPED; el resto PASS.

- [ ] **Step 3: Declarar el extra y el package-data**

En `backend/pyproject.toml`, dentro de `[project.optional-dependencies]`, después de la lista `dev`, añadir:

```toml
# E7 (ADR-013): SOLO para entrenar y evaluar offline el modelo de
# estancamiento (`python scripts/train_stall_model.py`). La API sirve el
# artefacto JSON en Python puro y NO necesita ninguna de las dos.
# scikit-learn >= 1.5.0 corrige CVE-2024-5206.
ml = [
    "scikit-learn==1.5.2",
    "numpy==1.26.4",
]
```

y al final del archivo, después de `[tool.setuptools.packages.find]`:

```toml
[tool.setuptools.package-data]
# El artefacto del modelo viaja con el paquete: la API lo lee de ahi.
agrosense = ["ml/artifacts/*.json"]
```

- [ ] **Step 4: Instalar, fijar el cierre y auditar**

Run:
```bash
cd backend
python -m pip install "scikit-learn==1.5.2" "numpy==1.26.4"
python -m pip show scikit-learn scipy joblib threadpoolctl | grep -E "^(Name|Version)"
```
Añadir a `backend/requirements.lock.txt`, en orden alfabético, una línea `nombre==versión` por cada uno de `joblib`, `scikit-learn`, `scipy`, `threadpoolctl` con las versiones que imprimió `pip show` (no tocar `numpy==1.26.4`, ya está). Luego:

Run: `cd backend && python -m pip_audit -r requirements.lock.txt`
Expected: `No known vulnerabilities found`. Si aparece un aviso en scipy/joblib/threadpoolctl, subir esa transitiva a la primera versión corregida compatible, reinstalar y repetir.

- [ ] **Step 5: Escribir el ADR**

`docs/adr/013-modelo-estancamiento-offline.md`:

```markdown
# ADR-013 — Modelo de estancamiento: entrenamiento offline, artefacto JSON versionado e inferencia en Python puro (E7)

- **Estado:** Aceptado
- **Fecha:** 2026-09-27
- **Contexto:** E7 (UC-AN4) es el primer modelo de ML que entra al producto.
  AGENTS.md exige preprocesamiento compartido entre entrenamiento e
  inferencia, cero fuga, split temporal + agrupado por parcela, artefacto
  versionado, métricas documentadas, reproducibilidad con un solo comando
  («no .pkl black boxes») y procedencia completa. v1 falló en las cuatro
  cosas: fuga (`altura_actual` contenía al target), split aleatorio con el
  mismo árbol a ambos lados, preprocesamiento duplicado que divergió y el
  pipeline ML completo ejecutado dentro de un endpoint `async`.
  ADR-003 ya fijó que `ml/` vive fuera del dominio y solo importa `domain/`.
  El protocolo validado está en
  `docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md`.

  Al reconstruir el protocolo desde `Monitoreo_4` aparecieron tres
  discrepancias en la documentación, resueltas aquí (§Decisión 1-2):
  el umbral «≤ 5 cm» del spike de mortalidad no es la etiqueta del modelo;
  los 153 eventos son de la ola de entrenamiento (la de prueba tiene 157);
  y la columna `Unidad de monitoreo` es el tipo de unidad, no la parcela.

- **Opciones consideradas:**
  - *Entrenar desde un endpoint (`POST /train`).* Rechazada: repite el
    error de v1 (pipeline ML síncrono en una petición); además el modelo se
    entrena con el dataset de referencia, no con el de cada proyecto, y un
    reentrenamiento por proyecto con ~100 árboles sería ruido. El ML eval
    gate exige revisión humana antes de servir un modelo nuevo.
  - *Entrenar offline y guardar el `Pipeline` con pickle/joblib.* Rechazada:
    AGENTS.md prohíbe las cajas negras `.pkl` (y `.gitignore` ya las
    excluye), cargar un pickle ejecuta código arbitrario y ata la API a la
    versión exacta de scikit-learn.
  - *Tabla `ml_models` como registro de modelos.* Rechazada por YAGNI: hay
    un modelo, su artefacto vive en git y cada snapshot guarda
    `model_version` + `artifact_sha256`. Se reabre cuando haya dos modelos
    servidos a la vez (E8).
  - *Calcular las predicciones al vuelo en cada lectura, sin tabla.*
    Rechazada: AGENTS.md pide que toda predicción sea trazable a sus datos y
    a su modelo; sin snapshot no hay dónde anclar esa procedencia (mismo
    argumento que ADR-008).
  - **Entrenamiento offline + artefacto JSON + inferencia en Python puro +
    snapshot por monitoreo** (elegida).

- **Decisión:**
  1. **Etiqueta** (`domain/stall_rules.py`): `stall_label(prev, curr)` es
     True si el árbol está vivo y medido en t y t+1 y su altura no cambió,
     comparada en milímetros (`round(h * 1000)`). Reproduce exactamente el
     panel del protocolo (618/153 en M2→M3, 717/157 en M3→M4); comparar en
     centímetros fusionaba 0,24 y 0,245 m. `STAGNATION_THRESHOLD_M` (≤ 5 cm)
     sigue siendo la definición descriptiva de la comparación E4 y no se
     toca: las métricas del modelo solo valen para la igualdad.
  2. **Features relativas a la ola** (`ml/stall_features.py`): `h_t`,
     `copa_t`, `dh_lag`, `dcopa_lag`, `estanco_lag`, `h_prev`, `esbeltez_t`,
     `fito_empeoro` (numéricas) y `locality`, `species`, `monitoring_unit`,
     `fito_t` (categóricas). `monitoring_unit` es el tipo de unidad (3
     niveles). La parcela (`sampling_unit_code`) NO es feature: es la unidad
     de agrupamiento de la validación. Las features de la ola t se calculan
     solo con observaciones `campaign <= t`; la etiqueta, aparte.
  3. **Preprocesamiento compartido** (`ml/preprocessing.py`): Python puro,
     `fit_preprocessor` (mediana + media/desviación poblacional para
     numéricas; moda + categorías para categóricas) y `transform`. Un test
     de paridad demuestra que reproduce `SimpleImputer` + `StandardScaler` +
     `OneHotEncoder(handle_unknown="ignore")`. scikit-learn solo ajusta la
     `LogisticRegression` sobre la matriz ya transformada.
  4. **Entrenamiento offline, un comando:**
     `cd backend && python scripts/train_stall_model.py --data data/raw/anexo1.xlsx`.
     Verifica el SHA-256 del dataset, evalúa (temporal M2→M3 / M3→M4;
     GroupKFold de 5 folds por parcela; IC 95 % por bootstrap de parcelas;
     dos controles negativos; líneas base de prevalencia, persistencia y
     tasa por especie), aplica el gate y solo entonces escribe el artefacto
     y `docs/ml/evaluacion-estancamiento.md`. `--check` reentrena y compara
     contra el artefacto versionado.
     Gate: PR-AUC temporal ≥ 0.36 (límite inferior del IC del protocolo);
     supera a prevalencia y persistencia; el control con la etiqueta
     permutada en todo el conjunto ≤ 0.31 (vigila fugas: sin señal, el
     pipeline debe caer a la prevalencia); y supera al control permutado
     dentro de cada parcela.
     **Desvío del protocolo:** el protocolo usa como control la permutación
     dentro de parcela y reporta 0.238. Al reproducirlo con esta
     featurización da ≈ 0.33 (20 corridas, rango 0.24–0.40), porque conserva
     la tasa de cada parcela y la especie y el predio permiten aprenderla:
     no es fuga, es señal de sitio. Por eso ese control pasa a medir cuánto
     aporta el modelo por encima de la tasa de la parcela, y el control de
     fugas es la permutación global (≈ 0.227, rango 0.16–0.33).
     El artefacto servido se reentrena con el mismo procedimiento sobre las
     olas M2 y M3; las métricas evalúan el procedimiento.
  5. **Artefacto** `backend/src/agrosense/ml/artifacts/stall_logreg.json`,
     en git: formato, `model_version`, `features_version`,
     `preprocessing_version`, parámetros del preprocesador, coeficientes,
     configuración, evaluación completa y procedencia (SHA-256 del dataset,
     hoja, `MAPPING_VERSION` de la ingesta, commit, versiones de Python,
     scikit-learn y numpy, fecha). El cargador rechaza un artefacto de otra
     versión de features o de preprocesamiento: si alguien cambia las
     features sin reentrenar, la API responde 503 en vez de servir
     predicciones con una semántica distinta.
  6. **Dependencia:** `scikit-learn==1.5.2` + `numpy==1.26.4` en el extra
     `ml`, nunca en producción (test de arquitectura). El cierre entra al
     `requirements.lock.txt` y pasa `pip-audit`.
  7. **Inferencia síncrona y barata:** `GET
     /projects/{id}/monitorings/{n}/stall-assessment` es `def`; puntuar ~800
     árboles son unas decenas de miles de multiplicaciones. El resultado se
     guarda en `stall_assessments` (UNIQUE(monitoring_id), `model_version`,
     `artifact_sha256`, `input_hash`) y se recalcula solo si cambia alguno.
     `input_hash` resume solo las observaciones `<= t`: subir M5 no invalida
     la evaluación de M4. Sin cola de trabajos (ADR-010 sigue pendiente).
  8. **`estancó_intervalo_previo`** es la función de dominio
     `stalled_previous_interval`; no se persiste como columna. E8 la deriva
     de las observaciones igual que la usa este modelo.
  9. **Presupuesto de alertas del 20 %** por rango (`select_alerts`), la
     misma función en la evaluación y en la API. «Persistente» = 2 o más
     intervalos seguidos sin crecer (convención del proyecto, pendiente de
     confirmar con el ingeniero).

- **Consecuencias:**
  - Train y serve no pueden divergir: comparten `build_wave`, `transform` y
    `logistic_scores`, y el cargador verifica las versiones.
  - El modelo se entrenó con un solo proyecto (3 predios, 30 especies). Una
    especie que no vio pesa cero en su one-hot: cada árbol lleva
    `known_species` y la UI lo avisa. La transferencia espacial no está
    evaluada (Protocolo §3: 3 localidades, no es viable).
  - En el proyecto de referencia, las predicciones de M2 y M3 son sobre
    datos de entrenamiento: no son una evaluación. La evaluación honesta es
    la del informe.
  - La probabilidad es condicional a que el árbol siga vivo; mortalidad es
    E8.
  - La API carga el artefacto una vez por proceso: un reentrenamiento exige
    reiniciar el servidor y subir `model_version`.
```

- [ ] **Step 6: Ejecutar los tests y verificar que pasan**

Run: `cd backend && python -m pytest tests/architecture -v`
Expected: PASS (los de `ml` siguen SKIPPED hasta la Task 3).

- [ ] **Step 7: Commit**

```bash
git add docs/adr/013-modelo-estancamiento-offline.md backend/pyproject.toml backend/requirements.lock.txt backend/tests/architecture/test_ml_dependencies.py backend/tests/architecture/test_layer_dependencies.py
git commit -m "docs(e7): ADR-013 y extra ml para el modelo de estancamiento

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## S2 · Etiqueta y regla de negocio

### Task 2: `domain/stall_rules.py`

**Files:**
- Create: `backend/src/agrosense/domain/stall_rules.py`
- Create: `backend/tests/domain/test_stall_rules.py`
- Create: `backend/tests/ml/__init__.py` (vacío)
- Create: `backend/tests/ml/builders.py`
- Create: `backend/tests/ml/test_stall_labels_real.py`

**Interfaces:**
- Consumes: `agrosense.domain.entities.Observation`; `agrosense.domain.analysis_rules.PHYTOSANITARY_STATES`, `normalize_phytosanitary`.
- Produces:
  - `ALERT_BUDGET: float = 0.20`, `PERSISTENT_STALL_INTERVALS: int = 2`
  - `height_unchanged(prev_m: float, curr_m: float) -> bool`
  - `is_at_risk(obs: Observation | None) -> bool` — vivo (`alive is True`) y con altura
  - `stall_label(prev: Observation | None, curr: Observation | None) -> bool | None`
  - `stalled_previous_interval(by_campaign: Mapping[int, Observation], t: int) -> bool | None` (= `estancó_intervalo_previo`)
  - `stall_streak(by_campaign: Mapping[int, Observation], t: int) -> int`
  - `is_persistent_stall(streak: int) -> bool`
  - `phytosanitary_worsened(prev_raw: str | None, curr_raw: str | None) -> bool | None`
  - `alert_count(n_at_risk: int, budget: float = ALERT_BUDGET) -> int`
  - `select_alerts(scores: Mapping[str, float], budget: float = ALERT_BUDGET) -> frozenset[str]`
  - `tests/ml/builders.py`: `obs(tree_id, campaign, height, *, crown=0.30, alive=True, phyto="Bueno") -> Observation`, `tree(tree_id, *, species="Senna viarum", plot="U1", locality="Guayabal", unit="Parcela") -> Tree`, `synthetic_panel(n_plots=10, per_plot=12) -> tuple[list[Tree], list[Observation]]`

- [ ] **Step 1: Escribir los constructores de test**

`backend/tests/ml/builders.py`:

```python
"""Constructores de entidades de dominio para los tests de E7."""
from __future__ import annotations

from agrosense.domain.entities import Observation, StatusSemantic, Tree


def obs(
    tree_id: str,
    campaign: int,
    height: float | None,
    *,
    crown: float | None = 0.30,
    alive: bool | None = True,
    phyto: str | None = "Bueno",
) -> Observation:
    return Observation(
        tree_id=tree_id,
        campaign=campaign,
        height_m=height,
        crown_diameter_m=crown,
        dap_cm=None,
        dap_status=StatusSemantic.SIN_CENSO,
        phytosanitary=phyto,
        alive=alive,
        colonization=None,
    )


def tree(
    tree_id: str,
    *,
    species: str = "Senna viarum",
    plot: str | None = "U1",
    locality: str | None = "Guayabal",
    unit: str | None = "Parcela",
) -> Tree:
    return Tree(
        tree_id=tree_id,
        species=species,
        locality=locality,
        sampling_unit_code=plot,
        monitoring_unit=unit,
    )


def synthetic_panel(n_plots: int = 10, per_plot: int = 12) -> tuple[list[Tree], list[Observation]]:
    """Panel de 4 monitoreos con senal: la especie "Lenta lenta" casi no crece.

    Determinista (sin azar) y con ambas clases en cada ola y en cada parcela,
    para que GroupKFold y el bootstrap por parcela tengan con que trabajar.
    """
    trees: list[Tree] = []
    observations: list[Observation] = []
    for p in range(n_plots):
        for i in range(per_plot):
            tid = f"P{p}_T{i}"
            slow = i % 3 == 0
            trees.append(
                tree(
                    tid,
                    species="Lenta lenta" if slow else "Rapida rapida",
                    plot=f"U{p}",
                    locality="Guayabal" if p % 2 else "Tres Jotas",
                )
            )
            h = 0.30 + 0.01 * i
            for c in range(1, 5):
                observations.append(obs(tid, c, round(h, 3), crown=round(0.20 + 0.1 * h, 3)))
                stalls = slow and (c + p) % 4 != 0
                h += 0.0 if stalls else 0.05 * (1 + (i + p + c) % 3)
    return trees, observations
```

`backend/tests/ml/__init__.py`: archivo vacío.

- [ ] **Step 2: Escribir los tests de dominio que fallan**

`backend/tests/domain/test_stall_rules.py`:

```python
"""Reglas de estancamiento (E7): Protocolo Estancamiento §2 y §6."""
from __future__ import annotations

import pytest

from agrosense.domain.stall_rules import (
    ALERT_BUDGET,
    PERSISTENT_STALL_INTERVALS,
    alert_count,
    height_unchanged,
    is_at_risk,
    is_persistent_stall,
    phytosanitary_worsened,
    select_alerts,
    stall_label,
    stall_streak,
    stalled_previous_interval,
)
from tests.ml.builders import obs


def test_same_height_is_a_stall():
    assert stall_label(obs("A", 1, 0.40), obs("A", 2, 0.40)) is True


def test_any_growth_is_not_a_stall():
    assert stall_label(obs("A", 1, 0.40), obs("A", 2, 0.41)) is False


def test_half_centimetre_counts_as_growth():
    # Regresion FR_1_31 del dataset real: 0.24 -> 0.245 crecio 5 mm.
    assert height_unchanged(0.24, 0.245) is False


def test_float_noise_is_not_growth():
    assert height_unchanged(0.3, 0.1 + 0.2) is True


def test_a_contraction_is_not_a_stall():
    assert stall_label(obs("A", 1, 0.50), obs("A", 2, 0.45)) is False


@pytest.mark.parametrize(
    "prev, curr",
    [
        (obs("A", 1, 0.40), obs("A", 2, 0.40, alive=False)),  # muere: es mortalidad
        (obs("A", 1, 0.40, alive=False), obs("A", 2, 0.40)),  # revive: replanteo
        (obs("A", 1, None), obs("A", 2, 0.40)),  # sin altura
        (obs("A", 1, 0.40), obs("A", 2, 0.40, alive=None)),  # supervivencia en blanco
        (None, obs("A", 2, 0.40)),  # entra en este monitoreo
        (obs("A", 1, 0.40), None),  # sin censo en t+1
    ],
)
def test_outside_the_population_at_risk_there_is_no_label(prev, curr):
    assert stall_label(prev, curr) is None


def test_is_at_risk_requires_alive_and_measured():
    assert is_at_risk(obs("A", 1, 0.4)) is True
    assert is_at_risk(obs("A", 1, 0.4, alive=False)) is False
    assert is_at_risk(obs("A", 1, None)) is False
    assert is_at_risk(None) is False


def test_stalled_previous_interval_looks_at_t_minus_1_and_t_only():
    serie = {1: obs("A", 1, 0.40), 2: obs("A", 2, 0.40), 3: obs("A", 3, 0.50)}
    assert stalled_previous_interval(serie, 2) is True
    assert stalled_previous_interval(serie, 3) is False
    assert stalled_previous_interval(serie, 1) is None  # M1 no tiene intervalo previo


def test_streak_counts_consecutive_stalls_ending_at_t():
    serie = {
        1: obs("A", 1, 0.50),
        2: obs("A", 2, 0.50),
        3: obs("A", 3, 0.50),
        4: obs("A", 4, 0.60),
    }
    assert stall_streak(serie, 3) == 2
    assert stall_streak(serie, 4) == 0
    assert stall_streak(serie, 1) == 0


def test_persistent_means_at_least_two_intervals():
    assert PERSISTENT_STALL_INTERVALS == 2
    assert is_persistent_stall(1) is False
    assert is_persistent_stall(2) is True


@pytest.mark.parametrize(
    "prev, curr, expected",
    [
        ("Bueno", "Regular", True),
        ("Regular", "Malo", True),
        ("Regular", "Bueno", False),
        ("Bueno", "Bueno", False),
        (" regular ", "MALO", True),
        (" ", "Malo", None),
        ("Bueno", None, None),
    ],
)
def test_phytosanitary_worsened(prev, curr, expected):
    assert phytosanitary_worsened(prev, curr) is expected


def test_alert_budget_is_twenty_percent():
    assert ALERT_BUDGET == 0.20
    assert alert_count(717) == 143  # Protocolo §6: "~143 de 717"
    assert alert_count(0) == 0
    assert alert_count(3) == 1  # nunca cero alertas si hay arboles en riesgo
    assert alert_count(15) == 3


def test_alert_budget_must_be_a_fraction():
    with pytest.raises(ValueError):
        alert_count(10, budget=0.0)
    with pytest.raises(ValueError):
        alert_count(10, budget=1.5)


def test_select_alerts_takes_the_highest_scores_and_breaks_ties_by_tree_id():
    scores = {"C": 0.9, "A": 0.5, "B": 0.5, "D": 0.1, "E": 0.2}
    assert select_alerts(scores, budget=0.4) == frozenset({"C", "A"})
```

- [ ] **Step 3: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/domain/test_stall_rules.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agrosense.domain.stall_rules'`.

- [ ] **Step 4: Implementar**

`backend/src/agrosense/domain/stall_rules.py`:

```python
"""Definiciones del estancamiento de crecimiento (E7, UC-AN4).

Fuente: docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md §2 y §6.

    Estancado(i, t) = 1  si  altura(i, t) == altura(i, t+1)
                       y arbol vivo en ambos

La etiqueta NO usa una expectativa por especie o sitio (fuga por expectativa,
Protocolo §4.2). Mide "crecimiento no detectable por el protocolo de campo",
no "crecimiento nulo": con alturas redondeadas a 5 cm, parte de los ceros son
arboles que crecieron 1-3 cm.

Por que no es `STAGNATION_THRESHOLD_M` (rules.py, <= 5 cm): ese umbral es la
definicion DESCRIPTIVA de la comparacion entre monitoreos (E4). El modelo se
valido con la igualdad (153 estancados en M2->M3, 157 en M3->M4) y sus
metricas solo valen para esa etiqueta (ADR-013).

Puro: sin I/O ni framework. Lo consumen el modelo (ml/), el caso de uso de
deteccion y, en E8, el modelo de mortalidad: `stalled_previous_interval` es
la feature `estancó_intervalo_previo`.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

from agrosense.domain.analysis_rules import PHYTOSANITARY_STATES, normalize_phytosanitary
from agrosense.domain.entities import Observation

# Protocolo §6: se revisa en campo una FRACCION fija de arboles (los de mayor
# probabilidad), no los que superan 0.5.
ALERT_BUDGET = 0.20

# Convencion del proyecto (ADR-013, D7 del plan de E7): la nota del Slice 4
# dice "≈0 en N intervalos" sin fijar N. Un intervalo ya es
# `stalled_previous_interval`; dos seguidos es el minimo que merece
# "persistente". Pendiente de confirmar con el ingeniero.
PERSISTENT_STALL_INTERVALS = 2


def _mm(height_m: float) -> int:
    return round(height_m * 1000)


def height_unchanged(prev_m: float, curr_m: float) -> bool:
    """La altura no cambio, comparada en milimetros.

    En milimetros y no en centimetros: el dataset trae alturas con medio
    centimetro (FR_1_31: 0.24 -> 0.245) y redondear a cm las fusionaria. En
    milimetros tampoco se confunde el ruido de coma flotante con crecimiento.
    """
    return _mm(prev_m) == _mm(curr_m)


def is_at_risk(observation: Observation | None) -> bool:
    """Vivo y con altura medida: puede estancarse (o no) hasta el proximo monitoreo."""
    return (
        observation is not None
        and observation.alive is True
        and observation.height_m is not None
    )


def stall_label(prev: Observation | None, curr: Observation | None) -> bool | None:
    """Etiqueta del intervalo (prev, curr]; None fuera de la poblacion en riesgo.

    Poblacion en riesgo (Protocolo §2): vivo y medido en AMBOS extremos. Los
    que mueren se excluyen: mortalidad es otro proceso (E8).
    """
    if prev is None or curr is None or not (is_at_risk(prev) and is_at_risk(curr)):
        return None
    assert prev.height_m is not None and curr.height_m is not None
    return height_unchanged(prev.height_m, curr.height_m)


def stalled_previous_interval(by_campaign: Mapping[int, Observation], t: int) -> bool | None:
    """`estancó_intervalo_previo`: no crecio en (t-1, t]. Solo lee t-1 y t."""
    return stall_label(by_campaign.get(t - 1), by_campaign.get(t))


def stall_streak(by_campaign: Mapping[int, Observation], t: int) -> int:
    """Intervalos seguidos sin crecer que terminan en t."""
    streak = 0
    k = t
    while stall_label(by_campaign.get(k - 1), by_campaign.get(k)) is True:
        streak += 1
        k -= 1
    return streak


def is_persistent_stall(streak: int) -> bool:
    return streak >= PERSISTENT_STALL_INTERVALS


def phytosanitary_worsened(prev_raw: str | None, curr_raw: str | None) -> bool | None:
    """El estado fitosanitario empeoro (Bueno < Regular < Malo). None si falta alguno."""
    prev = normalize_phytosanitary(prev_raw)
    curr = normalize_phytosanitary(curr_raw)
    if prev is None or curr is None:
        return None
    return PHYTOSANITARY_STATES.index(curr) > PHYTOSANITARY_STATES.index(prev)


def alert_count(n_at_risk: int, budget: float = ALERT_BUDGET) -> int:
    """Cuantos arboles se marcan para revision: floor(n * budget), minimo 1."""
    if not 0.0 < budget <= 1.0:
        raise ValueError(f"el presupuesto de alertas debe estar en (0, 1], recibido {budget}")
    if n_at_risk <= 0:
        return 0
    return max(1, math.floor(n_at_risk * budget + 1e-9))


def select_alerts(scores: Mapping[str, float], budget: float = ALERT_BUDGET) -> frozenset[str]:
    """Los `alert_count` arboles de mayor score; empate -> tree_id ascendente (estable)."""
    k = alert_count(len(scores), budget)
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return frozenset(tree_id for tree_id, _ in ranked[:k])
```

- [ ] **Step 5: Ejecutar y verificar que pasan**

Run: `cd backend && python -m pytest tests/domain/test_stall_rules.py -v`
Expected: PASS.

- [ ] **Step 6: Test de regresión contra el dataset real**

`backend/tests/ml/test_stall_labels_real.py`:

```python
"""La etiqueta reproduce el panel del protocolo sobre el dataset real."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from agrosense.domain.stall_rules import stall_label

REFERENCE_PATH = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"

pytestmark = pytest.mark.skipif(
    not REFERENCE_PATH.exists(),
    reason="dataset de referencia local ausente (data/raw/anexo1.xlsx)",
)


@pytest.fixture(scope="module")
def series():
    from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

    data = ExcelCampaignSource().read(REFERENCE_PATH.read_bytes(), REFERENCE_PATH.name)
    by_tree: dict[str, dict] = defaultdict(dict)
    for o in data.observations:
        by_tree[o.tree_id][o.campaign] = o
    return by_tree


@pytest.mark.parametrize(
    "t, at_risk, stalled",
    [(1, 651, 112), (2, 618, 153), (3, 717, 157)],
)
def test_label_reproduces_the_protocol_panel(series, t, at_risk, stalled):
    labels = [stall_label(s.get(t), s.get(t + 1)) for s in series.values()]
    known = [label for label in labels if label is not None]
    assert len(known) == at_risk
    assert sum(known) == stalled


def test_half_centimetre_tree_is_not_stalled(series):
    s = series["FR_1_31"]
    assert (s[3].height_m, s[4].height_m) == (0.24, 0.245)
    assert stall_label(s[3], s[4]) is False
```

Run: `cd backend && python -m pytest tests/ml/test_stall_labels_real.py -v`
Expected: PASS (o SKIPPED si falta el dataset local; en la máquina de desarrollo existe).

- [ ] **Step 7: Commit**

```bash
git add backend/src/agrosense/domain/stall_rules.py backend/tests/domain/test_stall_rules.py backend/tests/ml/__init__.py backend/tests/ml/builders.py backend/tests/ml/test_stall_labels_real.py
git commit -m "feat(e7): etiqueta de estancamiento y regla de negocio en el dominio

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## S3 · Features y preprocesamiento compartidos

### Task 3: `ml/stall_features.py`

**Files:**
- Create: `backend/src/agrosense/ml/__init__.py`
- Create: `backend/src/agrosense/ml/stall_features.py`
- Create: `backend/tests/ml/test_stall_features.py`

**Interfaces:**
- Consumes: Task 2 (`is_at_risk`, `stall_label`, `stalled_previous_interval`, `phytosanitary_worsened`); `domain.rules.plot_key`; `domain.analysis_rules.normalize_phytosanitary`.
- Produces:
  - `FEATURES_VERSION = "2026-09-27-e7.1"`
  - `NUMERIC_FEATURES: tuple[str, ...] = ("h_t", "copa_t", "dh_lag", "dcopa_lag", "estanco_lag", "h_prev", "esbeltez_t", "fito_empeoro")`
  - `CATEGORICAL_FEATURES: tuple[str, ...] = ("locality", "species", "monitoring_unit", "fito_t")`
  - `FeatureValue = float | str | None`
  - `@dataclass(frozen=True) WaveRow(tree_id: str, plot: str | None, wave: int, features: dict[str, FeatureValue], label: bool | None)`
  - `build_wave(trees: Sequence[Tree], observations: Sequence[Observation], t: int, *, labeled: bool) -> list[WaveRow]` — filas ordenadas por `tree_id`
  - `fingerprint(trees: Sequence[Tree], observations: Sequence[Observation], t: int) -> str` — SHA-256 hex

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/ml/test_stall_features.py`:

```python
"""Featurizacion del modelo de estancamiento: relativa a la ola y sin fugas."""
from __future__ import annotations

import re

import pytest

from agrosense.ml.stall_features import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    build_wave,
    fingerprint,
)
from tests.ml.builders import obs, tree


def _dataset():
    trees = [
        tree("A", plot="U1"),
        tree("B", plot="U2", species="Cedrela montana"),
        tree("C", plot="U1"),
    ]
    observations = [
        obs("A", 1, 0.40, crown=0.20),
        obs("A", 2, 0.40, crown=0.25, phyto="Regular"),
        obs("A", 3, 0.40, crown=0.30),
        obs("B", 1, 0.50),
        obs("B", 2, 0.60),
        obs("B", 3, 0.70),
        obs("C", 2, 0.30),  # C entra en M2 (sin historia)...
        obs("C", 3, 0.30, alive=False),  # ...y muere en M3
    ]
    return trees, observations


def test_feature_names_are_wave_relative():
    # Protocolo §10, "test de smoke anti-leakage": nada de altura_M3.
    for name in NUMERIC_FEATURES + CATEGORICAL_FEATURES:
        assert not re.search(r"_m\d+$", name.lower()), name


def test_labeled_wave_keeps_trees_alive_and_measured_in_t_and_t_plus_1():
    trees, observations = _dataset()
    rows = build_wave(trees, observations, 2, labeled=True)
    assert [r.tree_id for r in rows] == ["A", "B"]
    assert [r.label for r in rows] == [True, False]
    assert all(r.wave == 2 for r in rows)


def test_unlabeled_wave_keeps_every_tree_alive_and_measured_in_t():
    trees, observations = _dataset()
    rows = build_wave(trees, observations, 2, labeled=False)
    assert [r.tree_id for r in rows] == ["A", "B", "C"]
    assert all(r.label is None for r in rows)


def test_lag_features():
    trees, observations = _dataset()
    rows = {r.tree_id: r.features for r in build_wave(trees, observations, 2, labeled=True)}
    a = rows["A"]
    assert a["h_t"] == 0.40
    assert a["h_prev"] == 0.40
    assert a["dh_lag"] == 0.0
    assert a["estanco_lag"] == 1.0
    assert a["dcopa_lag"] == pytest.approx(0.05)
    assert a["fito_empeoro"] == 1.0
    assert a["fito_t"] == "Regular"
    assert a["esbeltez_t"] == pytest.approx(0.40 / 0.25)
    assert (a["species"], a["locality"], a["monitoring_unit"]) == (
        "Senna viarum",
        "Guayabal",
        "Parcela",
    )
    b = rows["B"]
    assert b["estanco_lag"] == 0.0
    assert b["dh_lag"] == pytest.approx(0.10)


def test_tree_without_history_has_missing_lags():
    trees, observations = _dataset()
    rows = {r.tree_id: r.features for r in build_wave(trees, observations, 2, labeled=False)}
    c = rows["C"]
    for name in ("dh_lag", "dcopa_lag", "estanco_lag", "h_prev", "fito_empeoro"):
        assert c[name] is None, name


def test_features_never_read_the_future():
    trees, observations = _dataset()
    futuro = [
        o.model_copy(update={"height_m": 9.0, "crown_diameter_m": 9.9, "phytosanitary": "Malo"})
        if o.campaign == 3 and o.alive
        else o
        for o in observations
    ]
    antes = [r.features for r in build_wave(trees, observations, 2, labeled=True)]
    despues = [r.features for r in build_wave(trees, futuro, 2, labeled=True)]
    assert antes == despues


def test_zero_crown_gives_missing_slenderness():
    rows = build_wave([tree("A")], [obs("A", 1, 0.4, crown=0.0)], 1, labeled=False)
    assert rows[0].features["esbeltez_t"] is None


def test_plot_is_the_grouping_key_not_a_feature():
    trees, observations = _dataset()
    row = build_wave(trees, observations, 2, labeled=True)[0]
    assert row.plot == "U1"
    assert "plot" not in row.features
    assert "sampling_unit_code" not in row.features


def test_fingerprint_ignores_later_monitorings_only():
    trees, observations = _dataset()
    con_m4 = observations + [obs("B", 4, 0.9)]
    assert fingerprint(trees, observations, 3) == fingerprint(trees, con_m4, 3)
    corregido = [
        o.model_copy(update={"height_m": 0.41}) if (o.tree_id, o.campaign) == ("A", 2) else o
        for o in observations
    ]
    assert fingerprint(trees, observations, 3) != fingerprint(trees, corregido, 3)
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/ml/test_stall_features.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agrosense.ml'`.

- [ ] **Step 3: Implementar**

`backend/src/agrosense/ml/__init__.py`:

```python
"""Modelos de ML de AgroSense (ADR-003, ADR-013).

Este archivo se queda VACIO a proposito: la API importa `agrosense.ml.*`
para servir el modelo, y cualquier import aqui (p. ej. de `train_stall`)
arrastraria numpy/scikit-learn a produccion.
"""
```

`backend/src/agrosense/ml/stall_features.py`:

```python
"""Featurizacion del modelo de estancamiento (E7), COMPARTIDA por
entrenamiento e inferencia (AGENTS.md: "Training and inference must share
preprocessing logic"; leccion de v1).

Relativa a la ola: `h_t`, `dh_lag`, `estanco_lag`... nunca `altura_M3`, asi el
mismo modelo sirve para M5 sin reentrenar (Protocolo §3).

Anti-fuga por construccion (Protocolo §4.1 y §4.3): las features de la ola t
se calculan con `history`, que SOLO contiene observaciones con
`campaign <= t`. La etiqueta, que necesita t+1, la calcula aparte la regla de
dominio `stall_label` y nunca entra en `features`. Solo rezagos: ningun
agregado de la historia completa del arbol.

La parcela (`plot_key`) viaja en `WaveRow.plot` como unidad de agrupamiento
de la validacion; NO es feature (ADR-013 §2).

Python puro: esta ruta corre en cada peticion de la API (ADR-013).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from agrosense.domain.analysis_rules import normalize_phytosanitary
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.rules import plot_key
from agrosense.domain.stall_rules import (
    is_at_risk,
    phytosanitary_worsened,
    stall_label,
    stalled_previous_interval,
)

# Cambiar CUALQUIER definicion de abajo = nueva version; el cargador del
# modelo rechaza un artefacto entrenado con otra (ADR-013 §5).
FEATURES_VERSION = "2026-09-27-e7.1"

NUMERIC_FEATURES: tuple[str, ...] = (
    "h_t",
    "copa_t",
    "dh_lag",
    "dcopa_lag",
    "estanco_lag",
    "h_prev",
    "esbeltez_t",
    "fito_empeoro",
)
CATEGORICAL_FEATURES: tuple[str, ...] = ("locality", "species", "monitoring_unit", "fito_t")

FeatureValue = float | str | None


@dataclass(frozen=True)
class WaveRow:
    """Un arbol en el instante de prediccion t (una observacion arbol+ola)."""

    tree_id: str
    plot: str | None
    wave: int
    features: dict[str, FeatureValue]
    label: bool | None


def _history(
    observations: Sequence[Observation], max_campaign: int
) -> dict[str, dict[int, Observation]]:
    by_tree: dict[str, dict[int, Observation]] = defaultdict(dict)
    for o in observations:
        if o.campaign <= max_campaign:
            by_tree[o.tree_id][o.campaign] = o
    return by_tree


def _as_float(value: bool | None) -> float | None:
    return None if value is None else float(value)


def _features(tree: Tree, history: Mapping[int, Observation], t: int) -> dict[str, FeatureValue]:
    cur = history[t]
    assert cur.height_m is not None
    h_t = cur.height_m
    copa_t = cur.crown_diameter_m

    dh_lag = dcopa_lag = h_prev = fito_empeoro = None
    prev = history.get(t - 1)
    if prev is not None and is_at_risk(prev):
        assert prev.height_m is not None
        h_prev = prev.height_m
        dh_lag = h_t - prev.height_m
        if copa_t is not None and prev.crown_diameter_m is not None:
            dcopa_lag = copa_t - prev.crown_diameter_m
        fito_empeoro = _as_float(phytosanitary_worsened(prev.phytosanitary, cur.phytosanitary))

    return {
        "h_t": h_t,
        "copa_t": copa_t,
        "dh_lag": dh_lag,
        "dcopa_lag": dcopa_lag,
        "estanco_lag": _as_float(stalled_previous_interval(history, t)),
        "h_prev": h_prev,
        "esbeltez_t": h_t / copa_t if copa_t else None,
        "fito_empeoro": fito_empeoro,
        "locality": tree.locality,
        "species": tree.species,
        "monitoring_unit": tree.monitoring_unit,
        "fito_t": normalize_phytosanitary(cur.phytosanitary),
    }


def build_wave(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    t: int,
    *,
    labeled: bool,
) -> list[WaveRow]:
    """Filas de la ola t, ordenadas por tree_id.

    `labeled=True` (entrenamiento/evaluacion): solo arboles con etiqueta
    definida, es decir vivos y medidos en t y t+1.
    `labeled=False` (inferencia): todo arbol vivo y medido en t; el futuro no
    se conoce y no se mira.
    """
    history = _history(observations, max_campaign=t)
    following = (
        {o.tree_id: o for o in observations if o.campaign == t + 1} if labeled else {}
    )
    rows: list[WaveRow] = []
    for tree in sorted(trees, key=lambda tr: tr.tree_id):
        own = history.get(tree.tree_id, {})
        if not is_at_risk(own.get(t)):
            continue
        label: bool | None = None
        if labeled:
            label = stall_label(own.get(t), following.get(tree.tree_id))
            if label is None:
                continue
        rows.append(
            WaveRow(
                tree_id=tree.tree_id,
                plot=plot_key(tree),
                wave=t,
                features=_features(tree, own, t),
                label=label,
            )
        )
    return rows


def fingerprint(trees: Sequence[Tree], observations: Sequence[Observation], t: int) -> str:
    """Huella de TODO lo que puede cambiar la prediccion de la ola t.

    Solo observaciones `<= t`: cargar M5 no invalida la evaluacion de M4.
    """
    payload = {
        "features_version": FEATURES_VERSION,
        "t": t,
        "trees": sorted(
            (
                [tr.tree_id, tr.species, tr.locality, tr.monitoring_unit, plot_key(tr)]
                for tr in trees
            ),
            key=lambda row: row[0],
        ),
        "observations": sorted(
            (
                [o.tree_id, o.campaign, o.height_m, o.crown_diameter_m, o.phytosanitary, o.alive]
                for o in observations
                if o.campaign <= t
            ),
            key=lambda row: (row[0], row[1]),
        ),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Ejecutar y verificar que pasan (incluida la arquitectura)**

Run: `cd backend && python -m pytest tests/ml/test_stall_features.py tests/architecture -v`
Expected: PASS; `test_layer_does_not_import_outwards[ml]` y `test_ml_serving_path_is_pure_python` ya no se saltan y pasan.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/ml/__init__.py backend/src/agrosense/ml/stall_features.py backend/tests/ml/test_stall_features.py
git commit -m "feat(e7): featurizacion relativa a la ola, compartida train/serve

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 4: `ml/preprocessing.py`

**Files:**
- Create: `backend/src/agrosense/ml/preprocessing.py`
- Create: `backend/tests/ml/test_preprocessing.py`

**Interfaces:**
- Consumes: `FeatureValue` de Task 3 (solo como tipo, vía `Mapping[str, float | str | None]`).
- Produces:
  - `PREPROCESSING_VERSION = "2026-09-27-e7.1"`
  - `@dataclass(frozen=True) PreprocessorParams(numeric: tuple[str, ...], categorical: tuple[str, ...], medians: dict[str, float], means: dict[str, float], scales: dict[str, float], modes: dict[str, str], categories: dict[str, tuple[str, ...]])` con `feature_names -> list[str]` (numéricas, luego `"col=categoría"`), `to_json() -> dict`, `from_json(data: Mapping) -> PreprocessorParams`
  - `fit_preprocessor(rows: Sequence[Mapping[str, float | str | None]], numeric: Sequence[str], categorical: Sequence[str]) -> PreprocessorParams`
  - `transform(params: PreprocessorParams, rows: Sequence[Mapping[str, float | str | None]]) -> list[list[float]]`

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/ml/test_preprocessing.py`:

```python
"""Preprocesamiento compartido: se ajusta con train, se aplica igual en serve."""
from __future__ import annotations

import math

import pytest

from agrosense.ml.preprocessing import PreprocessorParams, fit_preprocessor, transform

ROWS = [
    {"x": 1.0, "y": None, "c": "a"},
    {"x": None, "y": 2.0, "c": None},
    {"x": 3.0, "y": 5.0, "c": "b"},
    {"x": 10.0, "y": 1.0, "c": "a"},
]


def test_missing_numbers_take_the_training_median():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    assert params.medians == {"x": 3.0, "y": 2.0}


def test_standardizes_with_population_std_of_the_imputed_column():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    imputed = [1.0, 3.0, 3.0, 10.0]
    mean = sum(imputed) / 4
    std = math.sqrt(sum((v - mean) ** 2 for v in imputed) / 4)
    assert params.means["x"] == pytest.approx(mean)
    assert params.scales["x"] == pytest.approx(std)
    row = transform(params, [{"x": 10.0, "y": 2.0, "c": "a"}])[0]
    assert row[0] == pytest.approx((10.0 - mean) / std)


def test_missing_category_takes_the_mode_and_one_hot_follows_sorted_categories():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    assert params.modes == {"c": "a"}
    assert params.feature_names == ["x", "y", "c=a", "c=b"]
    assert transform(params, [{"x": 1.0, "y": 1.0, "c": None}])[0][2:] == [1.0, 0.0]


def test_unknown_category_encodes_as_all_zeros():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    assert transform(params, [{"x": 1.0, "y": 1.0, "c": "nueva"}])[0][2:] == [0.0, 0.0]


def test_constant_column_is_not_divided_by_zero():
    params = fit_preprocessor([{"x": 2.0}, {"x": 2.0}], ("x",), ())
    assert params.scales["x"] == 1.0
    assert transform(params, [{"x": 2.0}]) == [[0.0]]


def test_a_column_without_any_value_in_training_is_an_error():
    with pytest.raises(ValueError, match="x"):
        fit_preprocessor([{"x": None}, {"x": None}], ("x",), ())


def test_params_roundtrip_through_json():
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    assert PreprocessorParams.from_json(params.to_json()) == params


def test_fit_only_sees_the_rows_it_is_given():
    train = fit_preprocessor(ROWS[:2], ("x", "y"), ("c",))
    assert train.medians["x"] == 1.0  # el 10.0 de la fila 4 no se filtra al ajuste


def test_matches_sklearn_column_transformer():
    np = pytest.importorskip("numpy")
    pd = pytest.importorskip("pandas")
    pytest.importorskip("sklearn")
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    serve = ROWS + [{"x": 2.0, "y": 3.0, "c": "zzz"}]
    params = fit_preprocessor(ROWS, ("x", "y"), ("c",))
    ours = np.asarray(transform(params, serve))

    df = pd.DataFrame(serve)
    df[["x", "y"]] = df[["x", "y"]].astype(float)
    df["c"] = df["c"].map(lambda v: np.nan if v is None else v)
    ct = ColumnTransformer(
        [
            ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), ["x", "y"]),
            (
                "cat",
                make_pipeline(
                    SimpleImputer(strategy="most_frequent"),
                    OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                ),
                ["c"],
            ),
        ]
    )
    ct.fit(df.iloc[: len(ROWS)])
    np.testing.assert_allclose(ours, ct.transform(df), atol=1e-12)
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/ml/test_preprocessing.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agrosense.ml.preprocessing'`.

- [ ] **Step 3: Implementar**

`backend/src/agrosense/ml/preprocessing.py`:

```python
"""Preprocesamiento UNICO del modelo de estancamiento (ADR-013 §3).

Reproduce, en Python puro, el `ColumnTransformer` del protocolo:

    numericas:   SimpleImputer(median)        -> StandardScaler (ddof=0)
    categoricas: SimpleImputer(most_frequent) -> OneHotEncoder(handle_unknown="ignore")

Por que no el de scikit-learn: la API no debe cargar scikit-learn, y un
pickle del Pipeline seria una caja negra (AGENTS.md). Los parametros
ajustados son numeros y listas: viajan en el artefacto JSON. Un test de
paridad compara contra scikit-learn.

Fuga por preprocesamiento (Protocolo §4.4): `fit_preprocessor` se llama SOLO
con filas de entrenamiento; la inferencia solo llama `transform`.
"""
from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PREPROCESSING_VERSION = "2026-09-27-e7.1"

Row = Mapping[str, float | str | None]


@dataclass(frozen=True)
class PreprocessorParams:
    numeric: tuple[str, ...]
    categorical: tuple[str, ...]
    medians: dict[str, float]
    means: dict[str, float]
    scales: dict[str, float]
    modes: dict[str, str]
    categories: dict[str, tuple[str, ...]]

    @property
    def feature_names(self) -> list[str]:
        names = list(self.numeric)
        for col in self.categorical:
            names.extend(f"{col}={value}" for value in self.categories[col])
        return names

    def to_json(self) -> dict:
        return {
            "numeric": list(self.numeric),
            "categorical": list(self.categorical),
            "medians": dict(self.medians),
            "means": dict(self.means),
            "scales": dict(self.scales),
            "modes": dict(self.modes),
            "categories": {k: list(v) for k, v in self.categories.items()},
        }

    @classmethod
    def from_json(cls, data: Mapping) -> PreprocessorParams:
        return cls(
            numeric=tuple(data["numeric"]),
            categorical=tuple(data["categorical"]),
            medians={k: float(v) for k, v in data["medians"].items()},
            means={k: float(v) for k, v in data["means"].items()},
            scales={k: float(v) for k, v in data["scales"].items()},
            modes={k: str(v) for k, v in data["modes"].items()},
            categories={k: tuple(str(c) for c in v) for k, v in data["categories"].items()},
        )


def fit_preprocessor(
    rows: Sequence[Row], numeric: Sequence[str], categorical: Sequence[str]
) -> PreprocessorParams:
    if not rows:
        raise ValueError("fit_preprocessor necesita al menos una fila de entrenamiento")
    medians: dict[str, float] = {}
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    for col in numeric:
        present = [float(r[col]) for r in rows if r.get(col) is not None]
        if not present:
            raise ValueError(f"la columna numerica {col!r} no tiene ningun valor en entrenamiento")
        median = float(statistics.median(present))
        imputed = [float(r[col]) if r.get(col) is not None else median for r in rows]
        std = statistics.pstdev(imputed)
        medians[col] = median
        means[col] = statistics.fmean(imputed)
        scales[col] = std if std > 0 else 1.0

    modes: dict[str, str] = {}
    categories: dict[str, tuple[str, ...]] = {}
    for col in categorical:
        present_cat = [str(r[col]) for r in rows if r.get(col) is not None]
        if not present_cat:
            raise ValueError(f"la columna categorica {col!r} no tiene valores en entrenamiento")
        counts = Counter(present_cat)
        top = max(counts.values())
        modes[col] = min(value for value, n in counts.items() if n == top)
        categories[col] = tuple(sorted(counts))

    return PreprocessorParams(
        numeric=tuple(numeric),
        categorical=tuple(categorical),
        medians=medians,
        means=means,
        scales=scales,
        modes=modes,
        categories=categories,
    )


def transform(params: PreprocessorParams, rows: Sequence[Row]) -> list[list[float]]:
    out: list[list[float]] = []
    for r in rows:
        vector: list[float] = []
        for col in params.numeric:
            raw = r.get(col)
            value = params.medians[col] if raw is None else float(raw)
            vector.append((value - params.means[col]) / params.scales[col])
        for col in params.categorical:
            raw_cat = r.get(col)
            value_cat = params.modes[col] if raw_cat is None else str(raw_cat)
            vector.extend(1.0 if value_cat == c else 0.0 for c in params.categories[col])
        out.append(vector)
    return out
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `cd backend && python -m pytest tests/ml/test_preprocessing.py tests/architecture/test_layer_dependencies.py -v`
Expected: PASS (la paridad con scikit-learn corre porque el extra `ml` está instalado).

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/ml/preprocessing.py backend/tests/ml/test_preprocessing.py
git commit -m "feat(e7): preprocesamiento compartido en Python puro, con paridad sklearn

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## S4 · Modelo servible

### Task 5: `ml/stall_model.py` — formato, carga validada y scoring

**Files:**
- Create: `backend/src/agrosense/ml/stall_model.py`
- Create: `backend/tests/ml/test_stall_model.py`
- Modify: `backend/tests/ml/builders.py` (añadir `artifact_dict` al final)

**Interfaces:**
- Consumes: Task 3 (`build_wave`, `fingerprint`, `FEATURES_VERSION`, `FeatureValue`, `NUMERIC_FEATURES`, `CATEGORICAL_FEATURES`); Task 4 (`PreprocessorParams`, `transform`, `PREPROCESSING_VERSION`).
- Produces:
  - `ARTIFACT_FORMAT = 1`, `ARTIFACT_PATH: Path` (`ml/artifacts/stall_logreg.json`)
  - `class StallModelError(ValueError)`
  - `sigmoid(z: float) -> float`
  - `logistic_scores(params: PreprocessorParams, coefficients: Sequence[float], intercept: float, rows: Sequence[Mapping[str, FeatureValue]]) -> list[float]`
  - `@dataclass(frozen=True) StallModel(model_version: str, artifact_sha256: str, params: PreprocessorParams, coefficients: tuple[float, ...], intercept: float, model_card: dict)` con `known_species -> frozenset[str]`, `predict_rows(rows) -> list[float]`, `predict(trees, observations, t) -> dict[str, float]`, `fingerprint(trees, observations, t) -> str`
  - `load_stall_model(path: Path = ARTIFACT_PATH) -> StallModel`
  - `model_card` con exactamente las claves: `model_version, artifact_sha256, dataset_sha256, trained_on, pr_auc, pr_auc_ci_low, pr_auc_ci_high, roc_auc, prevalence_pct, recall_at_budget_pct, precision_at_budget_pct`
  - Formato del artefacto (lo escribe la Task 7): `{"format", "model_version", "features_version", "preprocessing_version", "created_at", "preprocessor": PreprocessorParams.to_json(), "model": {"type": "logistic_regression", "feature_names", "coefficients", "intercept"}, "training": {...}, "evaluation": {"temporal": {"pr_auc", "pr_auc_ci": [lo, hi], "roc_auc", "prevalence_pct", "recall_at_budget_pct", "precision_at_budget_pct", ...}, ...}, "provenance": {"dataset_file", "dataset_sha256", ...}}`
  - `tests/ml/builders.py`: `artifact_dict(params, coefficients, intercept, *, model_version="stall-test-1") -> dict`

- [ ] **Step 1: Añadir el constructor de artefactos de test**

Al final de `backend/tests/ml/builders.py`:

```python
def artifact_dict(params, coefficients, intercept, *, model_version: str = "stall-test-1") -> dict:
    """Artefacto minimo valido con el formato de ADR-013 (sin entrenar)."""
    from agrosense.ml.preprocessing import PREPROCESSING_VERSION
    from agrosense.ml.stall_features import FEATURES_VERSION
    from agrosense.ml.stall_model import ARTIFACT_FORMAT

    return {
        "format": ARTIFACT_FORMAT,
        "model_version": model_version,
        "features_version": FEATURES_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "created_at": "2026-09-27T00:00:00+00:00",
        "preprocessor": params.to_json(),
        "model": {
            "type": "logistic_regression",
            "feature_names": params.feature_names,
            "coefficients": list(coefficients),
            "intercept": intercept,
        },
        "training": {},
        "evaluation": {
            "temporal": {
                "pr_auc": 0.47,
                "pr_auc_ci": [0.36, 0.58],
                "roc_auc": 0.73,
                "prevalence_pct": 21.9,
                "recall_at_budget_pct": 45.0,
                "precision_at_budget_pct": 50.0,
            }
        },
        "provenance": {"dataset_file": "anexo1.xlsx", "dataset_sha256": "0" * 64},
    }
```

- [ ] **Step 2: Escribir los tests que fallan**

`backend/tests/ml/test_stall_model.py`:

```python
"""Modelo servible: artefacto JSON validado y scoring en Python puro."""
from __future__ import annotations

import hashlib
import json

import pytest

from agrosense.ml.preprocessing import fit_preprocessor
from agrosense.ml.stall_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, build_wave
from agrosense.ml.stall_model import StallModelError, load_stall_model, sigmoid
from tests.ml.builders import artifact_dict, synthetic_panel

CARD_KEYS = {
    "model_version",
    "artifact_sha256",
    "dataset_sha256",
    "trained_on",
    "pr_auc",
    "pr_auc_ci_low",
    "pr_auc_ci_high",
    "roc_auc",
    "prevalence_pct",
    "recall_at_budget_pct",
    "precision_at_budget_pct",
}


def _artifact():
    trees, observations = synthetic_panel()
    rows = build_wave(trees, observations, 2, labeled=False)
    params = fit_preprocessor([r.features for r in rows], NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    coefficients = [0.0] * len(params.feature_names)
    coefficients[params.feature_names.index("estanco_lag")] = 2.0
    return trees, observations, artifact_dict(params, coefficients, -1.0)


def _write(tmp_path, data) -> object:
    path = tmp_path / "stall.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_sigmoid_is_stable_at_the_extremes():
    assert sigmoid(1000.0) == 1.0
    assert sigmoid(-1000.0) == 0.0
    assert sigmoid(0.0) == 0.5


def test_load_roundtrip(tmp_path):
    _, _, data = _artifact()
    path = _write(tmp_path, data)
    model = load_stall_model(path)
    assert model.model_version == "stall-test-1"
    assert model.artifact_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert model.known_species == frozenset({"Lenta lenta", "Rapida rapida"})
    assert set(model.model_card) == CARD_KEYS
    assert model.model_card["pr_auc_ci_low"] == 0.36


def test_predict_scores_every_tree_alive_and_measured_in_t(tmp_path):
    trees, observations, data = _artifact()
    model = load_stall_model(_write(tmp_path, data))
    probs = model.predict(trees, observations, 3)
    assert set(probs) == {r.tree_id for r in build_wave(trees, observations, 3, labeled=False)}
    assert all(0.0 < p < 1.0 for p in probs.values())
    rows = {r.tree_id: r for r in build_wave(trees, observations, 3, labeled=False)}
    stalled = [probs[t] for t, r in rows.items() if r.features["estanco_lag"] == 1.0]
    grew = [probs[t] for t, r in rows.items() if r.features["estanco_lag"] == 0.0]
    assert min(stalled) > max(grew)  # coeficiente positivo en estanco_lag


def test_missing_artifact_is_a_model_error(tmp_path):
    with pytest.raises(StallModelError):
        load_stall_model(tmp_path / "no-existe.json")


def test_invalid_json_is_a_model_error(tmp_path):
    path = tmp_path / "roto.json"
    path.write_text("{no es json", encoding="utf-8")
    with pytest.raises(StallModelError):
        load_stall_model(path)


@pytest.mark.parametrize("key", ["features_version", "preprocessing_version", "format"])
def test_artifact_from_another_version_is_rejected(tmp_path, key):
    _, _, data = _artifact()
    data[key] = "otra"
    with pytest.raises(StallModelError):
        load_stall_model(_write(tmp_path, data))


def test_coefficients_must_match_the_features(tmp_path):
    _, _, data = _artifact()
    data["model"]["coefficients"] = data["model"]["coefficients"][:-1]
    with pytest.raises(StallModelError):
        load_stall_model(_write(tmp_path, data))


def test_incomplete_artifact_is_a_model_error(tmp_path):
    _, _, data = _artifact()
    del data["evaluation"]
    with pytest.raises(StallModelError):
        load_stall_model(_write(tmp_path, data))
```

- [ ] **Step 3: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/ml/test_stall_model.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agrosense.ml.stall_model'`.

- [ ] **Step 4: Implementar**

`backend/src/agrosense/ml/stall_model.py`:

```python
"""Modelo de estancamiento servible (E7, ADR-013 §5).

Carga el artefacto JSON versionado y puntua arboles en Python puro: la API
no importa scikit-learn. `logistic_scores` es la UNICA implementacion de la
prediccion: la usa la inferencia y tambien la evaluacion del entrenamiento,
asi que las metricas del informe salen del mismo codigo que sirve la API.

El cargador falla (`StallModelError`) si el artefacto no existe, no es JSON,
esta incompleto o se entreno con otra version de features o de
preprocesamiento: nunca se sirve una prediccion con semantica distinta a la
evaluada.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agrosense.domain.entities import Observation, Tree
from agrosense.ml.preprocessing import PREPROCESSING_VERSION, PreprocessorParams, transform
from agrosense.ml.stall_features import (
    FEATURES_VERSION,
    FeatureValue,
    build_wave,
)
from agrosense.ml.stall_features import (
    fingerprint as data_fingerprint,
)

ARTIFACT_FORMAT = 1
ARTIFACT_PATH = Path(__file__).parent / "artifacts" / "stall_logreg.json"


class StallModelError(ValueError):
    """El artefacto del modelo falta o no es valido para este codigo."""


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def logistic_scores(
    params: PreprocessorParams,
    coefficients: Sequence[float],
    intercept: float,
    rows: Sequence[Mapping[str, FeatureValue]],
) -> list[float]:
    matrix = transform(params, rows)
    return [
        sigmoid(intercept + sum(c * x for c, x in zip(coefficients, vector, strict=True)))
        for vector in matrix
    ]


@dataclass(frozen=True)
class StallModel:
    model_version: str
    artifact_sha256: str
    params: PreprocessorParams
    coefficients: tuple[float, ...]
    intercept: float
    model_card: dict

    @property
    def known_species(self) -> frozenset[str]:
        return frozenset(self.params.categories.get("species", ()))

    def predict_rows(self, rows: Sequence[Mapping[str, FeatureValue]]) -> list[float]:
        return logistic_scores(self.params, self.coefficients, self.intercept, rows)

    def predict(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> dict[str, float]:
        """P(no crecer hasta t+1 | sigue vivo) de cada arbol vivo y medido en t."""
        rows = build_wave(trees, observations, t, labeled=False)
        scores = self.predict_rows([r.features for r in rows])
        return {r.tree_id: s for r, s in zip(rows, scores, strict=True)}

    def fingerprint(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> str:
        return data_fingerprint(trees, observations, t)


def _model_card(data: Mapping, sha: str) -> dict:
    temporal = data["evaluation"]["temporal"]
    provenance = data["provenance"]
    return {
        "model_version": str(data["model_version"]),
        "artifact_sha256": sha,
        "dataset_sha256": str(provenance["dataset_sha256"]),
        "trained_on": str(provenance["dataset_file"]),
        "pr_auc": float(temporal["pr_auc"]),
        "pr_auc_ci_low": float(temporal["pr_auc_ci"][0]),
        "pr_auc_ci_high": float(temporal["pr_auc_ci"][1]),
        "roc_auc": float(temporal["roc_auc"]),
        "prevalence_pct": float(temporal["prevalence_pct"]),
        "recall_at_budget_pct": float(temporal["recall_at_budget_pct"]),
        "precision_at_budget_pct": float(temporal["precision_at_budget_pct"]),
    }


def load_stall_model(path: Path = ARTIFACT_PATH) -> StallModel:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        name = Path(path).name
        raise StallModelError(f"no se encontro el artefacto del modelo ({name})") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise StallModelError("el artefacto del modelo no es JSON valido") from exc
    if not isinstance(data, dict) or data.get("format") != ARTIFACT_FORMAT:
        raise StallModelError("formato de artefacto desconocido")
    if data.get("features_version") != FEATURES_VERSION:
        raise StallModelError("el artefacto se entreno con otras features: reentrene el modelo")
    if data.get("preprocessing_version") != PREPROCESSING_VERSION:
        raise StallModelError("el artefacto se entreno con otro preprocesamiento: reentrene")
    sha = hashlib.sha256(raw).hexdigest()
    try:
        params = PreprocessorParams.from_json(data["preprocessor"])
        coefficients = tuple(float(c) for c in data["model"]["coefficients"])
        intercept = float(data["model"]["intercept"])
        card = _model_card(data, sha)
        version = str(data["model_version"])
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise StallModelError("el artefacto del modelo esta incompleto") from exc
    if len(coefficients) != len(params.feature_names):
        raise StallModelError("los coeficientes no corresponden a las features del artefacto")
    return StallModel(
        model_version=version,
        artifact_sha256=sha,
        params=params,
        coefficients=coefficients,
        intercept=intercept,
        model_card=card,
    )
```

- [ ] **Step 5: Ejecutar y verificar que pasan**

Run: `cd backend && python -m pytest tests/ml/test_stall_model.py tests/architecture -v`
Expected: PASS (y la ruta de inferencia sigue sin numpy/sklearn).

- [ ] **Step 6: Commit**

```bash
git add backend/src/agrosense/ml/stall_model.py backend/tests/ml/test_stall_model.py backend/tests/ml/builders.py
git commit -m "feat(e7): modelo servible desde artefacto JSON validado

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## S5 · Entrenamiento, evaluación y ML eval gate

### Task 6: `ml/evaluation.py`

**Files:**
- Create: `backend/src/agrosense/ml/evaluation.py`
- Create: `backend/tests/ml/test_evaluation.py`

**Interfaces:**
- Consumes: `domain.stall_rules.select_alerts` (Task 2).
- Produces:
  - `pr_auc(y: Sequence[int], scores: Sequence[float]) -> float`
  - `roc_auc(y: Sequence[int], scores: Sequence[float]) -> float`
  - `recall_precision_at_budget(tree_ids: Sequence[str], y: Sequence[int], scores: Sequence[float], budget: float) -> tuple[float, float]`
  - `grouped_bootstrap_ci(y, scores, plot_codes: Sequence[str], *, n_boot: int, seed: int, level: float = 0.95) -> tuple[float, float]`
  - `species_rate_scores(train_species: Sequence[str | None], train_y: Sequence[int], test_species: Sequence[str | None]) -> list[float]`

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/ml/test_evaluation.py`:

```python
"""Metricas del ML eval gate (Protocolo §5)."""
from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from agrosense.ml.evaluation import (  # noqa: E402
    grouped_bootstrap_ci,
    pr_auc,
    recall_precision_at_budget,
    roc_auc,
    species_rate_scores,
)


def test_constant_scores_give_the_prevalence():
    y = [1, 0, 0, 0, 1, 0, 0, 0, 0, 0]
    assert pr_auc(y, [0.5] * 10) == pytest.approx(0.2)
    assert roc_auc(y, [0.5] * 10) == pytest.approx(0.5)


def test_perfect_ranking():
    y = [1, 1, 0, 0]
    assert pr_auc(y, [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)


def test_recall_and_precision_use_the_alert_budget():
    ids = [f"T{i}" for i in range(10)]
    y = [1, 1, 0, 0, 0, 0, 0, 0, 0, 1]
    scores = [0.9, 0.8, 0.7, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.05]
    recall, precision = recall_precision_at_budget(ids, y, scores, 0.2)  # k = 2
    assert recall == pytest.approx(2 / 3)
    assert precision == pytest.approx(1.0)


def test_bootstrap_resamples_plots_not_rows():
    y = [1, 0, 1, 0, 0, 1, 0, 0]
    scores = [0.9, 0.2, 0.7, 0.3, 0.1, 0.8, 0.4, 0.2]
    # Una sola parcela: todo remuestreo es identico -> IC degenerado.
    lo, hi = grouped_bootstrap_ci(y, scores, ["U1"] * 8, n_boot=30, seed=1)
    assert lo == pytest.approx(hi)


def test_bootstrap_is_deterministic_and_brackets_the_estimate():
    y = [1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0]
    scores = [0.8, 0.3, 0.2, 0.6, 0.4, 0.1, 0.7, 0.5, 0.2, 0.9, 0.3, 0.4]
    plots = ["U1", "U1", "U1", "U2", "U2", "U2", "U3", "U3", "U3", "U4", "U4", "U4"]
    a = grouped_bootstrap_ci(y, scores, plots, n_boot=200, seed=42)
    b = grouped_bootstrap_ci(y, scores, plots, n_boot=200, seed=42)
    assert a == b
    assert a[0] <= pr_auc(y, scores) <= a[1]


def test_species_rate_is_fitted_on_train_and_falls_back_to_prevalence():
    scores = species_rate_scores(["A", "A", "B", "B"], [1, 1, 0, 1], ["A", "B", "Nueva", None])
    assert scores == [1.0, 0.5, 0.75, 0.75]
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/ml/test_evaluation.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agrosense.ml.evaluation'`.

- [ ] **Step 3: Implementar**

`backend/src/agrosense/ml/evaluation.py`:

```python
"""Metricas del ML eval gate del modelo de estancamiento (E7).

SOLO entrenamiento/evaluacion offline: importa numpy y scikit-learn, que no
son dependencias de produccion (ADR-013). La API nunca importa este modulo.

PR-AUC es la metrica principal (Protocolo §5): la clase positiva es
minoritaria (~22 %) y la exactitud seria enganosa.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from agrosense.domain.stall_rules import select_alerts


def pr_auc(y: Sequence[int], scores: Sequence[float]) -> float:
    return float(average_precision_score(np.asarray(y, dtype=int), np.asarray(scores, dtype=float)))


def roc_auc(y: Sequence[int], scores: Sequence[float]) -> float:
    return float(roc_auc_score(np.asarray(y, dtype=int), np.asarray(scores, dtype=float)))


def recall_precision_at_budget(
    tree_ids: Sequence[str], y: Sequence[int], scores: Sequence[float], budget: float
) -> tuple[float, float]:
    """Si se revisa en campo el `budget` de arboles con mayor score.

    Usa `select_alerts`, la MISMA regla con la que la API marca arboles.
    """
    flagged = select_alerts(dict(zip(tree_ids, scores, strict=True)), budget)
    positives = sum(y)
    hits = sum(1 for tid, yi in zip(tree_ids, y, strict=True) if yi and tid in flagged)
    recall = hits / positives if positives else 0.0
    precision = hits / len(flagged) if flagged else 0.0
    return recall, precision


def grouped_bootstrap_ci(
    y: Sequence[int],
    scores: Sequence[float],
    plot_codes: Sequence[str],
    *,
    n_boot: int,
    seed: int,
    level: float = 0.95,
) -> tuple[float, float]:
    """IC del PR-AUC remuestreando PARCELAS con reemplazo, no filas.

    Las filas de una parcela no son independientes (suelo, pendiente,
    cuadrilla): remuestrear filas daria un IC falsamente estrecho.
    """
    y_arr = np.asarray(y, dtype=int)
    s_arr = np.asarray(scores, dtype=float)
    plots = sorted(set(plot_codes))
    codes = np.asarray(plot_codes, dtype=object)
    index = {p: np.flatnonzero(codes == p) for p in plots}
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(n_boot):
        chosen = rng.integers(0, len(plots), size=len(plots))
        idx = np.concatenate([index[plots[i]] for i in chosen])
        if y_arr[idx].min() == y_arr[idx].max():
            continue
        values.append(float(average_precision_score(y_arr[idx], s_arr[idx])))
    if not values:
        raise ValueError("ningun remuestreo tuvo ambas clases: no hay IC")
    alpha = (1.0 - level) / 2.0
    lo, hi = np.quantile(values, [alpha, 1.0 - alpha])
    return float(lo), float(hi)


def species_rate_scores(
    train_species: Sequence[str | None],
    train_y: Sequence[int],
    test_species: Sequence[str | None],
) -> list[float]:
    """Linea base "tasa media por especie" (Protocolo §5), ajustada SOLO en train."""
    totals: dict[str | None, list[int]] = defaultdict(lambda: [0, 0])
    for species, label in zip(train_species, train_y, strict=True):
        totals[species][0] += int(label)
        totals[species][1] += 1
    prevalence = sum(train_y) / len(train_y)
    return [
        totals[s][0] / totals[s][1] if s is not None and s in totals else prevalence
        for s in test_species
    ]
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `cd backend && python -m pytest tests/ml/test_evaluation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/ml/evaluation.py backend/tests/ml/test_evaluation.py
git commit -m "feat(e7): metricas del ML eval gate con bootstrap por parcela

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 7: `ml/train_stall.py` — entrenamiento, evaluación, gate y artefacto

**Files:**
- Create: `backend/src/agrosense/ml/train_stall.py`
- Create: `backend/tests/ml/test_train_stall.py`

**Interfaces:**
- Consumes: Tasks 2-6 (`build_wave`, `WaveRow`, `NUMERIC_FEATURES`, `CATEGORICAL_FEATURES`, `FEATURES_VERSION`, `fit_preprocessor`, `transform`, `PreprocessorParams`, `PREPROCESSING_VERSION`, `logistic_scores`, `ARTIFACT_FORMAT`, `load_stall_model`, métricas de `evaluation`, `ALERT_BUDGET`).
- Produces:
  - `@dataclass(frozen=True) StallTrainConfig` (campos y valores por defecto abajo; `model_version = "stall-logreg-2026-09-27.1"`)
  - `@dataclass(frozen=True) FittedStallModel(params, coefficients: tuple[float, ...], intercept: float)` con `scores(rows: Sequence[WaveRow]) -> list[float]`
  - `fit_logistic(X: Sequence[Sequence[float]], y: Sequence[int], config) -> LogisticRegression`
  - `fit_stall_model(rows: Sequence[WaveRow], config, labels: Sequence[int] | None = None) -> FittedStallModel`
  - `permuted_within_plot(rows: Sequence[WaveRow], rng: np.random.Generator) -> list[int]`
  - `permuted_globally(rows: Sequence[WaveRow], rng: np.random.Generator) -> list[int]`
  - `evaluate(...)["permutation_control"]` = `{"n_permutations", "global": {"pr_auc_mean", "pr_auc_min", "pr_auc_max"}, "within_plot": {...}}`; checks del gate: `pr_auc_at_least_min`, `beats_prevalence`, `beats_persistence`, `permutation_control_near_prevalence`, `beats_within_plot_permutation`
  - `evaluate(trees, observations, config) -> dict` con claves `temporal`, `baselines`, `permutation_control`, `group_kfold`
  - `gate(evaluation: dict, config) -> dict` con `checks: dict[str, bool]`, `passed: bool`
  - `train_and_evaluate(trees, observations, config, provenance: Mapping[str, object]) -> dict` (el artefacto completo)
  - `diff_artifacts(a, b, *, tol: float = 1e-9) -> list[str]` (ignora `created_at`, `provenance/git_commit`, `provenance/git_dirty`)
  - `render_report(artifact: dict) -> str`

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/ml/test_train_stall.py`:

```python
"""Entrenamiento y ML eval gate del modelo de estancamiento (E7)."""
from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("sklearn")

from agrosense.ml.preprocessing import fit_preprocessor, transform  # noqa: E402
from agrosense.ml.stall_features import (  # noqa: E402
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    build_wave,
)
from agrosense.ml.stall_model import load_stall_model, logistic_scores  # noqa: E402
from agrosense.ml.train_stall import (  # noqa: E402
    StallTrainConfig,
    diff_artifacts,
    evaluate,
    fit_logistic,
    fit_stall_model,
    gate,
    permuted_globally,
    permuted_within_plot,
    render_report,
    train_and_evaluate,
)
from tests.ml.builders import synthetic_panel  # noqa: E402

FAST = StallTrainConfig(n_bootstrap=50, n_permutations=3)
PROVENANCE = {
    "dataset_file": "sintetico",
    "dataset_sha256": "0" * 64,
    "sheet": "-",
    "mapping_version": "-",
    "git_commit": "abc",
    "git_dirty": False,
    "python": "3.12",
    "sklearn": "1.5.2",
    "numpy": "1.26.4",
}
REFERENCE_PATH = Path(__file__).parents[2] / "data" / "raw" / "anexo1.xlsx"


def test_preprocessing_is_fitted_on_training_rows_only():
    trees, observations = synthetic_panel()
    train = build_wave(trees, observations, 2, labeled=True)
    model = fit_stall_model(train, FAST)
    assert model.params.medians["h_t"] == statistics.median(r.features["h_t"] for r in train)


def test_serving_scores_equal_sklearn_probabilities():
    trees, observations = synthetic_panel()
    train = build_wave(trees, observations, 2, labeled=True)
    feats = [r.features for r in train]
    params = fit_preprocessor(feats, NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    X = transform(params, feats)
    clf = fit_logistic(X, [int(bool(r.label)) for r in train], FAST)
    ours = logistic_scores(params, tuple(clf.coef_[0]), float(clf.intercept_[0]), feats)
    np.testing.assert_allclose(ours, clf.predict_proba(np.asarray(X))[:, 1], atol=1e-12)


def test_permutation_keeps_the_positives_of_each_plot():
    trees, observations = synthetic_panel()
    train = build_wave(trees, observations, 2, labeled=True)
    permuted = permuted_within_plot(train, np.random.default_rng(0))

    def per_plot(labels):
        c: Counter = Counter()
        for row, label in zip(train, labels, strict=True):
            c[row.plot] += label
        return c

    assert per_plot(permuted) == per_plot([int(bool(r.label)) for r in train])
    assert permuted != [int(bool(r.label)) for r in train]


def test_evaluate_reports_every_regime():
    trees, observations = synthetic_panel()
    ev = evaluate(trees, observations, FAST)
    assert set(ev) == {"temporal", "baselines", "permutation_control", "group_kfold"}
    t = ev["temporal"]
    assert t["n_train"] == len(build_wave(trees, observations, 2, labeled=True))
    assert t["n_test"] == len(build_wave(trees, observations, 3, labeled=True))
    assert 0.0 <= t["pr_auc"] <= 1.0
    assert t["pr_auc_ci"][0] <= t["pr_auc_ci"][1]
    assert set(ev["baselines"]) == {"prevalence", "persistence", "species_rate"}
    assert ev["group_kfold"]["folds"] == 5


def _ev(pr, perm_global, perm_within=0.33, persistence=0.35, prevalence=0.22):
    return {
        "temporal": {"pr_auc": pr},
        "baselines": {
            "prevalence": {"pr_auc": prevalence},
            "persistence": {"pr_auc": persistence},
        },
        "permutation_control": {
            "global": {"pr_auc_mean": perm_global},
            "within_plot": {"pr_auc_mean": perm_within},
        },
    }


def test_gate_accepts_the_protocol_result():
    assert gate(_ev(0.469, 0.238), StallTrainConfig())["passed"] is True


def test_gate_rejects_a_weak_model():
    result = gate(_ev(0.30, 0.24), StallTrainConfig())
    assert result["passed"] is False
    assert result["checks"]["pr_auc_at_least_min"] is False


def test_gate_rejects_a_leaky_pipeline():
    # Si el control SIN senal puntua alto, el pipeline filtra la etiqueta.
    result = gate(_ev(0.60, 0.45), StallTrainConfig())
    assert result["checks"]["permutation_control_near_prevalence"] is False
    assert result["passed"] is False


def test_gate_rejects_a_model_that_only_learns_plot_rates():
    result = gate(_ev(0.40, 0.23, perm_within=0.42), StallTrainConfig())
    assert result["checks"]["beats_within_plot_permutation"] is False
    assert result["passed"] is False


def test_global_permutation_keeps_the_number_of_positives():
    trees, observations = synthetic_panel()
    train = build_wave(trees, observations, 2, labeled=True)
    permuted = permuted_globally(train, np.random.default_rng(0))
    assert sum(permuted) == sum(int(bool(r.label)) for r in train)


def test_training_is_reproducible():
    trees, observations = synthetic_panel()
    a = train_and_evaluate(trees, observations, FAST, PROVENANCE)
    b = train_and_evaluate(trees, observations, FAST, PROVENANCE)
    assert diff_artifacts(a, b) == []


def test_artifact_records_provenance_and_loads_as_the_serving_model(tmp_path):
    trees, observations = synthetic_panel()
    artifact = train_and_evaluate(trees, observations, FAST, PROVENANCE)
    for key in ("model_version", "features_version", "preprocessing_version", "created_at"):
        assert artifact[key]
    assert artifact["training"]["config"]["seed"] == 42
    assert artifact["training"]["waves"] == [2, 3]
    assert artifact["provenance"]["dataset_sha256"] == "0" * 64
    path = tmp_path / "a.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    model = load_stall_model(path)
    probs = model.predict(trees, observations, 4)
    assert probs and all(0.0 < p < 1.0 for p in probs.values())
    assert "Evaluación del modelo de estancamiento" in render_report(artifact)


def test_diff_artifacts_ignores_only_volatile_fields():
    base = {"created_at": "a", "provenance": {"git_commit": "x", "d": "1"}, "m": {"c": [0.1]}}
    other = {
        "created_at": "b",
        "provenance": {"git_commit": "y", "d": "1"},
        "m": {"c": (0.1 + 1e-12,)},
    }
    assert diff_artifacts(base, other) == []
    other["m"]["c"] = (0.2,)
    assert diff_artifacts(base, other) == ["m/c/0"]
    other["provenance"]["d"] = "2"
    assert "provenance/d" in diff_artifacts(base, other)


@pytest.mark.skipif(
    not REFERENCE_PATH.exists(),
    reason="dataset de referencia local ausente (data/raw/anexo1.xlsx)",
)
def test_reference_dataset_passes_the_gate():
    from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

    data = ExcelCampaignSource().read(REFERENCE_PATH.read_bytes(), REFERENCE_PATH.name)
    config = StallTrainConfig(n_bootstrap=200, n_permutations=5)
    ev = evaluate(data.trees, data.observations, config)
    t = ev["temporal"]
    assert (t["n_train"], t["positives_train"]) == (618, 153)
    assert (t["n_test"], t["positives_test"]) == (717, 157)
    assert t["pr_auc"] >= 0.36
    assert ev["permutation_control"]["global"]["pr_auc_mean"] <= 0.31
    assert t["pr_auc"] > ev["permutation_control"]["within_plot"]["pr_auc_mean"]
    assert gate(ev, config)["passed"] is True
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/ml/test_train_stall.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agrosense.ml.train_stall'`.

- [ ] **Step 3: Implementar**

`backend/src/agrosense/ml/train_stall.py`:

```python
"""Entrenamiento y evaluacion del modelo de estancamiento (E7, ADR-013).

Protocolo: docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md.

  - Regimen PRIMARIO, temporal: entrena con la ola M2 (etiqueta M2->M3) y
    prueba con la ola M3 (etiqueta M3->M4). Ninguna observacion (arbol+ola)
    queda a ambos lados.
  - Regimen SECUNDARIO, diagnostico: GroupKFold de 5 folds agrupado por
    PARCELA (`Codigo de unidad muestreo`) sobre las olas etiquetadas.
  - IC 95 % del PR-AUC por bootstrap de parcelas; dos controles negativos:
    etiqueta permutada en todo el conjunto (vigila fugas) y dentro de cada
    parcela (cuanto da aprender solo la tasa de la parcela).
  - Lineas base: prevalencia, persistencia (estanco_lag) y tasa por especie.

El artefacto que se sirve se reentrena con el MISMO procedimiento sobre las
olas `final_waves`: el gate evalua el procedimiento y el artefacto guarda las
metricas de esa evaluacion.

SOLO offline: numpy y scikit-learn no son dependencias de produccion.
"""
from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold

from agrosense.domain.entities import Observation, Tree
from agrosense.domain.stall_rules import ALERT_BUDGET
from agrosense.ml.evaluation import (
    grouped_bootstrap_ci,
    pr_auc,
    recall_precision_at_budget,
    roc_auc,
    species_rate_scores,
)
from agrosense.ml.preprocessing import (
    PREPROCESSING_VERSION,
    PreprocessorParams,
    fit_preprocessor,
    transform,
)
from agrosense.ml.stall_features import (
    CATEGORICAL_FEATURES,
    FEATURES_VERSION,
    NUMERIC_FEATURES,
    WaveRow,
    build_wave,
)
from agrosense.ml.stall_model import ARTIFACT_FORMAT, logistic_scores

NO_PLOT = "(sin parcela)"

# Campos que cambian en cada corrida sin cambiar el modelo.
_VOLATILE: frozenset[tuple[str, ...]] = frozenset(
    {("created_at",), ("provenance", "git_commit"), ("provenance", "git_dirty")}
)


@dataclass(frozen=True)
class StallTrainConfig:
    """Configuracion completa del entrenamiento; viaja en el artefacto."""

    model_version: str = "stall-logreg-2026-09-27.1"
    train_wave: int = 2
    test_wave: int = 3
    final_waves: tuple[int, ...] = (2, 3)
    C: float = 0.5
    class_weight: str = "balanced"
    max_iter: int = 2000
    solver: str = "lbfgs"
    seed: int = 42
    n_bootstrap: int = 1000
    n_permutations: int = 20
    cv_folds: int = 5
    alert_budget: float = ALERT_BUDGET
    # Gate: limite inferior del IC 95 % del protocolo (0.36) y limite superior
    # del IC del control permutado (0.31). Protocolo §5.
    gate_min_pr_auc: float = 0.36
    gate_max_permuted_pr_auc: float = 0.31
    expected_dataset_sha256: str = (
        "28583c3b48874626f3d7d7ae35d485634a8c8089b4c03a5997f5ba756b57a0dd"
    )


@dataclass(frozen=True)
class FittedStallModel:
    params: PreprocessorParams
    coefficients: tuple[float, ...]
    intercept: float

    def scores(self, rows: Sequence[WaveRow]) -> list[float]:
        # La MISMA funcion que usa la API (stall_model.logistic_scores).
        return logistic_scores(
            self.params, self.coefficients, self.intercept, [r.features for r in rows]
        )


def _labels(rows: Sequence[WaveRow]) -> list[int]:
    return [int(bool(r.label)) for r in rows]


def _plots(rows: Sequence[WaveRow]) -> list[str]:
    return [r.plot or NO_PLOT for r in rows]


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def fit_logistic(
    X: Sequence[Sequence[float]], y: Sequence[int], config: StallTrainConfig
) -> LogisticRegression:
    clf = LogisticRegression(
        C=config.C,
        class_weight=config.class_weight,
        max_iter=config.max_iter,
        solver=config.solver,
        random_state=config.seed,
    )
    clf.fit(np.asarray(X, dtype=float), np.asarray(y, dtype=int))
    return clf


def fit_stall_model(
    rows: Sequence[WaveRow],
    config: StallTrainConfig,
    labels: Sequence[int] | None = None,
) -> FittedStallModel:
    """Ajusta preprocesamiento + logistica SOLO con `rows` (fuga §4.4)."""
    feats = [r.features for r in rows]
    params = fit_preprocessor(feats, NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    y = _labels(rows) if labels is None else [int(v) for v in labels]
    clf = fit_logistic(transform(params, feats), y, config)
    return FittedStallModel(
        params=params,
        coefficients=tuple(float(c) for c in clf.coef_[0]),
        intercept=float(clf.intercept_[0]),
    )


def permuted_within_plot(rows: Sequence[WaveRow], rng: np.random.Generator) -> list[int]:
    """Etiquetas barajadas DENTRO de cada parcela (control negativo, Protocolo §5)."""
    labels = _labels(rows)
    by_plot: dict[str, list[int]] = defaultdict(list)
    for i, plot in enumerate(_plots(rows)):
        by_plot[plot].append(i)
    out = list(labels)
    for plot in sorted(by_plot):
        idx = by_plot[plot]
        shuffled = [labels[i] for i in idx]
        rng.shuffle(shuffled)
        for i, value in zip(idx, shuffled, strict=True):
            out[i] = value
    return out


def _temporal(train, test, model, config) -> dict:
    y = _labels(test)
    scores = model.scores(test)
    plots = _plots(test)
    recall, precision = recall_precision_at_budget(
        [r.tree_id for r in test], y, scores, config.alert_budget
    )
    lo, hi = grouped_bootstrap_ci(y, scores, plots, n_boot=config.n_bootstrap, seed=config.seed)
    prevalence = sum(y) / len(y)
    return {
        "train_wave": config.train_wave,
        "test_wave": config.test_wave,
        "n_train": len(train),
        "positives_train": sum(_labels(train)),
        "n_test": len(test),
        "positives_test": sum(y),
        "n_test_plots": len(set(plots)),
        "prevalence_pct": _round(100 * prevalence, 2),
        "pr_auc": _round(pr_auc(y, scores)),
        "pr_auc_ci": [_round(lo), _round(hi)],
        "roc_auc": _round(roc_auc(y, scores)),
        "alert_budget_pct": _round(100 * config.alert_budget, 1),
        "recall_at_budget_pct": _round(100 * recall, 2),
        "precision_at_budget_pct": _round(100 * precision, 2),
    }


def _baselines(train, test) -> dict:
    y = _labels(test)
    persistence = [float(r.features["estanco_lag"] or 0.0) for r in test]
    species = species_rate_scores(
        [r.features["species"] for r in train],  # type: ignore[misc]
        _labels(train),
        [r.features["species"] for r in test],  # type: ignore[misc]
    )
    return {
        "prevalence": {"pr_auc": _round(sum(y) / len(y))},
        "persistence": {"pr_auc": _round(pr_auc(y, persistence))},
        "species_rate": {"pr_auc": _round(pr_auc(y, species))},
    }


def permuted_globally(rows: Sequence[WaveRow], rng: np.random.Generator) -> list[int]:
    """Etiquetas barajadas en todo el conjunto: el modelo no puede aprender nada."""
    return [int(v) for v in rng.permutation(_labels(rows))]


def _permutation_control(train, test, config) -> dict:
    """Dos controles negativos (ADR-013 §4).

    - `global`: sin ninguna senal; un pipeline sin fugas cae a la prevalencia.
      Es el control que vigila las fugas.
    - `within_plot`: conserva la tasa de cada parcela; lo que puntua es cuanto
      rinde aprender SOLO la tasa de la parcela. El modelo real debe superarlo.
    """
    y = _labels(test)

    def run(permute) -> dict:
        rng = np.random.default_rng(config.seed)
        values = [
            pr_auc(y, fit_stall_model(train, config, permute(train, rng)).scores(test))
            for _ in range(config.n_permutations)
        ]
        return {
            "pr_auc_mean": _round(float(np.mean(values))),
            "pr_auc_min": _round(min(values)),
            "pr_auc_max": _round(max(values)),
        }

    return {
        "n_permutations": config.n_permutations,
        "global": run(permuted_globally),
        "within_plot": run(permuted_within_plot),
    }


def _group_kfold(pooled: Sequence[WaveRow], config) -> dict:
    """Diagnostico: GroupKFold con la PARCELA como grupo (nunca el individuo)."""
    plot_codes = _plots(pooled)
    oof = [0.0] * len(pooled)
    by_fold: list[float] = []
    splitter = GroupKFold(n_splits=config.cv_folds)
    for fit_idx, held_idx in splitter.split(np.zeros(len(pooled)), groups=plot_codes):
        fold_model = fit_stall_model([pooled[i] for i in fit_idx], config)
        held = [pooled[i] for i in held_idx]
        held_scores = fold_model.scores(held)
        for i, score in zip(held_idx, held_scores, strict=True):
            oof[i] = score
        held_y = _labels(held)
        if 0 < sum(held_y) < len(held_y):
            by_fold.append(pr_auc(held_y, held_scores))
    return {
        "folds": config.cv_folds,
        "grouping": "Codigo de unidad muestreo (parcela)",
        "pr_auc_pooled": _round(pr_auc(_labels(pooled), oof)),
        "pr_auc_by_fold": [_round(v) for v in by_fold],
    }


def evaluate(
    trees: Sequence[Tree], observations: Sequence[Observation], config: StallTrainConfig
) -> dict:
    train = build_wave(trees, observations, config.train_wave, labeled=True)
    test = build_wave(trees, observations, config.test_wave, labeled=True)
    model = fit_stall_model(train, config)
    return {
        "temporal": _temporal(train, test, model, config),
        "baselines": _baselines(train, test),
        "permutation_control": _permutation_control(train, test, config),
        "group_kfold": _group_kfold(list(train) + list(test), config),
    }


def gate(evaluation: Mapping, config: StallTrainConfig) -> dict:
    t = evaluation["temporal"]
    b = evaluation["baselines"]
    c = evaluation["permutation_control"]
    checks = {
        "pr_auc_at_least_min": t["pr_auc"] >= config.gate_min_pr_auc,
        "beats_prevalence": t["pr_auc"] > b["prevalence"]["pr_auc"],
        "beats_persistence": t["pr_auc"] > b["persistence"]["pr_auc"],
        "permutation_control_near_prevalence": (
            c["global"]["pr_auc_mean"] <= config.gate_max_permuted_pr_auc
        ),
        "beats_within_plot_permutation": t["pr_auc"] > c["within_plot"]["pr_auc_mean"],
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "min_pr_auc": config.gate_min_pr_auc,
        "max_permuted_pr_auc": config.gate_max_permuted_pr_auc,
    }


def _config_json(config: StallTrainConfig) -> dict:
    return {k: list(v) if isinstance(v, tuple) else v for k, v in asdict(config).items()}


def train_and_evaluate(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    config: StallTrainConfig,
    provenance: Mapping[str, object],
) -> dict:
    """Evalua, aplica el gate y reentrena el modelo servible. Devuelve el artefacto."""
    evaluation = evaluate(trees, observations, config)
    evaluation["gate"] = gate(evaluation, config)
    final_rows = [
        row for w in config.final_waves for row in build_wave(trees, observations, w, labeled=True)
    ]
    final = fit_stall_model(final_rows, config)
    return {
        "format": ARTIFACT_FORMAT,
        "model_version": config.model_version,
        "features_version": FEATURES_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "preprocessor": final.params.to_json(),
        "model": {
            "type": "logistic_regression",
            "feature_names": final.params.feature_names,
            "coefficients": list(final.coefficients),
            "intercept": final.intercept,
        },
        "training": {
            "config": _config_json(config),
            "waves": list(config.final_waves),
            "n_rows": len(final_rows),
            "positives": sum(_labels(final_rows)),
        },
        "evaluation": evaluation,
        "provenance": dict(provenance),
    }


def diff_artifacts(a, b, *, tol: float = 1e-9, _path: tuple[str, ...] = ()) -> list[str]:
    """Rutas donde dos artefactos difieren (floats con tolerancia)."""
    if _path in _VOLATILE:
        return []
    here = "/".join(_path)
    if isinstance(a, dict) and isinstance(b, dict):
        out: list[str] = []
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append("/".join(_path + (key,)))
                continue
            out.extend(diff_artifacts(a[key], b[key], tol=tol, _path=_path + (key,)))
        return out
    if isinstance(a, list | tuple) and isinstance(b, list | tuple):
        if len(a) != len(b):
            return [here]
        out = []
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out.extend(diff_artifacts(x, y, tol=tol, _path=_path + (str(i),)))
        return out
    if isinstance(a, bool) or isinstance(b, bool):
        return [] if a == b else [here]
    if isinstance(a, int | float) and isinstance(b, int | float):
        return [] if math.isclose(a, b, rel_tol=tol, abs_tol=tol) else [here]
    return [] if a == b else [here]


def render_report(artifact: Mapping) -> str:
    """Informe de metricas (docs/ml/evaluacion-estancamiento.md), generado."""
    ev = artifact["evaluation"]
    t = ev["temporal"]
    b = ev["baselines"]
    c = ev["permutation_control"]
    cg = c["global"]
    cw = c["within_plot"]
    g = ev["group_kfold"]
    decision = ev["gate"]
    p = artifact["provenance"]
    tr = artifact["training"]
    estado = "APROBADO" if decision["passed"] else "RECHAZADO"
    olas = ", ".join(f"M{w}" for w in tr["waves"])
    folds = ", ".join(f"{v:.3f}" for v in g["pr_auc_by_fold"])
    dirty = " (con cambios sin confirmar)" if p.get("git_dirty") else ""
    lines = [
        f"# Evaluación del modelo de estancamiento — {artifact['model_version']}",
        "",
        "> Generado por `cd backend && python scripts/train_stall_model.py "
        "--data data/raw/anexo1.xlsx`. No editar a mano.",
        "",
        f"**ML eval gate: {estado}**",
        "",
        "## Procedencia",
        "",
        "| Campo | Valor |",
        "|---|---|",
        f"| Dataset | `{p['dataset_file']}` (hoja `{p['sheet']}`) |",
        f"| SHA-256 del dataset | `{p['dataset_sha256']}` |",
        f"| Versión de la ingesta | `{p['mapping_version']}` |",
        f"| Features | `{artifact['features_version']}` |",
        f"| Preprocesamiento | `{artifact['preprocessing_version']}` |",
        f"| Commit del código | `{p['git_commit']}`{dirty} |",
        f"| Versiones | Python {p['python']}, scikit-learn {p['sklearn']}, numpy {p['numpy']} |",
        f"| Semilla | {tr['config']['seed']} |",
        f"| Entrenado | {artifact['created_at']} |",
        "",
        "## Régimen primario — validación adelantada en el tiempo",
        "",
        f"Entrena con la ola M{t['train_wave']} "
        f"(etiqueta M{t['train_wave']}→M{t['train_wave'] + 1}, "
        f"n = {t['n_train']}, {t['positives_train']} estancados) y prueba con la ola "
        f"M{t['test_wave']} (etiqueta M{t['test_wave']}→M{t['test_wave'] + 1}, "
        f"n = {t['n_test']}, {t['positives_test']} estancados, {t['n_test_plots']} parcelas).",
        "",
        "| Modelo | PR-AUC |",
        "|---|---|",
        f"| Prevalencia (sin modelo) | {b['prevalence']['pr_auc']:.3f} |",
        f"| Persistencia (estancó antes) | {b['persistence']['pr_auc']:.3f} |",
        f"| Tasa media por especie | {b['species_rate']['pr_auc']:.3f} |",
        f"| **Regresión logística** | **{t['pr_auc']:.3f}** (IC 95 % por parcelas "
        f"{t['pr_auc_ci'][0]:.2f}–{t['pr_auc_ci'][1]:.2f}) |",
        f"| Control negativo: etiqueta permutada en todo el conjunto ({c['n_permutations']} "
        f"corridas) | {cg['pr_auc_mean']:.3f} (rango {cg['pr_auc_min']:.3f}–"
        f"{cg['pr_auc_max']:.3f}) |",
        f"| Control: permutada dentro de cada parcela (solo la tasa de la parcela) | "
        f"{cw['pr_auc_mean']:.3f} (rango {cw['pr_auc_min']:.3f}–{cw['pr_auc_max']:.3f}) |",
        "",
        f"ROC-AUC {t['roc_auc']:.3f}. Con un presupuesto de alertas del "
        f"{t['alert_budget_pct']:.0f} %: recall {t['recall_at_budget_pct']:.1f} %, "
        f"precisión {t['precision_at_budget_pct']:.1f} %.",
        "",
        "## Régimen secundario — GroupKFold por parcela (diagnóstico)",
        "",
        f"{g['folds']} folds agrupados por {g['grouping']}: PR-AUC agregado "
        f"{g['pr_auc_pooled']:.3f}; por fold {folds}.",
        "",
        "## Gate",
        "",
        "| Criterio | Resultado |",
        "|---|---|",
        *[f"| `{k}` | {'cumple' if v else 'no cumple'} |" for k, v in decision["checks"].items()],
        "",
        "## Artefacto servido",
        "",
        f"Reentrenado con el mismo procedimiento sobre las olas {olas} (n = {tr['n_rows']}, "
        f"{tr['positives']} estancados). Las métricas de arriba evalúan el procedimiento, "
        "no este reentrenamiento.",
        "",
        "## Lectura honesta",
        "",
        "La evidencia de que el modelo supera a una regla de una línea es sugestiva, no "
        "concluyente (Protocolo §5): los intervalos de la logística y de la tasa por especie "
        "se solapan. La etiqueta mide «crecimiento no detectable por el protocolo», no "
        "«crecimiento nulo». La probabilidad es condicional a que el árbol siga vivo.",
        "",
    ]
    return "\n".join(lines)
```

- [ ] **Step 4: Ejecutar y verificar que pasan (incluido el gate de CV por parcela)**

Run: `cd backend && python -m pytest tests/ml/test_train_stall.py tests/architecture/test_ml_eval_gate.py -v`
Expected: PASS; `test_groupkfold_uses_plot` deja de saltarse y pasa (la línea `splitter.split(np.zeros(len(pooled)), groups=plot_codes)` nombra la parcela). `test_reference_dataset_passes_the_gate` tarda del orden de decenas de segundos.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/ml/train_stall.py backend/tests/ml/test_train_stall.py
git commit -m "feat(e7): entrenamiento, evaluacion honesta y ML eval gate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 8: El comando único, el artefacto versionado y las métricas documentadas

**Files:**
- Create: `backend/scripts/train_stall_model.py`
- Create: `backend/tests/ml/test_train_script.py`
- Create: `backend/tests/ml/test_committed_artifact.py`
- Create (generado): `backend/src/agrosense/ml/artifacts/stall_logreg.json`
- Create (generado): `docs/ml/evaluacion-estancamiento.md`

**Interfaces:**
- Consumes: Task 7 (`StallTrainConfig`, `train_and_evaluate`, `diff_artifacts`, `render_report`); `ARTIFACT_PATH`, `load_stall_model` (Task 5); `ExcelCampaignSource`, `SHEET_NAME` (`adapters/ingester/excel_source.py`); `MAPPING_VERSION` (`adapters/ingester/column_mapping.py`).
- Produces: `main(argv: list[str] | None = None) -> int` (0 = ok, 1 = gate rechazado o no reproducible, 2 = dataset inesperado); el artefacto en `ARTIFACT_PATH`; el informe en `docs/ml/evaluacion-estancamiento.md`.

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/ml/test_train_script.py`:

```python
"""El comando unico de entrenamiento se niega a entrenar con otros datos."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

SCRIPT = Path(__file__).parents[2] / "scripts" / "train_stall_model.py"


def _load():
    spec = importlib.util.spec_from_file_location("train_stall_model", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rejects_a_dataset_that_is_not_the_versioned_one(tmp_path):
    data = tmp_path / "otro.xlsx"
    data.write_bytes(b"no es el anexo")
    out = tmp_path / "a.json"
    code = _load().main(
        ["--data", str(data), "--out", str(out), "--report", str(tmp_path / "r.md")]
    )
    assert code == 2
    assert not out.exists()
```

`backend/tests/ml/test_committed_artifact.py`:

```python
"""El artefacto versionado carga, paso el gate y es de este dataset."""
from __future__ import annotations

import json

from agrosense.ml.stall_model import ARTIFACT_PATH, load_stall_model

DATASET_SHA256 = "28583c3b48874626f3d7d7ae35d485634a8c8089b4c03a5997f5ba756b57a0dd"


def test_committed_artifact_is_servable():
    model = load_stall_model()
    assert model.model_version.startswith("stall-logreg-")
    assert len(model.coefficients) == len(model.params.feature_names)
    assert model.model_card["dataset_sha256"] == DATASET_SHA256


def test_committed_artifact_passed_the_gate():
    data = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    ev = data["evaluation"]
    assert ev["gate"]["passed"] is True
    assert (ev["temporal"]["n_test"], ev["temporal"]["positives_test"]) == (717, 157)
    assert ev["temporal"]["pr_auc"] >= 0.36
    assert data["provenance"]["git_dirty"] is False
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/ml/test_train_script.py tests/ml/test_committed_artifact.py -v`
Expected: FAIL (`FileNotFoundError` del script; `StallModelError` porque el artefacto aún no existe).

- [ ] **Step 3: Implementar el script**

`backend/scripts/train_stall_model.py`:

```python
"""Entrena y evalua el modelo de estancamiento (E7, ADR-013). EL comando unico.

Uso (desde backend/, con `pip install -e ".[dev,ml]"`):
    python scripts/train_stall_model.py --data data/raw/anexo1.xlsx
    python scripts/train_stall_model.py --data data/raw/anexo1.xlsx --check

Sin `--check`: evalua (temporal + GroupKFold por parcela + bootstrap +
control permutado + lineas base), aplica el ML eval gate y, SOLO si lo pasa,
escribe el artefacto versionado y el informe de metricas.
Con `--check`: reentrena y compara contra el artefacto versionado; no
escribe nada. Es la prueba de reproducibilidad de AGENTS.md.

Este script es el composition root: lee el Excel con el adapter de ingesta
(el mismo que usa la carga de la API) y le pasa entidades de dominio a ml/,
que no puede importar adapters/ (ADR-003).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND / "src"))

from agrosense.adapters.ingester.column_mapping import MAPPING_VERSION  # noqa: E402
from agrosense.adapters.ingester.excel_source import (  # noqa: E402
    SHEET_NAME,
    ExcelCampaignSource,
)
from agrosense.ml.stall_model import ARTIFACT_PATH  # noqa: E402
from agrosense.ml.train_stall import (  # noqa: E402
    StallTrainConfig,
    diff_artifacts,
    render_report,
    train_and_evaluate,
)

REPORT_PATH = REPO / "docs" / "ml" / "evaluacion-estancamiento.md"


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip()


def _provenance(data_path: Path, sha: str) -> dict:
    import numpy
    import sklearn

    status = _git("status", "--porcelain")
    return {
        "dataset_file": data_path.name,
        "dataset_sha256": sha,
        "sheet": SHEET_NAME,
        "mapping_version": MAPPING_VERSION,
        "git_commit": _git("rev-parse", "HEAD") or "desconocido",
        "git_dirty": bool(status),
        "python": platform.python_version(),
        "sklearn": sklearn.__version__,
        "numpy": numpy.__version__,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Entrena y evalua el modelo de estancamiento.")
    parser.add_argument("--data", type=Path, required=True, help="Excel de campo (Monitoreo_4)")
    parser.add_argument("--out", type=Path, default=ARTIFACT_PATH)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument(
        "--check", action="store_true", help="reentrena y compara; no escribe nada"
    )
    parser.add_argument(
        "--allow-other-data",
        action="store_true",
        help="acepta un dataset distinto del versionado (su huella queda en el artefacto)",
    )
    args = parser.parse_args(argv)
    config = StallTrainConfig()
    # La consola de Windows (cp1252) no sabe escribir "→" del informe.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    raw = args.data.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != config.expected_dataset_sha256 and not args.allow_other_data:
        print(
            f"El dataset no es la version esperada (sha256 {sha[:12]}..., se esperaba "
            f"{config.expected_dataset_sha256[:12]}...). Use --allow-other-data si es intencional.",
            file=sys.stderr,
        )
        return 2

    campaign = ExcelCampaignSource().read(raw, args.data.name)
    artifact = train_and_evaluate(
        campaign.trees, campaign.observations, config, _provenance(args.data, sha)
    )
    report = render_report(artifact)
    passed = artifact["evaluation"]["gate"]["passed"]

    if args.check:
        if not args.out.exists():
            print(f"No hay artefacto versionado en {args.out}", file=sys.stderr)
            return 1
        committed = json.loads(args.out.read_text(encoding="utf-8"))
        diffs = diff_artifacts(committed, artifact)
        if diffs:
            print(
                "El reentrenamiento NO reproduce el artefacto:\n  " + "\n  ".join(diffs),
                file=sys.stderr,
            )
            return 1
        print(f"Reproducible: {artifact['model_version']} coincide con {args.out.name}.")
        return 0 if passed else 1

    if not passed:
        print(report)
        print("ML eval gate RECHAZADO: no se escribe el artefacto.", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    print(report)
    print(f"Artefacto: {args.out}\nInforme: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Ejecutar el test del script**

Run: `cd backend && python -m pytest tests/ml/test_train_script.py -v`
Expected: PASS.

- [ ] **Step 5: Confirmar el código ANTES de entrenar**

El artefacto registra el commit del código y `git_dirty`; entrenar con el árbol limpio deja la procedencia exacta.

```bash
git add backend/scripts/train_stall_model.py backend/tests/ml/test_train_script.py backend/tests/ml/test_committed_artifact.py
git commit -m "feat(e7): comando unico de entrenamiento y verificacion de reproducibilidad

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git status --porcelain
```
Expected: `git status --porcelain` no imprime nada.

- [ ] **Step 6: Entrenar (el comando documentado)**

Run: `cd backend && python scripts/train_stall_model.py --data data/raw/anexo1.xlsx`
Expected: salida 0, «ML eval gate: APROBADO», n = 618 / 153 y n = 717 / 157, PR-AUC temporal ≥ 0.36 (el prototipo de este plan dio 0.478, IC 0.37–0.57, ROC-AUC 0.738), control permutado global ≤ 0.31 (prototipo ≈ 0.23) y PR-AUC por encima del control dentro de parcela (prototipo ≈ 0.33). Se crean `backend/src/agrosense/ml/artifacts/stall_logreg.json` y `docs/ml/evaluacion-estancamiento.md`.
Si el gate se rechaza: NO bajar umbrales; volver a la Task 3/7 con un test que reproduzca la discrepancia (AGENTS.md: un bug entra al loop en 5).

- [ ] **Step 7: Verificar reproducibilidad y el artefacto**

Run:
```bash
cd backend
python scripts/train_stall_model.py --data data/raw/anexo1.xlsx --check
python -m pytest tests/ml/test_committed_artifact.py -v
```
Expected: «Reproducible: stall-logreg-2026-09-27.1 coincide con stall_logreg.json.» y PASS.

- [ ] **Step 8: Commit del artefacto y del informe**

```bash
git add backend/src/agrosense/ml/artifacts/stall_logreg.json docs/ml/evaluacion-estancamiento.md
git commit -m "feat(e7): artefacto stall-logreg-2026-09-27.1 y metricas del eval gate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## S6 · Persistencia y caso de uso UC-AN4

### Task 9: Tabla `stall_assessments`, migración y repositorio

**Files:**
- Modify: `backend/src/agrosense/adapters/db/models.py` (nueva clase después de `AIReportRow`)
- Create: `backend/alembic/versions/e7c1a3b5d7f9_e7_stall_assessments.py`
- Modify: `backend/src/agrosense/adapters/db/repository.py` (import de `StallAssessmentRow` y nueva clase al final)
- Create: `backend/tests/db/test_stall_assessment_migration.py`
- Create: `backend/tests/db/test_stall_assessment_repository.py`

**Interfaces:**
- Consumes: `Base`, `_utcnow`, `Project`, `MonitoringRow` (models existentes).
- Produces:
  - `StallAssessmentRow` (tabla `stall_assessments`): `id`, `project_id` (FK CASCADE, index), `monitoring_id` (FK CASCADE, `UNIQUE` `uq_stall_assessment_monitoring`), `model_version: str(50)`, `artifact_sha256: str(64)`, `input_hash: str(64)`, `computed_at: datetime tz`, `payload: JSON`
  - `StallAssessmentRepository(session)`: `get(monitoring_id: int) -> StallAssessmentRow | None`; `save(project_id: int, monitoring_id: int, model_version: str, artifact_sha256: str, input_hash: str, payload: dict) -> StallAssessmentRow` (reemplaza)

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/db/test_stall_assessment_migration.py`:

```python
"""La migracion de `stall_assessments` (E7) deriva del modelo de dominio."""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import Base

BACKEND = Path(__file__).parents[2]


@pytest.fixture(scope="module")
def migrated_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.set_main_option("sqlalchemy.url", "sqlite://")
    with engine.connect() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        conn.commit()
    yield engine
    engine.dispose()


def test_migration_creates_stall_assessments(migrated_engine):
    assert "stall_assessments" in set(inspect(migrated_engine).get_table_names())


def test_migrated_columns_match_the_model(migrated_engine):
    en_db = {c["name"] for c in inspect(migrated_engine).get_columns("stall_assessments")}
    en_modelo = {c.name for c in Base.metadata.tables["stall_assessments"].columns}
    assert en_db == en_modelo


def test_one_assessment_per_monitoring(migrated_engine):
    nombres = {
        u["name"] for u in inspect(migrated_engine).get_unique_constraints("stall_assessments")
    }
    assert "uq_stall_assessment_monitoring" in nombres
```

`backend/tests/db/test_stall_assessment_repository.py`:

```python
"""StallAssessmentRepository: un snapshot por monitoreo, que se reemplaza."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agrosense.adapters.db.models import Base, MonitoringRow, Project, StallAssessmentRow
from agrosense.adapters.db.repository import StallAssessmentRepository


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()


@pytest.fixture()
def monitoring(session):
    project = Project(project_code="AGS-2026-1", owner_id="eng-1", name="P1")
    session.add(project)
    session.flush()
    m = MonitoringRow(project_id=project.id, number=3)
    session.add(m)
    session.commit()
    return project.id, m.id


PAYLOAD = {"alert_budget_pct": 20.0, "persistent_min_intervals": 2, "summary": {}, "trees": []}


def test_save_creates_the_row(session, monitoring):
    project_id, monitoring_id = monitoring
    repo = StallAssessmentRepository(session)
    row = repo.save(project_id, monitoring_id, "stall-v1", "a" * 64, "h" * 64, PAYLOAD)
    assert row.id is not None
    stored = repo.get(monitoring_id)
    assert (stored.model_version, stored.artifact_sha256, stored.input_hash) == (
        "stall-v1",
        "a" * 64,
        "h" * 64,
    )
    assert stored.payload == PAYLOAD
    assert stored.computed_at is not None


def test_save_again_replaces_it(session, monitoring):
    project_id, monitoring_id = monitoring
    repo = StallAssessmentRepository(session)
    repo.save(project_id, monitoring_id, "stall-v1", "a" * 64, "h1" * 32, PAYLOAD)
    repo.save(project_id, monitoring_id, "stall-v2", "b" * 64, "h2" * 32, PAYLOAD)
    total = session.scalar(select(func.count()).select_from(StallAssessmentRow))
    assert total == 1
    assert repo.get(monitoring_id).model_version == "stall-v2"


def test_get_without_assessment_is_none(session, monitoring):
    _, monitoring_id = monitoring
    assert StallAssessmentRepository(session).get(monitoring_id) is None
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/db/test_stall_assessment_migration.py tests/db/test_stall_assessment_repository.py -v`
Expected: FAIL con `ImportError: cannot import name 'StallAssessmentRow'`.

- [ ] **Step 3: Implementar el modelo**

En `backend/src/agrosense/adapters/db/models.py`, justo después de la clase `AIReportRow`:

```python
class StallAssessmentRow(Base):
    """Deteccion de estancados de UN monitoreo (E7, UC-AN4).

    Snapshot, como `monitoring_analyses` (ADR-008): la lista de arboles con
    su probabilidad, si entran en el presupuesto de alertas y la regla de
    negocio observada. Procedencia por fila (AGENTS.md, ADR-013): que modelo
    (`model_version` + `artifact_sha256`) y que datos (`input_hash`, solo
    observaciones <= este monitoreo) lo produjeron. Si cambia cualquiera de
    los tres, el caso de uso lo recalcula y REEMPLAZA.
    """

    __tablename__ = "stall_assessments"
    __table_args__ = (
        UniqueConstraint("monitoring_id", name="uq_stall_assessment_monitoring"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    monitoring_id: Mapped[int] = mapped_column(
        ForeignKey("monitorings.id", ondelete="CASCADE"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
```

(Si `ForeignKey` o `DateTime` no están ya importados en `models.py`, añadirlos al import de `sqlalchemy` existente; `AIReportRow` ya los usa, así que deberían estar.)

- [ ] **Step 4: Escribir la migración**

`backend/alembic/versions/e7c1a3b5d7f9_e7_stall_assessments.py`:

```python
"""E7: stall_assessments (deteccion de estancados, UC-AN4)

docs/superpowers/plans/2026-09-27-e7-estancados.md, docs/adr/013-modelo-estancamiento-offline.md.

Un snapshot por monitoreo (UNIQUE(monitoring_id)): recalcular REEMPLAZA,
igual que `monitoring_analyses` (ADR-008).

Revision ID: e7c1a3b5d7f9
Revises: d4b8f2a6c9e1
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e7c1a3b5d7f9'
down_revision: str | None = 'd4b8f2a6c9e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'stall_assessments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('monitoring_id', sa.Integer(), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('artifact_sha256', sa.String(length=64), nullable=False),
        sa.Column('input_hash', sa.String(length=64), nullable=False),
        sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['monitoring_id'], ['monitorings.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('monitoring_id', name='uq_stall_assessment_monitoring'),
    )
    op.create_index('ix_stall_assessments_project_id', 'stall_assessments', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_stall_assessments_project_id', table_name='stall_assessments')
    op.drop_table('stall_assessments')
```

- [ ] **Step 5: Implementar el repositorio**

En `backend/src/agrosense/adapters/db/repository.py`, añadir `StallAssessmentRow` a la lista importada de `agrosense.adapters.db.models`, y al final del archivo:

```python
class StallAssessmentRepository:
    """Persistencia de la deteccion de estancados (E7, UC-AN4).

    Un snapshot por monitoreo: `save` reemplaza el existente. Misma defensa
    que `AIReportRepository.save` ante dos peticiones simultaneas: si la
    segunda choca con `uq_stall_assessment_monitoring`, relee y actualiza.
    """

    def __init__(self, session: Session):
        self._s = session

    def get(self, monitoring_id: int) -> StallAssessmentRow | None:
        return self._s.scalar(
            select(StallAssessmentRow).where(StallAssessmentRow.monitoring_id == monitoring_id)
        )

    @staticmethod
    def _apply(row, project_id, monitoring_id, model_version, artifact_sha256, input_hash, payload):
        row.project_id = project_id
        row.monitoring_id = monitoring_id
        row.model_version = model_version
        row.artifact_sha256 = artifact_sha256
        row.input_hash = input_hash
        row.payload = payload
        row.computed_at = datetime.now(UTC)

    def save(
        self,
        project_id: int,
        monitoring_id: int,
        model_version: str,
        artifact_sha256: str,
        input_hash: str,
        payload: dict,
    ) -> StallAssessmentRow:
        values = (project_id, monitoring_id, model_version, artifact_sha256, input_hash, payload)
        row = self.get(monitoring_id)
        if row is None:
            row = StallAssessmentRow(project_id=project_id, monitoring_id=monitoring_id)
            self._s.add(row)
        self._apply(row, *values)
        try:
            self._s.commit()
        except IntegrityError:
            self._s.rollback()
            row = self.get(monitoring_id)
            if row is None:
                raise
            self._apply(row, *values)
            try:
                self._s.commit()
            except Exception:
                self._s.rollback()
                raise
        return row
```

- [ ] **Step 6: Ejecutar y verificar que pasan**

Run: `cd backend && python -m pytest tests/db/test_stall_assessment_migration.py tests/db/test_stall_assessment_repository.py tests/db/test_ai_report_migration.py -v`
Expected: PASS (la migración de E9 sigue llegando a `head`).

- [ ] **Step 7: Commit**

```bash
git add backend/src/agrosense/adapters/db/models.py backend/src/agrosense/adapters/db/repository.py backend/alembic/versions/e7c1a3b5d7f9_e7_stall_assessments.py backend/tests/db/test_stall_assessment_migration.py backend/tests/db/test_stall_assessment_repository.py
git commit -m "feat(e7): snapshot stall_assessments con procedencia del modelo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 10: Caso de uso UC-AN4

**Files:**
- Modify: `backend/src/agrosense/application/dtos.py` (nueva dataclass al final)
- Create: `backend/src/agrosense/application/use_cases/stall_detection.py`
- Create: `backend/tests/application/test_stall_detection.py`

**Interfaces:**
- Consumes: Task 2 (`ALERT_BUDGET`, `PERSISTENT_STALL_INTERVALS`, `is_persistent_stall`, `select_alerts`, `stall_streak`, `stalled_previous_interval`); `domain.rules.plot_key`; `AppError`; repos con `get_owned`, `get_monitoring`, `load_dataset`; `StallAssessmentRepository` (Task 9) por forma.
- Produces:
  - `StallAssessmentDTO(project_id: int, monitoring: int, model_version: str, artifact_sha256: str, input_hash: str, computed_at: datetime, model_card: dict, alert_budget_pct: float, persistent_min_intervals: int, summary: dict, trees: list[dict])`
  - `class StallScorer(Protocol)`: `model_version: str`, `artifact_sha256: str`, `model_card: dict`, `known_species: frozenset[str]`, `predict(trees, observations, t) -> dict[str, float]`, `fingerprint(trees, observations, t) -> str` (lo cumple `StallModel` de la Task 5)
  - `build_stall_payload(trees, observations, number: int, probabilities: Mapping[str, float], known_species: frozenset[str], budget: float = ALERT_BUDGET) -> dict` — claves `alert_budget_pct`, `persistent_min_intervals`, `summary` (`at_risk, flagged, stalled_last_interval, persistent, without_history, unknown_species`), `trees` (cada uno `tree_id, species, locality, plot, probability, flagged, stalled_last_interval, stall_streak, persistent, known_species`; orden: probabilidad desc, `tree_id` asc)
  - `get_stall_assessment(project_id: int, number: int, owner_id: str, project_repo, analysis_repo, assessment_repo, scorer: StallScorer, *, only_flagged: bool = False) -> StallAssessmentDTO`

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/application/test_stall_detection.py`:

```python
"""UC-AN4: deteccion de estancados, con repos y modelo falsos."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from agrosense.application.errors import AppError
from agrosense.application.use_cases.stall_detection import (
    build_stall_payload,
    get_stall_assessment,
)
from agrosense.domain.stall_rules import is_at_risk
from tests.ml.builders import obs, tree

CARD = {
    "model_version": "stall-test-1",
    "artifact_sha256": "a" * 64,
    "dataset_sha256": "0" * 64,
    "trained_on": "anexo1.xlsx",
    "pr_auc": 0.47,
    "pr_auc_ci_low": 0.36,
    "pr_auc_ci_high": 0.58,
    "roc_auc": 0.73,
    "prevalence_pct": 21.9,
    "recall_at_budget_pct": 45.0,
    "precision_at_budget_pct": 50.0,
}


def _dataset():
    trees = [
        tree("T1", plot="U1"),
        tree("T2", plot="U1"),
        tree("T3", plot="U2"),
        tree("T4", plot="U2"),
        tree("T5", plot="U2", species="Especie rara"),
    ]
    observations = [
        obs("T1", 1, 0.5), obs("T1", 2, 0.5), obs("T1", 3, 0.5),  # persistente
        obs("T2", 1, 0.4), obs("T2", 2, 0.5), obs("T2", 3, 0.5),  # estanco una vez
        obs("T3", 1, 0.4), obs("T3", 2, 0.5), obs("T3", 3, 0.6),  # crece
        obs("T4", 1, 0.4), obs("T4", 2, 0.5), obs("T4", 3, 0.5, alive=False),  # murio
        obs("T5", 3, 0.3),  # entra en M3, sin historia
    ]
    return trees, observations


class _Projects:
    def __init__(self):
        self.monitorings = {n: SimpleNamespace(id=100 + n, number=n) for n in (1, 2, 3)}

    def get_owned(self, project_id, owner_id):
        return SimpleNamespace(id=project_id) if owner_id == "eng-1" else None

    def get_monitoring(self, project_id, number):
        return self.monitorings.get(number)


class _Dataset:
    def __init__(self, trees, observations):
        self.trees, self.observations = trees, observations

    def load_dataset(self, project_id):
        return self.trees, self.observations


class _Assessments:
    def __init__(self):
        self.rows: dict = {}
        self.saves = 0

    def get(self, monitoring_id):
        return self.rows.get(monitoring_id)

    def save(self, project_id, monitoring_id, model_version, artifact_sha256, input_hash, payload):
        self.saves += 1
        row = SimpleNamespace(
            project_id=project_id,
            monitoring_id=monitoring_id,
            model_version=model_version,
            artifact_sha256=artifact_sha256,
            input_hash=input_hash,
            payload=payload,
            computed_at=datetime(2026, 9, 27, tzinfo=UTC),
        )
        self.rows[monitoring_id] = row
        return row


class _Scorer:
    model_version = "stall-test-1"
    artifact_sha256 = "a" * 64
    model_card = CARD
    known_species = frozenset({"Senna viarum"})

    def __init__(self):
        self.calls = 0

    def predict(self, trees, observations, t):
        self.calls += 1
        at_risk = sorted(o.tree_id for o in observations if o.campaign == t and is_at_risk(o))
        return {tid: (i + 1) / (len(at_risk) + 1) for i, tid in enumerate(at_risk)}

    def fingerprint(self, trees, observations, t):
        return f"fp-{t}-{len(observations)}"


def _call(dataset=None, assessments=None, scorer=None, owner="eng-1", number=3, **kw):
    trees, observations = dataset or _dataset()
    return get_stall_assessment(
        7,
        number,
        owner,
        _Projects(),
        _Dataset(trees, observations),
        assessments if assessments is not None else _Assessments(),
        scorer or _Scorer(),
        **kw,
    )


def test_foreign_project_is_not_found():
    with pytest.raises(AppError) as err:
        _call(owner="otro")
    assert err.value.code == "PROJECT_NOT_FOUND"


def test_missing_monitoring_is_not_found():
    with pytest.raises(AppError) as err:
        _call(number=9)
    assert err.value.code == "MONITORING_NOT_FOUND"


def test_payload_applies_the_business_rule():
    trees, observations = _dataset()
    probs = {"T1": 0.9, "T2": 0.4, "T3": 0.2, "T5": 0.3}
    payload = build_stall_payload(trees, observations, 3, probs, frozenset({"Senna viarum"}))
    assert payload["alert_budget_pct"] == 20.0
    assert payload["persistent_min_intervals"] == 2
    assert payload["summary"] == {
        "at_risk": 4,
        "flagged": 1,
        "stalled_last_interval": 2,
        "persistent": 1,
        "without_history": 1,
        "unknown_species": 1,
    }
    rows = {r["tree_id"]: r for r in payload["trees"]}
    assert "T4" not in rows  # muerto en M3: no esta en riesgo
    assert rows["T1"] == {
        "tree_id": "T1",
        "species": "Senna viarum",
        "locality": "Guayabal",
        "plot": "U1",
        "probability": 0.9,
        "flagged": True,
        "stalled_last_interval": True,
        "stall_streak": 2,
        "persistent": True,
        "known_species": True,
    }
    assert rows["T2"]["stall_streak"] == 1 and rows["T2"]["persistent"] is False
    assert rows["T3"]["stalled_last_interval"] is False
    assert rows["T5"]["stalled_last_interval"] is None
    assert rows["T5"]["known_species"] is False
    assert [r["tree_id"] for r in payload["trees"]] == ["T1", "T2", "T5", "T3"]


def test_assessment_returns_provenance_and_model_card():
    dto = _call()
    assert dto.monitoring == 3
    assert dto.model_version == "stall-test-1"
    assert dto.input_hash == "fp-3-13"
    assert dto.model_card == CARD
    assert dto.summary["at_risk"] == 4


def test_snapshot_is_reused_when_nothing_changed():
    assessments, scorer = _Assessments(), _Scorer()
    _call(assessments=assessments, scorer=scorer)
    _call(assessments=assessments, scorer=scorer)
    assert scorer.calls == 1
    assert assessments.saves == 1


def test_a_new_model_recomputes():
    assessments = _Assessments()
    _call(assessments=assessments)
    nuevo = _Scorer()
    nuevo.model_version = "stall-test-2"
    _call(assessments=assessments, scorer=nuevo)
    assert assessments.saves == 2
    assert assessments.rows[103].model_version == "stall-test-2"


def test_changed_data_recomputes():
    assessments = _Assessments()
    trees, observations = _dataset()
    _call(dataset=(trees, observations), assessments=assessments)
    _call(dataset=(trees, observations + [obs("T6", 3, 0.2)]), assessments=assessments)
    assert assessments.saves == 2


def test_only_flagged_filters_trees_but_not_the_summary():
    dto = _call(only_flagged=True)
    assert [t["tree_id"] for t in dto.trees] == ["T5"]  # mayor probabilidad del _Scorer
    assert dto.summary["at_risk"] == 4
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/application/test_stall_detection.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'agrosense.application.use_cases.stall_detection'`.

- [ ] **Step 3: Añadir el DTO**

Al final de `backend/src/agrosense/application/dtos.py`:

```python
@dataclass(frozen=True)
class StallAssessmentDTO:
    """Deteccion de estancados de un monitoreo (E7, UC-AN4).

    `trees` y `summary` salen del snapshot tal cual; `model_card` describe el
    modelo que los produjo (metricas honestas de su evaluacion, ADR-013).
    """

    project_id: int
    monitoring: int
    model_version: str
    artifact_sha256: str
    input_hash: str
    computed_at: datetime
    model_card: dict
    alert_budget_pct: float
    persistent_min_intervals: int
    summary: dict
    trees: list[dict]
```

- [ ] **Step 4: Implementar el caso de uso**

`backend/src/agrosense/application/use_cases/stall_detection.py`:

```python
"""UC-AN4: detectar arboles estancados en un monitoreo (E7).

Para el monitoreo `number` (= instante de prediccion t), cada arbol vivo y
medido en t recibe:
  - `probability`: P(su altura no cambie hasta t+1 | sigue vivo), del modelo
    versionado (ADR-013), calculada por el `scorer` inyectado.
  - `flagged`: entra en el presupuesto de alertas (el 20 % con mayor
    probabilidad, Protocolo §6). Nunca un umbral de 0.5.
  - La regla de negocio OBSERVADA: `stalled_last_interval` (no crecio en
    (t-1, t]; es `estancó_intervalo_previo`), `stall_streak` y `persistent`.

El resultado se guarda como snapshot por monitoreo (`stall_assessments`,
criterio de ADR-008) con la version del modelo, la huella del artefacto y la
huella de los datos; se recalcula solo si cambia alguna de las tres.

El scorer se inyecta por parametro (ADR-003). `StallScorer` solo describe su
forma: application/ no importa ml/ (la flecha va hacia adentro).
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Protocol

from agrosense.application.dtos import StallAssessmentDTO
from agrosense.application.errors import AppError
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.rules import plot_key
from agrosense.domain.stall_rules import (
    ALERT_BUDGET,
    PERSISTENT_STALL_INTERVALS,
    is_persistent_stall,
    select_alerts,
    stall_streak,
    stalled_previous_interval,
)


class StallScorer(Protocol):
    model_version: str
    artifact_sha256: str
    model_card: dict
    known_species: frozenset[str]

    def predict(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> dict[str, float]: ...

    def fingerprint(
        self, trees: Sequence[Tree], observations: Sequence[Observation], t: int
    ) -> str: ...


def _owned_project(project_repo, project_id: int, owner_id: str):
    project = project_repo.get_owned(project_id, owner_id)
    if project is None:
        raise AppError("PROJECT_NOT_FOUND", f"El proyecto {project_id} no existe.")
    return project


def _monitoring(project_repo, project_id: int, number: int):
    monitoring = project_repo.get_monitoring(project_id, number)
    if monitoring is None:
        raise AppError(
            "MONITORING_NOT_FOUND",
            f"El proyecto no tiene el monitoreo M{number}. Cargue su Excel primero.",
        )
    return monitoring


def build_stall_payload(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    number: int,
    probabilities: Mapping[str, float],
    known_species: frozenset[str],
    budget: float = ALERT_BUDGET,
) -> dict:
    """Arma el snapshot: probabilidad del modelo + regla de negocio de dominio."""
    history: dict[str, dict[int, Observation]] = defaultdict(dict)
    for o in observations:
        if o.campaign <= number:
            history[o.tree_id][o.campaign] = o
    flagged = select_alerts(probabilities, budget)

    rows: list[dict] = []
    for tr in trees:
        if tr.tree_id not in probabilities:
            continue
        own = history[tr.tree_id]
        streak = stall_streak(own, number)
        rows.append(
            {
                "tree_id": tr.tree_id,
                "species": tr.species,
                "locality": tr.locality,
                "plot": plot_key(tr),
                "probability": float(probabilities[tr.tree_id]),
                "flagged": tr.tree_id in flagged,
                "stalled_last_interval": stalled_previous_interval(own, number),
                "stall_streak": streak,
                "persistent": is_persistent_stall(streak),
                "known_species": tr.species in known_species,
            }
        )
    rows.sort(key=lambda r: (-r["probability"], r["tree_id"]))

    summary = {
        "at_risk": len(rows),
        "flagged": sum(1 for r in rows if r["flagged"]),
        "stalled_last_interval": sum(1 for r in rows if r["stalled_last_interval"] is True),
        "persistent": sum(1 for r in rows if r["persistent"]),
        "without_history": sum(1 for r in rows if r["stalled_last_interval"] is None),
        "unknown_species": sum(1 for r in rows if not r["known_species"]),
    }
    return {
        "alert_budget_pct": round(budget * 100, 1),
        "persistent_min_intervals": PERSISTENT_STALL_INTERVALS,
        "summary": summary,
        "trees": rows,
    }


def get_stall_assessment(
    project_id: int,
    number: int,
    owner_id: str,
    project_repo,
    analysis_repo,
    assessment_repo,
    scorer: StallScorer,
    *,
    only_flagged: bool = False,
) -> StallAssessmentDTO:
    """UC-AN4. Reutiliza el snapshot si modelo, artefacto y datos no cambiaron.

    Raises:
        AppError("PROJECT_NOT_FOUND" | "MONITORING_NOT_FOUND")
    """
    _owned_project(project_repo, project_id, owner_id)
    monitoring = _monitoring(project_repo, project_id, number)
    trees, observations = analysis_repo.load_dataset(project_id)
    input_hash = scorer.fingerprint(trees, observations, number)

    row = assessment_repo.get(monitoring.id)
    fresh = (
        row is not None
        and row.model_version == scorer.model_version
        and row.artifact_sha256 == scorer.artifact_sha256
        and row.input_hash == input_hash
    )
    if not fresh:
        payload = build_stall_payload(
            trees,
            observations,
            number,
            scorer.predict(trees, observations, number),
            scorer.known_species,
        )
        row = assessment_repo.save(
            project_id,
            monitoring.id,
            scorer.model_version,
            scorer.artifact_sha256,
            input_hash,
            payload,
        )

    payload = row.payload
    rows = [t for t in payload["trees"] if t["flagged"]] if only_flagged else list(payload["trees"])
    return StallAssessmentDTO(
        project_id=project_id,
        monitoring=number,
        model_version=row.model_version,
        artifact_sha256=row.artifact_sha256,
        input_hash=row.input_hash,
        computed_at=row.computed_at,
        model_card=dict(scorer.model_card),
        alert_budget_pct=float(payload["alert_budget_pct"]),
        persistent_min_intervals=int(payload["persistent_min_intervals"]),
        summary=dict(payload["summary"]),
        trees=rows,
    )
```

- [ ] **Step 5: Ejecutar y verificar que pasan**

Run: `cd backend && python -m pytest tests/application/test_stall_detection.py tests/architecture -v`
Expected: PASS (application sigue sin importar `ml/`).

- [ ] **Step 6: Commit**

```bash
git add backend/src/agrosense/application/dtos.py backend/src/agrosense/application/use_cases/stall_detection.py backend/tests/application/test_stall_detection.py
git commit -m "feat(e7): caso de uso UC-AN4 con snapshot y regla de negocio

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## S7 · API

### Task 11: Contrato del endpoint

**Files:**
- Modify: `backend/src/agrosense/adapters/api/schemas.py` (nuevas clases al final)
- Modify: `backend/src/agrosense/adapters/api/errors.py` (`_CODE_HTTP`)
- Create: `backend/tests/api/test_stall_contract.py`

**Interfaces:**
- Consumes: nada de tareas previas (contrato primero).
- Produces (fuente de verdad del contrato):

```
GET /projects/{project_id}/monitorings/{number}/stall-assessment?only_flagged=<bool, por defecto false>
  auth:        Bearer (Supabase). Sin sesión -> 401.
  path:        project_id: int; number: int, 1..1000 (fuera de rango -> 422).
  query:       only_flagged: bool. true = solo los árboles del presupuesto de alertas.
  200:         StallAssessmentResponse. `trees` ordenado por probability desc, tree_id asc
               (orden fijo, sin parámetro de orden). Sin paginación: ≤ ~1 000 árboles por
               monitoreo, mismo criterio que el análisis (ADR-008). `summary` siempre es el
               del monitoreo completo, aunque only_flagged=true.
  404:         PROJECT_NOT_FOUND (también si es de otro ingeniero) | MONITORING_NOT_FOUND
  503:         STALL_MODEL_UNAVAILABLE (artefacto ausente, corrupto o de otra versión)
  errores:     {"detail": {"code", "message"}}; nunca trazas.
```

- `StallTreeResponse`, `StallSummaryResponse`, `StallModelCardResponse`, `StallAssessmentResponse` (campos abajo); `_CODE_HTTP["STALL_MODEL_UNAVAILABLE"] = 503`.

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/api/test_stall_contract.py`:

```python
"""Contrato de la deteccion de estancados (E7): forma y validaciones."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agrosense.adapters.api.errors import _CODE_HTTP
from agrosense.adapters.api.schemas import (
    StallAssessmentResponse,
    StallModelCardResponse,
    StallSummaryResponse,
    StallTreeResponse,
)

TREE = {
    "tree_id": "FR_1_31",
    "species": "Lafoensia speciosa",
    "locality": "Tres Jotas",
    "plot": "GEB/MED-LV/NV/FR/1",
    "probability": 0.62,
    "flagged": True,
    "stalled_last_interval": None,
    "stall_streak": 0,
    "persistent": False,
    "known_species": True,
}
CARD = {
    "model_version": "stall-logreg-2026-09-27.1",
    "artifact_sha256": "a" * 64,
    "dataset_sha256": "0" * 64,
    "trained_on": "anexo1.xlsx",
    "pr_auc": 0.478,
    "pr_auc_ci_low": 0.37,
    "pr_auc_ci_high": 0.58,
    "roc_auc": 0.738,
    "prevalence_pct": 21.9,
    "recall_at_budget_pct": 43.3,
    "precision_at_budget_pct": 47.6,
}
SUMMARY = {
    "at_risk": 718,
    "flagged": 143,
    "stalled_last_interval": 157,
    "persistent": 24,
    "without_history": 0,
    "unknown_species": 0,
}


def test_tree_shape():
    t = StallTreeResponse(**TREE)
    assert t.stalled_last_interval is None
    assert t.flagged is True


def test_probability_is_a_probability():
    with pytest.raises(ValidationError):
        StallTreeResponse(**{**TREE, "probability": 1.2})


def test_streak_is_never_negative():
    with pytest.raises(ValidationError):
        StallTreeResponse(**{**TREE, "stall_streak": -1})


def test_full_response_shape():
    r = StallAssessmentResponse(
        project_id=7,
        monitoring=4,
        input_hash="h" * 64,
        computed_at="2026-09-27T10:00:00Z",
        alert_budget_pct=20.0,
        persistent_min_intervals=2,
        model=StallModelCardResponse(**CARD),
        summary=StallSummaryResponse(**SUMMARY),
        trees=[StallTreeResponse(**TREE)],
    )
    assert r.model.pr_auc_ci_low == 0.37
    assert r.summary.flagged == 143


def test_model_unavailable_is_a_503():
    assert _CODE_HTTP["STALL_MODEL_UNAVAILABLE"] == 503
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/api/test_stall_contract.py -v`
Expected: FAIL con `ImportError: cannot import name 'StallAssessmentResponse'`.

- [ ] **Step 3: Implementar el contrato**

Al final de `backend/src/agrosense/adapters/api/schemas.py` (el módulo ya importa `BaseModel`, `Field` y `datetime`; si falta alguno, añadirlo al import existente):

```python
# ── E7: deteccion de estancados (UC-AN4) ─────────────────────────────────────


class StallTreeResponse(BaseModel):
    """Un arbol vivo y medido en el monitoreo, con su riesgo de estancarse."""

    tree_id: str
    species: str
    locality: str | None
    plot: str | None
    probability: float = Field(
        ge=0.0, le=1.0, description="P(la altura no cambie hasta el proximo monitoreo | sigue vivo)."
    )
    flagged: bool = Field(description="Entra en el presupuesto de alertas para revision en campo.")
    stalled_last_interval: bool | None = Field(
        description="No crecio desde el monitoreo anterior (estancó_intervalo_previo). "
        "null = sin historia medida."
    )
    stall_streak: int = Field(ge=0, description="Intervalos seguidos sin crecer hasta este monitoreo.")
    persistent: bool
    known_species: bool = Field(description="La especie estaba en los datos de entrenamiento.")


class StallSummaryResponse(BaseModel):
    at_risk: int = Field(ge=0)
    flagged: int = Field(ge=0)
    stalled_last_interval: int = Field(ge=0)
    persistent: int = Field(ge=0)
    without_history: int = Field(ge=0)
    unknown_species: int = Field(ge=0)


class StallModelCardResponse(BaseModel):
    """Que modelo produjo el resultado y cuanto vale, segun su evaluacion honesta."""

    model_config = {"protected_namespaces": ()}

    model_version: str
    artifact_sha256: str
    dataset_sha256: str
    trained_on: str
    pr_auc: float
    pr_auc_ci_low: float
    pr_auc_ci_high: float
    roc_auc: float
    prevalence_pct: float
    recall_at_budget_pct: float
    precision_at_budget_pct: float


class StallAssessmentResponse(BaseModel):
    """Deteccion de estancados de un monitoreo (E7, UC-AN4)."""

    model_config = {"protected_namespaces": ()}

    project_id: int
    monitoring: int
    input_hash: str
    computed_at: datetime
    alert_budget_pct: float = Field(description="Porcentaje de arboles marcados (escala 0-100).")
    persistent_min_intervals: int
    model: StallModelCardResponse
    summary: StallSummaryResponse
    trees: list[StallTreeResponse]
```

En `backend/src/agrosense/adapters/api/errors.py`, dentro de `_CODE_HTTP`, después de `"LLM_UNAVAILABLE": 503,`:

```python
    # El artefacto del modelo de estancamiento falta o es de otra version
    # (ADR-013): no es un fallo del cliente; reintentar tras el despliegue sirve.
    "STALL_MODEL_UNAVAILABLE": 503,
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `cd backend && python -m pytest tests/api/test_stall_contract.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/adapters/api/schemas.py backend/src/agrosense/adapters/api/errors.py backend/tests/api/test_stall_contract.py
git commit -m "feat(e7): contrato del endpoint de deteccion de estancados

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 12: Endpoint y tests de integración

**Files:**
- Create: `backend/src/agrosense/adapters/api/routes/stall.py`
- Modify: `backend/src/agrosense/adapters/api/app.py` (registrar el router después del de `ai_reports`)
- Create: `backend/tests/api/test_stall_api.py`

**Interfaces:**
- Consumes: Task 5 (`load_stall_model`, `StallModel`, `StallModelError`), Task 9 (`StallAssessmentRepository`), Task 10 (`get_stall_assessment`, `StallAssessmentDTO`), Task 11 (schemas); `ProjectRepository`, `ProjectAnalysisRepository`, `CurrentEngineer`, `get_session`, `raise_for_value_error`.
- Produces: `router`; `_scorer()` (punto de sustitución en tests); `get_stall_assessment_endpoint`.

- [ ] **Step 1: Escribir los tests que fallan**

`backend/tests/api/test_stall_api.py`:

```python
"""Deteccion de estancados por la API (E7), de punta a punta sobre SQLite."""
from __future__ import annotations

import io

import pytest
from openpyxl import Workbook

from agrosense.adapters.api.routes import stall as rutas
from agrosense.application.errors import AppError
from agrosense.domain.stall_rules import is_at_risk
from tests.auth.keys import ENGINEER_B, bearer

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
X0, Y0 = 4735700.0, 2199400.0
HEADERS = [
    "LOCALIDAD", "Codigo de unidad muestreo", "ID Parcela", "Diseño floristico",
    "Cobertura vegetal asociada", "ID_MUEST", "Especie_M1", "Familia", "Coord_X", "Coord_Y",
    "Altura total (m)_M1", "Diámetro. Copa (m)_M1", "Sobrevivencia M1", "Estado Fitosanitario_M1",
    "Altura total (m)_M2", "Diámetro. Copa (m)_M2", "Sobrevivencia M2", "Estado Fitosanitario_M2",
]
CARD = {
    "model_version": "stall-fake-1",
    "artifact_sha256": "f" * 64,
    "dataset_sha256": "0" * 64,
    "trained_on": "anexo1.xlsx",
    "pr_auc": 0.47,
    "pr_auc_ci_low": 0.36,
    "pr_auc_ci_high": 0.58,
    "roc_auc": 0.73,
    "prevalence_pct": 21.9,
    "recall_at_budget_pct": 45.0,
    "precision_at_budget_pct": 50.0,
}


class _FakeScorer:
    model_version = "stall-fake-1"
    artifact_sha256 = "f" * 64
    model_card = CARD
    known_species = frozenset({"Senna viarum"})

    def __init__(self):
        self.calls = 0

    def predict(self, trees, observations, t):
        self.calls += 1
        ids = sorted(o.tree_id for o in observations if o.campaign == t and is_at_risk(o))
        return {tid: (i + 1) / (len(ids) + 1) for i, tid in enumerate(ids)}

    def fingerprint(self, trees, observations, t):
        return "h" * 64


@pytest.fixture()
def scorer(monkeypatch):
    fake = _FakeScorer()
    monkeypatch.setattr(rutas, "_scorer", lambda: fake)
    return fake


def _excel(n=6) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Monitoreo_2"
    ws.append(HEADERS)
    for i in range(n):
        ws.append([
            "Guayabal", f"U{i // 2}", 1, "Rehabilitación vegetal", "Bosque de galería",
            f"G_{i}", "Senna viarum", "Fabaceae", X0 + 30 * i, Y0 + 30 * (i % 2),
            0.5, 0.3, "Vivo", "Bueno",
            0.5 if i % 2 == 0 else 0.6, 0.3, "Vivo", "Bueno",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def proyecto(client):
    pid = client.post("/projects", json={"name": "Estancados API"}).json()["id"]
    r = client.post(f"/projects/{pid}/campaigns", files={"file": ("m.xlsx", _excel(), XLSX)})
    assert r.status_code == 201, r.text
    return pid


def _url(pid, n=2):
    return f"/projects/{pid}/monitorings/{n}/stall-assessment"


def test_requires_a_session(anon_client):
    assert anon_client.get(_url(1)).status_code == 401


def test_foreign_project_is_not_found(client, proyecto, scorer):
    r = client.get(_url(proyecto), headers=bearer(ENGINEER_B))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_unknown_monitoring_is_not_found(client, proyecto, scorer):
    r = client.get(_url(proyecto, 9))
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "MONITORING_NOT_FOUND"


def test_monitoring_number_is_validated(client, proyecto, scorer):
    assert client.get(_url(proyecto, 0)).status_code == 422


def test_returns_the_assessment(client, proyecto, scorer):
    r = client.get(_url(proyecto))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["monitoring"] == 2
    assert body["alert_budget_pct"] == 20.0
    assert body["model"]["model_version"] == "stall-fake-1"
    assert body["summary"] == {
        "at_risk": 6,
        "flagged": 1,
        "stalled_last_interval": 3,
        "persistent": 0,
        "without_history": 0,
        "unknown_species": 0,
    }
    probs = [t["probability"] for t in body["trees"]]
    assert probs == sorted(probs, reverse=True)
    assert body["trees"][0]["flagged"] is True


def test_second_read_reuses_the_snapshot(client, proyecto, scorer):
    client.get(_url(proyecto))
    client.get(_url(proyecto))
    assert scorer.calls == 1


def test_only_flagged(client, proyecto, scorer):
    body = client.get(_url(proyecto), params={"only_flagged": "true"}).json()
    assert [t["flagged"] for t in body["trees"]] == [True]
    assert body["summary"]["at_risk"] == 6


def test_model_unavailable_is_a_clean_503(client, proyecto, monkeypatch):
    def _roto():
        raise AppError("STALL_MODEL_UNAVAILABLE", "El modelo no está disponible.")

    monkeypatch.setattr(rutas, "_scorer", _roto)
    r = client.get(_url(proyecto))
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "STALL_MODEL_UNAVAILABLE"


def test_serves_the_committed_model(client, proyecto):
    # Sin sustituir el scorer: el artefacto versionado de la Task 8.
    r = client.get(_url(proyecto))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model"]["model_version"].startswith("stall-logreg-")
    assert all(0.0 < t["probability"] < 1.0 for t in body["trees"])
```

- [ ] **Step 2: Ejecutar y verificar que fallan**

Run: `cd backend && python -m pytest tests/api/test_stall_api.py -v`
Expected: FAIL con `ImportError: cannot import name 'stall'`.

- [ ] **Step 3: Implementar la ruta**

`backend/src/agrosense/adapters/api/routes/stall.py`:

```python
"""Endpoint de deteccion de estancados de un monitoreo (E7, UC-AN4).

Regla ADR-003: parsear -> caso de uso -> mapear respuesta. Cero logica de
negocio aqui. Contrato: docs/superpowers/plans/2026-09-27-e7-estancados.md,
Task 11.

    GET /projects/{project_id}/monitorings/{number}/stall-assessment?only_flagged=
        -> 200 StallAssessmentResponse
        -> 404 PROJECT_NOT_FOUND | MONITORING_NOT_FOUND
        -> 503 STALL_MODEL_UNAVAILABLE

`def` y no `async def` (leccion de v1): el caso de uso consulta la base y
puntua en CPU; FastAPI lo manda al threadpool. Puntuar ~800 arboles es
barato, no hace falta cola (ADR-013 §7).

El modelo se carga UNA vez por proceso (`lru_cache`); un artefacto nuevo
exige reiniciar el servidor. Si la carga falla no se cachea: el siguiente
intento vuelve a leer el archivo.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import CurrentEngineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import (
    StallAssessmentResponse,
    StallModelCardResponse,
    StallSummaryResponse,
    StallTreeResponse,
)
from agrosense.adapters.db.repository import (
    ProjectAnalysisRepository,
    ProjectRepository,
    StallAssessmentRepository,
)
from agrosense.application.dtos import StallAssessmentDTO
from agrosense.application.errors import AppError
from agrosense.application.use_cases.stall_detection import get_stall_assessment
from agrosense.ml.stall_model import StallModel, StallModelError, load_stall_model

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]
NumberPath = Annotated[int, Path(ge=1, le=1000, description="Numero de monitoreo (M1 = 1).")]


@lru_cache(maxsize=1)
def _cached_model() -> StallModel:
    return load_stall_model()


def _scorer() -> StallModel:
    try:
        return _cached_model()
    except StallModelError as exc:
        logger.warning("Modelo de estancamiento no disponible", exc_info=exc)
        raise AppError(
            "STALL_MODEL_UNAVAILABLE",
            "El modelo de detección de estancados no está disponible en este servidor.",
        ) from exc


def _to_response(dto: StallAssessmentDTO) -> StallAssessmentResponse:
    return StallAssessmentResponse(
        project_id=dto.project_id,
        monitoring=dto.monitoring,
        input_hash=dto.input_hash,
        computed_at=dto.computed_at,
        alert_budget_pct=dto.alert_budget_pct,
        persistent_min_intervals=dto.persistent_min_intervals,
        model=StallModelCardResponse(**dto.model_card),
        summary=StallSummaryResponse(**dto.summary),
        trees=[StallTreeResponse(**t) for t in dto.trees],
    )


@router.get(
    "/projects/{project_id}/monitorings/{number}/stall-assessment",
    response_model=StallAssessmentResponse,
)
def get_stall_assessment_endpoint(
    project_id: int,
    number: NumberPath,
    session: SessionDep,
    engineer: CurrentEngineer,
    only_flagged: Annotated[
        bool, Query(description="Solo los arboles del presupuesto de alertas.")
    ] = False,
) -> StallAssessmentResponse:
    try:
        dto = get_stall_assessment(
            project_id,
            number,
            engineer.id,
            ProjectRepository(session),
            ProjectAnalysisRepository(session),
            StallAssessmentRepository(session),
            _scorer(),
            only_flagged=only_flagged,
        )
    except ValueError as exc:
        raise_for_value_error(exc)
    return _to_response(dto)
```

En `backend/src/agrosense/adapters/api/app.py`, después del bloque que registra `ai_reports_router`, añadir con el mismo estilo:

```python
    from agrosense.adapters.api.routes.stall import router as stall_router

    app.include_router(stall_router)
```

- [ ] **Step 4: Ejecutar y verificar que pasan**

Run: `cd backend && python -m pytest tests/api/test_stall_api.py tests/api/test_stall_contract.py tests/architecture -v`
Expected: PASS (`adapters/api` no importa pandas: `ml.stall_model` es Python puro).

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/adapters/api/routes/stall.py backend/src/agrosense/adapters/api/app.py backend/tests/api/test_stall_api.py
git commit -m "feat(e7): endpoint GET stall-assessment (UC-AN4)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## S8 · UI

### Task 13: Capa de acceso a datos del frontend

**Files:**
- Modify: `frontend/src/api/types.ts` (añadir al final)
- Create: `frontend/src/api/stall.ts`
- Create: `frontend/src/api/stall.test.ts`

**Interfaces:**
- Consumes: contrato de la Task 11; `request` de `frontend/src/api/http.ts`.
- Produces: tipos `StallTree`, `StallSummary`, `StallModelCard`, `StallAssessment`; `getStallAssessment(projectId: number, number: number, onlyFlagged: boolean, signal?: AbortSignal): Promise<StallAssessment>`.

- [ ] **Step 1: Escribir el test que falla**

`frontend/src/api/stall.test.ts`:

```ts
/** Capa de acceso a la detección de estancados (E7). Mockea `fetch` global. */
import { afterEach, describe, expect, it, vi } from "vitest";

import { getStallAssessment } from "./stall";

function mockFetch(body: unknown, status = 200) {
  const spy = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getStallAssessment", () => {
  it("pide solo los marcados", async () => {
    const spy = mockFetch({ trees: [] });
    await getStallAssessment(7, 4, true);
    expect(spy.mock.calls[0][0]).toBe("/projects/7/monitorings/4/stall-assessment?only_flagged=true");
  });

  it("sin filtro no manda el parámetro", async () => {
    const spy = mockFetch({ trees: [] });
    await getStallAssessment(7, 4, false);
    expect(spy.mock.calls[0][0]).toBe("/projects/7/monitorings/4/stall-assessment");
  });

  it("propaga el código del contrato", async () => {
    mockFetch({ detail: { code: "STALL_MODEL_UNAVAILABLE", message: "No disponible." } }, 503);
    await expect(getStallAssessment(7, 4, true)).rejects.toMatchObject({
      code: "STALL_MODEL_UNAVAILABLE",
    });
  });
});
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd frontend && npx vitest run src/api/stall.test.ts`
Expected: FAIL («Failed to resolve import "./stall"»).

- [ ] **Step 3: Implementar**

Al final de `frontend/src/api/types.ts`:

```ts
/** E7 · Detección de estancados (UC-AN4). Espejo de `StallAssessmentResponse`. */
export interface StallTree {
  tree_id: string;
  species: string;
  locality: string | null;
  plot: string | null;
  /** Probabilidad 0–1 de que la altura no cambie hasta el próximo monitoreo. */
  probability: number;
  flagged: boolean;
  /** null = el árbol no tiene medición en el monitoreo anterior. */
  stalled_last_interval: boolean | null;
  stall_streak: number;
  persistent: boolean;
  known_species: boolean;
}

export interface StallSummary {
  at_risk: number;
  flagged: number;
  stalled_last_interval: number;
  persistent: number;
  without_history: number;
  unknown_species: number;
}

export interface StallModelCard {
  model_version: string;
  artifact_sha256: string;
  dataset_sha256: string;
  trained_on: string;
  pr_auc: number;
  pr_auc_ci_low: number;
  pr_auc_ci_high: number;
  roc_auc: number;
  prevalence_pct: number;
  recall_at_budget_pct: number;
  precision_at_budget_pct: number;
}

export interface StallAssessment {
  project_id: number;
  monitoring: number;
  input_hash: string;
  computed_at: string;
  alert_budget_pct: number;
  persistent_min_intervals: number;
  model: StallModelCard;
  summary: StallSummary;
  trees: StallTree[];
}
```

`frontend/src/api/stall.ts`:

```ts
/** Acceso a la detección de estancados de un monitoreo (E7, UC-AN4). */
import { request } from "./http";
import type { StallAssessment } from "./types";

export function getStallAssessment(
  projectId: number,
  number: number,
  onlyFlagged: boolean,
  signal?: AbortSignal,
): Promise<StallAssessment> {
  return request<StallAssessment>(`/projects/${projectId}/monitorings/${number}/stall-assessment`, {
    query: { only_flagged: onlyFlagged ? "true" : undefined },
    signal,
  });
}
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd frontend && npx vitest run src/api/stall.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/stall.ts frontend/src/api/stall.test.ts
git commit -m "feat(e7): acceso a datos de la deteccion de estancados

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task 14: Panel «Árboles en riesgo de estancarse» y journey E2E

**Files:**
- Create: `frontend/src/components/StallPanel.tsx`
- Create: `frontend/src/components/StallPanel.test.tsx`
- Modify: `frontend/src/pages/MonitoringAnalysisPage.tsx` (import + panel después de `<AIReportPanel … />`)
- Modify: `frontend/src/pages/E2E3Flow.test.tsx` (constante `STALL`, rama en `mockApi`, nuevo `it`)

**Interfaces:**
- Consumes: Task 13 (`getStallAssessment`, `StallAssessment`); `useAsync`.
- Produces: `StallPanel({ projectId, number }: { projectId: number; number: number })`.

- [ ] **Step 1: Escribir el test del componente que falla**

`frontend/src/components/StallPanel.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { StallAssessment } from "../api/types";
import { StallPanel } from "./StallPanel";

vi.mock("../api/stall", () => ({ getStallAssessment: vi.fn() }));

import { getStallAssessment } from "../api/stall";

const mocked = vi.mocked(getStallAssessment);

const BASE: StallAssessment = {
  project_id: 7,
  monitoring: 4,
  input_hash: "abcdef0123456789".repeat(4),
  computed_at: "2026-09-27T10:00:00Z",
  alert_budget_pct: 20,
  persistent_min_intervals: 2,
  model: {
    model_version: "stall-logreg-2026-09-27.1",
    artifact_sha256: "a".repeat(64),
    dataset_sha256: "0".repeat(64),
    trained_on: "anexo1.xlsx",
    pr_auc: 0.478,
    pr_auc_ci_low: 0.37,
    pr_auc_ci_high: 0.58,
    roc_auc: 0.738,
    prevalence_pct: 21.9,
    recall_at_budget_pct: 43.3,
    precision_at_budget_pct: 47.6,
  },
  summary: {
    at_risk: 718,
    flagged: 143,
    stalled_last_interval: 157,
    persistent: 24,
    without_history: 0,
    unknown_species: 0,
  },
  trees: [
    {
      tree_id: "FR_9_99",
      species: "Lafoensia speciosa",
      locality: "San Antonio",
      plot: "GEB/SA/1",
      probability: 0.62,
      flagged: true,
      stalled_last_interval: true,
      stall_streak: 2,
      persistent: true,
      known_species: true,
    },
  ],
};

describe("StallPanel", () => {
  it("muestra el resumen, la lectura honesta del modelo y los árboles marcados", async () => {
    mocked.mockResolvedValue(BASE);
    render(<StallPanel projectId={7} number={4} />);
    expect(await screen.findByText("FR_9_99")).toBeInTheDocument();
    expect(screen.getByText(/143 de 718 árboles vivos/)).toBeInTheDocument();
    expect(screen.getByText(/sugestiva, no concluyente/)).toBeInTheDocument();
    expect(screen.getByText("62 %")).toBeInTheDocument();
    expect(screen.getByText(/2 intervalos seguidos/)).toBeInTheDocument();
    expect(mocked).toHaveBeenLastCalledWith(7, 4, true, expect.anything());
  });

  it("«Ver todos» pide la lista completa", async () => {
    mocked.mockResolvedValue(BASE);
    render(<StallPanel projectId={7} number={4} />);
    await screen.findByText("FR_9_99");
    await userEvent.click(screen.getByLabelText("Ver todos los árboles vivos"));
    await waitFor(() => expect(mocked).toHaveBeenLastCalledWith(7, 4, false, expect.anything()));
  });

  it("avisa de las especies que el modelo no vio", async () => {
    mocked.mockResolvedValue({ ...BASE, summary: { ...BASE.summary, unknown_species: 5 } });
    render(<StallPanel projectId={7} number={4} />);
    expect(await screen.findByText(/5 árboles son de especies que el modelo no vio/))
      .toBeInTheDocument();
  });

  it("muestra el error del backend", async () => {
    mocked.mockRejectedValue(new Error("El modelo de detección de estancados no está disponible."));
    render(<StallPanel projectId={7} number={4} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/no está disponible/);
  });
});
```

- [ ] **Step 2: Ejecutar y verificar que falla**

Run: `cd frontend && npx vitest run src/components/StallPanel.test.tsx`
Expected: FAIL («Failed to resolve import "./StallPanel"»).

- [ ] **Step 3: Implementar el componente**

`frontend/src/components/StallPanel.tsx`:

```tsx
/**
 * Árboles en riesgo de estancarse (E7, UC-AN4). Solo presenta lo que calculó
 * el backend: la probabilidad, quién entra en el presupuesto de alertas y la
 * regla observada vienen hechas (AGENTS.md: sin reglas de negocio aquí).
 */
import { useState } from "react";

import { getStallAssessment } from "../api/stall";
import type { StallTree } from "../api/types";
import { useAsync } from "../hooks/useAsync";

const nf = (value: number, digits: number) =>
  value.toLocaleString("es-CO", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const pct = (probability: number) => `${nf(probability * 100, 0)} %`;

function intervaloAnterior(t: StallTree): string {
  if (t.stalled_last_interval === null) return "Sin historia";
  return t.stalled_last_interval ? "No creció" : "Creció";
}

export function StallPanel({ projectId, number }: { projectId: number; number: number }) {
  const [verTodos, setVerTodos] = useState(false);
  const estado = useAsync(
    (signal) => getStallAssessment(projectId, number, !verTodos, signal),
    [projectId, number, verTodos],
  );
  const a = estado.data;

  return (
    <section className="card">
      <h2>Árboles en riesgo de estancarse</h2>
      <p className="muted">
        Probabilidad de que la altura no cambie hasta el próximo monitoreo, si el árbol sigue
        vivo. Se marcan para revisión en campo los árboles con mayor probabilidad, hasta el
        presupuesto de alertas.
      </p>

      {estado.loading && !a && <p className="muted">Calculando…</p>}
      {estado.error && (
        <p className="form-error" role="alert">
          {estado.error.message}
        </p>
      )}

      {a && (
        <>
          <p>
            {a.summary.flagged} de {a.summary.at_risk} árboles vivos marcados para revisión (
            {nf(a.alert_budget_pct, 0)} %). {a.summary.stalled_last_interval} no crecieron desde
            el monitoreo anterior y {a.summary.persistent} llevan{" "}
            {a.persistent_min_intervals} intervalos seguidos o más sin crecer.
          </p>
          <p className="warn">
            Señal sugestiva, no concluyente: PR-AUC {nf(a.model.pr_auc, 2)} (IC 95 %{" "}
            {nf(a.model.pr_auc_ci_low, 2)}–{nf(a.model.pr_auc_ci_high, 2)}) frente a una
            prevalencia de {nf(a.model.prevalence_pct, 1)} %. Con este presupuesto el modelo
            recuperó el {nf(a.model.recall_at_budget_pct, 0)} % de los estancados con una
            precisión del {nf(a.model.precision_at_budget_pct, 0)} % en su evaluación.
          </p>
          {a.summary.unknown_species > 0 && (
            <p className="warn">
              {a.summary.unknown_species} árboles son de especies que el modelo no vio al
              entrenar: su probabilidad se apoya solo en las demás variables.
            </p>
          )}
          {a.summary.without_history > 0 && (
            <p className="muted">
              {a.summary.without_history} árboles no tienen medición en el monitoreo anterior.
            </p>
          )}

          <label className="checkbox">
            <input
              type="checkbox"
              checked={verTodos}
              onChange={(e) => setVerTodos(e.target.checked)}
            />{" "}
            Ver todos los árboles vivos
          </label>

          <figure className="data-table">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Árbol</th>
                    <th>Especie</th>
                    <th>Predio</th>
                    <th>Parcela</th>
                    <th>Probabilidad</th>
                    <th>Intervalo anterior</th>
                    <th>Intervalos sin crecer</th>
                    <th>Revisar</th>
                  </tr>
                </thead>
                <tbody>
                  {a.trees.map((t) => (
                    <tr key={t.tree_id}>
                      <td>{t.tree_id}</td>
                      <td>
                        {t.species}
                        {!t.known_species && " *"}
                      </td>
                      <td>{t.locality ?? "—"}</td>
                      <td>{t.plot ?? "—"}</td>
                      <td>{pct(t.probability)}</td>
                      <td>{intervaloAnterior(t)}</td>
                      <td>{t.stall_streak}</td>
                      <td>{t.flagged ? "Sí" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </figure>

          <p className="muted provenance">
            Modelo {a.model.model_version} · datos {a.input_hash.slice(0, 12)} · calculado{" "}
            {new Date(a.computed_at).toLocaleString("es-CO")}
          </p>
        </>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Ejecutar y verificar que pasa**

Run: `cd frontend && npx vitest run src/components/StallPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Montar el panel en la página**

En `frontend/src/pages/MonitoringAnalysisPage.tsx`, añadir el import junto a los demás componentes:

```tsx
import { StallPanel } from "../components/StallPanel";
```

y justo después de `<AIReportPanel key={`${projectId}-${number}`} projectId={projectId} number={number} />`:

```tsx
      {/* key: un panel nuevo por monitoreo, como el del borrador de IA. */}
      <StallPanel key={`stall-${projectId}-${number}`} projectId={projectId} number={number} />
```

- [ ] **Step 6: Escribir el journey E2E que falla**

En `frontend/src/pages/E2E3Flow.test.tsx`:

1. Añadir `StallAssessment` al import de tipos: `import type { MonitoringAnalysis, StallAssessment } from "../api/types";`
2. Después de la constante `ANALISIS`, añadir:

```tsx
// E7: especie, predio y porcentajes elegidos para no chocar con los textos
// que los tests de E3 buscan con getByText.
const STALL: StallAssessment = {
  project_id: 7, monitoring: 4, input_hash: "fedcba9876543210".repeat(4),
  computed_at: "2026-09-27T10:00:00Z", alert_budget_pct: 20, persistent_min_intervals: 2,
  model: {
    model_version: "stall-logreg-2026-09-27.1", artifact_sha256: "a".repeat(64),
    dataset_sha256: "0".repeat(64), trained_on: "anexo1.xlsx", pr_auc: 0.478,
    pr_auc_ci_low: 0.37, pr_auc_ci_high: 0.58, roc_auc: 0.738, prevalence_pct: 21.9,
    recall_at_budget_pct: 43.3, precision_at_budget_pct: 47.6,
  },
  summary: {
    at_risk: 718, flagged: 143, stalled_last_interval: 157, persistent: 24,
    without_history: 0, unknown_species: 0,
  },
  trees: [
    {
      tree_id: "FR_9_99", species: "Lafoensia speciosa", locality: "San Antonio",
      plot: "GEB/SA/1", probability: 0.62, flagged: true, stalled_last_interval: true,
      stall_streak: 2, persistent: true, known_species: true,
    },
  ],
};
```

3. En `mockApi`, antes de `return json(404, …)`:

```tsx
    if (url.startsWith("/projects/7/monitorings/4/stall-assessment")) return json(200, STALL);
```

4. Al final del `describe("E2/E3 en la interfaz", …)`, añadir:

```tsx
  it("E7: el análisis muestra los árboles en riesgo de estancarse y permite ver todos", async () => {
    const calls = mockApi();
    renderAt("/proyectos/7/monitoreos/4");

    expect(await screen.findByRole("heading", { name: "Árboles en riesgo de estancarse" }))
      .toBeInTheDocument();
    expect(await screen.findByText("FR_9_99")).toBeInTheDocument();
    expect(screen.getByText(/143 de 718 árboles vivos/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.endsWith("/stall-assessment?only_flagged=true"))).toBe(true);

    await userEvent.click(screen.getByLabelText("Ver todos los árboles vivos"));
    await waitFor(() =>
      expect(calls.some((c) => c.url === "/projects/7/monitorings/4/stall-assessment")).toBe(true),
    );
  });
```

- [ ] **Step 7: Ejecutar el journey y los tests de la página**

Run: `cd frontend && npx vitest run src/pages/E2E3Flow.test.tsx src/components/StallPanel.test.tsx`
Expected: PASS (los tests previos de E3 siguen en verde: el mock de estancados usa textos que no chocan).

- [ ] **Step 8: Tipos y lint del frontend**

Run: `cd frontend && npx tsc -b && npm run lint`
Expected: 0 errores.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/StallPanel.tsx frontend/src/components/StallPanel.test.tsx frontend/src/pages/MonitoringAnalysisPage.tsx frontend/src/pages/E2E3Flow.test.tsx
git commit -m "feat(e7): panel de arboles en riesgo de estancarse en el analisis

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## S9 · Cierre: verify + review

### Task 15: Gates, evidencia y documentación

**Files:**
- Create: `docs/verificacion-e7.md`
- Modify: `docs/obsidian-agrosense/01-Proyecto/Roadmap.md` (sección «Slice 4» y línea «Siguiente…»)
- Modify: `docs/obsidian-agrosense/06-Slices/Slice 4 - Detección de Estancados.md` (estado, tabla de tasks, archivos, correcciones)
- Modify: `docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md` (callout de correcciones en §9)
- Modify: `docs/04-vision-producto.md` (§9 E7, §11 fila 10, §13 fila ADR-013)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: evidencia de verificación (AGENTS.md, Completion 1-8).

- [ ] **Step 1: Correr los gates (una vez, la suite completa)**

Run, en este orden, y copiar la línea final de cada salida a la tabla del Step 3:

```bash
cd backend
python -m pytest -q
python -m ruff check src tests scripts
python -m pip_audit -r requirements.lock.txt
python scripts/train_stall_model.py --data data/raw/anexo1.xlsx --check
cd ../frontend
npx vitest run
npx tsc -b
npm run build
npm run lint
npm audit --omit=dev
```

Expected: todo en verde; `--check` imprime «Reproducible: …».

- [ ] **Step 2: Migración en Supabase**

Run: `cd backend && alembic upgrade head && alembic current`
Expected: `e7c1a3b5d7f9 (head)`.

- [ ] **Step 3: Escribir `docs/verificacion-e7.md`**

Estructura (las cifras entre `‹›` se sustituyen por las salidas reales del Step 1 y del informe `docs/ml/evaluacion-estancamiento.md`; no se inventan):

```markdown
# Verificación — E7 · Detección de estancados

Fecha: ‹fecha›. Plan: `docs/superpowers/plans/2026-09-27-e7-estancados.md`.
Decisión: `docs/adr/013-modelo-estancamiento-offline.md`.

**Criterio de salida**: el ingeniero abre el análisis de un monitoreo y ve qué
árboles vivos tienen más riesgo de no crecer hasta el próximo, con el 20 %
marcado para revisión, la regla observada y la lectura honesta del modelo.

## Gates

| # | Gate | Resultado |
|---|---|---|
| 1 | `pytest` local (SQLite) | ‹N passed, M deselected› |
| 2 | `ruff check src tests scripts` | ‹limpio› |
| 3 | `pip-audit -r requirements.lock.txt` (incluye scikit-learn 1.5.2) | ‹sin vulnerabilidades› |
| 4 | Frontend: `vitest run` | ‹N passed› |
| 5 | Frontend: `tsc -b` + `npm run build` + `npm run lint` | ‹0 errores› |
| 6 | `npm audit --omit=dev` | ‹0 vulnerabilidades› |
| 7 | Migración `e7c1a3b5d7f9` (`stall_assessments`) | ‹aplicada, head› |
| 8 | Tests de arquitectura (capas, inferencia en Python puro, sklearn fuera de producción, CV por parcela) | ‹verde› |
| 9 | **ML eval gate** | ‹APROBADO› |
| 10 | Reproducibilidad (`--check`) | ‹Reproducible› |

## ML eval gate

| Criterio | Valor | Umbral |
|---|---|---|
| Train M2→M3 | ‹618 / 153› | igual al panel del protocolo |
| Test M3→M4 | ‹717 / 157› | igual al panel del protocolo |
| PR-AUC temporal | ‹…› (IC 95 % por parcelas ‹…–…›) | ≥ 0.36 |
| Persistencia / tasa por especie | ‹…› / ‹…› | la logística supera a persistencia |
| Control: etiqueta permutada en todo el conjunto | ‹…› | ≤ 0.31 |
| Control: permutada dentro de cada parcela | ‹…› | por debajo del PR-AUC temporal |
| GroupKFold por parcela (diagnóstico) | ‹…› | — |
| Recall / precisión al 20 % | ‹…› / ‹…› | — |

Artefacto `stall-logreg-2026-09-27.1`, SHA-256 ‹…›, commit ‹…›.

## Limitaciones declaradas

1. Entrenado con un solo proyecto (3 predios, 30 especies); especies nuevas pesan cero (`known_species`).
2. En el proyecto de referencia, M2 y M3 son datos de entrenamiento: sus predicciones no son evaluación.
3. La etiqueta mide crecimiento no detectable por el protocolo, no crecimiento nulo.
4. Evidencia sugestiva, no concluyente, frente a la regla por especie (IC solapados).
5. Sin fechas de medición: todo es «por intervalo de monitoreo».
6. «Persistente» = 2 intervalos: convención pendiente de confirmar con el ingeniero.
```

- [ ] **Step 4: Actualizar la documentación viva**

1. `docs/obsidian-agrosense/06-Slices/Slice 4 - Detección de Estancados.md`: frontmatter `status: hecho` y `tags: [slice, hecho]`; en el callout inicial «**Estado**: ✅ Hecho (‹fecha›)»; en la tabla «Tasks» marcar las 9 filas como ✅ y cambiar la Task 9 a «`estancó_intervalo_previo` = `domain.stall_rules.stalled_previous_interval` (derivada, no persistida — ADR-013)»; reemplazar la tabla «Archivos» por las rutas reales (`domain/stall_rules.py`, `ml/stall_features.py`, `ml/preprocessing.py`, `ml/stall_model.py`, `ml/train_stall.py`, `scripts/train_stall_model.py`); añadir antes de «Links»:

```markdown
> [!warning] Correcciones al implementar (E7, ADR-013)
> - Los **153** estancados son de la ola de **entrenamiento** (M2→M3); la de prueba (M3→M4) tiene **157**.
> - `Unidad de monitoreo` es el **tipo** de unidad (3 niveles), no la parcela. La parcela (`Codigo de unidad muestreo`) no es feature: es la unidad de agrupamiento.
> - La igualdad de alturas se compara en milímetros (0,24 → 0,245 m cuenta como crecimiento).
> - El umbral «≤ 5 cm» es la definición descriptiva de E4, no la etiqueta del modelo.
> - El control negativo que vigila fugas es la permutación **global** de la etiqueta; la permutación dentro de parcela conserva la tasa de cada parcela y puntúa ≈ 0.33 (ADR-013).
```

2. `docs/obsidian-agrosense/04-ML/Protocolo Estancamiento.md`: al final de la tabla «Features del modelo» (§9) añadir el mismo callout de correcciones (viñetas 2, 3 y 5).
3. `docs/obsidian-agrosense/01-Proyecto/Roadmap.md`: renombrar el encabezado «Slice 4: Detección de Estancados ⬜ ← siguiente» a «Slice 4 / E7: Detección de Estancados ✅ (‹fecha›)», añadir bajo él «> Plan: `docs/superpowers/plans/2026-09-27-e7-estancados.md`. Decisión: `docs/adr/013-modelo-estancamiento-offline.md`. Métricas: `docs/ml/evaluacion-estancamiento.md`.» y cambiar la línea «Siguiente según … **E7 · Estancados**» por «Siguiente según `docs/04-vision-producto.md` §11: **E8 · Mortalidad** (consume `stalled_previous_interval`).»
4. `docs/04-vision-producto.md`: encabezado de §9 → «### E7 · Detección de estancados — ✅ hecho (‹fecha›)» con una viñeta «Modelo offline + artefacto JSON versionado + inferencia en Python puro (ADR-013); snapshot `stall_assessments`.»; en §11 fila 10 añadir « ✅»; en §13 añadir la fila «| ADR-013 | Modelo de estancamiento offline, artefacto JSON e inferencia en Python puro | E7 |».

Ningún documento puede decir «GroupKFold por árbol» (lo vigila `tests/architecture/test_ml_eval_gate.py`).

- [ ] **Step 5: Re-ejecutar el gate de documentos**

Run: `cd backend && python -m pytest tests/architecture/test_ml_eval_gate.py -v`
Expected: PASS.

- [ ] **Step 6: Review (fase 7)**

Usar las skills `requesting-code-review` y `security-review` sobre `git diff master...e7-estancados`. Checklist mínimo del revisor:
- ¿Alguna feature lee observaciones de `t+1`? (`build_wave` y su test de futuro).
- ¿Algún ajuste (`fit_preprocessor`, especie, mediana) ve filas de prueba?
- ¿Los grupos de CV son la parcela?
- ¿La API importa numpy/sklearn? (test de arquitectura).
- ¿El 503 filtra rutas o trazas? (`test_model_unavailable_is_a_clean_503`).
- ¿Un proyecto ajeno responde 404?
Cada hallazgo → test de regresión → vuelve a la tarea correspondiente.

- [ ] **Step 7: Commit**

```bash
git add docs/verificacion-e7.md docs/obsidian-agrosense docs/04-vision-producto.md
git commit -m "docs(e7): verificacion, roadmap y correcciones del protocolo

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Autorrevisión del plan

- **Cobertura del spec:** etiqueta y regla de negocio en dominio (T2); features relativas a la ola y fugas §4.1/§4.3 (T3); preprocesamiento compartido y fuga §4.4 (T4, T7); fuga §4.2 (la etiqueta no usa expectativa, T2); split temporal primario + GroupKFold por parcela + bootstrap por parcela + control permutado + líneas base (T6, T7); artefacto versionado, reproducible con un comando, semillas y procedencia (T7, T8); dependencia nueva con ADR y auditoría (T1); inferencia barata y síncrona (T5, T12); presupuesto de alertas del 20 % (T2, T6, T10); `estancó_intervalo_previo` para E8 (T2, T10); UC-AN4 (T10); contrato primero (T11); UI y journey E2E (T13, T14); gates de completitud (T15). Fuera de alcance, declarado en el Protocolo §10 como mejoras: curva de costos, calibración por localidad, calibration plot e importancia de coeficientes en la UI.
- **Placeholders:** solo los valores `‹›` de `docs/verificacion-e7.md`, que por definición son salidas de comandos del Step 1.
- **Consistencia de tipos:** `build_wave(..., labeled=)`, `WaveRow`, `PreprocessorParams`, `logistic_scores`, `StallModel.predict/fingerprint/known_species/model_card`, `StallScorer`, `build_stall_payload`, `get_stall_assessment(..., only_flagged=)`, `StallAssessmentRepository.get/save` y los nombres de claves del payload y del contrato coinciden entre tareas.
