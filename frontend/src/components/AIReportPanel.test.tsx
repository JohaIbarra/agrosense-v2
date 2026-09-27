import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AIReportPanel } from "./AIReportPanel";

const REPORT = {
  project_id: 1,
  monitoring: 1,
  model_name: "qwen2.5:3b",
  prompt_version: "2026-09-27-e9.1",
  content: "Borrador generado por IA: revise las cifras antes de usarlo.\n\nHay 2 árboles.",
  unverified_numbers: [] as string[],
  created_at: "2026-09-27T00:00:00Z",
  stale: false,
};

vi.mock("../api/aiReports", () => ({
  getAIReport: vi.fn(),
  generateAIReport: vi.fn(),
}));

import { generateAIReport, getAIReport } from "../api/aiReports";

const mockedGet = vi.mocked(getAIReport);
const mockedGenerate = vi.mocked(generateAIReport);

describe("AIReportPanel", () => {
  it("cuando no hay borrador, ofrece generarlo", async () => {
    mockedGet.mockResolvedValue(null);
    render(<AIReportPanel projectId={1} number={1} />);
    await waitFor(() => screen.getByText("Generar borrador"));
  });

  it("muestra el contenido y permite regenerar cuando ya hay borrador", async () => {
    mockedGet.mockResolvedValue(REPORT);
    render(<AIReportPanel projectId={1} number={1} />);
    await waitFor(() => screen.getByText(/Hay 2 árboles/));
    expect(screen.getByText("Regenerar")).toBeInTheDocument();
  });

  it("avisa cuando el borrador quedó desactualizado", async () => {
    mockedGet.mockResolvedValue({ ...REPORT, stale: true });
    render(<AIReportPanel projectId={1} number={1} />);
    await waitFor(() => screen.getByText(/análisis cambió/));
  });

  it("avisa de los numeros no verificados", async () => {
    mockedGet.mockResolvedValue({ ...REPORT, unverified_numbers: ["250%"] });
    render(<AIReportPanel projectId={1} number={1} />);
    await waitFor(() => screen.getByText(/250%/));
  });

  it("al generar, llama a generateAIReport y muestra el resultado", async () => {
    mockedGet.mockResolvedValue(null);
    mockedGenerate.mockResolvedValue(REPORT);
    const { getByText } = render(<AIReportPanel projectId={1} number={1} />);
    await waitFor(() => getByText("Generar borrador"));
    getByText("Generar borrador").click();
    await waitFor(() => screen.getByText(/Hay 2 árboles/));
    expect(mockedGenerate).toHaveBeenCalledWith(1, 1);
  });

  it("ignora una generación tardía si el ingeniero ya cambió de monitoreo", async () => {
    // Regresión: sin la ref al monitoreo actual, el borrador de M1 pisaba
    // el panel de M2 cuando la generación de 180 s terminaba después de
    // que el ingeniero ya hubiera cambiado de monitoreo (mismo componente,
    // sin desmontar — el `key` de la página es la otra mitad del arreglo,
    // no cubierta por este test unitario).
    mockedGet.mockResolvedValue(null);
    let resolverGeneracion!: (value: typeof REPORT) => void;
    mockedGenerate.mockReturnValue(
      new Promise((resolve) => {
        resolverGeneracion = resolve;
      }),
    );

    const { rerender, getByText, queryByText } = render(
      <AIReportPanel projectId={1} number={1} />,
    );
    await waitFor(() => getByText("Generar borrador"));
    getByText("Generar borrador").click();
    await waitFor(() => expect(mockedGenerate).toHaveBeenCalledWith(1, 1));

    // El ingeniero cambia a M2 antes de que la generación de M1 termine
    // (la generación pendiente sigue viva; no se espera a que termine).
    rerender(<AIReportPanel projectId={1} number={2} />);

    // Ahora llega, tarde, la respuesta de la generación de M1.
    await act(async () => {
      resolverGeneracion(REPORT); // REPORT.monitoring === 1
      await Promise.resolve();
    });

    expect(queryByText(/Hay 2 árboles/)).not.toBeInTheDocument();
  });
});
