---
aliases: [Setup, Instalación, Stack, Commands]
tags: [tecnico, setup, comandos]
---

# Setup Técnico

> [!abstract] Stack, instalación y comandos útiles
> Todo lo que necesitas para desarrollar en AgroSense v2.

---

## Stack

| Capa | Tecnología | Versión |
|---|---|---|
| Lenguaje | Python | 3.12.1 |
| Backend | FastAPI | latest |
| DB | Supabase PostgreSQL | sa-east-1 |
| ORM | SQLAlchemy | 2.0 |
| Migraciones | Alembic | latest |
| ML | scikit-learn + pandas | latest |
| Frontend | React TypeScript | (futuro) |
| Tests | pytest | latest |
| Lint | ruff | latest |

---

## Instalación

### 1. Clonar el repo

```bash
git clone https://github.com/JohaIbarra/agrosense-v2.git
cd agrosense-v2/backend
```

### 2. Crear entorno virtual (recomendado)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -e ".[dev]"
```

### 4. Configurar .env

```bash
# Crear backend/.env con:
DATABASE_URL=postgresql://postgres.xxx:password@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
```

> [!warning] Nunca subir .env a GitHub
> Ya está en `.gitignore`.

---

## Comandos Útiles

> [[Comandos]] para lista completa

### Desarrollo

```bash
# Correr el servidor
uvicorn agrosense.adapters.api.app:create_app --factory --reload

# CLI de ingesta
python -m agrosense.adapters.ingester.cli data/raw/anexo1.xlsx
```

### Tests

```bash
# Todos los tests (excepto DB remota)
pytest tests/ -v --ignore=tests/db

# Solo tests de API (SQLite en memoria)
pytest tests/api/ -v

# Solo tests de dominio
pytest tests/domain/ -v

# Con cobertura
pytest tests/ --cov=agrosense --cov-report=html
```

### Lint

```bash
# Verificar
ruff check src/ tests/

# Auto-corregir
ruff check src/ tests/ --fix
```

### Base de Datos

```bash
# Crear migración
alembic revision --autogenerate -m "descripcion"

# Aplicar migración
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Git

```bash
# Ver estado
git status

# Ver commits
git log --oneline -10

# Volver a checkpoint
git checkout checkpoint-antes-de-opus
```

---

## Estructura del Proyecto

```
agrosense-v2/
├── backend/
│   ├── src/agrosense/      # Código fuente
│   ├── tests/              # Tests
│   ├── alembic/            # Migraciones
│   ├── data/raw/           # Dataset (gitignored)
│   ├── .env                # Config (gitignored)
│   └── pyproject.toml      # Dependencias
├── docs/                   # Documentación
│   ├── obsidian-agrosense/ # Este vault
│   ├── adr/                # Decisiones de arquitectura
│   ├── 01-discovery.md
│   ├── 02-domain.md
│   └── 03-architecture.md
└── frontend/               # (futuro)
```

---

## Supabase

> [[Base de Datos]] para detalle completo

| Parámetro | Valor |
|---|---|
| Región | sa-east-1 (São Paulo) |
| Puerto session pooler | 5432 |
| Host | `aws-0-sa-east-1.pooler.supabase.com` |
| DB | `postgres` |

> [!warning] DNS intermitente
> El pooler de Supabase a veces falla resolución DNS.
> Si hay errores de conexión, reintentar.

---

## Python Environment

```python
import sys
print(sys.version)
# 3.12.1 (tags/v3.12.1:2305ca5, Dec  7 2023) [MSC v.1937 64 bit (AMD64)]

import platform
print(platform.python_implementation())
# CPython
```

---

## Dependencias Principales

```toml
# pyproject.toml
[project]
dependencies = [
    "pandas>=2.0",
    "pydantic>=2.0",
    "openpyxl>=3.1",
    "fastapi>=0.104",
    "uvicorn[standard]>=0.24",
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "psycopg2-binary>=2.9",
    "python-multipart>=0.0.6",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "ruff>=0.1",
    "httpx>=0.25",  # TestClient
]
```

---

## Links

- [[Comandos]] — Lista completa de comandos
- [[Base de Datos]] — Schema y queries
- [[Sistema]] — Arquitectura
- [[Slice 1 - Fundación de Datos]] — Primera funcionalidad
