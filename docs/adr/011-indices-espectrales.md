# ADR-011 — NDVI por predio: proveedor externo, lectura guardada (E10a)

- **Estado:** Aceptado
- **Fecha:** 2026-09-22
- **Contexto:** El ingeniero quiere ver cómo cambia el verdor de sus predios
  con imágenes Sentinel-2. AgroSense no tiene ni cuenta ni presupuesto de
  proveedor satelital, y la máquina de campo no tiene GDAL.

  El camino obvio —descargar el COG de la escena y abrirlo con rasterio—
  costaba ~60 MB de dependencias binarias en el backend **para leer un
  recorte de 65 × 91 píxeles**. Desproporcionado.

- **Opciones consideradas:**
  - *Sentinel Hub / Copernicus con cuenta.* Es lo que usa la industria, pero
    exige registro y credenciales, y crear cuentas no es algo que el asistente
    haga. Queda para cuando el proyecto tenga su propia cuenta.
  - *Descargar el COG y calcular con rasterio.* Control total, ninguna
    dependencia de un servicio ajeno… y GDAL entero en el backend por un
    recorte diminuto.
  - *Delegar el cálculo en un servicio de teselas público* (elegida).

- **Decisión:**
  1. **Proveedor: Microsoft Planetary Computer.** Sirve el catálogo STAC de
     Sentinel-2 L2A y calcula estadísticos por polígono **sin cuenta, sin
     clave y sin GDAL**. Comprobado en el spike: NDVI medio de Guayabal
     0,495 sobre 1 308 píxeles, en ~1 s por consulta.
  2. **Puerto `SatelliteIndexSource`, y aquí sí.** ADR-003 solo admite
     interfaz donde hay variación real, y la hay: el mismo cálculo lo sirven
     Sentinel Hub, Copernicus y un TiTiler propio, y cuál se use depende de
     quién despliegue. Además es la **única dependencia de red** del sistema:
     sin puerto, los tests tendrían que salir a internet.
  3. **La lectura se guarda** (`satellite_index_values`), al revés que el
     mapa. La diferencia es de dónde viene el dato: el mapa se deriva de la
     base en 20 ms y siempre se puede rehacer; esto cuesta una petición de red
     por (escena, predio) y **no se puede reproducir** si el proveedor deja de
     servir la escena. Se guarda con su procedencia: qué escena, qué
     proveedor, sobre qué polígono (`polygon_hash`).
  4. **Leer y refrescar son dos operaciones.** `GET …/indices/NDVI` sirve lo
     guardado y nunca toca al proveedor; `POST …/refresh` sale a buscar. Abrir
     la pantalla no puede depender de que un tercero esté en pie.
  5. **El polígono es el contorno de lo plantado**, derivado de los mismos
     árboles que dibuja el mapa (E6). No hay que dibujar la finca a mano y el
     índice se mide exactamente sobre lo que se restauró.
  6. **Por predio y no por parcela.** Un píxel de Sentinel-2 mide 10 × 10 m:
     una parcela de 20 × 20 m son cuatro píxeles y tres tocan lo de al lado.
     El umbral de fiabilidad (25 px) se fijó **con el dato real**: San Antonio
     devuelve 10 píxeles y su franja es de un píxel de ancho, así que todos
     son píxeles mezclados. Se marca en vez de presentarse como sólido.

- **Consecuencias:**
  - Si Planetary Computer cambia o cierra, se escribe otro adaptador; el caso
    de uso, la tabla y la pantalla no se tocan. Las lecturas ya guardadas
    siguen siendo válidas y dicen de qué proveedor salieron.
  - Una consulta de 6 escenas × 3 predios son 18 peticiones, ~18 s medidos.
    Por eso el tope es explícito (`max_scenes`, máximo 24) y la operación es
    idempotente: lo ya medido no se vuelve a pedir. Si algún día hay que
    barrer años de histórico, eso sí es trabajo para la cola (ADR-010).
  - Si el proveedor se cae a mitad, se guarda lo conseguido y se informa. Una
    serie temporal parcial sirve; perder las diez lecturas anteriores porque
    falló la undécima, no.
  - Las imágenes son de terceros y su licencia es suya: el producto muestra
    siempre de qué proveedor y colección viene cada cifra.
