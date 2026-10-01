/** Capacidades opcionales del servidor (p. ej. IA local). Mockea `fetch` global. */
import { afterEach, describe, expect, it, vi } from "vitest";

import { getFeatures } from "./features";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getFeatures", () => {
  it("pide /api/v1/features y devuelve el contrato", async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ai_reports: false }) });
    vi.stubGlobal("fetch", spy);
    await expect(getFeatures()).resolves.toEqual({ ai_reports: false });
    expect(spy.mock.calls[0][0]).toBe("/api/v1/features");
  });
});
