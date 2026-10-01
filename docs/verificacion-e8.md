# Verificación — E8 · Riesgo de mortalidad (2026-09-30)

Rama `e8-mortalidad`. Evidencia de los gates de AGENTS.md §Completion, con los comandos usados.

| # | Gate | Comando | Resultado |
|---|---|---|---|
| 1 | Tests backend | `cd backend && python -m pytest -q` | ✅ 862 passed, 45 deselected (smoke de Supabase) |
| 1 | Tests frontend | `cd frontend && npm run test` | ✅ 131 passed |
| 1 | E2E | `cd frontend && npm run e2e` | ✅ 3 passed (incluye el panel de mortalidad en M3) |
| 2 | Lint | `ruff check src tests scripts` · `npm run lint` | ✅ limpio · 0 errores (6 avisos previos) |
| 3 | Tipos | `python -m mypy` · `tsc` (build y `tsconfig.e2e.json`) | ✅ 0 errores |
| 4 | Build | `npm run build` · `pip wheel` (CI) · `docker build` (CI) | ✅ local; imagen verificada en CI |
| 5 | Seguridad | `pip-audit -r requirements.lock.txt` · `npm audit --omit=dev` | ✅ sin vulnerabilidades |
| 6 | Arquitectura | `tests/architecture` (inferencia y entrenamiento propio en Python puro; adapters no ve entrenamiento) | ✅ |
| 7 | Revisión | Revisión independiente automática (fase 7) | ✅ 1 hallazgo medio corregido con regresión; 1 bajo corregido; 1 bajo a deuda J |

## ML eval gate

- `python scripts/train_mortality_general.py --data data/raw/anexo1.xlsx` → gate PASA
  (lift/azar: Anexo 1 1.615, Werden 2018 1.467, Werden 2020 1.287; coeficiente −1.04 a −1.18).
- `... --check` → «Reproducible: el reentrenamiento coincide con el artefacto versionado».
- Sin fuga: features de t solo con observaciones ≤ t (test), `h_pct` idéntico en entrenamiento y
  servicio (test), el gate del modelo propio nunca entrena con el intervalo de prueba.
- Paridad: logística pura vs scikit-learn (1e-4) y PR-AUC puro vs `average_precision_score`.
- Anexo 1 en vivo: M1 y M2 general (sin historia / pocos eventos), M3 propio (2.42× vs 1.68×
  en M2→M3), M4 general (2.88× vs 2.42× en M3→M4); 0.14 s por evaluación.
