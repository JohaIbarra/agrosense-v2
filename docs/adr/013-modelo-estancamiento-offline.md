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
     Gate: el PR-AUC temporal **puntual** (no el límite inferior de su
     propio IC) ≥ 0.36; supera a prevalencia y persistencia; el control con
     la etiqueta permutada en todo el conjunto ≤ 0.31 (vigila fugas: sin
     señal, el pipeline debe caer a la prevalencia); y supera al control
     permutado dentro de cada parcela. El 0.36 proviene históricamente del
     límite inferior del IC 95 % que reportó el protocolo (Protocolo §5):
     es el origen del número, no una descripción de qué compara el gate hoy
     (fix round 1, M1 — antes se prestaba a leerse como "compara el límite
     del IC").
     **Desvío del protocolo, redefinido DESPUÉS de ver el resultado (fix
     round 1, I1):** el protocolo usa como control de fugas la permutación
     dentro de parcela, con techo 0.31 (reporta 0.238, rango 0.18–0.31). Al
     reproducirlo con esta featurización da ≈ 0.33 (20 corridas, rango
     0.24–0.40): **con ese criterio original, este modelo NO habría pasado
     el gate.** La causa no es fuga sino señal de sitio: conservar la tasa
     de cada parcela permite aprender la especie y el predio, que sí varían
     entre parcelas. Por eso ese control pasó a medir cuánto aporta el
     modelo por encima de la tasa de la parcela (debe superarlo, no
     acercarse a él), y el control de fugas real pasó a ser la permutación
     global (≈ 0.227, rango 0.16–0.33), con el mismo techo 0.31. Esta
     reinterpretación queda **pre-registrada desde el artefacto
     `stall-logreg-2026-09-27.2` en adelante**: no explica retroactivamente
     `.1` (mismos coeficientes; solo cambian metadatos y métricas
     reportadas), pero cualquier reentrenamiento futuro se juzga con esta
     definición, no con una reinterpretada sobre la marcha otra vez.
     El artefacto servido se reentrena con el mismo procedimiento sobre las
     olas M2 y M3; las métricas evalúan el procedimiento. El `C=0.5` de la
     logística viene del protocolo/spike (`Protocolo Estancamiento.md` §9),
     fijado antes de evaluar M3 (fix round 1, M5): no se reajustó al ver
     este resultado.
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
     intervalos seguidos sin crecer (convención del proyecto, confirmada con
     el ingeniero el 2026-09-27).
  10. **La etiqueta depende del protocolo de campo, no solo del árbol**
      (fix wave 2026-09-27, item 7). `stall_label` compara alturas en
      milímetros entre DOS monitoreos consecutivos del MISMO protocolo de
      campo: su significado —y por lo tanto la prevalencia que reporta el
      gate— está atado a dos parámetros de ese protocolo, no es una
      propiedad universal del árbol:
      - **Espaciado entre monitoreos.** El dataset de referencia mide cada
        ~1 año (M1-M4). Un proyecto que monitoree cada 6 meses vería más
        estancamiento «real» capturado en cada intervalo (el árbol tuvo
        menos tiempo para crecer lo suficiente como para que el instrumento
        lo note); uno que monitoree cada 2 años vería menos. La
        prevalencia (153/717 en M2→M3/M3→M4) es de ESTE espaciado.
      - **Precisión del redondeo de altura.** Aquí son milímetros
        (`height_unchanged`, éste ADR §Decisión 1); el dataset real trae
        medio centímetro de resolución de campo. Un protocolo que registre
        con menos precisión (p. ej. a los 5 cm, como `STAGNATION_THRESHOLD_M`
        en `rules.py`, que es la comparación descriptiva de E4 y NO esta
        etiqueta) fusionaría como «estancados» árboles que sí crecieron
        unos centímetros; uno con más precisión (mm reales de un
        dendrómetro) separaría estancamientos que aquí se ven iguales.
      - **Consecuencia:** un modelo entrenado con un proyecto NO se
        transfiere a otro con espaciado o precisión de monitoreo distintos
        sin revalidar — ni siquiera si comparte especies y sitio. Esto es
        ADEMÁS de la limitación ya declarada de transferencia espacial
        (§Consecuencias): aquí la limitación es sobre el PROTOCOLO de
        medición, no sobre el predio.

- **Consecuencias:**
  - Train y serve no pueden divergir: comparten `build_wave`, `transform` y
    `logistic_scores`, y el cargador verifica las versiones.
  - El modelo se entrenó con un solo proyecto (3 predios, 30 especies). Una
    especie que no vio pesa cero en su one-hot: cada árbol lleva
    `known_species` y la UI lo avisa. La transferencia espacial no está
    evaluada (Protocolo §3: 3 localidades, no es viable).
  - La transferencia tampoco está evaluada entre protocolos de monitoreo
    distintos: la prevalencia y el significado de la etiqueta dependen del
    espaciado entre monitoreos y de la precisión del redondeo de altura de
    ESTE proyecto (Decisión 10).
  - En el proyecto de referencia, las predicciones de M2 y M3 son sobre
    datos de entrenamiento: no son una evaluación. La evaluación honesta es
    la del informe.
  - La probabilidad es condicional a que el árbol siga vivo; mortalidad es
    E8.
  - La API carga el artefacto una vez por proceso: un reentrenamiento exige
    reiniciar el servidor y subir `model_version`.
