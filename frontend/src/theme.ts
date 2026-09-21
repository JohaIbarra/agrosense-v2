/**
 * Paleta del dashboard.
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
  risk: "#c2410c",
  /** Efecto protector con IC concluyente. */
  protective: "#0f766e",
  /** IC que cruza 1: no es un hallazgo. */
  inconclusive: "#9ca3af",
  /** Barra del IC 95%. */
  interval: "#6b7280",
  /** Linea de referencia en OR = 1. */
  reference: "#111827",
  selected: "#1d4ed8",
  grid: "#e5e7eb",
  axis: "#4b5563",
} as const;
