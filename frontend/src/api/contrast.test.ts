/**
 * Test de la capa de acceso al contraste de especies con el referente
 * (UC-AN3). Sigue el patrón de `client.test.ts`: mockea `fetch` global en vez
 * de espiar `http.request` (que es una función exportada de un módulo ESM,
 * no un método de un objeto — `vi.spyOn` no la intercepta de forma fiable).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { getReferenceContrast } from "./contrast";

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

describe("getReferenceContrast", () => {
  it("pide el contraste del proyecto por su id", async () => {
    const spy = mockFetch([]);
    await getReferenceContrast(42);
    expect(spy.mock.calls[0][0]).toBe("/projects/42/reference-contrast");
  });
});
