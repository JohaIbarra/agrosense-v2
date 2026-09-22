# Verificación — E6 · Mapa del predio (+ E6b · ortofoto)

Fecha: 2026-09-22. Plan: `docs/superpowers/plans/2026-09-22-e6-mapa-del-predio.md`.
Decisión: `docs/adr/009-mapa-sin-tabla-propia.md`.

**Criterio de salida**: el ingeniero abre el mapa de su proyecto y ve sus
árboles sobre imagen satelital, coloreados por estado, puede recorrer los
monitoreos M1→Mn, pinchar un árbol para ver su historia y cambiar a un mapa de
calor por parcela. **Cumplido y probado**; la revisión visual en navegador
sigue pendiente del ingeniero (la extensión de Chrome no está conectada).

## Gates

| # | Gate | Resultado |
|---|---|---|
| 1 | `pytest` local (SQLite) | ✅ 510 passed, 42 deselected (106 s) |
| 2 | `pytest -m supabase` | ✅ 43 passed (4 nuevos de E6/E6b) |
| 3 | `ruff check src tests` | ✅ limpio |
| 4 | Frontend: `vitest run` | ✅ 76 passed (11 archivos; 18 nuevos de E6/E6b) |
| 5 | Frontend: `tsc -b` + `npm run build` + `npm run lint` | ✅ 0 errores (6 avisos de `any`: 4 previos + 2 del doble de Leaflet) |
| 6 | `pip-audit -r requirements.lock.txt` | ✅ sin vulnerabilidades conocidas (incluida pyproj 3.8.0) |
| 7 | `npm audit --omit=dev` | ✅ 0 vulnerabilidades |
| 8 | Migración `f1b2c3d4e5a7` (`imagery_layers`) | ✅ aplicada a Supabase (head). El mapa en sí no tiene tabla (ADR-009) |
| 9 | Test de arquitectura (capas) | ✅ `domain`/`application` no importan pyproj ni adapters |

## La proyección, contra los datos reales

`tests/geo/test_projection.py` (**9 tests**). Los tres centroides de predio del
Anexo, proyectados desde EPSG:9377, reproducen la tabla de
`docs/verificacion-e0.md` §6 con tolerancia de 5 m —que es el redondeo de esa
tabla, no el error del cálculo:

| Predio | Esperado (E0) | Calculado |
|---|---|---|
| Guayabal | 5,8017° N / 75,3852° O | 5,8017 / −75,3852 |
| San Antonio | 5,8013° N / 75,3876° O | 5,8013 / −75,3876 |
| Tres Jotas | 5,8054° N / 75,3850° O | 5,8054 / −75,3850 |

Dos guardas más: la **extensión** del sitio mide 646 × 907 m (la misma de E0;
si la escala cambiara, el test se dispara) y un test comprueba que el punto
cae en Colombia y no en el golfo de Guinea, que es donde aparecen los árboles
cuando se invierten `(x, y)` con `(lat, lon)` —el error clásico de esta
conversión.

Con el Anexo completo cargado: **856 árboles, 54 parcelas, 4 monitoreos en
20 ms**, extensión 646 × 907 m, 0 árboles sin coordenada, payload de 279 KB.

## Qué prueba cada capa

- `tests/geo/test_map_payload.py` (**13 tests**): un punto por árbol con
  coordenada; el estado por monitoreo (incluido «muerto» pisando el estado
  fitosanitario residual y «sin dato» cuando no consta); alturas para el
  historial; un árbol censado tarde no recibe estados que no tuvo; bounds que
  encierran todo; centroide y contorno por parcela; **la supervivencia de la
  parcela es la misma que publica el análisis de E3** (no puede haber dos
  verdades); marca de muestra pequeña; árboles sin coordenada contados y no
  inventados; proyecto vacío que devuelve un mapa vacío válido.
- `tests/api/test_e6_map_api.py` (**8 tests**): 401 sin sesión, 404 del
  proyecto ajeno y del inexistente, el payload completo desde un Excel con
  `Coord_X`/`Coord_Y`, y un proyecto sin cargas que responde **200 con el mapa
  vacío, no 404** (existe; solo que aún no hay nada que ver).
- `tests/smoke/test_e6_smoke.py` (**4 tests contra Supabase**): las
  coordenadas sobreviven al viaje completo archivo → Postgres → entidades →
  grados; la parcela trae contorno y supervivencia; el proyecto ajeno no tiene
  mapa; y la capa de imagen respeta `UNIQUE(project_id, name)` y desaparece
  con su proyecto por cascada.
- `frontend/src/map/model.test.ts` (**8 tests**): qué se dibuja con cada
  filtro, los colores de estado reservados, la rampa secuencial de
  supervivencia y la historia de un árbol (crecimiento solo entre monitoreos
  consecutivos con altura).
- `frontend/src/map/MapPage.test.tsx` (**10 tests**) con **Leaflet simulado**:
  jsdom no tiene tamaño ni canvas, así que el doble registra *qué* se manda
  dibujar. Verifica el punto por árbol con su color, el aviso de árboles sin
  coordenada, que **cambiar de monitoreo repinta sin volver a pedir datos**,
  el filtro por predio, el historial al pinchar y los polígonos de la capa de
  calor con su tooltip. Y para E6b: que se empieza con el satélite solo, que
  elegir la ortofoto la añade con su opacidad guardada, que volver a «solo
  satélite» la quita, y que el formulario dice que la imagen no se sube.

## Contra el servidor real

Con uvicorn levantado: `/projects/{project_id}/map` aparece en el OpenAPI con
las nueve propiedades del contrato, y sin token responde
`401 {"code": "UNAUTHENTICATED"}`.

## E6b · La ortofoto del proyecto

**Hallazgo del spike:** las teselas de OpenAerialMap **redirigen a TiTiler**
(`titiler.hotosm.org/cog/tiles/…?url=<COG>`). Es decir, un GeoTIFF en la nube
ya se sirve como teselas sin que AgroSense ejecute GDAL ni guarde la imagen.
Eso parte la épica en dos, y la mitad barata cubre el caso de hoy:

- **Hecho:** el proyecto registra su ortofoto como **plantilla de teselas**
  (`imagery_layers`), y el mapa la dibuja debajo de los árboles, con opacidad
  regulable y sus créditos. `tests/api/test_e6b_imagery_api.py` (**12 tests**)
  y `tests/domain/test_imagery_rules.py` (**20 tests**).
- **Pendiente de decisión:** subir el GeoTIFF propio. Necesita almacenamiento
  (Supabase Storage), conversión a COG (rasterio/GDAL) y un tilador. Es
  infraestructura con coste, no una tarde de trabajo (ver abajo).

Lo que se valida de la plantilla, y por qué: la escribe el ingeniero pero
**la carga su navegador**, así que cada tesela es una petición a un tercero.
Solo `https://` (un `http://` lo bloquea el navegador en una página cifrada, y
`javascript:`/`data:` no son fuentes de teselas sino inyección), debe traer
`{z}`, `{x}` e `{y}`, y se rechazan `{s}`/`{r}` porque exigirían configurar
subdominios y dejarían plantillas que nunca cargan.

### Probado con una imagen libre de OpenAerialMap

Ejercicio de punta a punta con la imagen real *«Carretera _ Puente Rio Chico»*
(Santiago Pastor, CC-BY 4.0), tomada de la API pública de OAM:

1. `POST /projects/{id}/imagery` con su plantilla TMS → **201**.
2. `GET /projects/{id}/map` devuelve la capa dentro del mismo payload del mapa
   (una sola petición, como el resto de E6).
3. La plantilla guardada, resuelta a la tesela 16/18127/32945, devuelve
   **HTTP 200, `image/png`, 42 506 bytes, PNG válido**.

## Decisiones tomadas en el camino

- **Sin PostGIS y sin tabla** (ADR-009): hoy no se hace ninguna pregunta
  espacial —se pide el mapa entero de un proyecto— y derivarlo cuesta 20 ms.
- **pyproj** en vez de escribir la inversa de la proyección: una errata en un
  coeficiente mueve los árboles sin romper ningún test evidente.
- **Leaflet directo, sin react-leaflet**: la versión 5 exige React 19.
- **Carga diferida**: `MapPage` queda en su propio chunk (160 kB / 47 kB gzip)
  y no entra en la ruta de proyectos. El bundle principal sigue en 828 kB
  (deuda #O, que es Recharts).

## Decisión que le toca al ingeniero

**¿Subir el GeoTIFF, o seguir pegando la dirección?** Hoy funciona lo segundo
y no cuesta nada. Lo primero exige: un bucket de Supabase Storage con las
políticas de acceso, convertir el GeoTIFF a COG al subirlo (rasterio/GDAL,
~60 MB de dependencias en el backend) y un tilador que sirva las teselas.
Una ortofoto de dron de un predio como Guayabal pesa entre 200 MB y 2 GB, así
que también hay que decidir un límite y quién paga el almacenamiento. Lo dejo
planteado porque cambia el coste de operar AgroSense, no solo su código.

## Pendiente del ingeniero

1. Abrir `/proyectos/{id}/mapa` con su cuenta y confirmar que las teselas de
   Esri cargan y que los árboles caen sobre el predio que conoce. **Es la
   comprobación que ningún test puede hacer**: que el sitio dibujado sea el
   sitio real.
2. Decidir si el mapa de calor debe colorear por otra variable además de la
   supervivencia (crecimiento medio, por ejemplo). Hoy el payload ya lleva
   `mean_height` por parcela y monitoreo.
3. Responder la decisión de arriba sobre el GeoTIFF.
