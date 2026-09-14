# Épica 1 — Fundación de Datos: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingerir el archivo de campo (formato ancho `Monitoreo_4`) y producir el dataset long canónico con invariantes de dominio validadas — la única fuente de verdad de todos los análisis futuros.

**Architecture:** Monolito modular (ADR-003): `domain/` con entidades e invariantes puras, `adapters/ingester/` que traduce el formato ancho de campo a `Observation` canónicas, storage versionado de crudos (ADR-004). El slice es demostrable vía CLI + tests, sin API ni frontend todavía.

**Tech Stack:** Python 3.12, pandas, pydantic (validación de contrato de entrada), pytest, SQLite en tests (ADR-002 permite dialecto test).

**Spec:** `docs/02-domain.md` (entidades, StatusSemantic, invariantes, errores) + `docs/adr/004-ingesta-datos.md` (formato ancho → long) + `docs/01-discovery.md` §6 (señal del dataset).

## Global Constraints

- Python ≥3.12; deps pineadas en `pyproject.toml` (regla AGENTS.md: reproducible).
- `domain/` NO importa pandas, pydantic, sqlalchemy ni ningún framework (ADR-003).
- Nada de imputación en ingesta: blancos → `StatusSemantic`, nunca medianas (docs/02-domain.md §1).
- Contrato de entrada tolerante a los nombres reales del archivo: `DAP (CM)`, `Sobrevivemcia M1` (typo real), `Diámetro. Copa (m)_M2`, espacios `' '` (ADR-004).
- El ingester rechaza la campaña COMPLETA ante violación de invariante (sin persistencia parcial).
- Tests de dominio sin DB ni archivos (puros); tests de ingester con el dataset real de referencia.
- Dataset de referencia: `Anexo 1 Base de datos 4 MONITOREO.xlsx` hoja `Monitoreo_4` — NO entra al repo (regla .gitignore); los tests lo leen de `data/raw/` local y se marcan skip si no existe.

---

## File Structure

```
backend/
├── pyproject.toml                    # deps pineadas + pytest + ruff config
├── src/agrosense/
│   ├── domain/
│   │   ├── entities.py               # Observation, Tree, Campaign, StatusSemantic
│   │   ├── errors.py                 # DomainError codes (§5 del domain doc)
│   │   └── rules.py                  # invariantes puras (validan list[Observation])
│   └── adapters/ingester/
│       ├── column_mapping.py         # nombres reales de campo → canónicos (versionado)
│       ├── wide_to_long.py           # ancho → list[Observation] + Tree
│       └── ingest.py                 # orquesta: parse → validate → return
└── tests/
    ├── domain/test_rules.py          # invariantes (puras, sin I/O)
    ├── domain/test_entities.py       # constructores validan (post_init)
    └── ingester/test_ingest.py       # con dataset real (skip si ausente)
```

Responsabilidades: `entities.py` define QUÉ es válido; `rules.py` valida SERIES temporales entre observaciones; `column_mapping.py` es el único lugar que conoce los typos del archivo; `wide_to_long.py` hace la transformación; `ingest.py` orquesta y es la interfaz del módulo.

---

### Task 1: Scaffolding del backend (pyproject + estructura)

**Files:**
- Create: `backend/pyproject.toml`, `backend/src/agrosense/__init__.py`
- Create: `backend/src/agrosense/domain/__init__.py`, `backend/src/agrosense/adapters/__init__.py`, `backend/src/agrosense/adapters/ingester/__init__.py`
- Create: `backend/tests/__init__.py`, `backend/tests/domain/__init__.py`, `backend/tests/ingester/__init__.py`

**Interfaces:**
- Produces: paquete instalable `agrosense` (importable como `from agrosense.domain import ...`); config pytest con `testpaths=["tests"]`.

- [ ] **Step 1: Crear `backend/pyproject.toml`**

```toml
[project]
name = "agrosense"
version = "0.1.0"
description = "AgroSense AI v2 - plataforma de analisis de restauracion ecologica"
requires-python = ">=3.12"
dependencies = [
    "pandas==2.2.2",
    "pydantic==2.9.2",
]

[project.optional-dependencies]
dev = [
    "pytest==8.3.3",
    "ruff==0.6.9",
]

[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]
```

- [ ] **Step 2: Crear `__init__.py` vacíos** en cada directorio listado arriba.

- [ ] **Step 3: Instalar y verificar**

Run: `cd backend && pip install -e ".[dev]" && pytest --collect-only`
Expected: "no tests ran" (exit 5) SIN error de import — el paquete existe.

- [ ] **Step 4: Commit**

```bash
git add backend/
git commit -m "feat(backend): scaffolding paquete agrosense + pytest + ruff config"
```

---

### Task 2: Entidades de dominio + errores (con validación en construcción)

**Files:**
- Create: `backend/src/agrosense/domain/entities.py`
- Create: `backend/src/agrosense/domain/errors.py`
- Test: `backend/tests/domain/test_entities.py`

**Interfaces:**
- Produces:
  - `class StatusSemantic(str, Enum)`: `SIN_CENSO`, `BAJO_UMBRAL_DAP`, `MEDIDO`
  - `class Observation(BaseModel)` con campos: `tree_id: str`, `campaign: int` (1-4), `height_m: float | None`, `crown_diameter_m: float | None`, `dap_cm: float | None`, `dap_status: StatusSemantic`, `phytosanitary: str | None`, `alive: bool | None`, `colonization: str | None`
  - `class Tree(BaseModel)` con campos: `tree_id: str`, `species: str`, `family: str | None`, `common_name: str | None`, `guild: str | None`, `plot_id: str | None`, `locality: str | None`, `coord_x: float | None`, `coord_y: float | None`, `elevation_m: float | None`
  - `class DomainError(Exception)` con `code: str` y `message: str`; subclases: `SpeciesMismatchError`, `DeathViolationError`, `NegativeMeasurementError`, `NonContiguousCensusError`, `SuspiciousContractionWarning(Exception)` (warning, no error)

- [ ] **Step 1: Escribir tests fallidos** — `backend/tests/domain/test_entities.py`

```python
import pytest
from agrosense.domain.entities import Observation, StatusSemantic
from agrosense.domain.errors import NegativeMeasurementError


def test_observation_valid():
    obs = Observation(
        tree_id="T1", campaign=2, height_m=0.45, crown_diameter_m=0.30,
        dap_cm=None, dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary="Bueno", alive=True, colonization=None,
    )
    assert obs.tree_id == "T1"


def test_negative_height_rejected():
    with pytest.raises(NegativeMeasurementError):
        Observation(
            tree_id="T1", campaign=2, height_m=-0.1, crown_diameter_m=0.30,
            dap_cm=None, dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
            phytosanitary="Bueno", alive=True, colonization=None,
        )


def test_negative_crown_rejected():
    with pytest.raises(NegativeMeasurementError):
        Observation(
            tree_id="T1", campaign=2, height_m=None, crown_diameter_m=-0.5,
            dap_cm=None, dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
            phytosanitary=None, alive=None, colonization=None,
        )


def test_negative_dap_rejected():
    with pytest.raises(NegativeMeasurementError):
        Observation(
            tree_id="T1", campaign=2, height_m=None, crown_diameter_m=None,
            dap_cm=-1.5, dap_status=StatusSemantic.MEDIDO,
            phytosanitary=None, alive=None, colonization=None,
        )


def test_campaign_out_of_range_rejected():
    with pytest.raises(Exception):
        Observation(
            tree_id="T1", campaign=5, height_m=None, crown_diameter_m=None,
            dap_cm=None, dap_status=StatusSemantic.SIN_CENSO,
            phytosanitary=None, alive=None, colonization=None,
        )
```

- [ ] **Step 2: Correr tests y verificar que fallan** — Run: `cd backend && pytest tests/domain/test_entities.py -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: agrosense.domain.entities`.

- [ ] **Step 3: Implementar `errors.py`**

```python
"""Errores de dominio: códigos accionables (docs/02-domain.md §5)."""


class DomainError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class SpeciesMismatchError(DomainError):
    def __init__(self, tree_id: str, found: str, expected: str):
        super().__init__(
            "SPECIES_MISMATCH",
            f"Arbol {tree_id} cambia de especie entre campanas: {expected} -> {found}",
        )


class DeathViolationError(DomainError):
    def __init__(self, tree_id: str, campaign: int):
        super().__init__(
            "DEATH_VIOLATION",
            f"Arbol {tree_id} muerto en campana {campaign} revive o crece despues",
        )


class NegativeMeasurementError(DomainError):
    def __init__(self, field: str, value: float, tree_id: str, campaign: int):
        super().__init__(
            "NEGATIVE_MEASUREMENT",
            f"{field}={value} < 0 en arbol {tree_id}, campana {campaign}",
        )


class NonContiguousCensusError(DomainError):
    def __init__(self, tree_id: str, campaigns: list[int]):
        super().__init__(
            "NON_CONTIGUOUS_CENSUS",
            f"Arbol {tree_id} con censo no contiguo: {sorted(campaigns)}",
        )


class SuspiciousContractionWarning(Exception):
    """No es error: contraccion >1cm es error de medicion documentado (warning)."""

    def __init__(self, tree_id: str, campaign: int, contraction_m: float):
        self.tree_id = tree_id
        self.campaign = campaign
        self.contraction_m = contraction_m
        super().__init__(
            f"Arbol {tree_id} 'encoge' {contraction_m:.3f} m hasta campana {campaign} "
            f"(error de medicion de campo documentado)"
        )
```

- [ ] **Step 4: Implementar `entities.py`**

```python
"""Entidades de dominio (docs/02-domain.md). Pydantic SOLO como validador
de construccion: los tipos son del dominio, no de la DB ni de la API."""
from enum import Enum

from pydantic import BaseModel, field_validator

from agrosense.domain.errors import NegativeMeasurementError


class StatusSemantic(str, Enum):
    SIN_CENSO = "sin_censo"            # arbol no censado esa campana
    BAJO_UMBRAL_DAP = "bajo_umbral_dap"  # no alcanza umbral de medicion DAP
    MEDIDO = "medido"                  # valor real


class Observation(BaseModel):
    tree_id: str
    campaign: int
    height_m: float | None
    crown_diameter_m: float | None
    dap_cm: float | None
    dap_status: StatusSemantic
    phytosanitary: str | None
    alive: bool | None
    colonization: str | None

    @field_validator("campaign")
    @classmethod
    def campaign_in_range(cls, v: int) -> int:
        if not 1 <= v <= 4:
            raise ValueError(f"campaign debe ser 1-4, recibido {v}")
        return v

    @field_validator("height_m", "crown_diameter_m", "dap_cm")
    @classmethod
    def measurement_not_negative(cls, v, info):
        if v is not None and v < 0:
            raise NegativeMeasurementError(info.field_name, v, "?", 0)
        return v


class Tree(BaseModel):
    tree_id: str
    species: str
    family: str | None = None
    common_name: str | None = None
    guild: str | None = None
    plot_id: str | None = None
    locality: str | None = None
    coord_x: float | None = None
    coord_y: float | None = None
    elevation_m: float | None = None
```

Nota: el validator lanza `NegativeMeasurementError` con tree_id/campaign provisionales; el ingester (Task 5) lo re-raisea con contexto real. Alternativa más limpia si molesta: validar negativos SOLO en `rules.py` con contexto — decisión del implementador, pero los tests de arriba deben pasar tal cual.

- [ ] **Step 5: Correr tests hasta pasar** — Run: `pytest tests/domain/test_entities.py -v`
Expected: 5 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agrosense/domain/ backend/tests/domain/test_entities.py
git commit -m "feat(domain): Observation, Tree, StatusSemantic + errores accionables"
```

---

### Task 3: Invariantes temporales (rules.py — la serie, no la fila)

**Files:**
- Create: `backend/src/agrosense/domain/rules.py`
- Test: `backend/tests/domain/test_rules.py`

**Interfaces:**
- Consumes: `Observation`, `Tree`, errores de Task 2.
- Produces:
  - `def validate_tree_observations(tree: Tree, observations: list[Observation]) -> list[SuspiciousContractionWarning]` — lanza `DeathViolationError` / `NonContiguousCensusError` / `SpeciesMismatchError` según corresponda; devuelve warnings (no los lanza).
  - `def growth_between(prev: Observation, curr: Observation) -> float` — altura actual − previa; asume ambas censadas con altura.
  - `STAGNATION_THRESHOLD_M = 0.05` y `MAX_CONTRACTION_M = 0.01` como constantes de dominio (docs/02-domain.md §4).

**Invariantes que este módulo captura (docs/02-domain.md §2):**
1. Muerto no revive: `alive=False` en campaña k ⇒ `alive=False` en todas las posteriores y mediciones congeladas.
2. Censo contiguo desde el primer censo (sin huecos).
3. Contracción ≤1cm entre campañas consecutivas censadas: mayor ⇒ warning `SuspiciousContractionWarning`, nunca error.
4. Especie del `Tree` consistente con lo observado (el mismatch se detecta en ingester comparando Trees del mismo tree_id entre filas del ancho).

- [ ] **Step 1: Escribir tests fallidos** — `backend/tests/domain/test_rules.py`

```python
import pytest
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.errors import (
    DeathViolationError,
    NonContiguousCensusError,
    SpeciesMismatchError,
)
from agrosense.domain.rules import STAGNATION_THRESHOLD_M, growth_between, validate_tree_observations


def make_obs(campaign, height, alive, tree_id="T1"):
    return Observation(
        tree_id=tree_id, campaign=campaign, height_m=height,
        crown_diameter_m=0.2, dap_cm=None,
        dap_status=StatusSemantic.BAJO_UMBRAL_DAP,
        phytosanitary="Bueno", alive=alive, colonization=None,
    )


def make_tree(species="Quercus humboldtii", tree_id="T1"):
    return Tree(tree_id=tree_id, species=species)


def test_healthy_series_passes():
    tree = make_tree()
    obs = [make_obs(1, 0.2, True), make_obs(2, 0.3, True), make_obs(3, 0.4, True)]
    warnings = validate_tree_observations(tree, obs)
    assert warnings == []


def test_dead_tree_frozen_passes():
    tree = make_tree()
    obs = [make_obs(1, 0.2, True), make_obs(2, 0.25, False), make_obs(3, 0.25, False)]
    warnings = validate_tree_observations(tree, obs)
    assert warnings == []


def test_dead_tree_revives_raises():
    tree = make_tree()
    obs = [make_obs(1, 0.2, False), make_obs(2, 0.3, True)]
    with pytest.raises(DeathViolationError):
        validate_tree_observations(tree, obs)


def test_dead_tree_grows_raises():
    tree = make_tree()
    obs = [make_obs(1, 0.2, True), make_obs(2, 0.25, False), make_obs(3, 0.5, False)]
    with pytest.raises(DeathViolationError):
        validate_tree_observations(tree, obs)


def test_census_gap_raises():
    tree = make_tree()
    obs = [make_obs(1, 0.2, True), make_obs(3, 0.4, True)]
    with pytest.raises(NonContiguousCensusError):
        validate_tree_observations(tree, obs)


def test_contraction_small_is_warning():
    tree = make_tree()
    obs = [make_obs(1, 0.30, True), make_obs(2, 0.295, True)]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 0  # 5mm <= 1cm: ni warning


def test_contraction_large_warns_not_raises():
    tree = make_tree()
    obs = [make_obs(1, 0.30, True), make_obs(2, 0.20, True)]
    warnings = validate_tree_observations(tree, obs)
    assert len(warnings) == 1
    assert "encoge" in str(warnings[0])


def test_species_checked_by_caller_pattern():
    # SpeciesMismatch no se detecta DENTRO de validate (tree ya trae especie);
    # lo valida el ingester contra las filas del archivo. Este test documenta
    # el contrato: validate NO lanza SpeciesMismatch por si solo.
    tree = make_tree(species="X")
    obs = [make_obs(1, 0.2, True)]
    validate_tree_observations(tree, obs)  # no raise


def test_growth_between():
    a = make_obs(1, 0.20, True)
    b = make_obs(2, 0.32, True)
    assert growth_between(a, b) == pytest.approx(0.12)
    assert STAGNATION_THRESHOLD_M == 0.05
```

- [ ] **Step 2: Verificar fallo** — Run: `pytest tests/domain/test_rules.py -v`
Expected: FAIL — `cannot import ... rules`.

- [ ] **Step 3: Implementar `rules.py`**

```python
"""Invariantes de dominio sobre SERIES de observaciones (docs/02-domain.md §2).
Pure: sin I/O, sin framework. Recibe Observations YA validadas por construccion."""
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.errors import (
    DeathViolationError,
    NonContiguousCensusError,
    SuspiciousContractionWarning,
)

STAGNATION_THRESHOLD_M = 0.05   # <=5cm/periodo => factor de riesgo ~35x (spike)
MAX_CONTRACTION_M = 0.01        # tolerancia de medicion de campo


def growth_between(prev: Observation, curr: Observation) -> float:
    """Crecimiento entre campanas consecutivas censadas (invariante 3)."""
    if prev.height_m is None or curr.height_m is None:
        raise ValueError("growth_between requiere alturas censadas")
    return curr.height_m - prev.height_m


def validate_tree_observations(
    tree: Tree, observations: list[Observation]
) -> list[SuspiciousContractionWarning]:
    """Valida la serie temporal de un arbol. Lanza DomainError si viola
    invariante dura; devuelve warnings de contraccion sospechosa."""
    if not observations:
        return []

    obs_sorted = sorted(observations, key=lambda o: o.campaign)
    campaigns = [o.campaign for o in obs_sorted if o.alive is not None or o.height_m is not None]

    # Invariante 5: censo contiguo desde el primer censo
    if campaigns and campaigns != list(range(campaigns[0], campaigns[-1] + 1)):
        raise NonContiguousCensusError(tree.tree_id, campaigns)

    warnings: list[SuspiciousContractionWarning] = []

    dead_campaign: int | None = None
    prev: Observation | None = None

    for obs in obs_sorted:
        censused = obs.alive is not None or obs.height_m is not None
        if not censused:
            continue

        # Invariante 2: muerto no revive ni crece
        if dead_campaign is not None:
            if obs.alive:
                raise DeathViolationError(tree.tree_id, obs.campaign)
            if prev is not None and prev.height_m is not None and obs.height_m is not None:
                if abs(obs.height_m - prev.height_m) > 1e-9:
                    raise DeathViolationError(tree.tree_id, obs.campaign)
            prev = obs
            continue

        if obs.alive is False:
            dead_campaign = obs.campaign

        # Invariante 6: contraccion acotada (warning, no error)
        if prev is not None and prev.height_m is not None and obs.height_m is not None:
            contraction = prev.height_m - obs.height_m
            if contraction > MAX_CONTRACTION_M:
                warnings.append(
                    SuspiciousContractionWarning(tree.tree_id, obs.campaign, contraction)
                )
        prev = obs

    return warnings
```

- [ ] **Step 4: Correr tests hasta pasar** — Run: `pytest tests/domain/test_rules.py -v`
Expected: 9 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/domain/rules.py backend/tests/domain/test_rules.py
git commit -m "feat(domain): invariantes de serie temporal (muerte, censo, contraccion)"
```

---

### Task 4: Column mapping versionado (el único que conoce los typos del archivo)

**Files:**
- Create: `backend/src/agrosense/adapters/ingester/column_mapping.py`
- Test: `backend/tests/ingester/test_column_mapping.py`

**Interfaces:**
- Produces:
  - `MAPPING_VERSION = "2026-09-anexo1"` (para provenance).
  - `def map_columns(df_columns: list[str]) -> dict[str, str]` — devuelve `{nombre_real_del_archivo: nombre_canonico}` para las columnas que reconoce; ignora las desconocidas (las registra en `unmapped` con logging).
  - Nombres canónicos: `tree_id, plot_id, locality, species, family, common_name, guild, coord_x, coord_y, elevation_m, campaign, height_m, crown_diameter_m, dap_cm, alive, phytosanitary, colonization`.
  - Constantes de alias (subset): `"ID_MUEST" → tree_id`, `"ID Parcela" → plot_id`, `"LOCALIDAD" → locality`, `"Especie_M1" → species`, `"Familia" → family`, `"NombCom_M1" → common_name`, `"Altura" → elevation_m` (columna real del anexo: `Altura` ES elevación en metros — verificar contra dataset), `"Coord_X" → coord_x`, `"Coord_Y" → coord_y`, y por campaña k=1..4: `"Altura total (m)_M{k}" → height_m` (con campaign=k), `"Diámetro. Copa (m)_M{k}" → crown_diameter_m`, `"DAP (CM)" / "DAP (CM) M3" / "DAP M4" → dap_cm`, `"Sobrevivemcia M1" / "Sobrevivencia M{k}" → alive`, `"Estado Fitosanitario_M{k}" → phytosanitary`, `"Colonizació\nEpífitas v" → colonization`.
  - `def parse_alive(raw) -> bool | None`: `"Vivo" → True`, `"Muerto" → False`, `NaN/" "/"NaN" → None`.
  - `def parse_status(raw_dap, alive) -> StatusSemantic`: dap>0 y alive ⇒ `MEDIDO`; dap en {0, None} con árbol censado ⇒ `BAJO_UMBRAL_DAP`; fila completa vacía ⇒ `SIN_CENSO` (lo decide `wide_to_long`, esta función recibe el flag `censused`).

- [ ] **Step 1: Escribir tests fallidos** — `backend/tests/ingester/test_column_mapping.py`

```python
import math

from agrosense.adapters.ingester.column_mapping import (
    MAPPING_VERSION,
    map_columns,
    parse_alive,
)


def test_maps_real_annex_columns():
    cols = [
        "ID_MUEST", "ID Parcela", "LOCALIDAD", "Especie_M1", "Familia", "NombCom_M1",
        "Altura", "Coord_X", "Coord_Y",
        "Altura total (m)_M1", "Altura total (m)_M2", "Altura total (m)_M3", "Altura total (m)_M4",
        "Diámetro. Copa (m)_M1", "Diámetro. Copa (m)_M2",
        "DAP (CM)", "DAP (CM) M3", "DAP M4",
        "Sobrevivemcia M1", "Sobrevivencia M2", "Sobrevivencia M3", "Sobrevivencia M4",
        "Estado Fitosanitario_M1", "Estado Fitosanitario_M2",
        "ColumnaRara", "OtraDesconocida",
    ]
    mapping = map_columns(cols)
    assert mapping["ID_MUEST"] == "tree_id"
    assert mapping["LOCALIDAD"] == "locality"
    assert mapping["Altura total (m)_M3"] == "height_m"
    assert mapping["DAP (CM) M3"] == "dap_cm"
    assert mapping["Sobrevivemcia M1"] == "alive"        # typo real del archivo
    assert mapping["DAP (CM)"] == "dap_cm"
    assert mapping["Estado Fitosanitario_M2"] == "phytosanitary"
    assert "ColumnaRara" not in mapping
    assert MAPPING_VERSION == "2026-09-anexo1"


def test_parse_alive_semantics():
    assert parse_alive("Vivo") is True
    assert parse_alive("Muerto") is False
    assert parse_alive(" ") is None
    assert parse_alive("NaN") is None
    assert parse_alive(float("nan")) is None
    assert parse_alive(None) is None
```

- [ ] **Step 2: Verificar fallo** — Run: `pytest tests/ingester/test_column_mapping.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implementar `column_mapping.py`**

```python
"""Unico lugar del sistema que conoce los nombres REALES del archivo de
campo (typos incluidos: 'Sobrevivemcia M1'). Versionado para provenance
(ADR-004). Las campanas M1..M4 comparten nombres canonicos; la campana
se extrae del sufijo _M{k}."""
import math

MAPPING_VERSION = "2026-09-anexo1"

# (nombre real exacto, canonico, campaign o None si fijo)
_ALIASES: list[tuple[str, str, int | None]] = [
    ("ID_MUEST", "tree_id", None),
    ("ID Parcela", "plot_id", None),
    ("LOCALIDAD", "locality", None),
    ("Especie_M1", "species", None),
    ("Familia", "family", None),
    ("NombCom_M1", "common_name", None),
    ("Gremio ecológico de la ", "guild", None),   # truncada en el archivo real
    ("Altura", "elevation_m", None),               # ojo: en el anexo 'Altura' es elevacion
    ("Coord_X", "coord_x", None),
    ("Coord_Y", "coord_y", None),
]
for k in range(1, 5):
    _ALIASES += [
        (f"Altura total (m)_M{k}", "height_m", k),
        (f"Diámetro. Copa (m)_M{k}", "crown_diameter_m", k),
        (f"Estado Fitosanitario_M{k}", "phytosanitary", k),
        (f"Sobrevivencia M{k}", "alive", k),
        (f"DAP (CM) M{k}", "dap_cm", k),
    ]
_ALIASES += [
    ("Sobrevivemcia M1", "alive", 1),   # typo REAL del archivo
    ("DAP (CM)", "dap_cm", 1),
    ("DAP M4", "dap_cm", 4),
    ("Colonizació\nEpífitas v", "colonization", None),
]


def map_columns(df_columns: list[str]) -> dict[str, str]:
    """Devuelve {nombre_real: canonico} solo para columnas reconocidas."""
    known = {real: canonical for real, canonical, _ in _ALIASES}
    return {c: known[c] for c in df_columns if c in known}


def parse_alive(raw) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, float) and math.isnan(raw):
        return None
    s = str(raw).strip()
    if s in ("", "NaN", "nan", "None"):
        return None
    if s == "Vivo":
        return True
    if s == "Muerto":
        return False
    return None
```

- [ ] **Step 4: Correr tests hasta pasar** — Run: `pytest tests/ingester/test_column_mapping.py -v` → 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/src/agrosense/adapters/ingester/column_mapping.py backend/tests/ingester/test_column_mapping.py
git commit -m "feat(ingester): column mapping versionado del formato ancho real"
```

---

### Task 5: Transformación ancho → long y orquestación (ingest)

**Files:**
- Create: `backend/src/agrosense/adapters/ingester/wide_to_long.py`
- Create: `backend/src/agrosense/adapters/ingester/ingest.py`
- Test: `backend/tests/ingester/test_ingest.py`

**Interfaces:**
- Consumes: Task 2 (entities, errors), Task 3 (`validate_tree_observations`), Task 4 (`map_columns`, `parse_alive`, `MAPPING_VERSION`).
- Produces:
  - `@dataclass IngestResult: trees: list[Tree]; observations: list[Observation]; warnings: list[SuspiciousContractionWarning]; mapping_version: str`
  - `def ingest_wide(df: pd.DataFrame) -> IngestResult` — interfaz del módulo. Lanza `DomainError` con contexto (tree_id/campaign reales) ante invariante dura. Acepta DataFrame YA leído (el CLI/endpoint futuro decide de dónde).

**Reglas de transformación (ADR-004):**
- Una fila del ancho = un árbol con hasta 4 observaciones (una por campaña con columnas M{k}).
- `sin_censo` de campaña k = TODAS las columnas M{k} del árbol vacías (NaN o `' '`).
- Especie/identidad vienen de columnas fijas (una por árbol). Mismatch de especie entre filas con mismo tree_id ⇒ `SpeciesMismatchError` (no puede ocurrir en formato ancho de 1 fila por árbol, pero el contrato lo cubre para CSV long futuros).
- DAP por campaña: `>0` ⇒ MEDIDO; `0` o vacío con árbol censado ⇒ BAJO_UMBRAL_DAP. Alturas vacías con censo ⇒ altura None (censado sin esa medida).
- Después de construir todos los árboles: `validate_tree_observations` por árbol; warnings se acumulan (NO abortan); DomainError aborta todo.

- [ ] **Step 1: Escribir tests fallidos** — `backend/tests/ingester/test_ingest.py`

```python
import pandas as pd
import pytest

from agrosense.adapters.ingester.ingest import ingest_wide
from agrosense.adapters.ingester.column_mapping import MAPPING_VERSION
from agrosense.domain.entities import StatusSemantic
from agrosense.domain.errors import DeathViolationError


def make_wide_df(rows: list[dict]) -> pd.DataFrame:
    base = {
        "ID_MUEST": "T1", "ID Parcela": 1, "LOCALIDAD": "Guayabal",
        "Especie_M1": "Quercus humboldtii", "Familia": "Fagaceae",
        "NombCom_M1": "Roble", "Altura": 2700, "Coord_X": 1.0, "Coord_Y": 2.0,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def test_wide_to_long_basic():
    df = make_wide_df([{
        "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
        "Altura total (m)_M2": 0.3, "Sobrevivencia M2": "Vivo",
        "Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo",
        "Altura total (m)_M4": 0.5, "Sobrevivencia M4": "Vivo",
        "DAP (CM)": 0.0,
    }])
    result = ingest_wide(df)
    assert len(result.trees) == 1
    assert len(result.observations) == 4
    obs_by_campaign = {o.campaign: o for o in result.observations}
    assert obs_by_campaign[2].height_m == pytest.approx(0.3)
    assert obs_by_campaign[1].dap_status == StatusSemantic.BAJO_UMBRAL_DAP
    assert result.mapping_version == MAPPING_VERSION


def test_sin_censo_campaign_excluded():
    df = make_wide_df([{
        # M1 y M2 completamente vacias -> sin censo
        "Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo",
        "Altura total (m)_M4": 0.5, "Sobrevivencia M4": "Vivo",
    }])
    result = ingest_wide(df)
    campaigns = {o.campaign for o in result.observations}
    assert campaigns == {3, 4}


def test_dead_tree_valid():
    df = make_wide_df([{
        "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Vivo",
        "Altura total (m)_M2": 0.25, "Sobrevivencia M2": "Muerto",
        "Altura total (m)_M3": 0.25, "Sobrevivencia M3": "Muerto",
        "Altura total (m)_M4": 0.25, "Sobrevivencia M4": "Muerto",
    }])
    result = ingest_wide(df)
    assert len(result.observations) == 4


def test_dead_revives_rejected_with_context():
    df = make_wide_df([{
        "Altura total (m)_M1": 0.2, "Sobrevivemcia M1": "Muerto",
        "Altura total (m)_M2": 0.3, "Sobrevivencia M2": "Vivo",
        "Altura total (m)_M3": 0.4, "Sobrevivencia M3": "Vivo",
        "Altura total (m)_M4": 0.5, "Sobrevivencia M4": "Vivo",
    }])
    with pytest.raises(DeathViolationError) as exc_info:
        ingest_wide(df)
    assert "T1" in str(exc_info.value)


def test_contraction_warns_but_ingests():
    df = make_wide_df([{
        "Altura total (m)_M1": 0.30, "Sobrevivemcia M1": "Vivo",
        "Altura total (m)_M2": 0.20, "Sobrevivencia M2": "Vivo",
        "Altura total (m)_M3": 0.30, "Sobrevivencia M3": "Vivo",
        "Altura total (m)_M4": 0.35, "Sobrevivencia M4": "Vivo",
    }])
    result = ingest_wide(df)
    assert len(result.warnings) == 1
    assert len(result.observations) == 4


@pytest.mark.skipif(
    not __import__("pathlib").Path("data/raw/anexo1.xlsx").exists(),
    reason="dataset de referencia local ausente",
)
def test_real_annex_ingests():
    """E2E contra el dataset real: 856 arboles, sin errores de dominio duros."""
    from tests_helpers import read_reference_dataset  # helper del test
    df = read_reference_dataset()
    result = ingest_wide(df)
    assert len(result.trees) == 856
    assert all(o.dap_status in list(StatusSemantic) for o in result.observations)
    # los warnings de contraccion son esperados (~13 casos documentados)
    assert 0 < len(result.warnings) < 50
```

- [ ] **Step 2: Verificar fallo** — Run: `pytest tests/ingester/test_ingest.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implementar `wide_to_long.py`**

```python
"""Transformacion ancho -> list[Tree] + list[Observation] (ADR-004).
Pydantic valida construccion; rules.py valida series; aqui solo traducimos."""
import math

import pandas as pd

from agrosense.adapters.ingester.column_mapping import map_columns, parse_alive
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.errors import SpeciesMismatchError
from agrosense.domain.rules import validate_tree_observations
from agrosense.domain.errors import SuspiciousContractionWarning


def _is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    return isinstance(v, str) and v.strip() == ""


def _num(v: float | None) -> float | None:
    return None if _is_blank(v) else float(v)


CAMPAIGN_SUFFIX_COLS = {"height_m", "crown_diameter_m", "dap_cm", "alive",
                        "phytosanitary"}


def wide_to_long(df: pd.DataFrame) -> tuple[list[Tree], list[Observation], list[SuspiciousContractionWarning]]:
    trees: list[Tree] = []
    observations: list[Observation] = []
    all_warnings: list[SuspiciousContractionWarning] = []

    alias_to_canonical_campaign: dict[str, tuple[str, int | None]] = {}
    for real, canonical, campaign in _iter_aliases():
        alias_to_canonical_campaign[real] = (canonical, campaign)

    # Columnas fijas (una por arbol)
    fixed_cols = {r: c for r, (c, k) in alias_to_canonical_campaign.items() if k is None}

    # Columnas por campana: canonical -> {campaign: real_col}
    per_campaign: dict[str, dict[int, str]] = {}
    for real, (canonical, campaign) in alias_to_canonical_campaign.items():
        if campaign is not None:
            per_campaign.setdefault(canonical, {})[campaign] = real

    species_by_tree: dict[str, str] = {}

    for _, row in df.iterrows():
        tree_id = str(row[fixed_cols_inv(fixed_cols, "tree_id")])
        species = str(row[fixed_cols_inv(fixed_cols, "species")]).strip()
        if tree_id in species_by_tree and species_by_tree[tree_id] != species:
            raise SpeciesMismatchError(tree_id, species, species_by_tree[tree_id])
        species_by_tree[tree_id] = species

        tree = Tree(
            tree_id=tree_id,
            species=species,
            family=_clean(row, fixed_cols, "family"),
            common_name=_clean(row, fixed_cols, "common_name"),
            guild=_clean(row, fixed_cols, "guild"),
            plot_id=_clean(row, fixed_cols, "plot_id"),
            locality=_clean(row, fixed_cols, "locality"),
            coord_x=_num(row[fixed_cols_inv(fixed_cols, "coord_x")]) if fixed_cols_inv(fixed_cols, "coord_x") in row.index else None,
            coord_y=_num(row[fixed_cols_inv(fixed_cols, "coord_y")]) if fixed_cols_inv(fixed_cols, "coord_y") in row.index else None,
            elevation_m=_num(row[fixed_cols_inv(fixed_cols, "elevation_m")]) if fixed_cols_inv(fixed_cols, "elevation_m") in row.index else None,
        )
        trees.append(tree)

        tree_obs: list[Observation] = []
        for campaign in (1, 2, 3, 4):
            cols = {c: per_campaign.get(c, {}).get(campaign) for c in CAMPAIGN_SUFFIX_COLS}
            values = {c: row[real] if real in row.index else None for c, real in cols.items()}
            censused = any(not _is_blank(v) for v in values.values())
            if not censused:
                continue  # sin_censo: no hay Observation

            dap_raw = values.get("dap_cm")
            dap = _num(dap_raw)
            alive = parse_alive(values.get("alive"))

            obs = Observation(
                tree_id=tree_id,
                campaign=campaign,
                height_m=_num(values.get("height_m")),
                crown_diameter_m=_num(values.get("crown_diameter_m")),
                dap_cm=dap if (dap is not None and dap > 0) else None,
                dap_status=(
                    StatusSemantic.MEDIDO
                    if dap is not None and dap > 0
                    else StatusSemantic.BAJO_UMBRAL_DAP
                ),
                phytosanitary=_clean_value(values.get("phytosanitary")),
                alive=alive,
                colonization=None,
            )
            tree_obs.append(obs)

        all_warnings.extend(validate_tree_observations(tree, tree_obs))
        observations.extend(tree_obs)

    return trees, observations, all_warnings


def _iter_aliases():
    from agrosense.adapters.ingester import column_mapping as cm
    return cm._ALIASES


def fixed_cols_inv(fixed_cols: dict[str, str], canonical: str) -> str:
    for real, c in fixed_cols_cols(fixed_cols).items():
        if c == canonical:
            return real
    raise KeyError(canonical)


def fixed_cols_cols(fixed_cols):
    return fixed_cols
```

NOTA PARA EL IMPLEMENTADOR: el esqueleto de arriba tiene helpers confusos
(`fixed_cols_inv` iterando dicts). Simplifica: construye un dict inverso
`canonical -> real_col` una sola vez antes del loop de filas:
`inv = {c: r for r, c in fixed_cols.items()}` y úsalo directo. La lógica de
negocio (sin_censo, StatusSemantic, muerte) es el contrato; la estética
del helper no. Escribe el código LIMPIO que pase los tests.

- [ ] **Step 4: Implementar `ingest.py` (orquestador fino)**

```python
"""Interfaz del modulo ingester (ADR-004)."""
from dataclasses import dataclass, field

import pandas as pd

from agrosense.adapters.ingester.column_mapping import MAPPING_VERSION
from agrosense.adapters.ingester.wide_to_long import wide_to_long
from agrosense.domain.entities import Observation, Tree
from agrosense.domain.errors import SuspiciousContractionWarning


@dataclass
class IngestResult:
    trees: list[Tree]
    observations: list[Observation]
    warnings: list[SuspiciousContractionWarning] = field(default_factory=list)
    mapping_version: str = MAPPING_VERSION


def ingest_wide(df: pd.DataFrame) -> IngestResult:
    trees, observations, warnings = wide_to_long(df)
    return IngestResult(
        trees=trees, observations=observations,
        warnings=warnings, mapping_version=MAPPING_VERSION,
    )
```

- [ ] **Step 5: Helper del test real** — `backend/tests/ingester/tests_helpers.py` (o ajusta el import del test):

```python
from pathlib import Path

import pandas as pd

REFERENCE_PATH = Path(__file__).parents[3] / "data" / "raw" / "anexo1.xlsx"


def read_reference_dataset() -> pd.DataFrame:
    return pd.read_excel(REFERENCE_PATH, sheet_name="Monitoreo_4")
```

Y en `backend/`: crear `data/raw/` (gitignored), copiar el Anexo 1 como
`anexo1.xlsx`. El test del dataset real depende de ese archivo local.

- [ ] **Step 6: Correr tests sintéticos hasta pasar** — Run: `pytest tests/ingester/ -v -k "not real_annex"`
Expected: 5 PASSED.

- [ ] **Step 7: Correr el test E2E real** — Run: `pytest tests/ingester/test_ingest.py::test_real_annex_ingests -v`
Expected: PASSED con 856 árboles. Si falla: los mensajes de dominio dicen exactamente qué árbol/invariante — corregir el mapping o debatir si es dato real inválido (documentar en ese caso).

- [ ] **Step 8: Commit**

```bash
git add backend/src/agrosense/adapters/ingester/ backend/tests/ingester/
git commit -m "feat(ingester): ancho->long canonico con invariantes y StatusSemantic"
```

---

### Task 6: CLI de demostración (el slice es demostrable por sí solo)

**Files:**
- Create: `backend/src/agrosense/adapters/ingester/cli.py`
- Test: `backend/tests/ingester/test_cli.py`

**Interfaces:**
- Consumes: `ingest_wide`.
- Produces: `python -m agrosense.adapters.ingester.cli <archivo.xlsx> [--sheet Monitoreo_4]` — imprime resumen: árboles, observaciones por campaña, muertes, warnings, versión de mapping; exit code 1 con error de dominio legible.

- [ ] **Step 1: Test fallido** — `backend/tests/ingester/test_cli.py`

```python
import subprocess
import sys


def test_cli_help():
    r = subprocess.run(
        [sys.executable, "-m", "agrosense.adapters.ingester.cli", "--help"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "archivo" in (r.stdout + r.stderr).lower()


def test_cli_missing_file_fails():
    r = subprocess.run(
        [sys.executable, "-m", "agrosense.adapters.ingester.cli", "no_existe.xlsx"],
        capture_output=True, text=True,
    )
    assert r.returncode == 1
```

- [ ] **Step 2: Verificar fallo** → Run: `pytest tests/ingester/test_cli.py -v`

- [ ] **Step 3: Implementar `cli.py`**

```python
"""CLI de demostracion del ingester (slice 1 demostrable por si solo)."""
import argparse
import sys
from collections import Counter

import pandas as pd

from agrosense.adapters.ingester.ingest import ingest_wide
from agrosense.domain.errors import DomainError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingere formato ancho de campo a long canonico")
    parser.add_argument("archivo", help="Archivo .xlsx del monitoreo")
    parser.add_argument("--sheet", default="Monitoreo_4", help="Nombre de la hoja")
    args = parser.parse_args(argv)

    try:
        df = pd.read_excel(args.archivo, sheet_name=args.sheet)
    except FileNotFoundError:
        print(f"ERROR: archivo no encontrado: {args.archivo}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: no se pudo leer el archivo: {e}", file=sys.stderr)
        return 1

    try:
        result = ingest_wide(df)
    except DomainError as e:
        print(f"DOMINIO: {e}", file=sys.stderr)
        return 1

    deaths = sum(1 for o in result.observations if o.alive is False)
    by_campaign = Counter(o.campaign for o in result.observations)
    print(f"Arboles: {len(result.trees)}")
    print(f"Observaciones: {len(result.observations)}  {dict(sorted(by_campaign.items()))}")
    print(f"Muertes registradas: {deaths}")
    print(f"Warnings de contraccion: {len(result.warnings)}")
    print(f"Mapping version: {result.mapping_version}")
    for w in result.warnings[:5]:
        print(f"  WARN: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Correr tests** — Run: `pytest tests/ingester/test_cli.py -v` → 2 PASSED.

- [ ] **Step 5: Demostración real** — Run: `python -m agrosense.adapters.ingester.cli ../data/raw/anexo1.xlsx` (desde `backend/`).
Expected: `Arboles: 856`, observaciones ~2,700+, muertes ~400 (138 M4 + previas), warnings 1-20.

- [ ] **Step 6: Commit**

```bash
git add backend/src/agrosense/adapters/ingester/cli.py backend/tests/ingester/test_cli.py
git commit -m "feat(ingester): CLI de demostracion del slice fundacion de datos"
```

---

### Task 7: Lint + verificación final del slice (gate 6 del loop)

**Files:**
- Modify: ninguno (verificación) — salvo fixes que surjan.

**Interfaces:** Ninguna nueva.

- [ ] **Step 1: Lint** — Run: `cd backend && ruff check src tests`
Expected: 0 errores (corrige los que haya).

- [ ] **Step 2: Suite completa** — Run: `pytest -v`
Expected: todos PASSED (incluido el test del dataset real si el archivo local existe).

- [ ] **Step 3: Verificación de arquitectura (regla de dependencias ADR-003)** — Run:

```bash
grep -r "import pandas" src/agrosense/domain/ && echo "VIOLACION: domain importa pandas" || echo "OK: domain limpio"
grep -r "import pydantic" src/agrosense/domain/entities.py > /dev/null && echo "NOTE: pydantic en domain (aceptado por ADR-003: solo validador de construccion, documentado)"
grep -rn "from agrosense.adapters" src/agrosense/domain/ && echo "VIOLACION: domain importa adapters" || echo "OK"
```

Expected: domain sin pandas/sqlalchemy; pydantic solo en entities (decisión documentada en el ADR).

- [ ] **Step 4: Commit final + tag del slice**

```bash
git add -A
git commit -m "chore(slice-1): verify gate completo - lint, tests, dependencias"
```

---

## Self-Review (hecho al escribir)

- **Cobertura del spec:** StatusSemantic (§1 domain) → Tasks 2,4,5; invariantes 1-6 (§2) → Tasks 2,3,5; errores (§5) → Task 2; formato ancho→long (ADR-004) → Tasks 4,5; sin imputación → Task 5 (solo traducción); rechazo completo ante error → Task 5 (excepción aborta). UC2 completo requiere API — es el SIGUIENTE slice.
- **Placeholders:** ninguno; los snippets de código son completos. El esqueleto `wide_to_long` de Task 5 trae nota explícita para limpiar helpers (contrato = tests).
- **Consistencia de tipos:** `IngestResult` idéntico en Task 5 uso y Task 6 consumo; `StatusSemantic` mayúsculas consistente; `parse_alive` firma única.

## Nota de alcance

Este plan cubre el slice 1 (fundación de datos, sin API/DB). El slice 2 (persistencia + UC1/UC2 con API) y el slice 3 (análisis de mortalidad) se planifican al entrar al loop de nuevo, cada uno con su propio plan corto.
