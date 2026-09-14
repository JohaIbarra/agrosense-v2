# ADR-001 — Stack: FastAPI (Python) + React (TypeScript)

- **Estado:** Aceptado
- **Fecha:** 2026-09-14

## Contexto

v1 usaba FastAPI + React (JS) + scikit-learn. El equipo (1 dev + agente AI)
domina ese stack. Las skills de ML del proyecto (scikit-learn, pandas) son
Python puro. Deploy objetivo: cloud gratuito.

## Opciones consideradas

1. **Mantener FastAPI + React, migrando frontend a TypeScript** ✅
2. Mantener FastAPI + React JS (como v1)
3. Cambiar a Django/Next.js — reescritura completa

## Decisión

FastAPI + React **TypeScript**. Motivo:

- El costo de cambio de stack no compra nada demostrable; el riesgo de v1
  nunca fue el stack, fue el proceso (leakage, preprocessing duplicado).
- Python es requisito para la capa ML (scikit-learn, pandas) — sin discusión.
- TypeScript sí se justifica: la respuesta de análisis es un contrato JSON
  grande y anidado (proyecto → árboles → observaciones → scores). En JS sin
  tipos, cada cambio de backend rompe el frontend silenciosamente (v1
  dependía de `data?.model_metrics ||` en cadena). Los tipos son el contrato
  compartido — regla "el frontend consume el contrato" hecha executable.
- React se mantiene (no Vue/Svelte): el 90% de la UI de dashboards de v1 es
  portable, y el ecosistema de gráficas (recharts) ya está validado.

## Consecuencias

- Migración JSX→TSX en slices nuevos; el código v1 se porta con tipos añadidos.
- Frontend genera tipos desde el schema OpenAPI de FastAPI (una fuente).
