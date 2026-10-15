# Design

Sistema visual de Dendrova. El diseño se aprobó en Claude Design («Dendrova — rediseño», 2026-10-15) y vive en
código en `frontend/src/styles.css` (tokens en `:root`) y `frontend/src/components/icons.tsx`.

## Dirección

Panel estándar pulido (ver `PRODUCT.md`): la convención de las herramientas de trabajo — barra lateral, tarjetas de
indicadores, tablas densas — con acabado de primera y sin disfraz temático. Referentes de calidad: Linear, Vercel,
Stripe Dashboard.

## Marca

- Nombre: **Dendrova**. Símbolo: anillos de crecimiento con el centro desplazado, como un corte real del tronco
  (`BrandMark`, `frontend/public/favicon.svg`).

## Color

| Token | Valor | Uso |
|---|---|---|
| `--forest` | `#0e2219` | Barra lateral, panel de marca |
| `--accent` | `#1e5a40` | Acción principal, pestaña activa, enlaces |
| `--moss` | `#8fbf6a` | Acento sobre fondo oscuro (marca, ítem activo) |
| `--accent-soft` | `#e6f0ea` | Fondos de etiquetas y estados positivos |
| `--bg` / `--surface` | `#f3f5f2` / `#ffffff` | Página / tarjetas |
| `--text` / `--muted` | `#13201a` / `#55625b` | Texto / texto secundario (≥ 4.5:1 sobre blanco) |

Estados (reservados, nunca se usan como serie de datos): bueno `#2e7d4f`, regular/estancado `#d4a23c`,
malo/mortalidad `#b42318`, muerto `#5f6762`, sin dato `#c4cac5`. Series categóricas en `SERIES_COLORS`
(`AnalysisBarChart.tsx`); las dos primeras son «monitoreo anterior» (azul acero) y «actual» (ocre).

## Tipografía

- Interfaz: **Instrument Sans** (400–700). Datos, códigos de árbol y trazabilidad: **IBM Plex Mono** con cifras
  tabulares. Nombres científicos en cursiva. Se cargan de Google Fonts con alternativas del sistema.
- Escala: título de página 28/600, sección 16–20/600, cuerpo 14.5/400, etiquetas 12–13.

## Componentes y estados

Botones (`.btn-primary`, `.btn-ghost`, `.link-button`), etiquetas (`.badge-*`), chips de filtro, control segmentado
(M1…Mn), pestañas, tarjetas de indicador (`.stat`), tablas (`.data-table`, `.comparison`), accesos rápidos
(`.quick`). Estados: cargando (`.loading`, respeta `prefers-reduced-motion`), vacío (`.empty-card`), error
(`.form-error`, `.state-error`), aviso (`.warn`), confirmación (`.form-ok`).

## Responsive

La barra lateral se pliega en una franja superior con botón de menú por debajo de 960 px; tablas anchas se
desplazan dentro de su tarjeta; las listas largas de árboles en riesgo tienen altura máxima propia.
