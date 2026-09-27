import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ContrastPage } from "../pages/ContrastPage";

vi.mock("../api/contrast", () => ({
  getReferenceContrast: vi.fn().mockResolvedValue([
    {
      species: "Lafoensia speciosa",
      n_trees_in_project: 12,
      has_reference: true,
      gremio: "Tardia",
      stall_risk: {
        odds_ratio: 4.94, or_ci95: [2.71, 9.02], ci95_log_odds: null,
        significant: true, interpretation: "Se estanca ~4.9x mas de lo esperado.",
      },
      mortality_risk: {
        odds_ratio: 1.0, or_ci95: [0.4, 2.5], ci95_log_odds: null,
        significant: false, interpretation: "Sin efecto significativo.",
      },
      narrative: "Planto 12 arboles de Lafoensia speciosa...",
    },
    {
      species: "Especie inventada",
      n_trees_in_project: 3,
      has_reference: false,
      gremio: null,
      stall_risk: null,
      mortality_risk: null,
      narrative: "Sin referencia: esta especie no esta entre las del dataset cientifico.",
    },
  ]),
}));

vi.mock("../api/projects", () => ({
  getProject: vi.fn().mockResolvedValue({ id: 1, name: "Proyecto de prueba" }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/proyectos/1/referente-contraste"]}>
      <Routes>
        <Route path="/proyectos/:id/referente-contraste" element={<ContrastPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ContrastPage", () => {
  it("muestra la especie con referente y su lectura", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Lafoensia speciosa"));
    expect(screen.getByText(/4.9x mas/)).toBeInTheDocument();
  });

  it("marca la especie sin referencia en vez de omitirla", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Especie inventada"));
    expect(screen.getByText(/Sin referencia/)).toBeInTheDocument();
  });
});
