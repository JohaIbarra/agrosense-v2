/** Capa de acceso al riesgo de mortalidad (E8). Mockea `fetch` global. */
import { afterEach, describe, expect, it, vi } from "vitest";

import { getMortalityRisk } from "./mortality";
import type { MortalityRisk } from "./types";

function mockFetch(body: unknown, status = 200) {
  const spy = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getMortalityRisk", () => {
  it("pide solo los marcados", async () => {
    const spy = mockFetch({ trees: [] });
    await getMortalityRisk(7, 4, true);
    expect(spy.mock.calls[0][0]).toBe("/projects/7/monitorings/4/mortality-risk?only_flagged=true");
  });

  it("sin filtro no manda el parámetro", async () => {
    const spy = mockFetch({ trees: [] });
    await getMortalityRisk(7, 4, false);
    expect(spy.mock.calls[0][0]).toBe("/projects/7/monitorings/4/mortality-risk");
  });

  it("devuelve el cuerpo tipado según el contrato", async () => {
    const body = { model_kind: "general", score_kind: "relative_risk", trees: [] };
    mockFetch(body);
    const r: MortalityRisk = await getMortalityRisk(7, 4, false);
    expect(r.score_kind).toBe("relative_risk");
  });

  it("propaga el código del contrato", async () => {
    mockFetch({ detail: { code: "MORTALITY_MODEL_UNAVAILABLE", message: "No disponible." } }, 503);
    await expect(getMortalityRisk(7, 4, true)).rejects.toMatchObject({
      code: "MORTALITY_MODEL_UNAVAILABLE",
    });
  });
});
