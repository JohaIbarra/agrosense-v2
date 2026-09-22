import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AnalysisTable } from "../api/types";
import { formatValue } from "../analysis/format";
import { DataTable } from "./DataTable";

const TABLE: AnalysisTable = {
  id: "t",
  title: "Altura por especie y diseño — Guayabal",
  property: "Guayabal",
  columns: [
    { key: "species", label: "Especie", kind: "text" },
    { key: "c0_prev", label: "M3", kind: "decimal", decimals: 2, group: "ABB" },
    { key: "c0_cur", label: "M4", kind: "decimal", decimals: 2, group: "ABB" },
    { key: "pct", label: "% supervivencia", kind: "percent", decimals: 1 },
  ],
  rows: [
    { species: "Senna viarum", c0_prev: 0.5, c0_cur: 0.7981, pct: 100 },
    { species: "Cedrela montana", c0_prev: 0.33, c0_cur: null, pct: 80, _flags: ["low_sample"] },
    { species: "Inga punctata", c0_prev: 0.46, c0_cur: 0.589, pct: 88.8889 },
  ],
  footer: [{ species: "Media general", c0_prev: 0.43, c0_cur: 0.69, pct: 82.6 }],
  notes: ["Media de altura total (m)."],
};

function bodyRows() {
  const [, tbody] = screen.getAllByRole("rowgroup");
  return within(tbody).getAllByRole("row").map((r) => within(r).getAllByRole("cell")[0].textContent);
}

describe("formatValue", () => {
  it("usa los decimales y el tipo que declara la columna", () => {
    expect(formatValue(0.7981, { kind: "decimal", decimals: 2 })).toBe("0,80");
    expect(formatValue(88.8889, { kind: "percent", decimals: 1 })).toBe("88,9 %");
    expect(formatValue(1234, { kind: "int", decimals: 0 })).toBe("1.234");
    expect(formatValue(null, { kind: "decimal", decimals: 2 })).toBe("—");
  });
});

describe("DataTable", () => {
  it("muestra encabezados agrupados, valores formateados, pie y notas", () => {
    render(<DataTable table={TABLE} />);
    expect(screen.getByText("ABB")).toHaveAttribute("colspan", "2");
    expect(screen.getByText("0,80")).toBeInTheDocument();
    expect(screen.getByText("Media general")).toBeInTheDocument();
    expect(screen.getByText("Media de altura total (m).")).toBeInTheDocument();
    expect(screen.getByText(/Muestra pequeña/)).toBeInTheDocument();
  });

  it("ordena al hacer clic en el encabezado, y los vacíos quedan al final", async () => {
    render(<DataTable table={TABLE} />);
    expect(bodyRows()[0]).toContain("Senna viarum");
    await userEvent.click(screen.getByRole("button", { name: /Especie/ }));
    expect(bodyRows()[0]).toContain("Cedrela montana");
    await userEvent.click(screen.getByRole("button", { name: /M4/ }));
    await userEvent.click(screen.getByRole("button", { name: /M4/ }));
    const desc = bodyRows();
    expect(desc[0]).toContain("Senna viarum");
    expect(desc[2]).toContain("Cedrela montana"); // M4 vacío: al final
  });
});
