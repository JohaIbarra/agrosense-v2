/**
 * Paleta de las gráficas de efectos (forest plot), alineada con el sistema
 * visual de Dendrova (styles.css).
 *
 * El color codifica una sola cosa: si el intervalo de confianza es
 * concluyente y en que direccion. `inconclusive` es deliberadamente apagado
 * para que un OR puntual alto con IC ancho NO compita visualmente con un
 * hallazgo real.
 *
 * Riesgo y protector se distinguen ademas por posicion respecto a la linea de
 * 1.0, asi que la lectura no depende solo del color (rojo/verde es el par que
 * mas sufre con el daltonismo mas comun).
 */
export const COLORS = {
  /** Se estanca o muere mas de lo esperado, con IC concluyente. */
  risk: "#b42318",
  /** Efecto protector con IC concluyente. */
  protective: "#1e5a40",
  /** IC que cruza 1: no es un hallazgo. */
  inconclusive: "#a3aba5",
  /** Barra del IC 95%. */
  interval: "#6b7770",
  /** Linea de referencia en OR = 1. */
  reference: "#13201a",
  selected: "#2f5d8c",
  grid: "#e1e6e0",
  axis: "#55625b",
} as const;
