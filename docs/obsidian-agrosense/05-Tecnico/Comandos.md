---
aliases: [Comandos, Commands]
tags: [tecnico, comandos]
---

# Comandos Útiles

> [!abstract] Referencia rápida de comandos
> Copia y pega directamente en la terminal.

---

## Desarrollo

```bash
# Correr el servidor de desarrollo
cd backend
uvicorn agrosense.adapters.api.app:create_app --factory --reload

# CLI de ingesta
python -m agrosense.adapters.ingester.cli data/raw/anexo1.xlsx
```

---

## Tests

```bash
# TODO lo local. Nunca toca la red: 166 tests, ~80s
pytest

# El smoke contra Supabase real, a proposito: 4 tests
pytest -m supabase

# Por capa
pytest tests/domain/ tests/ingester/    # sin DB
pytest tests/api/ tests/db/             # SQLite en memoria
pytest tests/architecture/              # reglas de dependencia (AST)

# Los mas lentos, para saber donde se va el tiempo
pytest -q --durations=10

# Un solo test
pytest tests/api/test_review_regressions.py::TestSecondUpload -v
```

> [!danger] No quites el marker
> `addopts = -m "not supabase"` es lo que impide que `pytest` a secas se
> cuelgue contra el pooler. `tests/architecture/test_no_remote_db_by_default.py`
> falla si alguien añade un test que abra la conexion real sin marcarlo.

---

## Seguridad de dependencias

```bash
# Gate 5 de AGENTS.md. Audita el CIERRE, no solo las raices de pyproject:
# auditar solo las raices daba limpio mientras el entorno traia anyio 3.7.1
# con dos CVE.
python -m pip_audit -r requirements.lock.txt
```

---

## Lint

```bash
# Verificar
ruff check src/ tests/

# Auto-corregir
ruff check src/ tests/ --fix

# Verificar solo src
ruff check src/agrosense/
```

---

## Base de Datos

```bash
# Crear migración
alembic revision --autogenerate -m "descripcion"

# Aplicar migración
alembic upgrade head

# Rollback una migración
alembic downgrade -1

# Rollback completo
alembic downgrade base

# Ver historial
alembic history
```

---

## Git

```bash
# Ver estado
git status

# Ver commits recientes
git log --oneline -10

# Ver diffs
git diff

# Volver a checkpoint
git checkout checkpoint-antes-de-opus

# Volver a master
git checkout master

# Crear tag
git tag -a v0.1.0 -m "Slice 1 completo"

# Push
git push origin master

# Push con tags
git push origin --tags
```

---

## Supabase

> [!note] El driver es psycopg3 (ADR-002)
> `session.normalize_database_url()` reescribe la URL de Supabase a
> `postgresql+psycopg://`, asi que el `.env` no necesita el sufijo.

```bash
# Estado de la DB (usa la sesion del proyecto, no psycopg a pelo)
python -c "
from agrosense.adapters.db.session import get_session_factory
from agrosense.adapters.db.models import Project
s = get_session_factory()()
print('proyectos:', s.query(Project).count()); s.close()
"

# Borrar un proyecto de pruebas (cascade limpia arboles y observaciones)
python -c "
from agrosense.adapters.db.session import get_session_factory
from agrosense.adapters.db.models import Project
s = get_session_factory()()
for p in s.query(Project).filter(Project.name.like('test%')).all(): s.delete(p)
s.commit(); s.close()
"

# Deriva entre models y migracion aplicada
alembic check

# Diagnostico DNS (el pooler falla intermitentemente: reintentar)
nslookup aws-0-sa-east-1.pooler.supabase.com
```

---

## Entorno

```bash
# Verificar Python
python --version

# Verificar pip
pip --version

# Instalar dependencias
pip install -e ".[dev]"

# Verificar ruff
ruff --version

# Verificar pytest
pytest --version
```

---

## Atajos de PowerShell

```powershell
# Ejecutar varios comandos
cmd1; if ($?) { cmd2 }

# Buscar archivos
Get-ChildItem -Recurse -Filter "*.py"

# Verificar contenido
Select-String -Path "archivo.py" -Pattern "def "
```

---

## Links

- [[Setup Técnico]] — Instalación
- [[Sistema]] — Arquitectura
