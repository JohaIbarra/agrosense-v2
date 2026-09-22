/**
 * Journey del mapa (E6) con Leaflet simulado.
 *
 * jsdom no tiene tamaño de ventana ni canvas, así que Leaflet se sustituye por
 * un doble que REGISTRA lo que se le manda dibujar. Eso es justo lo que hay
 * que verificar: qué puntos, de qué color, en qué capa — y que cambiar de
 * monitoreo no vuelve a pedir datos al servidor.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProjectMap } from "../api/types";

// ── doble de Leaflet ──────────────────────────────────────────────────────
interface Dibujado {
  kind: "circle" | "polygon";
  latlng: unknown;
  fillColor?: string;
  onClick?: () => void;
  tooltip?: string;
}
const dibujado: Dibujado[] = [];
let capasLimpiadas = 0;

vi.mock("leaflet", () => {
  const marca = (kind: "circle" | "polygon") => (latlng: unknown, options: any) => {
    const item: Dibujado = { kind, latlng, fillColor: options?.fillColor };
    const self = {
      on(_: string, handler: () => void) {
        item.onClick = handler;
        return self;
      },
      bindTooltip(text: string) {
        item.tooltip = text;
        return self;
      },
      addTo() {
        dibujado.push(item);
        return self;
      },
    };
    return self;
  };
  const group = {
    clearLayers: () => {
      capasLimpiadas += 1;
      dibujado.length = 0;
    },
    addTo: () => group,
  };
  return {
    default: {
      map: () => ({ remove: () => {}, fitBounds: () => {} }),
      tileLayer: () => ({ addTo: () => {} }),
      layerGroup: () => group,
      circleMarker: marca("circle"),
      polygon: marca("polygon"),
    },
  };
});

// ── datos ─────────────────────────────────────────────────────────────────
const MAPA: ProjectMap = {
  project_id: 7,
  version: "2026-09-22-e6.1",
  srid: 9377,
  monitorings: [1, 2],
  properties: ["Guayabal", "Tres Jotas"],
  bounds: { south: 5.799, west: -75.388, north: 5.804, east: -75.384 },
  without_coordinates: 3,
  trees: [
    {
      id: "G_1", species: "Cedrela montana", property: "Guayabal", plot: "11",
      plot_key: "U1", lat: 5.7996, lon: -75.3876, elevation_m: 2746,
      states: { "1": "bueno", "2": "muerto" }, heights: { "1": 0.4, "2": null },
    },
    {
      id: "G_2", species: "Senna viarum", property: "Guayabal", plot: "11",
      plot_key: "U1", lat: 5.7997, lon: -75.3875, elevation_m: 2748,
      states: { "1": "bueno", "2": "regular" }, heights: { "1": 0.5, "2": 0.9 },
    },
    {
      id: "T_1", species: "Inga punctata", property: "Tres Jotas", plot: "21",
      plot_key: "U2", lat: 5.8040, lon: -75.3850, elevation_m: 2794,
      states: { "1": "bueno", "2": "bueno" }, heights: { "1": 0.6, "2": 0.8 },
    },
  ],
  plots: [
    {
      key: "U1", property: "Guayabal", plot: "11", n: 2, low_sample: true,
      centroid: { lat: 5.79965, lon: -75.38755 },
      hull: [[5.7996, -75.3876], [5.7997, -75.3875]],
      metrics: { "1": { n: 2, survival: 100, mean_height: 0.45 },
                 "2": { n: 2, survival: 50, mean_height: 0.9 } },
    },
    {
      key: "U2", property: "Tres Jotas", plot: "21", n: 9, low_sample: false,
      centroid: { lat: 5.804, lon: -75.385 },
      hull: [[5.8039, -75.3851], [5.8041, -75.3851], [5.8041, -75.3849]],
      metrics: { "1": { n: 9, survival: 100, mean_height: 0.6 },
                 "2": { n: 9, survival: 88.8889, mean_height: 0.8 } },
    },
  ],
};

const PROYECTO = { id: 7, name: "Restauración Guayabal", project_code: "AGS-2026-0007" };

function mockApi() {
  const llamadas: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      llamadas.push(url);
      const body = url.endsWith("/map") ? MAPA : PROYECTO;
      return Promise.resolve({
        ok: true, status: 200, headers: new Headers(), json: async () => body,
      });
    }),
  );
  return llamadas;
}

function renderMapa() {
  return render(
    <MemoryRouter initialEntries={["/proyectos/7/mapa"]}>
      <Routes>
        <Route path="/proyectos/:id/mapa" element={<MapPageBajoPrueba />} />
      </Routes>
    </MemoryRouter>,
  );
}

// import estático tras el vi.mock (hoisted por vitest)
import { MapPage as MapPageBajoPrueba } from "./MapPage";

beforeEach(() => {
  dibujado.length = 0;
  capasLimpiadas = 0;
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mapa del predio", () => {
  it("dibuja un punto por árbol del último monitoreo, con su color", async () => {
    mockApi();
    renderMapa();
    expect(await screen.findByRole("heading", { name: "Mapa del predio" })).toBeInTheDocument();

    await waitFor(() => expect(dibujado.length).toBe(3));
    const colores = dibujado.map((d) => d.fillColor);
    expect(colores).toContain("#4b4b4b"); // G_1 murió en M2
    expect(colores).toContain("#fab219"); // G_2 regular
    expect(colores).toContain("#0ca30c"); // T_1 bueno
    expect(dibujado.every((d) => d.kind === "circle")).toBe(true);
  });

  it("avisa de los árboles que el archivo no ubica", async () => {
    mockApi();
    renderMapa();
    expect(await screen.findByText(/3 sin coordenada en el archivo/)).toBeInTheDocument();
  });

  it("cambiar de monitoreo repinta sin volver a pedir datos", async () => {
    const llamadas = mockApi();
    renderMapa();
    await waitFor(() => expect(dibujado.length).toBe(3));
    const antes = llamadas.filter((u) => u.endsWith("/map")).length;

    await userEvent.click(screen.getByRole("button", { name: "M1" }));
    await waitFor(() => expect(dibujado.map((d) => d.fillColor)).toEqual([
      "#0ca30c", "#0ca30c", "#0ca30c",
    ]));
    expect(llamadas.filter((u) => u.endsWith("/map")).length).toBe(antes);
    expect(capasLimpiadas).toBeGreaterThan(0);
  });

  it("el filtro de predio deja solo sus árboles", async () => {
    mockApi();
    renderMapa();
    await waitFor(() => expect(dibujado.length).toBe(3));
    await userEvent.click(screen.getByRole("button", { name: "Tres Jotas" }));
    await waitFor(() => expect(dibujado.length).toBe(1));
    expect(dibujado[0].tooltip).toContain("T_1");
  });

  it("pinchar un árbol muestra su historial de alturas y crecimiento", async () => {
    mockApi();
    renderMapa();
    await waitFor(() => expect(dibujado.length).toBe(3));
    const g2 = dibujado.find((d) => d.tooltip?.startsWith("G_2"))!;
    await act(async () => g2.onClick!());

    expect(await screen.findByRole("heading", { name: "G_2" })).toBeInTheDocument();
    expect(screen.getByText("Senna viarum")).toBeInTheDocument();
    expect(screen.getByText("+0.40")).toBeInTheDocument(); // 0.9 − 0.5
  });

  it("la capa de parcelas pinta polígonos coloreados por supervivencia", async () => {
    mockApi();
    renderMapa();
    await waitFor(() => expect(dibujado.length).toBe(3));

    await userEvent.click(screen.getByRole("button", { name: "Calor por parcela" }));
    await waitFor(() => expect(dibujado.length).toBe(2));
    const poligono = dibujado.find((d) => d.kind === "polygon")!;
    expect(poligono.tooltip).toContain("88.9 % vivos de 9");
    const linea = dibujado.find((d) => d.kind === "circle")!;
    expect(linea.tooltip).toContain("muestra pequeña");
  });
});
