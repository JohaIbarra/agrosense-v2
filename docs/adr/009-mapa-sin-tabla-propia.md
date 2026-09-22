# ADR-009 — El mapa se deriva; la proyección vive en el backend (E6)

- **Estado:** Aceptado
- **Fecha:** 2026-09-22
- **Contexto:** El ingeniero quiere ver sus árboles sobre imagen satelital,
  coloreados por estado, con una línea de tiempo M1→Mn, el historial de un
  árbol al pincharlo y un mapa de calor por parcela. Los datos ya existen:
  856 árboles con coordenada única en `Coord_X`/`Coord_Y`, en EPSG:9377
  (confirmado en `docs/verificacion-e0.md` §6).

  `docs/04-vision-producto.md` §6.8 anticipaba **PostGIS** con geometrías en
  `properties` y `plots`. Antes de montarlo hay que preguntarse qué problema
  resolvería aquí.

- **Opciones consideradas:**
  - *PostGIS con columnas `geometry` y `ST_Transform`.* Es lo correcto cuando
    se consultan geometrías: «qué parcelas cruzan este polígono», «qué árboles
    hay a menos de 20 m». Hoy no se pregunta nada de eso: se pide el mapa
    entero de un proyecto. A cambio trae una extensión, una migración, tipos
    nuevos en el ORM y un dialecto más que mantener.
  - *Guardar un snapshot del mapa, como el análisis (ADR-008).* El análisis se
    guarda porque un informe lo cita y debe seguir siendo cierto. El mapa no
    se cita: se mira. Y derivarlo cuesta **20 ms** para los 856 árboles.
  - *Derivarlo en cada lectura* (elegida).

- **Decisión:**
  1. **Sin tabla ni migración.** `GET /projects/{id}/map` deriva el payload de
     `trees` + `observations` en la misma lectura que ya usa el análisis. 20 ms
     de cálculo y 279 KB de respuesta para el dataset de referencia.
  2. **La proyección es del backend**, en `adapters/geo/projection.py`, con
     **pyproj**. El frontend recibe grados y no sabe qué es un srid. Razón de
     pyproj y no las fórmulas a mano: una errata en un coeficiente de la
     inversa mueve los árboles cientos de metros **sin romper ningún test
     evidente**; PROJ es la implementación de referencia. Los tres centroides
     de predio del Anexo reproducen la tabla de E0 al cuarto decimal.
  3. **El sistema de coordenadas es del proyecto**, no del árbol
     (`projects.coordinate_srid`, 9377 por defecto), como ya decidió E0.
  4. **Un payload con todos los monitoreos.** La línea de tiempo se mueve sin
     volver a pedir datos, y la página sigue sin calcular nada (regla de E3).
  5. **Contorno de parcela = casco convexo de sus árboles.** Con uno o dos
     árboles se devuelve el punto o la línea: no se inventa un polígono, que
     sería afirmar una superficie que nadie midió.
  6. **Leaflet directo, sin react-leaflet**: su versión 5 exige React 19 y el
     proyecto usa React 18. Para una pantalla, el envoltorio no aporta y sí
     acopla el mapa a la versión de React.

- **Consecuencias:**
  - Cuando aparezca una pregunta espacial de verdad (buffers, intersecciones,
    capas de `geo_layers`), PostGIS entra con su propio ADR y su migración. El
    payload ya está aislado en `adapters/geo`, así que cambia quién calcula,
    no quién consume.
  - El payload crece de forma lineal con los árboles. A ~330 bytes por árbol,
    un proyecto de 10 000 árboles pesaría ~3 MB: ahí habrá que paginar por
    predio o servir teselas vectoriales. Anotado como límite conocido, no como
    deuda: hoy el mayor proyecto real tiene 856.
  - Las teselas satelitales son de **Esri World Imagery**, sin clave de API y
    con atribución visible. Es una dependencia externa del navegador del
    ingeniero: sin conexión, el mapa muestra los puntos sobre fondo vacío.
