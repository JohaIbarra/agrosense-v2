/**
 * El transporte adjunta el token de sesión y reacciona al 401 (E1).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, configureHttp, request } from "./http";

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
  configureHttp({ getAccessToken: async () => null, onUnauthorized: () => {} });
});

describe("http", () => {
  it("adjunta el token de sesión como Bearer", async () => {
    configureHttp({ getAccessToken: async () => "tok-123" });
    const spy = mockFetch([]);
    await request("/projects");
    expect(spy.mock.calls[0][1].headers.Authorization).toBe("Bearer tok-123");
  });

  it("sin sesión no inventa una cabecera Authorization", async () => {
    const spy = mockFetch([]);
    await request("/projects");
    expect(spy.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });

  it("envía JSON con su Content-Type en POST", async () => {
    const spy = mockFetch({ id: 1 });
    await request("/projects", { method: "POST", body: { name: "P" } });
    const init = spy.mock.calls[0][1];
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ name: "P" });
  });

  it("un 401 avisa a quien gestiona la sesión y lanza ApiError", async () => {
    const onUnauthorized = vi.fn();
    configureHttp({ onUnauthorized });
    mockFetch({ detail: { code: "UNAUTHENTICATED", message: "Inicie sesion." } }, 401);
    await expect(request("/projects")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("un 404 no cierra la sesión", async () => {
    const onUnauthorized = vi.fn();
    configureHttp({ onUnauthorized });
    mockFetch({ detail: { code: "PROJECT_NOT_FOUND", message: "No existe." } }, 404);
    await expect(request("/projects/9")).rejects.toMatchObject({ code: "PROJECT_NOT_FOUND" });
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it("traduce la validación de FastAPI a un mensaje con el campo", async () => {
    mockFetch({ detail: [{ loc: ["body", "name"], msg: "Field required" }] }, 422);
    await expect(request("/projects", { method: "POST", body: {} })).rejects.toMatchObject({
      code: "VALIDATION",
      message: expect.stringContaining("name"),
    });
  });
});
