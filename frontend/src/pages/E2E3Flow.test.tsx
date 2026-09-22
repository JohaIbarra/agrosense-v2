/**
 * Journey crítico de E2/E3 (proveedor de autenticación falso, API simulada):
 * ficha → subir Excel con fecha → ver avisos → abrir el análisis → cambiar de
 * análisis y de predio → descargar el reporte.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { AuthProvider, type AuthClient } from "../auth/AuthProvider";
import type { MonitoringAnalysis } from "../api/types";

const auth: AuthClient = {
  getSession: async () => ({ accessToken: "tok", email: "ing@example.com" }),
  onChange: () => () => {},
  signIn: async () => {},
  signUp: async () => true,
  signOut: async () => {},
};

const PROYECTO = {
  id: 7, project_code: "AGS-2026-0007", name: "Restauración Guayabal", locality: null,
  description: null, created_at: "2026-09-21T00:00:00Z", campaigns_count: 0,
  contract_code: null, objective: null, executing_org: null, contracting_entity: null,
  department: null, municipality: null, intervention_type: null, area_ha: null,
  planted_individuals: null, planting_density: null, establishment_date: null,
  start_date: null, end_date: null, legal_framework: null, environmental_authority: null,
  status: "activo", coordinate_srid: 9377,
};

const M4 = {
  number: 4, monitoring_date: "2024-11-15", field_crew: "Cuadrilla", recorder: null,
  notes: null, observations: 856,
};

const ANALISIS: MonitoringAnalysis = {
  project_id: 7, monitoring: 4, monitoring_date: "2024-11-15", previous: 3,
  monitorings: [1, 2, 3, 4], properties: ["Guayabal", "Tres Jotas"],
  analysis_version: "2026-09-22-e3.1", input_hash: "abcdef0123456789".repeat(4),
  computed_at: "2026-09-22T10:00:00Z",
  summary: [
    { key: "survival", label: "Supervivencia", kind: "percent", decimals: 1, value: 83.878 },
  ],
  sections: [
    {
      id: "composicion", title: "Composición", description: "Individuos vivos en M4.", notes: [],
      charts: [],
      tables: [
        {
          id: "c-g", title: "Composición por diseño florístico — Guayabal (M4)",
          property: "Guayabal", notes: [], footer: [{ species: "Total", total: 280 }],
          columns: [
            { key: "species", label: "Especie", kind: "text" },
            { key: "total", label: "Total", kind: "int", decimals: 0 },
          ],
          rows: [{ species: "Cedrela montana", total: 14 }],
        },
        {
          id: "c-tj", title: "Composición por diseño florístico — Tres Jotas (M4)",
          property: "Tres Jotas", notes: [], footer: [{ species: "Total", total: 374 }],
          columns: [
            { key: "species", label: "Especie", kind: "text" },
            { key: "total", label: "Total", kind: "int", decimals: 0 },
          ],
          rows: [{ species: "Dodonaea viscosa", total: 50 }],
        },
      ],
    },
    {
      id: "supervivencia", title: "Supervivencia", description: "Vivos / total.", notes: [],
      charts: [],
      tables: [
        {
          id: "s", title: "Supervivencia por predio y monitoreo", property: null, notes: [],
          footer: [],
          columns: [
            { key: "property", label: "Predio", kind: "text" },
            { key: "m4", label: "% M4", kind: "percent", decimals: 1 },
          ],
          rows: [{ property: "Guayabal", m4: 80.2292 }],
        },
      ],
    },
  ],
};

function mockApi() {
  const calls: { url: string; method: string; body: unknown }[] = [];
  const spy = vi.fn().mockImplementation((url: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    calls.push({ url, method, body: init.body });
    const json = (status: number, body: unknown) =>
      Promise.resolve({
        ok: status < 400, status, headers: new Headers(), json: async () => body,
      });
    if (url === "/projects/7" && method === "GET") return json(200, PROYECTO);
    if (url === "/projects/7/monitorings") {
      const subidos = calls.some((c) => c.method === "POST");
      return json(200, subidos ? [M4] : []);
    }
    if (url === "/projects/7/campaigns" && method === "POST") {
      return json(201, {
        valid: true, campaign_id: 1, trees: 856, observations: 3146, deaths: 340,
        monitorings: [1, 2, 3, 4], analyzed: [1, 2, 3, 4], errors: [],
        warnings: [
          { type: "contraction", tree_id: "FR_1_3", message: "Contracción de 7 cm entre M1 y M2" },
        ],
      });
    }
    if (url === "/projects/7/monitorings/4/analysis") return json(200, ANALISIS);
    if (url === "/projects/7/monitorings/4/report.xlsx") {
      return Promise.resolve({
        ok: true, status: 200,
        headers: new Headers({
          "Content-Disposition": 'attachment; filename="AgroSense_AGS-2026-0007_M4.xlsx"',
        }),
        blob: async () => new Blob(["xlsx"]),
      });
    }
    return json(404, { detail: { code: "NOT_FOUND", message: "no" } });
  });
  vi.stubGlobal("fetch", spy);
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider client={auth}>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("E2/E3 en la interfaz", () => {
  it("sube el Excel con la fecha, muestra los avisos y enlaza al análisis", async () => {
    const calls = mockApi();
    renderAt("/proyectos/7");
    expect(await screen.findByText(/Aún no hay monitoreos cargados/)).toBeInTheDocument();

    const file = new File(["x"], "anexo1.xlsx");
    await userEvent.upload(screen.getByLabelText("Archivo Excel (.xlsx)"), file);
    const fecha = screen.getByLabelText("Fecha del monitoreo");
    await userEvent.type(fecha, "2024-11-15");
    await userEvent.click(screen.getByRole("button", { name: "Cargar y analizar" }));

    expect(await screen.findByText(/856 árboles y 3146 observaciones de M1, M2, M3, M4/))
      .toBeInTheDocument();
    expect(screen.getByText(/Contracciones de altura/)).toBeInTheDocument();
    expect(screen.getByText("FR_1_3")).toBeInTheDocument();

    const post = calls.find((c) => c.method === "POST")!;
    const form = post.body as FormData;
    expect(form.get("monitoring_date")).toBe("2024-11-15");
    expect((form.get("file") as File).name).toBe("anexo1.xlsx");

    expect(await screen.findByRole("link", { name: "Ver análisis de M4" })).toHaveAttribute(
      "href",
      "/proyectos/7/monitoreos/4",
    );
  });

  it("muestra el análisis, filtra por predio, cambia de hoja y descarga el reporte", async () => {
    const calls = mockApi();
    const createUrl = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", { ...URL, createObjectURL: createUrl, revokeObjectURL: vi.fn() });
    renderAt("/proyectos/7/monitoreos/4");

    expect(await screen.findByRole("heading", { name: "Análisis del monitoreo M4" }))
      .toBeInTheDocument();
    expect(screen.getByText(/Comparado con M3/)).toBeInTheDocument();
    expect(screen.getByText("83,9 %")).toBeInTheDocument();
    expect(screen.getByText("Cedrela montana")).toBeInTheDocument();
    expect(screen.getByText("Dodonaea viscosa")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Tres Jotas" }));
    expect(screen.queryByText("Cedrela montana")).not.toBeInTheDocument();
    expect(screen.getByText("Dodonaea viscosa")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Supervivencia" }));
    expect(screen.getByText("80,2 %")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Descargar reporte (.xlsx)" }));
    await waitFor(() => expect(createUrl).toHaveBeenCalled());
    const pedido = calls.find((c) => c.url.endsWith("/report.xlsx"));
    expect(pedido).toBeDefined();
  });

  it("un error del backend en la carga se muestra tal cual", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, init: RequestInit = {}) => {
        if (init.method === "POST") {
          return Promise.resolve({
            ok: false, status: 422, headers: new Headers(),
            json: async () => ({
              detail: { code: "INVALID_MONITORING_DATE", message: "La fecha del M4 esta en el futuro." },
            }),
          });
        }
        const body = url === "/projects/7" ? PROYECTO : [];
        return Promise.resolve({ ok: true, status: 200, headers: new Headers(), json: async () => body });
      }),
    );
    renderAt("/proyectos/7");
    await screen.findByText(/Aún no hay monitoreos/);
    await userEvent.upload(screen.getByLabelText("Archivo Excel (.xlsx)"), new File(["x"], "a.xlsx"));
    await userEvent.click(screen.getByRole("button", { name: "Cargar y analizar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("esta en el futuro");
  });
});
