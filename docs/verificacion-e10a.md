# Verificación — E10a · NDVI Sentinel-2 por predio

Fecha: 2026-09-22. Decisión: `docs/adr/011-indices-espectrales.md`.

**Criterio de salida**: el ingeniero abre el NDVI de su proyecto, busca
imágenes de Sentinel-2 y ve cómo ha cambiado el verdor de cada predio en el
tiempo, con la procedencia de cada cifra. **Cumplido y probado contra el
proveedor real.**

## Gates

| # | Gate | Resultado |
|---|---|---|
| 1 | `pytest` local | ✅ 569 passed, 44 deselected (122 s) |
| 2 | `pytest -m supabase` | ✅ 44 passed (178 s) |
| 3 | `ruff check src tests` | ✅ limpio |
| 4 | Frontend: `vitest run` | ✅ 87 passed (13 archivos) |
| 5 | `tsc -b` + `npm run build` + `npm run lint` | ✅ 0 errores (6 avisos previos de `any`) |
| 6 | `pip-audit` · `npm audit --omit=dev` | ✅ sin vulnerabilidades |
| 7 | Migración `a2c4e6f8b1d3` (`satellite_index_values`) | ✅ aplicada a Supabase (head) |
| 8 | Test de arquitectura (capas) | ✅ `domain`/`application` no importan el adaptador ni urllib |

**Ningún test sale a internet.** El proveedor se sustituye por un doble en los
tests del caso de uso y de la API, y en los del adaptador se reemplaza `_post`,
que es el único punto que habla HTTP.

## Contra el proveedor real

Con los 856 árboles del Anexo y sus tres predios, ventana 2024:

```
búsqueda: 3 escenas en 1.0 s
  2024-12-18  nubes 36.7 %   2024-12-08  nubes 17.4 %   2024-11-28  nubes 54.6 %

2024-12-18  Guayabal     NDVI=0.495  px=1308  →  Vegetación moderada
2024-12-18  San Antonio  NDVI=0.450  px=10    →  (marcado: superficie pequeña)
2024-12-18  Tres Jotas   NDVI=0.400  px=2152  →  Suelo con vegetación escasa
2024-12-08  Guayabal     NDVI=0.505  px=1308  →  Vegetación moderada
2024-12-08  San Antonio  NDVI=0.453  px=10    →  (marcado)
2024-12-08  Tres Jotas   NDVI=0.478  px=2152  →  Vegetación moderada
```

~0,8–1,6 s por medición. Seis escenas × tres predios ≈ 18 s, que es el tope
por defecto de una consulta.

### El dato real cambió una regla

San Antonio (69 árboles en una franja estrecha) devuelve **10 píxeles
válidos** frente a los 1 308 de Guayabal. En una franja de un píxel de ancho
**todos** los píxeles están mezclados con lo que hay alrededor, así que su
NDVI no se sostiene igual. El umbral de fiabilidad se subió de 10 a **25
píxeles (2 500 m²)** por esa evidencia, y la pantalla marca esas filas en vez
de presentarlas como sólidas. Está escrito en `domain/satellite_rules.py` con
el porqué.

## Qué prueba cada capa

- `tests/domain/test_satellite_rules.py` (**14 tests**): vocabulario de
  índices, ventana válida (ordenada, no futura, no anterior a Sentinel-2, no
  más de 3 años), umbral de píxeles y la lectura en palabras del NDVI.
- `tests/satellite/test_planetary_computer.py` (**9 tests**): qué se le pide
  al proveedor y cómo se lee su respuesta; que dos escenas del mismo día son
  una fecha; que **sin píxeles válidos no hay dato y eso no es un error**; que
  un fallo de red sale como error de operación (con reintento) y que un 400
  **no** se reintenta.
- `tests/db/test_index_use_cases.py` (**11 tests**): mide cada predio en cada
  escena, no repite lo ya medido, marca lo poco fiable, **guarda lo
  conseguido si el proveedor se cae a mitad**, y si no logró nada y no había
  nada lo dice como fallo en vez de devolver una serie vacía que parece «no
  hay imágenes».
- `tests/api/test_e10a_index_api.py` (**10 tests**): 401/404 de siempre, 422
  para índice o ventana inválidos, **503 —no 500— cuando el proveedor está
  caído**, y que leer la serie guardada funciona aunque el proveedor no
  responda.
- `tests/smoke/test_e6_smoke.py` (**1 test nuevo contra Supabase**):
  `UNIQUE(proyecto, predio, índice, escena)` y cascada real.
- `frontend/src/pages/IndexPage.test.tsx` (**5 tests**): abrir la página no
  consulta al proveedor, buscar muestra el resumen, una medición de poca
  superficie se ve marcada, se dice de dónde salen las cifras y un 503 se
  muestra sin perder la página.

## Decisiones que se ven en el producto

- **Leer y refrescar están separados.** Abrir la pantalla sirve lo guardado y
  es instantáneo; buscar imágenes es una acción explícita que puede tardar.
- **El polígono es el contorno de lo plantado**, derivado de los mismos
  árboles del mapa: no hay que dibujar la finca a mano.
- **Cada cifra dice de dónde viene** (`planetary-computer/sentinel-2-l2a`) y
  sobre qué polígono se midió (`polygon_hash`).
- **Por predio, no por parcela**, por el tamaño del píxel (ver arriba).

## Pendiente del ingeniero

1. Abrir `/proyectos/{id}/ndvi`, pulsar «Buscar imágenes nuevas» y confirmar
   que la serie tiene sentido con lo que vio en campo. Ojo: el NDVI de un
   predio en restauración incluye el pasto entre los árboles, así que sube con
   la lluvia aunque los árboles no crezcan. **Es un indicador de contexto, no
   una medida de los árboles**; los árboles los mide el análisis de E3/E4.
2. Decidir si quiere más índices (NDMI para humedad, EVI en vegetación densa).
   El vocabulario está en `SPECTRAL_INDICES` y añadir uno es una decisión de
   dominio —qué significa—, no solo de cálculo.
