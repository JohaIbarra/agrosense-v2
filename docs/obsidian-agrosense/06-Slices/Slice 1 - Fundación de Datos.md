---
aliases: [Slice 1, Fundación de Datos, Ingesta]
tags: [slice, completado]
status: completado
fecha: 2024-09-14
---

# Slice 1 — Fundación de Datos

> [!abstract] Ingesta wide→long con validación de dominio
> **Estado**: ✅ Completado | **Tests**: 48/48 | **Commits**: 63f7d27..95e824f

---

## Objetivo

Transformar datos de monitoreo de campo (formato Excel wide) a formato
long canónico, con validación de dominio y detección de anomalías.

---

## Qué se construyó

### Domain Layer

| Archivo | Contenido |
|---|---|
| `domain/entities.py` | Observation, Tree, StatusSemantic |
| `domain/errors.py` | DeathViolation, CensusGap, SuspiciousRevival |
| `domain/rules.py` | validate_tree_observations, growth_between |

### Ingesta

| Archivo | Contenido |
|---|---|
| `adapters/ingester/column_mapping.py` | Mapeo de nombres de campo (typos, truncados) |
| `adapters/ingester/wide_to_long.py` | Transformación wide→long |
| `adapters/ingester/ingest.py` | Orquestación (IngestResult) |
| `adapters/ingester/cli.py` | CLI demo |

---

## Validaciones Implementadas

### DAP = 0.0

```python
# 714/717 casos en M1 son DAP = 0.0
# Solo ~3 son bajo umbral real
# → Marcar como "bajo_umbral_dap", NO como medición
```

### Replantación

```python
# Árbol muerto revive (alive: False → True)
# → Registrar warning
# → Verificar evidencia de replanteo
```

### Census Gap

```python
# Salto de campañas (M1 → M4 sin M2/M3)
# → Registrar warning
# → Crecimiento acumulado puede ser engañoso
```

---

## Resultados E2E

| Métrica | Valor |
|---|---|
| Árboles | 856 |
| Observaciones | 3,146 |
| Muertes detectadas | 340 |
| Warnings | 19 |
| Tiempo de ingesta | <2s |

---

## Tests

```
tests/domain/
  test_entities.py      — 10 tests
  test_rules.py         — 11 tests

tests/ingester/
  test_column_mapping.py — 6 tests
  test_ingest.py         — 10 tests (sintéticos)
  test_ingest_real.py    — 2 tests (dataset real)
  test_cli.py            — 3 tests
  test_seam_and_guards.py — 3 tests
  test_contract.py       — 11 tests (schemas)
```

**Total**: 48 tests, todos pasando.

---

## Commits

```
95e824f chore(slice-1): verify gate completo
63f7d27 refactor(ingester): seam publico + guards
```

---

## Lecciones Aprendidas

> [!note] Decisiones clave
> 1. **DAP = 0.0 no es error** — es marker de "bajo umbral"
> 2. **Replantación es warning** — no impide ingesta
> 3. **Column mapping versionado** — para trazabilidad
> 4. **CLI para validación** — ejecución standalone

---

## Links

- [[Slice 2 - Persistencia y API]] — Siguiente
- [[Modelo de Dominio]] — Entidades
- [[ADR-004 - Ingesta de Datos]] — Decisión
- [[Roadmap]] — Timeline
