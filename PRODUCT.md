# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Primario — ingeniero forestal o ambiental responsable de proyectos de restauración ecológica** (compensación
  ambiental, inversión forzosa del 1 %, planes de manejo, voluntarios) en Colombia. Tras cada campaña de
  monitoreo recibe el Excel de campo (una fila por árbol, columnas por monitoreo M1…Mn) y debe responder:
  cómo va la plantación, qué especies y parcelas fallan, y a qué árboles hay que volver. Hoy lo hace a mano
  con tablas dinámicas.
- **Secundario — cliente o empresa contratante**, a quien el ingeniero le muestra el avance del proyecto.

## Product Purpose

Convertir el Excel de campo de cada monitoreo en el análisis completo que el ingeniero hoy arma a mano
(composición, alturas, copa, supervivencia, estado fitosanitario, edades, DAP y comparación entre
monitoreos), más lo que una hoja de cálculo no da: árboles en riesgo de estancarse o morir para priorizar la
visita de campo, mapa por árbol, verdor satelital (NDVI) y contraste con un referente científico. Éxito: el
ingeniero sube el archivo y en minutos sabe qué está pasando y qué hacer, con cifras que puede defender.

## Positioning

Nombre: **DENDROVA** (antes AgroSense; ver Brand Commitments). Lo que un vecino no puede copiar con
honestidad: el análisis se recalcula siempre desde los datos crudos de su propio proyecto, cada cifra es
trazable (versión del cálculo, del modelo y huella de los datos) y los modelos de riesgo se evaluaron sin
fuga temporal y declaran sus límites (muestra pequeña, intervalos que cruzan 1, modelo propio solo si gana
al general).

## Operating Context

- **Oficina, computador:** después de la campaña, con el Excel listo; revisión del análisis, descarga del
  reporte `.xlsx`, preparación de informes para el contratante.
- **Campo, celular o tablet:** ubicar árboles en el mapa y consultar la lista de árboles a revisar, a menudo
  al sol y con mala señal.
- Vocabulario del oficio: monitoreo (M1, M2…), intervalo, predio, parcela (unidad de muestreo), cuadrilla,
  diseño florístico, cobertura, gremio ecológico (inicial / intermedia / tardía), estado fitosanitario
  (bueno / regular / malo), DAP, ortofoto.
- El Excel de campo es acumulado: el archivo de M4 trae M1–M4.

## Capabilities and Constraints

- Proyectos por usuario (cada ingeniero ve solo los suyos), carga del Excel con avisos de ingesta, fechas por
  monitoreo, análisis por monitoreo con 8 vistas y filtro por predio, reporte `.xlsx`, mapa satelital con
  historial por árbol y ortofotos, serie NDVI de Sentinel-2, contraste con el referente científico, paneles
  de riesgo de estancamiento y mortalidad.
- El referente científico (dataset y modelos mixtos de referencia) es **interno del ML**: no se muestra en la
  navegación ni como página para el usuario (decisión del usuario, 2026-10-15). Su información útil sí se
  conserva: la pantalla **Especies** del proyecto la traduce a lenguaje de campo («se estanca ~5× más que el
  promedio», «como el promedio») sin nombrar el referente; el detalle técnico (OR, IC) va plegado.
- Borrador de informe con IA local (Ollama): opcional, se oculta donde no hay modelo.
- Stack existente: React 18 + TypeScript + Vite, Recharts, Leaflet; API FastAPI. Sin framework CSS.
- Escala espacial: el satélite (10 m/píxel) no ve árboles individuales; solo la ortofoto de dron lo hace.
- Por ahora solo uso local; la publicación en internet está pospuesta.
- Renombre a DENDROVA (2026-10-15): hecho en la interfaz, los textos visibles del backend (título de la API,
  reporte `.xlsx`, mensajes) y la documentación principal. Se conservan a propósito los identificadores
  técnicos (paquete `agrosense`, repositorio `agrosense-v2`, base de datos, variables de entorno, prefijo `AGS-`).

## Brand Commitments

- Nombre: **DENDROVA** — *dendro* (árbol) + *nova* (nuevo): árboles nuevos. Reemplaza a AgroSense porque
  ya existen varios productos con ese nombre. Se descartó DENDRA (lo usa Dendra Systems, empresa de
  restauración con drones). No hay logo, colores ni tipografía previos que respetar.
- Tono pedido por el usuario: **técnico de campo** — sobrio y preciso, del oficio forestal.
- Dirección visual elegida por el usuario (2026-10-15): **panel estándar pulido** — la convención de las
  herramientas de trabajo ejecutada con acabado de primera, sin disfraz temático. Vara de calidad (elegida
  por Claude; el usuario no marcó referentes): Linear, Vercel y Stripe Dashboard. El diseño se aprueba en
  Claude Design antes de programarse. Rechazado explícitamente (2026-10-15): la dirección temática «cinta y
  placa de campo» — fondo gris aluminio, aspecto industrial, fucsia de cinta de marcación, tipografía
  condensada de señalética y adornos temáticos (placas estampadas, banderitas). No disfrazar la interfaz con
  objetos del oficio.
- Idioma: español de Colombia.

## Evidence on Hand

- Dataset real del proyecto de referencia: `Anexo 1 Base de datos 4 MONITOREO.xlsx` (856 árboles, M1–M4,
  3 predios, 54 parcelas, 30 especies).
- No hay testimonios, clientes ni casos publicados: no inventarlos.

## Product Principles

1. **El campo primero:** la pantalla responde «¿cómo va y a qué árboles voy?» antes que cualquier gráfica.
2. **Honestidad de los datos:** toda cifra es trazable y dice cuándo no es concluyente; nunca se adorna.
3. **Lenguaje del ingeniero, no del estadístico:** primero la lectura llana, el detalle técnico a un clic.
4. **El proyecto es del ingeniero:** su análisis se contrasta con el referente, nunca se mezcla.
5. **Sirve para cualquier proyecto de restauración**, no solo el de referencia.

## Accessibility & Inclusion

- Uso en campo al sol: contraste alto y objetivos táctiles amplios en mapa y listas.
- El estado fitosanitario no puede depender solo del color.
