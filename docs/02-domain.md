# Domain — AgroSense AI v2

Estado: COMPLETADO (2026-09-14) · DDD pragmático: entidades, invariantes,
casos de uso. Sin aggregates, domain events ni CQRS (ver AGENTS.md).

## 1. Entidades y value objects

### Project (Proyecto de restauración)
Un sitio de restauración ecológica monitoreado por un equipo de ingenieros.
- Atributos: `id`, `nombre`, `localidad/ubicación`, `fecha_inicio`,
  `especies_plantadas` (opcional).
- Un proyecto tiene muchos monitoreos (campañas de medición en el tiempo).
- Fuente de verdad: los datasets que el equipo sube por campaña.

### Tree (Árbol)
Un individuo plantado dentro de un proyecto, identificado de forma
persistente entre campañas.
- Identidad: `tree_id` = (parcela, número de individuo) o ID de muestreo.
- **Regla:** el árbol NO existe hasta su primer censo. Un registro sin
  ninguna medición en la campaña k significa que el árbol no se había
  censado aún (patrón `sin_censo`), no que faltan datos.
- Atributos fijos: especie, familia, nombre común, gremio ecológico,
  coordenadas, elevación.

### Observation (Observación de campaña) ← corazón del modelo
El estado de un árbol en un monitoreo determinado.
- Identidad: (`tree_id`, `monitoreo`).
- Atributos: altura total, diámetro de copa, DAP, estado fitosanitario,
  vivo/muerto, colonización de epífitas.

### StatusSemantic (value object clave)
Distingue TRES estados de un dato, descubiertos en el dataset real:

| Dato crudo | Estado de dominio | Significado |
|---|---|---|
| NaN / `' '` en TODAS las columnas de la campaña | `sin_censo` | Árbol no censado aún en esa campaña |
| DAP = 0.0 o NaN con árbol censado | `bajo_umbral_dap` | Árbol no alcanza el umbral de medición de DAP (~1.3 m de altura estándar) |
| Valor > 0 | `medido` | Medición real |

**Regla:** estos estados NO se imputan (imputarlos destruye la señal).
`sin_censo` excluye al árbol de features de ese período; `bajo_umbral_dap`
es en sí una feature binaria informativa (proxy de tamaño pequeño).

Otros value objects: `Species` (especie/familia/gremio), `Site`
(localidad/parcela), `MeasurementPolicy` (qué se mide en qué campaña y con
qué umbrales — parametrizable por proyecto).

## 2. Invariantes de dominio (a validar en ingesta)

1. **Alturas y copas no negativas.**
2. **Un árbol muerto no revive ni crece.** Si `Sobrevivencia_k = Muerto`
   entonces `Sobrevivencia_j = Muerto` para todo j > k, y alturas/copas
   se congelan en su último valor.
3. **El crecimiento es la diferencia de alturas consecutivas** entre
   campañas censadas: `crecimiento(k-1→k) = altura_k − altura_{k-1}`.
   Se calcula en el dominio; nunca llega como dato crudo.
4. **Identidad persistente:** un `tree_id` no puede cambiar de especie,
   parcela o coordenadas entre campañas (coherencia de identificación
   de campo).
5. **Censo monotónico:** si el árbol tiene datos en M_k, las campañas
   previas censadas deben ser contiguas desde su primer censo.
6. **Contracción tolerada pero acotada:** alturas pueden "encoger"
   ≤1 cm entre campañas (error de medición documentado, ~13/652 casos);
   contracciones mayores son error de datos → warning de ingesta.

## 3. Casos de uso

| # | Caso de uso | Actor | Descripción |
|---|---|---|---|
| UC1 | Crear proyecto | Ingeniero | Registrar un sitio de restauración nuevo |
| UC2 | Cargar monitoreo | Ingeniero | Subir CSV/XLSX de campaña a un proyecto; validar invariantes; rechazar con errores accionables |
| UC3 | Ver historial del proyecto | Ingeniero | Campañas cargadas, árboles censados, estado general |
| UC4 | Evaluar riesgo de mortalidad | Ingeniero | Score de muerte por árbol para el próximo período (señal validada: estancados 35x más riesgo) |
| UC5 | Detectar estancados/anómalos | Ingeniero | Árboles con crecimiento ≈0 + IsolationForest sobre trayectorias |
| UC6 | Analítica por especie/sitio | Ingeniero | Crecimiento, supervivencia y mortalidad agrupadas |
| UC7 | Traza de árbol | Ingeniero | Historial completo de un árbol (alturas, fito, muerte) |

## 4. Reglas de negocio derivadas (validadas con datos)

- **Estancado:** crecimiento acumulado del último período ≤ 5 cm →
  factor de riesgo de mortalidad ~35x (evidencia en discovery §6).
- **Muerte confirmada:** `Sobrevivencia = Muerto` en la campaña más
  reciente. Muertes previas: árbol sale del análisis de crecimiento.
- **DAP solo informativo como feature binaria** (`bajo_umbral` / medido);
  el valor continuo solo existe en árboles grandes (M3: 27, M4: 83) —
  no usarlo como regresor continuo sin tratar su censura por umbral.
- **Estado fitosanitario:** normalizar `' '` → `sin_censo` antes de
  cualquier análisis (2 encodings del mismo concepto en el crudo).

## 5. Errores de dominio (mensajes accionables)

- `SPECIES_MISMATCH`: árbol cambió de especie entre campañas.
- `DEATH_VIOLATION`: árbol muerto revive o crece post-mortem.
- `NEGATIVE_MEASUREMENT`: altura/copa < 0.
- `NON_CONTIGUOUS_CENSUS`: censo con huecos.
- `SUSPICIOUS_CONTRACTION`: contracción > 1 cm entre campañas (warning,
  no error).

## 6. Fuera del dominio (explícito)

- Auth/usuarios (futura épica).
- Forecasts precisos por árbol (señal insuficiente, ver discovery §6).
- Edición de datos cargados: el dataset crudo es inmutable; los errores
  se corrigen re-subiendo la campaña (auditable).
