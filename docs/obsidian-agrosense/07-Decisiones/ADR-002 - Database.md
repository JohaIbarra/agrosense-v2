---
aliases: [ADR-002, Database, Supabase, PostgreSQL]
tags: [adr, database]
status: aceptado
fecha: 2024-09-12
decision: "Supabase PostgreSQL (sa-east-1)"
rationale: "Resuelve seams de Auth (GoTrue) y Storage (S3) sin integraciones adicionales"
---

# ADR-002: Base de Datos

> [!abstract] Supabase PostgreSQL
> **Estado**: ✅ Aceptado

---

## Contexto

Necesitamos una base de datos para persistir datos de monitoreo,
proyectos y campañas. Debe soportar auth y storage en el futuro.

## Decisión

**Supabase PostgreSQL** (sa-east-1) como database principal.

## Alternativas Consideradas

| Opción | Pros | Contras | Veredicto |
|---|---|---|---|
| **Supabase** | Auth (GoTrue) + Storage (S3) nativos | Session pooler (RTT) | ✅ Elegido |
| **Neon** | Branching, serverless | Sin auth/storage nativos | Rechazado |
| **SQLite** | Simple, sin servidor | No escalable, sin auth | Solo tests |

## Razón Principal

> [!important] Supabase resuelve 2 seams futuros
> 1. **Auth**: GoTrue maneja usuarios sin código extra
> 2. **Storage**: S3-compatible para archivos de monitoreo

Neon es mejor para DB pura, pero Supabase resuelve más
problemas del dominio sin integraciones adicionales.

## Consecuencias

- Session pooler tiene ~200ms RTT (problema conocido)
- Tests usan SQLite (no Supabase) para evitar latencia
- Auth se implementará en slice futuro
- Storage se usará para archivos de monitoreo

---

## Configuración

```env
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
```

> [!warning] DNS intermitente
> El pooler a veces falla resolución DNS. Reintentar si hay errores.

---

## Links

- [[Sistema]] — Arquitectura
- [[Base de Datos]] — Schema
- [[Setup Técnico]] — Configuración
