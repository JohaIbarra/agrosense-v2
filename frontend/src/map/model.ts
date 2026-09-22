/**
 * Decisiones de dibujo del mapa, sin DOM ni Leaflet.
 *
 * Aquí no se calcula ninguna cifra: supervivencia, estados y contornos vienen
 * hechos del backend (E6). Lo que vive aquí es cómo se ve cada cosa —qué color
 * lleva un estado, qué árboles se muestran con el filtro puesto— que es
 * responsabilidad de la pantalla y se puede probar sin abrir un navegador.
 */
import type { MapPlot, MapTree, ProjectMap, TreeState } from "../api/types";

/** Colores de estado reservados (dataviz): nunca se usan como serie. */
export const STATE_COLORS: Record<TreeState, string> = {
  bueno: "#0ca30c",
  regular: "#fab219",
  malo: "#d03b3b",
  muerto: "#4b4b4b",
  sin_dato: "#b9b9b9",
};

export const STATE_LABELS: Record<TreeState, string> = {
  bueno: "Bueno",
  regular: "Regular",
  malo: "Malo",
  muerto: "Muerto",
  sin_dato: "Sin dato",
};

export const STATE_ORDER: TreeState[] = ["bueno", "regular", "malo", "muerto", "sin_dato"];

export const ALL_PROPERTIES = "__todos__";

/** Estado de un árbol en el monitoreo `m`, o `null` si no fue censado. */
export function stateAt(tree: MapTree, m: number): TreeState | null {
  return (tree.states[String(m)] as TreeState | undefined) ?? null;
}

export function heightAt(tree: MapTree, m: number): number | null {
  const h = tree.heights[String(m)];
  return h === undefined ? null : h;
}

/** Árboles que se dibujan: los del predio elegido, censados en ese monitoreo. */
export function visibleTrees(data: ProjectMap, monitoring: number, property: string): MapTree[] {
  return data.trees.filter(
    (t) =>
      (property === ALL_PROPERTIES || t.property === property) && stateAt(t, monitoring) !== null,
  );
}

export function visiblePlots(data: ProjectMap, monitoring: number, property: string): MapPlot[] {
  return data.plots.filter(
    (p) =>
      (property === ALL_PROPERTIES || p.property === property) &&
      p.metrics[String(monitoring)] !== undefined,
  );
}

/** Cuántos árboles hay de cada estado, en el orden de la leyenda. */
export function stateCounts(trees: MapTree[], monitoring: number): [TreeState, number][] {
  const counts = new Map<TreeState, number>(STATE_ORDER.map((s) => [s, 0]));
  for (const t of trees) {
    const s = stateAt(t, monitoring);
    if (s) counts.set(s, (counts.get(s) ?? 0) + 1);
  }
  return STATE_ORDER.map((s) => [s, counts.get(s) ?? 0] as [TreeState, number]).filter(
    ([, n]) => n > 0,
  );
}

/**
 * Color de una parcela según su supervivencia: una sola tinta, de claro a
 * oscuro (rampa secuencial; nunca un arcoíris). Verde porque más es mejor.
 */
export function survivalColor(survival: number): string {
  const ramp = ["#e6f4e6", "#b7e2b7", "#7fcb7f", "#41ad41", "#0f7a0f"];
  const i = Math.min(ramp.length - 1, Math.max(0, Math.floor(survival / 20)));
  return ramp[i];
}

export interface HistoryPoint {
  monitoring: number;
  state: TreeState | null;
  height: number | null;
  growth: number | null;
}

/**
 * Historia de un árbol a lo largo de los monitoreos del proyecto.
 *
 * El crecimiento es la diferencia con la medida anterior DEL MISMO ÁRBOL, y
 * solo entre monitoreos consecutivos con altura: no se interpola sobre un
 * hueco ni se compara con un muerto.
 */
export function treeHistory(tree: MapTree, monitorings: number[]): HistoryPoint[] {
  let previous: { m: number; height: number } | null = null;
  return monitorings.map((m) => {
    const height = heightAt(tree, m);
    const growth =
      previous !== null && height !== null && previous.m === m - 1
        ? Number((height - previous.height).toFixed(3))
        : null;
    if (height !== null) previous = { m, height };
    return { monitoring: m, state: stateAt(tree, m), height, growth };
  });
}
