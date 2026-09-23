/**
 * Journey del NDVI (E10a) con la API simulada.
 *
 * Lo que importa: que abrir la página no salga al proveedor, que buscar
 * imágenes muestre el resumen, y que una medición de poca superficie se vea
 * marcada en vez de presentarse como si fuera sólida.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

// En jsdom el contenedor responsivo mide 0 px y Recharts no dibuja nada: sin
// esto no hay ejes que inspeccionar. Es la ÚNICA razón del mock.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 700, height: 320 }),
  };
});

import { IndexPage } from "./IndexPage";
import type { IndexReading, ProjectIndex } from "../api/types";

const PROYECTO = { id: 7, name: "Restauración Guayabal", project_code: "AGS-2026-0007" };

function lectura(
  predio: string,
  fecha: string,
  media: number,
  extra: Partial<IndexReading> = {},
): IndexReading {
  return {
    property_name: predio,
    index: "NDVI",
    scene_id: `S2_${fecha}`,
    acquired_at: fecha,
    cloud_cover: 17.4,
    mean: media,
    median: media,
    minimum: media - 0.2,
    maximum: media + 0.2,
    std: 0.05,
    valid_pixels: 1308,
    reliable: true,
    reading: "Vegetación moderada",
    source: "planetary-computer/sentinel-2-l2a",
    ...extra,
  };
}

const VACIO: ProjectIndex = {
  project_id: 7, index: "NDVI", properties: [], last_refreshed_at: null, readings: [],
};

const CON_DATOS: ProjectIndex = {
  project_id: 7,
  index: "NDVI",
  properties: ["Guayabal", "San Antonio"],
  last_refreshed_at: "2026-09-22T10:00:00Z",
  readings: [
    lectura("Guayabal", "2024-12-08", 0.505),
    lectura("San Antonio", "2024-12-08", 0.453, {
      valid_pixels: 10,
      reliable: false,
      reading: "Vegetación moderada",
    }),
    lectura("Guayabal", "2024-12-18", 0.495),
  ],
};

function mockApi({ vacioAlPrincipio = true } = {}) {
  const llamadas: { url: string; method: string }[] = [];
  let refrescado = false;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((url: string, init: RequestInit = {}) => {
      const method = init.method ?? "GET";
      llamadas.push({ url, method });
      const json = (status: number, body: unknown) =>
        Promise.resolve({
          ok: status < 400, status, headers: new Headers(), json: async () => body,
        });
      if (url === "/projects/7") return json(200, PROYECTO);
      if (url.includes("/refresh")) {
        refrescado = true;
        return json(200, {
          ...CON_DATOS,
          summary: {
            scenes_found: 3, readings_added: 6, without_data: 1,
            interrupted: false, properties: ["Guayabal", "San Antonio"],
          },
        });
      }
      if (url.endsWith("/indices/NDVI")) {
        return json(200, vacioAlPrincipio && !refrescado ? VACIO : CON_DATOS);
      }
      return json(404, { detail: { code: "NOT_FOUND", message: "no" } });
    }),
  );
  return llamadas;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderPagina() {
  return render(
    <MemoryRouter initialEntries={["/proyectos/7/ndvi"]}>
      <Routes>
        <Route path="/proyectos/:id/ndvi" element={<IndexPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("NDVI por predio", () => {
  it("abrir la página no consulta al proveedor", async () => {
    const llamadas = mockApi();
    renderPagina();
    expect(await screen.findByText(/Todavía no hay mediciones/)).toBeInTheDocument();
    expect(llamadas.some((c) => c.method === "POST")).toBe(false);
  });

  it("buscar imágenes muestra el resumen y pinta la serie", async () => {
    const llamadas = mockApi();
    renderPagina();
    await screen.findByText(/Todavía no hay mediciones/);

    await userEvent.click(screen.getByRole("button", { name: "Buscar imágenes nuevas" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      /3 imágenes encontradas · 6 mediciones nuevas · 1 sin datos/,
    );
    expect(llamadas.filter((c) => c.method === "POST")).toHaveLength(1);
    expect(await screen.findByText("0.505")).toBeInTheDocument();
  });

  it("una medición de poca superficie se marca en vez de presumir solidez", async () => {
    mockApi({ vacioAlPrincipio: false });
    renderPagina();
    const celda = await screen.findByText("0.453");
    const fila = celda.closest("tr")!;
    expect(fila.className).toContain("low-sample");
    expect(within(fila).getByText(/superficie muy pequeña/)).toBeInTheDocument();
    expect(within(fila).getByText("10")).toBeInTheDocument();
  });

  it("dice de dónde salen las cifras", async () => {
    mockApi({ vacioAlPrincipio: false });
    renderPagina();
    expect(
      await screen.findByText(/planetary-computer\/sentinel-2-l2a/),
    ).toBeInTheDocument();
  });

  it("el eje Y muestra NDVI decimal, aunque llegue una lectura imposible", async () => {
    // Regresión: el eje llegó a mostrar «41158156». `domain={[0,1]}` sin
    // `allowDataOverflow` es un mínimo, no un anclaje, así que una sola
    // lectura corrupta estiraba la escala a decenas de millones.
    const corrupta: ProjectIndex = {
      ...CON_DATOS,
      readings: [
        ...CON_DATOS.readings,
        lectura("Guayabal", "2024-12-28", 41158156),
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string) =>
        Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers(),
          json: async () => (url === "/projects/7" ? PROYECTO : corrupta),
        }),
      ),
    );
    const { container } = renderPagina();
    await screen.findByText(/Verdor del predio/);
    await waitFor(() =>
      expect(container.querySelector(".recharts-yAxis")).toBeInTheDocument(),
    );

    const etiquetas = [
      ...container.querySelectorAll(".recharts-yAxis .recharts-cartesian-axis-tick-value"),
    ].map((t) => t.textContent ?? "");

    expect(etiquetas.length).toBeGreaterThan(0);
    for (const etiqueta of etiquetas) {
      expect(etiqueta).toMatch(/^-?\d\.\d{2}$/); // 0.45, -0.20… nunca 41158156
      expect(Math.abs(Number(etiqueta))).toBeLessThanOrEqual(1);
    }
    // Y el descarte se dice, no se esconde.
    expect(screen.getByText(/no puede ser un NDVI/)).toBeInTheDocument();
  });

  it("un fallo del proveedor se muestra tal cual, sin perder la página", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((url: string, init: RequestInit = {}) => {
        if ((init.method ?? "GET") === "POST") {
          return Promise.resolve({
            ok: false, status: 503, headers: new Headers(),
            json: async () => ({
              detail: {
                code: "SATELLITE_UNAVAILABLE",
                message: "No se pudo consultar las imágenes satelitales ahora mismo.",
              },
            }),
          });
        }
        const body = url === "/projects/7" ? PROYECTO : VACIO;
        return Promise.resolve({
          ok: true, status: 200, headers: new Headers(), json: async () => body,
        });
      }),
    );
    renderPagina();
    await screen.findByText(/Todavía no hay mediciones/);
    await userEvent.click(screen.getByRole("button", { name: "Buscar imágenes nuevas" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /No se pudo consultar las imágenes satelitales/,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Buscar imágenes nuevas" })).toBeEnabled(),
    );
  });
});
