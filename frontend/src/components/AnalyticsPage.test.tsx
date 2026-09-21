/**
 * Tests de la pantalla: composición, filtro y estados.
 *
 * La regla de escala («OR siempre, log-odds nunca») NO se prueba aquí: en
 * jsdom el SVG se renderiza con tamaño 0 y no emite texto, así que una
 * aserción sobre el DOM de esta página pasaría aunque el gráfico estuviera
 * dibujando la escala equivocada. Vive en `ForestPlot.test.tsx` (los valores
 * que entran al gráfico) y `SpeciesDetail.test.tsx` (los que se renderizan
 * como texto).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ModelVariance, SpeciesAnalytics } from "../api/types";
import { AnalyticsPage } from "../pages/AnalyticsPage";

// Datos reales del informe, recortados: Lafoensia (riesgo concluyente),
// Verbesina (protectora concluyente) y Erythrina (IC que cruza 1).
const LAFOENSIA: SpeciesAnalytics = {
  species: "Lafoensia speciosa",
  stall_risk: {
    odds_ratio: 4.9427,
    or_ci95: [2.2503, 10.856],
    ci95_log_odds: [0.8111, 2.3847],
    significant: true,
    interpretation: "Se estanca ~4.9x mas de lo esperado, IC 95% del OR [2.25, 10.86] no cruza 1.",
  },
  mortality_risk: {
    odds_ratio: 1.42,
    or_ci95: [0.52, 2.41],
    ci95_log_odds: [-0.65, 0.88],
    significant: false,
    interpretation: "Sin efecto significativo distinguible del promedio (IC 95% del OR [0.52, 2.41], cruza 1).",
  },
  n_observations: 28,
  n_trees: 14,
  gremio: "Inicial",
};

const VERBESINA: SpeciesAnalytics = {
  species: "Verbesina arborea",
  stall_risk: {
    odds_ratio: 0.2435,
    or_ci95: [0.115, 0.5154],
    ci95_log_odds: [-2.1624, -0.6631],
    significant: true,
    interpretation: "Se estanca ~4.1x menos de lo esperado (efecto protector), IC 95% del OR [0.12, 0.52] no cruza 1.",
  },
  mortality_risk: {
    odds_ratio: 0.9,
    or_ci95: [0.4, 2.0],
    ci95_log_odds: [-0.92, 0.69],
    significant: false,
    interpretation: "Sin efecto significativo distinguible del promedio (IC 95% del OR [0.40, 2.00], cruza 1).",
  },
  n_observations: 126,
  n_trees: 63,
  gremio: "Intermedia",
};

const ERYTHRINA: SpeciesAnalytics = {
  species: "Erythrina edulis",
  stall_risk: {
    odds_ratio: 1.9051,
    or_ci95: [0.8169, 4.4432],
    ci95_log_odds: [-0.2023, 1.4914],
    significant: false,
    interpretation: "Sin efecto significativo distinguible del promedio (IC 95% del OR [0.82, 4.44], cruza 1).",
  },
  mortality_risk: {
    odds_ratio: 1.1,
    or_ci95: [0.5, 2.4],
    ci95_log_odds: [-0.69, 0.87],
    significant: false,
    interpretation: "Sin efecto significativo distinguible del promedio (IC 95% del OR [0.50, 2.40], cruza 1).",
  },
  n_observations: 21,
  n_trees: 11,
  gremio: "Tardía",
};

const SPECIES = [LAFOENSIA, ERYTHRINA, VERBESINA];

const VARIANCE: ModelVariance[] = [
  {
    model: "stall",
    components: [
      { grouping: "especie", variance: 0.8463, sd: 0.9199, icc: 0.19, n_levels: 30, n_observations: 1335, n_events: 310 },
      { grouping: "parcela", variance: 0.3168, sd: 0.5628, icc: 0.0711, n_levels: 42, n_observations: 1335, n_events: 310 },
    ],
    species_to_plot_ratio: 2.672,
    interpretation:
      "La especie explica 2.7x mas varianza que la parcela: el estancamiento es sobre todo un problema de QUE se planta. La palanca principal es la seleccion de especies.",
  },
  {
    model: "mortality",
    components: [
      { grouping: "especie", variance: 0.4151, sd: 0.6443, icc: 0.1018, n_levels: 30, n_observations: 1405, n_events: 70 },
      { grouping: "parcela", variance: 0.372, sd: 0.6099, icc: 0.0912, n_levels: 45, n_observations: 1405, n_events: 70 },
    ],
    species_to_plot_ratio: 1.116,
    interpretation:
      "Especie y parcela pesan de forma similar (1.1x): la mortalidad depende tanto de que se planta como de las condiciones del sitio.",
  },
];

function mockApi(species: SpeciesAnalytics[] = SPECIES) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string) => {
      let body: unknown = [];
      if (url.includes("variance-decomposition")) body = VARIANCE;
      else if (url.includes("/plots")) body = [];
      else if (url.includes("/species")) {
        const match = /gremio=([^&]+)/.exec(url);
        body = match
          ? species.filter((s) => s.gremio === decodeURIComponent(match[1]))
          : species;
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => body });
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AnalyticsPage", () => {
  it("monta los dos rankings", async () => {
    mockApi();
    render(<AnalyticsPage />);
    expect(await screen.findByText(/Estancamiento por especie/)).toBeInTheDocument();
    expect(screen.getByText(/Mortalidad por especie/)).toBeInTheDocument();
  });

  it("muestra la lectura estratégica de los dos modelos", async () => {
    mockApi();
    render(<AnalyticsPage />);
    expect(await screen.findByText(/2.7x mas varianza que la parcela/)).toBeInTheDocument();
    expect(screen.getByText(/pesan de forma similar/)).toBeInTheDocument();
  });

  it("el panel comparativo deriva la razón de varianzas de la API", async () => {
    mockApi();
    render(<AnalyticsPage />);
    const tabla = await screen.findByRole("table");
    const fila = within(tabla).getByRole("rowheader", {
      name: /Razón \(especie\/parcela\)/,
    }).closest("tr")!;
    expect(within(fila).getByText("2.7×")).toBeInTheDocument();
    expect(within(fila).getByText("1.1×")).toBeInTheDocument();
  });

  it("no publica cifras que la API no respalda", async () => {
    mockApi();
    render(<AnalyticsPage />);
    await screen.findByRole("table");
    // Las filas de efectos fijos del informe se declaran pendientes, no se
    // rellenan con números escritos a mano.
    expect(screen.getByText(/efectos_fijos/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("4.64");
  });

  it("arranca sin especie seleccionada y lo explica", async () => {
    mockApi();
    render(<AnalyticsPage />);
    await screen.findByText(/Estancamiento por especie/);
    expect(screen.getByText(/Haz clic en una especie/)).toBeInTheDocument();
  });

  it("filtra por gremio pidiéndoselo al backend", async () => {
    mockApi();
    const user = userEvent.setup();
    render(<AnalyticsPage />);
    await screen.findByText(/Estancamiento por especie/);

    await user.click(screen.getByRole("button", { name: "Inicial" }));

    await waitFor(() => {
      const llamadas = (globalThis.fetch as any).mock.calls.map((c: any[]) => c[0]);
      expect(llamadas.some((u: string) => u.includes("gremio=Inicial"))).toBe(true);
    });
  });

  it("explica qué hacer cuando la analítica no está cargada", async () => {
    mockApi([]);
    render(<AnalyticsPage />);
    expect(await screen.findByText(/Analítica no cargada/)).toBeInTheDocument();
    expect(screen.getByText(/load_analytics.py/)).toBeInTheDocument();
  });
});
