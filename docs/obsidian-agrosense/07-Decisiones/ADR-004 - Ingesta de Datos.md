---
aliases: [ADR-004, Ingesta, wide-long]
tags: [adr, ingesta]
status: aceptado
fecha: 2024-09-13
decision: "Transformación wide->long en capa de ingesta antes del dominio"
rationale: "Validar reglas de dominio y detectar anomalías tempranamente antes de persistir"
---

# ADR-004: Ingesta de Datos

> [!abstract] wide→long en ingesta
> **Estado**: ✅ Aceptado

---

## Contexto

Los datos de campo llegan en formato Excel wide (una columna por campaña).
Necesitamos transformarlos a formato long para análisis y persistencia.

## Decisión

Transformar **wide→long en la capa de ingesta** (adapters/ingester),
antes de llegar al dominio.

## Alternativas Consideradas

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| **wide→long en ingesta** | Limpio, validado, trazable | Un paso más | ✅ Elegido |
| Directo a DB | Simple | Datos sucios, sin validación | Rechazado |
| En Frontend | Flexible | Lógica de negocio en UI | Rechazado |

## Formato Wide (campo)

```
Árbol | Especie | DAP_M1 | DAP_M2 | DAP_M3 | DAP_M4 | Altura_M1 | ...
A1    | Ceiba   | 0.0    | 5.2    | 6.1    | 7.0    | 3.5       | ...
```

## Formato Long (canónico)

```
tree_id | species | campaign | dap_cm | height_m | alive | ...
A1      | Ceiba   | 1        | 0.0    | 3.5      | True  | ...
A1      | Ceiba   | 2        | 5.2    | 4.1      | True  | ...
```

## Consecuencias

- Validación de dominio en ingesta (no en DB)
- Detección de anomalías antes de persistir
- Trazabilidad de transforms (column_mapping versionado)
- CLI para ejecución standalone

---

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `column_mapping.py` | Mapeo de nombres de campo |
| `wide_to_long.py` | Transformación |
| `ingest.py` | Orquestación |
| `cli.py` | CLI demo |

---

## Links

- [[Slice 1 - Fundación de Datos]] — Implementación
- [[Modelo de Dominio]] — Entidades
