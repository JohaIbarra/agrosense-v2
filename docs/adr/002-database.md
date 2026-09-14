# ADR-002 — Base de datos y plataforma: PostgreSQL managed (Supabase)

- **Estado:** Aceptado (revisado; reemplaza la redacción inicial "Neon o Supabase" sin desempate)
- **Fecha:** 2026-09-14 (revisión 2026-09-14 tras análisis comparativo real)

## Contexto

Requisitos reales (docs/01-discovery.md): multi-proyecto, datasets inmutables
por campaña, queries analíticas, deploy cloud gratuito, sin auth en MVP pero
**diseñado para añadirla después**, archivos crudos versionados con hash
(ADR-004), equipo = 1 dev + agente, dataset pequeño (~1 MB).

## Opciones consideradas

1. **Supabase (Postgres managed + plataforma)** ✅
2. Neon (Postgres serverless puro)
3. SQLite en disco del servicio
4. Archivos CSV por proyecto (sin DB)

## Análisis Neon vs Supabase (el que faltaba en la revisión inicial)

| Criterio | Neon | Supabase |
|---|---|---|
| Auth futura (requisito diferido del discovery) | no incluida → integrar terceros | GoTrue incluida, 50k MAU free |
| Storage crudo de campañas (ADR-004) | no incluido → S3 aparte | Storage S3-compatible, 1GB free |
| DB free tier | 0.5 GB | 500 MB (sobra 3 órdenes de magnitud) |
| Cold starts free | autosuspend | pausa 7d inactivo (mitigable) |
| Ventaja única | DB branching para CI/tests | plataforma completa (RLS, realtime, edge) |
| Foco del proveedor | pivot hacia AI-agents | core estable, comunidad masiva |

## Decisión

**Supabase.** El desempate NO es simplicidad de registro (la revisión
inicial eligió Neon por fricción de onboarding — error de criterio
documentado aquí): es que **dos seams de épicas futuras ya confirmadas
(auth y storage de archivos crudos) están resueltos nativamente**, el free
tier cubre el MVP completo con holgura, y RLS first-class anticipa el
multi-tenant si el producto crece. Neon solo ganaría si el DB branching
para CI fuera crítico hoy — es fase 8, no fase actual.

PostgreSQL sigue siendo la decisión de MOTOR (inalterada): SQLAlchemy +
Alembic + psycopg3, esquema idéntico al de la primera redacción.

## Consecuencias

- Dependencia de proveedor free tier (aceptado; Postgres puro migrable con pg_dump).
- DATABASE_URL SOLO en .env (gitignored), nunca en código.
- El paquete `supabase-py` NO entra al backend: usamos psycopg directo
  (la DB es Postgres normal; Auth/Storage de Supabase solo cuando sus
  épicas lleguen, con sus propios ADRs).
- Tests de integración contra la misma instancia Supabase con cleanup
  por test (o branch dedicado si se adopta branching en fase 8).
