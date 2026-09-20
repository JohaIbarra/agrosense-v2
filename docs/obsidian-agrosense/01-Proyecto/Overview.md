---
aliases: [Proyecto, AgroSense, Qué es]
tags: [proyecto, overview]
---

# AgroSense v2 — Overview

> [!abstract] Resumen ejecutivo
> Plataforma web para ingenieros de restauración ecológica que permite
> subir datos de monitoreo de campo, detectar árboles en riesgo, y
> generar analítica de crecimiento por especie y sitio.

---

## Por qué existe (v2 vs v1)

> [!warning] Problemas de v1 que resolvemos
> - **Target leakage**: `altura_actual` contenía al target (muerte)
> - **Split aleatorio**: mismo árbol en train y test
> - **Preprocessing duplicado**: train vs serve divergieron
> - **Pipeline síncrono**: endpoint async bloqueante

v2 corrige todo esto con:
- Preprocessing único compartido (train/serve)
- Split por árbol (nunca el mismo árbol en train y test)
- Spike ML obligatorio antes de construir
- Monolito modular con boundaries claros

---

## Usuarios

| Rol | Qué hace |
|---|---|
| **Ingeniero de campo** | Sube datasets de monitoreo (Excel), ve resultados |
| **Analista** | Consulta dashboards de crecimiento, mortalidad |
| **Administrador** | Gestiona proyectos y campañas |

---

## Fuente de datos

> [!important] Dataset principal
> `Anexo 1 Base de datos 4 MONITOREO.xlsx`
> - Hoja: `Monitoreo_4`
> - 856 árboles, 4 campañas (M1-M4)
> - 42 columnas
> - Región: restauración ecológica

---

## Funcionalidades clave

### 1. Ingesta de datos
- Upload de Excel (formato wide de campo)
- Transformación a formato long canónico
- Validación de dominio (alturas, muertes, replanteo)
- Deduplicación por SHA-256

### 2. Riesgo de mortalidad
- Predicción de muerte por árbol
- Señal validada: estancados ≤5cm tienen 35x más riesgo
- Mortalidad acumulada: 16%

### 3. Detección de estancados/anómalos
- IsolationForest + regla de negocio
- Crecimiento ≈ 0 como indicador

### 4. Analítica de crecimiento
- Dashboards por especie y sitio
- Portado de v1 (lo que funciona)

---

## Roadmap

> [[Roadmap]] para detalle completo

| Fase | Estado | Descripción |
|---|---|---|
| Slice 1 | ✅ | Fundación de datos (ingesta) |
| Slice 2 | 🔄 90% | Persistencia + API (falta gate) |
| Slice 3 | ⬜ | Riesgo de mortalidad |
| Slice 4 | ⬜ | Detección de estancados |
| Slice 5 | ⬜ | Analítica de crecimiento |

---

## Stack

> [[Setup Técnico]] para detalle técnico

| Capa | Tecnología |
|---|---|
| Backend | FastAPI + Python 3.12 |
| DB | Supabase PostgreSQL (sa-east-1) |
| ORM | SQLAlchemy 2.0 + Alembic |
| ML | scikit-learn + pandas |
| Frontend | React TypeScript (futuro) |

---

## Links

- [[Sistema]] — Arquitectura
- [[Modelo de Dominio]] — Entidades y reglas
- [[Resumen ML]] — Modelos y métricas
- [[Roadmap]] — Fases y slices
- [[Comandos]] — Comandos útiles
