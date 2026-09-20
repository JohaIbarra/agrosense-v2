---
aliases: [Home, Inicio, Dashboard]
tags: [home]
cssclass: dashboard
---

# AgroSense v2

> [!info] Plataforma de análisis de restauración ecológica
> Predicción de riesgo de mortalidad · Detección de estancamiento · Analítica de crecimiento

---

## Navegación

| Sección | Descripción |
|---|---|
| [[Overview]] | Qué es AgroSense, por qué existe, roadmap |
| [[Sistema]] | Arquitectura, diagramas, ADRs |
| [[Modelo de Dominio]] | Entidades, reglas, invariantes |
| [[Resumen ML]] | Spike ML, modelos, métricas |
| [[Setup Técnico]] | Stack, instalación, comandos |
| [[Slice 1 - Fundación de Datos]] | Ingesta wide→long |
| [[Slice 2 - Persistencia y API]] | Repos, routes, FastAPI |

---

## Estado del Proyecto

```dataview
TABLE status AS "Estado", fecha AS "Fecha"
FROM "06-Slices"
SORT file.name ASC
```

---

## Últimas Decisiones

```dataview
TABLE decision AS "Decisión", rationale AS "Razón"
FROM "07-Decisiones"
SORT file.ctime DESC
LIMIT 5
```

---

## Links Rápidos

- [[ADR-001 - Stack]] — FastAPI + React TS
- [[ADR-002 - Database]] — Supabase PostgreSQL
- [[ADR-003 - Arquitectura]] — Monolito modular
- [[ADR-004 - Ingesta de Datos]] — wide→long
- [[Roadmap]] — Fases y slices
- [[Comandos]] — Comandos útiles del proyecto

---

## Documentos vivos del repo

> [!tip] Estos NO están en la bóveda: viven en `docs/` y se actualizan con el código
> - `docs/deuda-tecnica.md` — brechas conocidas, cada una con dueño y gate
> - `docs/revision-slice2.md` — hallazgos de la fase 7 y su estado
> - `docs/verificacion-slice2.md` — evidencia de los gates, con comandos y salida
