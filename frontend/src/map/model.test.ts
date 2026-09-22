import { describe, expect, it } from "vitest";

import type { MapTree, ProjectMap } from "../api/types";
import {
  ALL_PROPERTIES,
  STATE_COLORS,
  stateCounts,
  survivalColor,
  treeHistory,
  visiblePlots,
  visibleTrees,
} from "./model";

function tree(id: string, property: string, states: Record<string, string>, heights = {}): MapTree {
  return {
    id,
    species: "Cedrela montana",
    property,
    plot: "11",
    plot_key: `${property}/11`,
    lat: 5.8,
    lon: -75.38,
    elevation_m: 2746,
    states,
    heights,
  } as MapTree;
}

const DATA: ProjectMap = {
  project_id: 7,
  version: "2026-09-22-e6.1",
  srid: 9377,
  monitorings: [1, 2, 3],
  properties: ["Guayabal", "Tres Jotas"],
  bounds: { south: 5.79, west: -75.39, north: 5.81, east: -75.38 },
  without_coordinates: 0,
  imagery: [],
  trees: [
    tree("G1", "Guayabal", { "1": "bueno", "2": "bueno", "3": "muerto" }, { "1": 0.4, "2": 0.7 }),
    tree("G2", "Guayabal", { "1": "bueno", "2": "regular" }),
    tree("T1", "Tres Jotas", { "1": "malo", "2": "malo", "3": "malo" }),
    tree("T2", "Tres Jotas", { "3": "bueno" }),
  ],
  plots: [
    {
      key: "Guayabal/11", property: "Guayabal", plot: "11", n: 2, low_sample: true,
      centroid: { lat: 5.8, lon: -75.38 }, hull: [[5.8, -75.38]],
      metrics: { "1": { n: 2, survival: 100, mean_height: 0.4 } },
    },
    {
      key: "Tres Jotas/21", property: "Tres Jotas", plot: "21", n: 9, low_sample: false,
      centroid: { lat: 5.81, lon: -75.385 }, hull: [[5.81, -75.385]],
      metrics: { "1": { n: 9, survival: 88.8889, mean_height: 0.5 } },
    },
  ],
};

describe("qué se dibuja", () => {
  it("solo los árboles censados en ese monitoreo", () => {
    expect(visibleTrees(DATA, 1, ALL_PROPERTIES).map((t) => t.id)).toEqual(["G1", "G2", "T1"]);
    expect(visibleTrees(DATA, 3, ALL_PROPERTIES).map((t) => t.id)).toEqual(["G1", "T1", "T2"]);
  });

  it("el filtro de predio no deja pasar los demás", () => {
    expect(visibleTrees(DATA, 1, "Tres Jotas").map((t) => t.id)).toEqual(["T1"]);
    expect(visiblePlots(DATA, 1, "Guayabal").map((p) => p.key)).toEqual(["Guayabal/11"]);
  });

  it("una parcela sin métricas en ese monitoreo no se pinta", () => {
    expect(visiblePlots(DATA, 3, ALL_PROPERTIES)).toEqual([]);
  });

  it("la leyenda cuenta por estado y omite los que no aparecen", () => {
    expect(stateCounts(visibleTrees(DATA, 2, ALL_PROPERTIES), 2)).toEqual([
      ["bueno", 1],
      ["regular", 1],
      ["malo", 1],
    ]);
  });
});

describe("colores", () => {
  it("cada estado lleva el suyo, y muerto no es un color de serie", () => {
    expect(STATE_COLORS.bueno).toBe("#0ca30c");
    expect(STATE_COLORS.malo).toBe("#d03b3b");
    expect(STATE_COLORS.muerto).toBe("#4b4b4b");
  });

  it("la supervivencia usa una sola tinta, de claro a oscuro", () => {
    const claro = survivalColor(10);
    const oscuro = survivalColor(95);
    expect(claro).not.toBe(oscuro);
    expect(survivalColor(0)).toBe(claro);
    expect(survivalColor(100)).toBe(oscuro);
  });
});

describe("historia de un árbol", () => {
  it("altura y crecimiento entre monitoreos consecutivos", () => {
    const h = treeHistory(DATA.trees[0], [1, 2, 3]);
    expect(h[0]).toEqual({ monitoring: 1, state: "bueno", height: 0.4, growth: null });
    expect(h[1]).toEqual({ monitoring: 2, state: "bueno", height: 0.7, growth: 0.3 });
    expect(h[2]).toEqual({ monitoring: 3, state: "muerto", height: null, growth: null });
  });

  it("un árbol que entra tarde no arrastra estados que no tuvo", () => {
    const h = treeHistory(DATA.trees[3], [1, 2, 3]);
    expect(h.map((p) => p.state)).toEqual([null, null, "bueno"]);
  });
});
