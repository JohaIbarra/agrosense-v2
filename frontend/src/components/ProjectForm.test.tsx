/**
 * Conversión del formulario al cuerpo de la API: crear omite lo vacío; editar
 * envía solo lo que cambió, y un campo vaciado se envía como null.
 */
import { describe, expect, it } from "vitest";

import type { Project } from "../api/types";
import { toInput } from "./ProjectForm";

const BASE: Project = {
  id: 1, project_code: "AGS-2026-0001", name: "Guayabal", locality: null, description: null,
  created_at: "2026-09-21T00:00:00Z", campaigns_count: 0, contract_code: "UPME 04-2014",
  objective: null, executing_org: null, contracting_entity: null, department: "Antioquia",
  municipality: null, intervention_type: "rehabilitacion", area_ha: 12.5,
  planted_individuals: 856, planting_density: null, establishment_date: null,
  start_date: null, end_date: null, legal_framework: null, environmental_authority: null,
  status: "activo", coordinate_srid: 9377,
};

function valores(extra: Record<string, string> = {}): Record<string, string> {
  const v: Record<string, string> = {};
  for (const [k, val] of Object.entries(BASE)) v[k] = val === null ? "" : String(val);
  return { ...v, ...extra };
}

describe("toInput", () => {
  it("al crear no envía campos vacíos y convierte los números", () => {
    const input = toInput({ name: "Nuevo", area_ha: "3.5", planted_individuals: "120", department: "" });
    expect(input).toEqual({ name: "Nuevo", area_ha: 3.5, planted_individuals: 120 });
  });

  it("al editar sin cambios no envía nada", () => {
    expect(toInput(valores(), BASE)).toEqual({});
  });

  it("al editar envía solo lo que cambió", () => {
    expect(toInput(valores({ municipality: "Sonsón" }), BASE)).toEqual({ municipality: "Sonsón" });
  });

  it("un campo vaciado al editar se envía como null para borrarlo", () => {
    expect(toInput(valores({ contract_code: "" }), BASE)).toEqual({ contract_code: null });
  });

  it("un número sin cambio de valor no se reenvía", () => {
    expect(toInput(valores({ area_ha: "12.50" }), BASE)).toEqual({});
  });
});
