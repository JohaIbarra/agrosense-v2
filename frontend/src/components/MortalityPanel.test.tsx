import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { MortalityRisk } from "../api/types";
import { MortalityPanel } from "./MortalityPanel";

vi.mock("../api/mortality", () => ({ getMortalityRisk: vi.fn() }));

import { getMortalityRisk } from "../api/mortality";

const mocked = vi.mocked(getMortalityRisk);

const BASE: MortalityRisk = {
  project_id: 7,
  monitoring: 3,
  model_kind: "general",
  score_kind: "relative_risk",
  model_version: "mortality-general-2026-09-30.1",
  artifact_sha256: "a".repeat(64),
  input_hash: "abcdef0123456789".repeat(4),
  computed_at: "2026-09-30T10:00:00Z",
  decision: { reason: "sin_intervalos_cerrados" },
  model: {
    model_version: "mortality-general-2026-09-30.1",
    trained_on: ["Anexo 1", "Werden 2018", "Werden 2020"],
    lopo: [{ held_out: "Anexo 1", median_lift: 1.683 }],
    gate_passed: true,
  },
  alert_budget_pct: 20,
  summary: { at_risk: 754, flagged: 151, stalled_last_interval: 120, without_history: 0 },
  trees: [
    {
      tree_id: "G_1",
      species: "Senna viarum",
      locality: "Guayabal",
      plot: "U1",
      height_m: 0.42,
      score: 0.083,
      risk_percentile: 97.5,
      flagged: true,
      stalled_last_interval: false,
    },
  ],
};

describe("MortalityPanel", () => {
  it("modelo general: explica el motivo, muestra percentil y nota de ranking relativo", async () => {
    mocked.mockResolvedValue(BASE);
    render(<MortalityPanel projectId={7} number={3} />);
    expect(await screen.findByText("G_1")).toBeInTheDocument();
    expect(screen.getByText(/Primer monitoreo: se usa el modelo general/)).toBeInTheDocument();
    expect(screen.getByText(/151 de 754 árboles vivos/)).toBeInTheDocument();
    expect(screen.getByText("percentil 98")).toBeInTheDocument();
    expect(screen.getByText(/ranking relativo, no una probabilidad/)).toBeInTheDocument();
    expect(mocked).toHaveBeenLastCalledWith(7, 3, true, expect.anything());
  });

  it("modelo propio: muestra el lift y el riesgo como porcentaje", async () => {
    mocked.mockResolvedValue({
      ...BASE,
      model_kind: "project",
      score_kind: "probability",
      decision: {
        reason: "propio_mejor",
        holdout_interval: "M2→M3",
        holdout_lift_project: 2.416,
        holdout_lift_general: 1.683,
      },
      trees: [{ ...BASE.trees[0], score: 0.083 }],
    });
    render(<MortalityPanel projectId={7} number={3} />);
    expect(await screen.findByText("8 %")).toBeInTheDocument();
    expect(screen.getByText(/lift 2,42 vs 1,68/)).toBeInTheDocument();
    expect(screen.queryByText(/ranking relativo/)).not.toBeInTheDocument();
  });

  it("explica pocos_eventos y general_mejor", async () => {
    mocked.mockResolvedValue({ ...BASE, decision: { reason: "pocos_eventos" } });
    const { unmount } = render(<MortalityPanel projectId={7} number={3} />);
    expect(await screen.findByText(/pocas muertes registradas/)).toBeInTheDocument();
    unmount();
    mocked.mockResolvedValue({
      ...BASE,
      decision: { reason: "general_mejor", holdout_interval: "M2→M3" },
    });
    render(<MortalityPanel projectId={7} number={3} />);
    expect(await screen.findByText(/predijo mejor el último intervalo \(M2→M3\)/))
      .toBeInTheDocument();
  });

  it("«Ver todos» pide la lista completa", async () => {
    mocked.mockResolvedValue(BASE);
    render(<MortalityPanel projectId={7} number={3} />);
    await screen.findByText("G_1");
    await userEvent.click(screen.getByLabelText("Ver todos los árboles vivos"));
    await waitFor(() => expect(mocked).toHaveBeenLastCalledWith(7, 3, false, expect.anything()));
  });

  it("estado vacío cuando no hay árboles marcados", async () => {
    mocked.mockResolvedValue({ ...BASE, trees: [] });
    render(<MortalityPanel projectId={7} number={3} />);
    expect(await screen.findByText(/No hay árboles marcados/)).toBeInTheDocument();
  });

  it("muestra el error del backend", async () => {
    mocked.mockRejectedValue(new Error("El modelo de mortalidad no está disponible."));
    render(<MortalityPanel projectId={7} number={3} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/no está disponible/);
  });
});
