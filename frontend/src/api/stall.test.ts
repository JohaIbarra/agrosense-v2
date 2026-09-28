/** Capa de acceso a la detección de estancados (E7). Mockea `fetch` global. */
import { afterEach, describe, expect, it, vi } from "vitest";

import { getStallAssessment } from "./stall";

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

describe("getStallAssessment", () => {
  it("pide solo los marcados", async () => {
    const spy = mockFetch({ trees: [] });
    await getStallAssessment(7, 4, true);
    expect(spy.mock.calls[0][0]).toBe("/projects/7/monitorings/4/stall-assessment?only_flagged=true");
  });

  it("sin filtro no manda el parámetro", async () => {
    const spy = mockFetch({ trees: [] });
    await getStallAssessment(7, 4, false);
    expect(spy.mock.calls[0][0]).toBe("/projects/7/monitorings/4/stall-assessment");
  });

  it("propaga el código del contrato", async () => {
    mockFetch({ detail: { code: "STALL_MODEL_UNAVAILABLE", message: "No disponible." } }, 503);
    await expect(getStallAssessment(7, 4, true)).rejects.toMatchObject({
      code: "STALL_MODEL_UNAVAILABLE",
    });
  });
});
