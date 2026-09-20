---
aliases: [Arquitectura, Sistema, Architecture]
tags: [arquitectura, sistema]
---

# Arquitectura del Sistema

> [!abstract] Visión general
> Monolito modular (ADR-003) con separación por capas:
> `domain/` → `application/` → `adapters/`

---

## Diagrama de Arquitectura

```mermaid
graph TB
    subgraph "Frontend (futuro)"
        UI[React TypeScript]
    end
    
    subgraph "Backend - FastAPI"
        API[adapters/api<br/>routes + schemas]
        APP[application/<br/>use cases]
        DOM[domain/<br/>entidades + reglas]
        DB[adapters/db<br/>repository + models]
        ING[adapters/ingester<br/>wide→long]
        ML[ml/<br/>modelos]
    end
    
    subgraph "Database"
        PG[(Supabase PostgreSQL)]
    end
    
    UI -->|HTTP| API
    API --> APP
    APP --> DOM
    APP --> DB
    APP --> ING
    APP --> ML
    DB --> PG
    
    style DOM fill:#f9f,stroke:#333
    style APP fill:#bbf,stroke:#333
    style API fill:#bfb,stroke:#333
    style DB fill:#fbb,stroke:#333
    style ING fill:#fbf,stroke:#333
    style ML fill:#bff,stroke:#333
```

---

## Regla de Dependencia

> [!important] ADR-003
> La dependencia va hacia adentro:
> - `adapters/` puede importar `application/` y `domain/`
> - `application/` puede importar `domain/`
> - `domain/` NO importa nada externo
> - `ml/` solo importa `domain/`

```mermaid
graph LR
    ADAPTERS --> APPLICATION
    APPLICATION --> DOMAIN
    ML --> DOMAIN
    
    style DOMAIN fill:#f9f,stroke:#333
```

---

## Capas

| Capa | Directorio | Responsabilidad |
|---|---|---|
| **Dominio** | `domain/` | Entidades, reglas, invariantes, errores |
| **Aplicación** | `application/` | Casos de uso (orquestación) |
| **Adapters API** | `adapters/api/` | FastAPI routes, schemas, error mapping |
| **Adapters DB** | `adapters/db/` | SQLAlchemy models, repositories, session |
| **Adapters Ingesta** | `adapters/ingester/` | Transformación wide→long |
| **ML** | `ml/` | Modelos, entrenamiento, inferencia |

---

## ADRs

| ADR | Decisión | Estado |
|---|---|---|
| [[ADR-001 - Stack]] | FastAPI + React TS | ✅ Aceptado |
| [[ADR-002 - Database]] | Supabase PostgreSQL | ✅ Aceptado |
| [[ADR-003 - Arquitectura]] | Monolito modular | ✅ Aceptado |
| [[ADR-004 - Ingesta de Datos]] | wide→long en ingesta | ✅ Aceptado |

---

## Estructura de Archivos

```
agrosense-v2/
├── backend/
│   ├── src/agrosense/
│   │   ├── domain/
│   │   │   ├── entities.py
│   │   │   ├── errors.py
│   │   │   └── rules.py
│   │   ├── application/
│   │   │   └── use_cases/
│   │   │       ├── create_project.py
│   │   │       └── upload_campaign.py
│   │   ├── adapters/
│   │   │   ├── api/
│   │   │   │   ├── app.py
│   │   │   │   ├── deps.py
│   │   │   │   ├── errors.py
│   │   │   │   ├── schemas.py
│   │   │   │   └── routes/
│   │   │   │       └── projects.py
│   │   │   ├── db/
│   │   │   │   ├── models.py
│   │   │   │   ├── session.py
│   │   │   │   └── repository.py
│   │   │   └── ingester/
│   │   │       ├── column_mapping.py
│   │   │       ├── wide_to_long.py
│   │   │       ├── ingest.py
│   │   │       └── cli.py
│   │   └── ml/  (futuro)
│   ├── tests/
│   ├── alembic/
│   └── pyproject.toml
├── docs/
│   ├── 01-discovery.md
│   ├── 02-domain.md
│   ├── 03-architecture.md
│   └── adr/
└── frontend/ (futuro)
```

---

## Seguridad

> [!warning] Reglas de seguridad
> - Secrets nunca en source control
> - `.env` gitignored
> - Autenticación y autorización explícitas
> - Input del usuario no es confiable
> - Uploads validados
> - Errores externos sanitizados

---

## Links

- [[ADR-001 - Stack]]
- [[ADR-002 - Database]]
- [[ADR-003 - Arquitectura]]
- [[ADR-004 - Ingesta de Datos]]
- [[Modelo de Dominio]]
- [[Setup Técnico]]
