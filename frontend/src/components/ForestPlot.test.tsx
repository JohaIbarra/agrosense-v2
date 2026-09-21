/**
 * La regla de escala del dashboard, probada donde vive.
 *
 * En jsdom el SVG se renderiza con tamaño 0 y no emite texto, así que montar
 * el gráfico no permite verificar nada sobre los números. Lo que sí se puede
 * probar — y es lo que importa — es `toPoint`: la función que decide qué
 * valores entran al gráfico.
 */
import { describe, expect, it } from "vitest";

import type { SpeciesAnalytics } from "../api/types";
import { toPoint, toPoints } from "./ForestPlot";

/** Lafoensia speciosa, el caso real del informe. */
const LAFOENSIA: SpeciesAnalytics = {
  species: "Lafoensia speciosa",
  stall_risk: {
    odds_ratio: 4.9427,
    or_ci95: [2.2503, 10.856],
    ci95_log_odds: [0.8111, 2.3847],
    significant: true,
    interpretation: "Se estanca ~4.9x mas de lo esperado.",
  },
  mortality_risk: {
    odds_ratio: null,
    or_ci95: null,
    ci95_log_odds: null,
    significant: null,
    interpretation: "Sin estimacion disponible para este modelo.",
  },
  n_observations: 28,
  n_trees: 14,
  gremio: "Inicial",
};

describe("toPoint", () => {
  it("usa el IC en ODDS RATIO, no el de log-odds", () => {
    const p = toPoint(LAFOENSIA, "stall_risk")!;
    // Si alguien cambiara `or_ci95` por `ci95_log_odds`, estos dos serían
    // 0.81 y 2.38 — y la barra quedaría fuera de su propio punto.
    expect(p.lo).toBeCloseTo(2.2503, 4);
    expect(p.hi).toBeCloseTo(10.856, 3);
  });

  it("el intervalo contiene al punto", () => {
    const p = toPoint(LAFOENSIA, "stall_risk")!;
    expect(p.lo).toBeLessThan(p.or);
    expect(p.or).toBeLessThan(p.hi);
  });

  it("la barra de error es asimétrica porque exp() no conserva la simetría", () => {
    const p = toPoint(LAFOENSIA, "stall_risk")!;
    const [abajo, arriba] = p.errorX;
    expect(abajo).toBeCloseTo(p.or - p.lo, 6);
    expect(arriba).toBeCloseTo(p.hi - p.or, 6);
    // El brazo superior es mucho más largo: es la firma de la escala log.
    expect(arriba).toBeGreaterThan(abajo * 2);
  });

  it("ningún extremo del intervalo puede ser negativo", () => {
    // Un OR negativo es imposible; verlo significaría estar dibujando
    // log-odds en un eje etiquetado como OR.
    const p = toPoint(LAFOENSIA, "stall_risk")!;
    expect(p.lo).toBeGreaterThan(0);
    expect(p.hi).toBeGreaterThan(0);
  });

  it("omite la especie cuando el modelo no la estimó", () => {
    // Las 3 parcelas que solo existen en el panel de mortalidad, y cualquier
    // especie sin efecto en un modelo, no deben dibujarse en el origen.
    expect(toPoint(LAFOENSIA, "mortality_risk")).toBeNull();
  });

  it("trata `significant: null` como no concluyente, no como concluyente", () => {
    const sinDato: SpeciesAnalytics = {
      ...LAFOENSIA,
      stall_risk: { ...LAFOENSIA.stall_risk, significant: null },
    };
    expect(toPoint(sinDato, "stall_risk")!.significant).toBe(false);
  });

  it("transporta la interpretación del backend sin reescribirla", () => {
    const p = toPoint(LAFOENSIA, "stall_risk")!;
    expect(p.interpretation).toBe(LAFOENSIA.stall_risk.interpretation);
  });
});

describe("toPoints — orden visual", () => {
  const protectora: SpeciesAnalytics = {
    ...LAFOENSIA,
    species: "Verbesina arborea",
    stall_risk: {
      odds_ratio: 0.2435,
      or_ci95: [0.115, 0.5154],
      ci95_log_odds: [-2.1624, -0.6631],
      significant: true,
      interpretation: "protectora",
    },
  };
  const media: SpeciesAnalytics = {
    ...LAFOENSIA,
    species: "Erythrina edulis",
    stall_risk: {
      odds_ratio: 1.9051,
      or_ci95: [0.8169, 4.4432],
      ci95_log_odds: [-0.2023, 1.4914],
      significant: false,
      interpretation: "no concluyente",
    },
  };

  it("ordena ascendente para que Recharts lo pinte de mayor a menor", () => {
    // Regresion del bug visual del 2026-09-21: con orden descendente, el
    // eje de categorias de Recharts (que dibuja de abajo hacia arriba)
    // mostraba la especie MAS protectora encabezando el ranking de riesgo.
    const ors = toPoints([media, protectora, LAFOENSIA], "stall_risk").map((p) => p.or);
    expect(ors).toEqual([...ors].sort((a, b) => a - b));
    expect(ors[ors.length - 1]).toBeCloseTo(4.9427, 3);
    expect(ors[0]).toBeCloseTo(0.2435, 3);
  });

  it("omite las especies sin estimacion en vez de ponerlas en el origen", () => {
    expect(toPoints([LAFOENSIA, media], "mortality_risk")).toHaveLength(0);
  });
});
