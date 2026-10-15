/**
 * Colores de las series: lo único que decide la gráfica por su cuenta.
 *
 * La regla es que los estados (bueno / regular / malo / muerto) y la
 * mortalidad llevan SIEMPRE su color reservado, y que ese color no se reutiliza
 * como «serie 4» en una gráfica cualquiera.
 */
import { describe, expect, it } from "vitest";

import { SERIES_COLORS, isHorizontal, seriesColor } from "./AnalysisBarChart";

describe("color de una serie", () => {
  it("una serie cualquiera toma la paleta categórica en orden fijo", () => {
    expect(seriesColor("m1", 0)).toBe(SERIES_COLORS[0]);
    expect(seriesColor("m2", 1)).toBe(SERIES_COLORS[1]);
  });

  it("la novena serie reutiliza la paleta, no inventa un tono", () => {
    expect(seriesColor("m9", 8)).toBe(SERIES_COLORS[0]);
  });

  it("el estado fitosanitario lleva su color reservado, esté donde esté", () => {
    expect(seriesColor("pct_good", 3)).toBe("#2e7d4f");
    expect(seriesColor("pct_poor", 0)).toBe("#b42318");
  });

  it("la comparación entre monitoreos usa los mismos colores de estado (E4)", () => {
    expect(seriesColor("to_bueno", 5)).toBe("#2e7d4f");
    expect(seriesColor("to_regular", 6)).toBe("#d4a23c");
    expect(seriesColor("to_malo", 7)).toBe("#b42318");
    expect(seriesColor("to_muerto", 1)).toBe("#5f6762");
    expect(seriesColor("to_sin_dato", 2)).toBe("#c4cac5");
  });

  it("la mortalidad es roja y el estancamiento ámbar, como en el mapa", () => {
    expect(seriesColor("mortality", 0)).toBe("#b42318");
    expect(seriesColor("stagnant_pct", 1)).toBe("#d4a23c");
  });

  it("ningún color reservado aparece en la paleta categórica", () => {
    for (const reservado of ["#2e7d4f", "#d4a23c", "#b42318", "#5f6762", "#c4cac5"]) {
      expect(SERIES_COLORS).not.toContain(reservado);
    }
  });
});

describe("orientación de la gráfica", () => {
  const filas = (nombres: string[]) => nombres.map((especie) => ({ especie }));

  it("pocas categorías de nombre corto van en columnas", () => {
    expect(isHorizontal(filas(["M1", "M2", "M3"]), "especie")).toBe(false);
  });

  it("muchas categorías van en barras horizontales", () => {
    expect(isHorizontal(filas(["a", "b", "c", "d", "e", "f", "g"]), "especie")).toBe(true);
  });

  it("pocas especies de nombre largo van en barras horizontales para que no se encimen", () => {
    const especies = ["Cecropia peltata", "Guazuma ulmifolia", "Inga punctata", "Senna reticulata"];
    expect(isHorizontal(filas(especies), "especie")).toBe(true);
  });
});
