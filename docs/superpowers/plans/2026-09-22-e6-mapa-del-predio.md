# Mapa del predio — Plan de implementación (E6)

> **Para quien ejecute:** cada tarea es un slice vertical con su ciclo TDD y
> su gate. Los pasos usan `- [ ]` para llevar la cuenta.

**Objetivo:** que el ingeniero vea sus 856 árboles sobre imagen satelital,
coloreados por estado, con una línea de tiempo M1→M4, el historial de un árbol
al hacer clic, y un mapa de calor por parcela.

**Arquitectura:** el backend proyecta EPSG:9377 → WGS84 y arma **un solo
payload** con todos los monitoreos; el frontend solo dibuja y filtra. Misma
regla que E3: ninguna cifra se calcula en la página. Sin tabla nueva y sin
migración — el mapa se deriva de `trees` + `observations` en una lectura
(856 puntos, ~40 ms), así que no hay nada que guardar ni que invalidar.

**Stack:** pyproj (backend) · Leaflet + react-leaflet (frontend) · teselas
satelitales de Esri World Imagery (sin API key, con atribución).

**Spec:** `docs/04-vision-producto.md` §6.8 y §9 (E6), más el orden aprobado
por el ingeniero el 2026-09-22 (mapa inmediatamente después del análisis).

## Restricciones globales

- El sistema de coordenadas es **del proyecto** (`projects.coordinate_srid`,
  9377 por defecto), no del árbol. Verificado en `docs/verificacion-e0.md` §6.
- Puntos de control de esa verificación, que los tests deben reproducir:
  Guayabal 5,8017° N / 75,3852° O · San Antonio 5,8013° N / 75,3876° O ·
  Tres Jotas 5,8054° N / 75,3850° O. Extensión conjunta 646 × 907 m.
- `domain/` y `application/` no importan pyproj, adapters ni FastAPI (el test
  de capas lo verifica).
- Colores de estado reservados (dataviz): bueno `#0ca30c`, regular `#fab219`,
  malo `#d03b3b`. Muerto y sin dato usan grises, nunca un color de serie.
- La página del mapa se carga con `import()` dinámico: el bundle ya pesa
  827 kB (deuda #O) y Leaflet no debe entrar en la ruta de proyectos.
- Un árbol sin coordenada no se inventa: se cuenta y se informa.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `domain/map_rules.py` (nuevo) | Qué estado se pinta (`map_state`), qué es una coordenada válida, umbral de parcela pequeña. Sin pyproj. |
| `adapters/geo/projection.py` (nuevo) | `to_wgs84(points, srid)` con pyproj; el único punto que sabe de proyecciones. |
| `adapters/geo/map_payload.py` (nuevo) | Arma el payload: árboles, parcelas (casco convexo + agregados), bounds. |
| `application/use_cases/project_map.py` (nuevo) | Autorización + orquestación; recibe el proyector por parámetro. |
| `adapters/api/routes/map.py` (nuevo) | `GET /projects/{id}/map`. |
| `adapters/api/schemas.py` | Esquemas del contrato del mapa. |
| `frontend/src/map/` (nuevo) | `MapPage.tsx`, `TreeLayer.tsx`, `PlotLayer.tsx`, `Timeline.tsx`, `TreePopup.tsx`, `colors.ts`. |
| `frontend/src/api/map.ts` (nuevo) | Acceso a datos del mapa. |

---

## Tarea 1 — Proyección de coordenadas (EPSG:9377 → WGS84)

**Archivos:**
- Crear: `backend/src/agrosense/adapters/geo/projection.py`
- Crear: `backend/tests/geo/test_projection.py`
- Modificar: `backend/pyproject.toml`, `backend/requirements.lock.txt`

**Interfaces — produce:**
```python
def to_wgs84(points: Sequence[tuple[float, float]], srid: int) -> list[tuple[float, float]]
    """(x, y) en `srid` → (lat, lon) en WGS84. Lote, no punto a punto."""

class UnsupportedSridError(ValueError): ...
```

- [ ] **Paso 1: test que falla** — los tres predios caen donde dice
  `verificacion-e0.md`, con tolerancia 0.0002° (≈20 m):

```python
def test_los_tres_predios_caen_donde_dice_la_verificacion_de_e0():
    puntos = [(4735663.15, 2199355.02), (4735900.0, 2199600.0)]
    (lat1, lon1), _ = to_wgs84(puntos, 9377)
    assert lat1 == pytest.approx(5.8017, abs=0.0002)
    assert lon1 == pytest.approx(-75.3852, abs=0.0002)
```

- [ ] **Paso 2:** `pytest tests/geo/test_projection.py -v` → FAIL (módulo no existe).
- [ ] **Paso 3:** instalar `pyproj`, fijarlo en `pyproject.toml` y regenerar
  `requirements.lock.txt`; implementar con un `Transformer` cacheado por srid
  (`always_xy=True`), devolviendo `(lat, lon)`.
- [ ] **Paso 4:** los tests pasan; añadir los casos de borde: srid desconocido
  → `UnsupportedSridError`; lista vacía → lista vacía; el orden de salida es
  el de entrada (test con 3 puntos distintos).
- [ ] **Paso 5:** `pip-audit -r requirements.lock.txt` y commit.

---

## Tarea 2 — Reglas de dominio del mapa

**Archivos:**
- Crear: `backend/src/agrosense/domain/map_rules.py`
- Crear: `backend/tests/domain/test_map_rules.py`

**Interfaces — produce:**
```python
MAP_STATES = ("bueno", "regular", "malo", "muerto", "sin_dato")
def map_state(alive: bool | None, phytosanitary: str | None) -> str
def has_coordinates(coord_x: float | None, coord_y: float | None) -> bool
MIN_TREES_FOR_PLOT_METRIC = 5   # reutiliza el criterio de E3
```

- [ ] **Paso 1: tests que fallan** — un árbol muerto es `"muerto"` aunque
  traiga estado fitosanitario (el estado de un muerto es un residuo del
  archivo); vivo sin estado → `"sin_dato"`; `" "` → `"sin_dato"`;
  "Bueno"/"Regular"/"Malo" → su color; `alive=None` → `"sin_dato"`.
- [ ] **Paso 2:** ejecutar → FAIL.
- [ ] **Paso 3:** implementar reutilizando `normalize_phytosanitary` de
  `analysis_rules` (una sola definición de los estados, no dos).
- [ ] **Paso 4:** tests en verde + el gate de capas sigue pasando.
- [ ] **Paso 5:** commit.

---

## Tarea 3 — Payload del mapa (árboles, parcelas, bounds)

**Archivos:**
- Crear: `backend/src/agrosense/adapters/geo/map_payload.py`
- Crear: `backend/tests/geo/test_map_payload.py`

**Interfaces — consume:** `to_wgs84`, `map_state`, `Tree`, `Observation`.
**Produce:**
```python
MAP_VERSION = "2026-09-22-e6.1"
def build_map(trees, observations, srid) -> dict
# {version, srid, monitorings: [1..n], bounds: {south, west, north, east},
#  properties: [...], without_coordinates: int,
#  trees: [{id, species, property, plot, lat, lon, elevation_m,
#           states: {"1": "bueno", ...}, heights: {"1": 0.4, ...}}],
#  plots: [{property, plot, centroid: {lat, lon}, n, hull: [[lat, lon], ...],
#           metrics: {"1": {survival: 92.7, mean_height: 0.51, n: 69}, ...}}]}
```

- [ ] **Paso 1: tests que fallan.** Con el mismo dataset de
  `tests/analysis/test_engine.py` (`TREES`, `OBS`): el payload trae un árbol
  por árbol con coordenada; `states["2"]` de un árbol muerto en M2 es
  `"muerto"`; los bounds encierran todos los puntos; la supervivencia de una
  parcela coincide con la que ya publica el análisis de E3 para esa parcela
  (**no puede haber dos verdades**); una parcela con menos de 5 árboles trae
  `"low_sample": true`; un árbol sin coordenada no aparece en `trees` pero sí
  cuenta en `without_coordinates`.
- [ ] **Paso 2:** ejecutar → FAIL.
- [ ] **Paso 3:** implementar. El casco convexo por parcela con monotone
  chain sobre los puntos proyectados (≤3 puntos → devolver los puntos tal
  cual, que dibujan una línea o un punto; es honesto y no inventa área).
- [ ] **Paso 4:** verde, incluidos los casos de borde: parcela de 1 árbol,
  proyecto sin ninguna coordenada (payload válido con `trees: []`).
- [ ] **Paso 5:** commit.

---

## Tarea 4 — Contrato y endpoint

**Archivos:**
- Crear: `backend/src/agrosense/application/use_cases/project_map.py`
- Crear: `backend/src/agrosense/adapters/api/routes/map.py`
- Modificar: `backend/src/agrosense/adapters/api/schemas.py`, `app.py`
- Crear: `backend/tests/api/test_e6_map_api.py`

**Contrato:**
```
GET /projects/{project_id}/map
  200 → ProjectMapResponse (el payload de la tarea 3 + project_id)
  401 sin sesión · 404 proyecto ajeno o inexistente
```

- [ ] **Paso 1: tests que fallan** — sin token → 401; proyecto de otro
  ingeniero → 404; proyecto propio → 200 con `trees`, `plots` y `bounds`;
  un proyecto sin ninguna carga → 200 con listas vacías y
  `monitorings: []` (no un 404: el proyecto existe, el mapa está vacío).
- [ ] **Paso 2:** ejecutar → FAIL.
- [ ] **Paso 3:** implementar. El caso de uso recibe `projector` y
  `map_builder` por parámetro (ADR-003: sin puerto donde no hay variación).
- [ ] **Paso 4:** verde + el test de capas sigue pasando.
- [ ] **Paso 5:** commit.

---

## Tarea 5 — El mapa en la interfaz

**Archivos:**
- Crear: `frontend/src/api/map.ts`, `frontend/src/map/{MapPage,TreeLayer,PlotLayer,Timeline,TreePopup}.tsx`, `frontend/src/map/colors.ts`
- Modificar: `frontend/src/App.tsx` (ruta `/proyectos/:id/mapa`, con `lazy()`),
  `frontend/src/pages/ProjectDetailPage.tsx` (enlace), `styles.css`
- Crear: `frontend/src/map/MapPage.test.tsx`

- [ ] **Paso 1: test que falla** (Leaflet simulado): la página pide
  `/projects/7/map`, pinta un marcador por árbol, el deslizador cambia de
  monitoreo **sin volver a pedir datos**, el clic en un árbol muestra su
  historial de alturas, y el conmutador «parcelas» cambia a los polígonos.
- [ ] **Paso 2:** ejecutar → FAIL.
- [ ] **Paso 3:** implementar. Capa base Esri World Imagery con su
  atribución; leyenda de estados; aviso visible cuando
  `without_coordinates > 0`.
- [ ] **Paso 4:** `vitest run`, `tsc -b`, `npm run build` (comprobar que
  Leaflet queda en su propio chunk).
- [ ] **Paso 5:** commit.

---

## Tarea 6 — Verificación y cierre

- [ ] `pytest`, `pytest -m supabase`, `ruff check`, `vitest`, `tsc`, build,
      `pip-audit`, `npm audit --omit=dev`.
- [ ] Contraste contra el dato real: correr el payload con el Anexo cargado y
      comprobar que los 856 árboles caen dentro de la extensión de 646 × 907 m
      de `verificacion-e0.md`.
- [ ] `docs/verificacion-e6.md` + ADR-009 (proyección en el backend y mapa sin
      tabla propia) + actualizar `04-vision-producto.md` y `deuda-tecnica.md`.
- [ ] Commit de la épica.

---

## Autorrevisión

- **Cobertura:** proyección (T1), color por estado (T2), payload y calor por
  parcela (T3), contrato (T4), línea de tiempo + historial al clic + satélite
  (T5), gates (T6). Las capas adicionales (`geo_layers` de §6.8) quedan
  **fuera**: no hay dato que poner en ellas todavía (YAGNI).
- **Sin marcadores de relleno:** cada tarea nombra archivos y asertos reales.
- **Consistencia de tipos:** `map_state` devuelve una cadena de `MAP_STATES`,
  que es la clave de `colors.ts`; `states`/`heights` se indexan por el número
  de monitoreo **como cadena** (JSON no admite claves numéricas) — el
  frontend hace `states[String(m)]`.
