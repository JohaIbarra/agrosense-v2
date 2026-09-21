/**
 * El detalle es el único sitio donde los números se renderizan como texto, así
 * que es donde la regla «OR siempre, log-odds nunca» se puede verificar de
 * verdad sobre el DOM.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SpeciesAnalytics } from "../api/types";
import { SpeciesDetail } from "./SpeciesDetail";

const LAFOENSIA: SpeciesAnalytics = {
  species: "Lafoensia speciosa",
  stall_risk: {
    odds_ratio: 4.9427,
    or_ci95: [2.2503, 10.856],
    ci95_log_odds: [0.8111, 2.3847],
    significant: true,
    interpretation: "Se estanca ~4.9x mas de lo esperado, IC 95% del OR no cruza 1.",
  },
  mortality_risk: {
    odds_ratio: 1.42,
    or_ci95: [0.5223, 3.861],
    ci95_log_odds: [-0.6494, 1.3509],
    significant: false,
    interpretation: "Sin efecto significativo distinguible del promedio.",
  },
  n_observations: 28,
  n_trees: 14,
  gremio: "Inicial",
};

const noop = () => {};

describe("SpeciesDetail", () => {
  it("muestra el intervalo en OR y nunca el de log-odds", () => {
    render(<SpeciesDetail species={LAFOENSIA} onClose={noop} />);
    const texto = document.body.textContent ?? "";

    // Lo que debe verse: el IC exponenciado.
    expect(texto).toContain("2.25");
    expect(texto).toContain("10.86");
    // Lo que jamás debe verse: los extremos en log-odds.
    expect(texto).not.toContain("0.81");
    expect(texto).not.toContain("2.38");
    expect(texto).not.toContain("-0.65");
  });

  it("no presenta un IC que cruza 1 como si fuera un hallazgo", () => {
    render(<SpeciesDetail species={LAFOENSIA} onClose={noop} />);
    // La mortalidad de esta especie no es concluyente: OR 1.42 con IC
    // [0.52, 3.86]. Debe quedar marcado como tal.
    expect(screen.getByText("IC cruza 1")).toBeInTheDocument();
    expect(screen.getByText("IC concluyente")).toBeInTheDocument();
    expect(
      screen.getByText(/Sin efecto significativo distinguible del promedio/),
    ).toBeInTheDocument();
  });

  it("usa la interpretación del backend, no una calculada aquí", () => {
    render(<SpeciesDetail species={LAFOENSIA} onClose={noop} />);
    expect(screen.getByText(LAFOENSIA.stall_risk.interpretation)).toBeInTheDocument();
    expect(screen.getByText(LAFOENSIA.mortality_risk.interpretation)).toBeInTheDocument();
  });

  it("avisa cuando la especie tiene pocos árboles", () => {
    render(<SpeciesDetail species={LAFOENSIA} onClose={noop} />);
    // 14 árboles: el intervalo es ancho y conviene decirlo.
    expect(screen.getByText(/señal a confirmar/)).toBeInTheDocument();
  });

  it("no avisa cuando la muestra es suficiente", () => {
    const grande = { ...LAFOENSIA, n_trees: 63 };
    render(<SpeciesDetail species={grande} onClose={noop} />);
    expect(screen.queryByText(/señal a confirmar/)).not.toBeInTheDocument();
  });

  it("dice 'sin estimación' en vez de inventar un cero", () => {
    const parcial: SpeciesAnalytics = {
      ...LAFOENSIA,
      mortality_risk: {
        odds_ratio: null,
        or_ci95: null,
        ci95_log_odds: null,
        significant: null,
        interpretation: "Sin estimacion disponible para este modelo.",
      },
    };
    render(<SpeciesDetail species={parcial} onClose={noop} />);
    expect(screen.getByText(/Sin estimación disponible/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("OR 0.00");
  });

  it("muestra el estado vacío sin especie seleccionada", () => {
    const onClose = vi.fn();
    render(<SpeciesDetail species={null} onClose={onClose} />);
    expect(screen.getByText(/Haz clic en una especie/)).toBeInTheDocument();
  });
});
