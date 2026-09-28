import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { StallAssessment } from "../api/types";
import { StallPanel } from "./StallPanel";

vi.mock("../api/stall", () => ({ getStallAssessment: vi.fn() }));

import { getStallAssessment } from "../api/stall";

const mocked = vi.mocked(getStallAssessment);

const BASE: StallAssessment = {
  project_id: 7,
  monitoring: 4,
  input_hash: "abcdef0123456789".repeat(4),
  computed_at: "2026-09-27T10:00:00Z",
  alert_budget_pct: 20,
  persistent_min_intervals: 2,
  model: {
    model_version: "stall-logreg-2026-09-27.1",
    artifact_sha256: "a".repeat(64),
    dataset_sha256: "0".repeat(64),
    trained_on: "anexo1.xlsx",
    pr_auc: 0.478,
    pr_auc_ci_low: 0.37,
    pr_auc_ci_high: 0.58,
    roc_auc: 0.738,
    prevalence_pct: 21.9,
    recall_at_budget_pct: 43.3,
    precision_at_budget_pct: 47.6,
  },
  summary: {
    at_risk: 718,
    flagged: 143,
    stalled_last_interval: 157,
    persistent: 24,
    without_history: 0,
    unknown_species: 0,
  },
  trees: [
    {
      tree_id: "FR_9_99",
      species: "Lafoensia speciosa",
      locality: "San Antonio",
      plot: "GEB/SA/1",
      probability: 0.62,
      flagged: true,
      stalled_last_interval: true,
      stall_streak: 2,
      persistent: true,
      known_species: true,
    },
  ],
};

describe("StallPanel", () => {
  it("muestra el resumen, la lectura honesta del modelo y los árboles marcados", async () => {
    mocked.mockResolvedValue(BASE);
    render(<StallPanel projectId={7} number={4} />);
    expect(await screen.findByText("FR_9_99")).toBeInTheDocument();
    expect(screen.getByText(/143 de 718 árboles vivos/)).toBeInTheDocument();
    expect(screen.getByText(/sugestiva, no concluyente/)).toBeInTheDocument();
    expect(screen.getByText("62 %")).toBeInTheDocument();
    expect(screen.getByText(/2 intervalos seguidos/)).toBeInTheDocument();
    expect(mocked).toHaveBeenLastCalledWith(7, 4, true, expect.anything());
  });

  it("«Ver todos» pide la lista completa", async () => {
    mocked.mockResolvedValue(BASE);
    render(<StallPanel projectId={7} number={4} />);
    await screen.findByText("FR_9_99");
    await userEvent.click(screen.getByLabelText("Ver todos los árboles vivos"));
    await waitFor(() => expect(mocked).toHaveBeenLastCalledWith(7, 4, false, expect.anything()));
  });

  it("avisa de las especies que el modelo no vio", async () => {
    mocked.mockResolvedValue({ ...BASE, summary: { ...BASE.summary, unknown_species: 5 } });
    render(<StallPanel projectId={7} number={4} />);
    expect(await screen.findByText(/5 árboles son de especies que el modelo no vio/))
      .toBeInTheDocument();
  });

  it("muestra el error del backend", async () => {
    mocked.mockRejectedValue(new Error("El modelo de detección de estancados no está disponible."));
    render(<StallPanel projectId={7} number={4} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/no está disponible/);
  });
});
