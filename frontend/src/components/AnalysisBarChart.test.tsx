/**
 * Colores de las series: lo único que decide la gráfica por su cuenta.
 *
 * La regla es que los estados (bueno / regular / malo / muerto) y la
 * mortalidad llevan SIEMPRE su color reservado, y que ese color no se reutiliza
 * como «serie 4» en una gráfica cualquiera.
 */
import { describe, expect, it } from "vitest";

import { SERIES_COLORS, seriesColor } from "./AnalysisBarChart";

describe("color de una serie", () => {
  it("una serie cualquiera toma la paleta categórica en orden fijo", () => {
    expect(seriesColor("m1", 0)).toBe(SERIES_COLORS[0]);
    expect(seriesColor("m2", 1)).toBe(SERIES_COLORS[1]);
  });

  it("la novena serie reutiliza la paleta, no inventa un tono", () => {
    expect(seriesColor("m9", 8)).toBe(SERIES_COLORS[0]);
  });

  it("el estado fitosanitario lleva su color reservado, esté donde esté", () => {
    expect(seriesColor("pct_good", 3)).toBe("#0ca30c");
    expect(seriesColor("pct_poor", 0)).toBe("#d03b3b");
  });

  it("la comparación entre monitoreos usa los mismos colores de estado (E4)", () => {
    expect(seriesColor("to_bueno", 5)).toBe("#0ca30c");
    expect(seriesColor("to_regular", 6)).toBe("#fab219");
    expect(seriesColor("to_malo", 7)).toBe("#d03b3b");
    expect(seriesColor("to_muerto", 1)).toBe("#4b4b4b");
    expect(seriesColor("to_sin_dato", 2)).toBe("#b9b9b9");
  });

  it("la mortalidad es roja y el estancamiento ámbar, como en el mapa", () => {
    expect(seriesColor("mortality", 0)).toBe("#d03b3b");
    expect(seriesColor("stagnant_pct", 1)).toBe("#fab219");
  });

  it("ningún color reservado aparece en la paleta categórica", () => {
    for (const reservado of ["#0ca30c", "#fab219", "#d03b3b", "#4b4b4b", "#b9b9b9"]) {
      expect(SERIES_COLORS).not.toContain(reservado);
    }
  });
});
