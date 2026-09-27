/**
 * Test de la capa de acceso al borrador de informe con IA (E9). Sigue el
 * patrón de `contrast.test.ts`: mockea `fetch` global.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { generateAIReport, getAIReport } from "./aiReports";

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

describe("getAIReport", () => {
  it("pide el borrador del monitoreo", async () => {
    const spy = mockFetch({
      project_id: 1, monitoring: 1, model_name: "qwen2.5:3b", prompt_version: "v1",
      content: "texto", unverified_numbers: [], created_at: "2026-09-27T00:00:00Z",
      stale: false,
    });
    await getAIReport(1, 1);
    expect(spy.mock.calls[0][0]).toBe("/projects/1/monitorings/1/ai-report");
  });

  it("devuelve null cuando todavia no hay borrador (404)", async () => {
    mockFetch(
      { detail: { code: "AI_REPORT_NOT_FOUND", message: "Genere el borrador primero." } },
      404,
    );
    expect(await getAIReport(1, 1)).toBeNull();
  });
});

describe("generateAIReport", () => {
  it("hace POST al mismo recurso", async () => {
    const spy = mockFetch({
      project_id: 1, monitoring: 1, model_name: "qwen2.5:3b", prompt_version: "v1",
      content: "texto", unverified_numbers: [], created_at: "2026-09-27T00:00:00Z",
      stale: false,
    });
    await generateAIReport(1, 1);
    expect(spy.mock.calls[0][0]).toBe("/projects/1/monitorings/1/ai-report");
    expect(spy.mock.calls[0][1].method).toBe("POST");
  });
});
