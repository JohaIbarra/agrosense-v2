---
aliases: [ADR-001, Stack, FastAPI, React]
tags: [adr, stack]
status: aceptado
fecha: 2024-09-12
decision: "FastAPI + React TypeScript"
rationale: "Async nativo, OpenAPI automático, tipado estricto y ecosistema sólido"
---

# ADR-001: Stack de Tecnologías

> [!abstract] FastAPI + React TypeScript
> **Estado**: ✅ Aceptado

---

## Contexto

Necesitamos un stack moderno, rápido, bien tipado y con buena
experiencia de desarrollo para el backend y frontend de AgroSense v2.

## Decisión

| Capa | Tecnología | Razón |
|---|---|---|
| Backend | **FastAPI** | Async nativo, OpenAPI automático, Python |
| Frontend | **React TypeScript** | Ecosistema, tipado, componentes |
| DB | **PostgreSQL** (Supabase) | Robusto, extensiones, SQL estándar |

## Alternativas Consideradas

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| Django | Batteries included, admin | Monolico pesado, ORM engorroso | Rechazado |
| Flask | Simple, flexible | Sin OpenAPI, sin async nativo | Rechazado |
| Streamlit | Rápido para prototipos | No es para producción, limitado | Rechazado |
| Vue.js | Simple | Menos ecosistema que React | Rechazado |

## Consecuencias

- OpenAPI se genera automáticamente de FastAPI
- Frontend puede generar tipos desde el schema
- Python 3.12 permite features modernas (match, type hints)
- FastAPI facilita tests con TestClient

---

## Links

- [[Sistema]] — Arquitectura
- [[Setup Técnico]] — Stack detallado
