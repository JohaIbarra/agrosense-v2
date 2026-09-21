/**
 * Tests de la capa de acceso a datos.
 *
 * Lo que se verifica no es "fetch funciona", sino las dos cosas que romperían
 * la pantalla en silencio: que los nombres con espacios viajen escapados y que
 * un error del backend llegue como `ApiError` con su `code`.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  fetchSpecies,
  fetchSpeciesDetail,
  fetchTopProtective,
  fetchVarianceDecomposition,
} from "./client";

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

describe("construcción de URL", () => {
  it("omite los parámetros vacíos en vez de mandar gremio=", async () => {
    const spy = mockFetch([]);
    await fetchSpecies({ gremio: null, sort: "stall_risk" });
    expect(spy.mock.calls[0][0]).toBe("/api/v1/analytics/species?sort=stall_risk");
  });

  it("incluye el gremio cuando hay filtro", async () => {
    const spy = mockFetch([]);
    await fetchSpecies({ gremio: "Inicial" });
    expect(spy.mock.calls[0][0]).toContain("gremio=Inicial");
  });

  it("escapa el nombre de la especie", async () => {
    // Sin encodeURIComponent, "Lafoensia speciosa" rompe la URL y ninguna
    // especie del dataset (todas llevan espacio) sería consultable.
    const spy = mockFetch({});
    await fetchSpeciesDetail("Lafoensia speciosa");
    expect(spy.mock.calls[0][0]).toBe(
      "/api/v1/analytics/species/Lafoensia%20speciosa",
    );
  });

  it("pasa el modelo a top-protective", async () => {
    const spy = mockFetch([]);
    await fetchTopProtective("mortality", 3);
    expect(spy.mock.calls[0][0]).toContain("model=mortality");
    expect(spy.mock.calls[0][0]).toContain("limit=3");
  });
});

describe("errores", () => {
  it("traduce {detail:{code,message}} a ApiError", async () => {
    mockFetch(
      { detail: { code: "SPECIES_NOT_FOUND", message: "No hay analítica." } },
      404,
    );
    await expect(fetchSpeciesDetail("Ficus inventada")).rejects.toMatchObject({
      code: "SPECIES_NOT_FOUND",
      status: 404,
      message: "No hay analítica.",
    });
  });

  it("distingue 'no cargado' para que la UI lo explique", async () => {
    mockFetch(
      { detail: { code: "ANALYTICS_NOT_LOADED", message: "Ejecute el script." } },
      404,
    );
    await expect(fetchVarianceDecomposition()).rejects.toBeInstanceOf(ApiError);
  });

  it("no filtra el cuerpo crudo cuando la respuesta no es JSON", async () => {
    // Un 502 del proxy devuelve HTML; el usuario no debe ver ese HTML.
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new Error("no es JSON");
        },
      }),
    );
    const error = await fetchSpecies().catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("UNKNOWN");
    expect(error.message).toContain("502");
  });
});
