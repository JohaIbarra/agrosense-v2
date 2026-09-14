# ADR-002 — Base de datos: PostgreSQL (managed free tier)

- **Estado:** Aceptado
- **Fecha:** 2026-09-14

## Contexto

Requisitos reales: multi-proyecto (varios sitios por ingeniero), datasets
inmutables por campaña, queries analíticas por árbol/especie/localidad,
deploy en cloud gratuito, sin auth por ahora. Datasets pequeños (cientos a
miles de filas por campaña).

## Opciones consideradas

1. **PostgreSQL** (Neon/Supabase free tier) ✅
2. SQLite en disco del servicio
3. Solo archivos CSV por proyecto (sin DB)

## Decisión

PostgreSQL managed (Neon o Supabase free tier). Motivo:

- **El volumen NO justifica Postgres; el ciclo de vida sí.** SQLite muere con
  el contenedor en free tiers con disco efímero (Render restartea y pierdes
  todo). Neon/Supabase dan PG persistente gratuito y generoso para este
  tamaño de datos.
- Multi-proyecto con relaciones (proyecto→campaña→árbol→observación) y
  agregaciones analíticas: SQL relacional es la herramienta natural.
- Migraciones con Alembic desde el día 1 (regla del AGENTS.md).
- Los CSV crudos subidos se guardan como **adjunto versionado** (para
  reproducibilidad/provenance), no como fuente de verdad de queries — la DB
  deriva de ellos vía ingester.

## Consecuencias

- Dependencia de un proveedor free tier (aceptado; migrable con pg_dump).
- Se necesita DATABASE_URL en config (nunca en código).
- SQLite queda permitido SOLO en tests locales rápidos vía el mismo esquema
  SQLAlchemy (mismo ORM, dos dialectos).
