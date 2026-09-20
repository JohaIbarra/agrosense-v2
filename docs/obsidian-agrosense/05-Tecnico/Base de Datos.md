---
aliases: [Base de Datos, Database, Schema]
tags: [tecnico, database]
---

# Base de Datos

> [!abstract] Schema de PostgreSQL y queries útiles
> Supabase PostgreSQL sa-east-1

---

## Tablas

```mermaid
erDiagram
    projects ||--o{ campaign_files : tiene
    projects ||--o{ trees : tiene
    trees ||--o{ observations : tiene
    
    projects {
        int id PK
        string name UK
        string locality
        text description
        datetime created_at
    }
    
    campaign_files {
        int id PK
        int project_id FK
        string filename
        string sha256 UK
        string mapping_version
        datetime ingested_at
        int trees
        int observations
        int deaths
    }
    
    trees {
        int id PK
        int project_id FK
        string tree_id
        string species
        string family
        string common_name
        string guild
        string plot_id
        string locality
        float coord_x
        float coord_y
        float elevation_m
    }
    
    observations {
        int id PK
        int tree_row_id FK
        int campaign
        float height_m
        float crown_diameter_m
        float dap_cm
        string dap_status
        string phytosanitary
        bool alive
        json colonization
    }
```

---

## Constraints

| Tabla | Constraint | Tipo |
|---|---|---|
| projects | `name` UNIQUE | Unique |
| campaign_files | `(project_id, sha256)` | Unique |
| trees | `(project_id, tree_id)` | Unique |
| observations | `(tree_row_id, campaign)` | Unique |
| campaign_files | `project_id` FK → projects | CASCADE |
| trees | `project_id` FK → projects | CASCADE |
| observations | `tree_row_id` FK → trees | CASCADE |

---

## Queries Útiles

### Contenido de la DB

```sql
-- Contar proyectos
SELECT count(*) FROM projects;

-- Contar árboles por proyecto
SELECT p.name, count(t.id) as trees
FROM projects p
JOIN trees t ON t.project_id = p.id
GROUP BY p.name;

-- Contar observaciones por proyecto
SELECT p.name, count(o.id) as observations
FROM projects p
JOIN trees t ON t.project_id = p.id
JOIN observations o ON o.tree_row_id = t.id
GROUP BY p.name;
```

### Diagnóstico

```sql
-- Sesiones activas
SELECT pid, state, query
FROM pg_stat_activity
WHERE datname = current_database();

-- Locks
SELECT * FROM pg_locks WHERE NOT granted;

-- Proyectos con datos
SELECT p.id, p.name,
       (SELECT count(*) FROM trees t WHERE t.project_id = p.id),
       (SELECT count(*) FROM observations o
        JOIN trees t ON o.tree_row_id = t.id
        WHERE t.project_id = p.id)
FROM projects p;
```

### Limpieza

```sql
-- Borrar proyecto y sus datos (CASCADE)
DELETE FROM projects WHERE id = 16;

-- Borrar todos los datos (cuidado)
TRUNCATE observations, trees, campaign_files, projects CASCADE;
```

---

## Conexión

```python
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"])
conn.autocommit = True

with conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM projects")
    print(cur.fetchone()[0])

conn.close()
```

---

## Migraciones

```bash
# Crear migración
alembic revision --autogenerate -m "descripcion"

# Aplicar
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## Links

- [[ADR-002 - Database]] — Decisión
- [[Setup Técnico]] — Configuración
- [[Sistema]] — Arquitectura
