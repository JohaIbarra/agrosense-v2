/**
 * El eje Y del NDVI (E10a).
 *
 * Regresión: el eje mostraba números como 41158156 porque `domain={[0,1]}`
 * en Recharts es un MÍNIMO, no un anclaje: sin `allowDataOverflow` el dominio
 * se estira hasta abarcar cualquier valor, así que una sola lectura imposible
 * arrastraba el eje a decenas de millones mientras el tooltip seguía bien.
 */
import { describe, expect, it } from "vitest";

import { NDVI_MAX, NDVI_MIN, formatNdviTick, ndviDomain, plottableNdvi } from "./ndviAxis";

describe("dominio del eje Y del NDVI", () => {
  it("se ciñe a los datos sin aplastar la lectura", () => {
    const [lo, hi] = ndviDomain([0.501, 0.434, 0.488]);
    expect(lo).toBeLessThanOrEqual(0.434);
    expect(hi).toBeGreaterThanOrEqual(0.501);
    // No es el rango teórico entero: eso aplastaría la variación real.
    expect(hi - lo).toBeLessThan(0.4);
  });

  it("NUNCA sale del rango teórico del NDVI, pase lo que pase con los datos", () => {
    for (const valores of [[41158156, 58841843], [-99, 42], [1e9], [Infinity, 0.5]]) {
      const [lo, hi] = ndviDomain(valores);
      expect(lo).toBeGreaterThanOrEqual(NDVI_MIN);
      expect(hi).toBeLessThanOrEqual(NDVI_MAX);
    }
  });

  it("un valor imposible no arrastra el eje: los demás mandan", () => {
    const sano = ndviDomain([0.501, 0.434, 0.488]);
    const conBasura = ndviDomain([0.501, 0.434, 0.488, 41158156]);
    expect(conBasura).toEqual(sano);
  });

  it("una serie plana conserva un margen legible en vez de quedar pegada al eje", () => {
    const [lo, hi] = ndviDomain([0.5, 0.5, 0.5]);
    expect(hi - lo).toBeGreaterThanOrEqual(0.1);
    expect(lo).toBeLessThan(0.5);
    expect(hi).toBeGreaterThan(0.5);
  });

  it("sin ningún valor utilizable cae en un rango de vegetación razonable", () => {
    expect(ndviDomain([])).toEqual([0, 1]);
    expect(ndviDomain([NaN, Infinity])).toEqual([0, 1]);
  });

  it("acepta NDVI negativo, que es físicamente real (agua, nube)", () => {
    const [lo, hi] = ndviDomain([-0.3, 0.2]);
    expect(lo).toBeLessThanOrEqual(-0.3);
    expect(hi).toBeGreaterThanOrEqual(0.2);
  });

  it("los límites del dominio son múltiplos limpios, no decimales sucios", () => {
    for (const v of ndviDomain([0.4337, 0.5012])) {
      expect(Math.round(v * 1000) / 1000).toBe(v);
    }
  });
});

describe("etiquetas del eje", () => {
  it("son decimales con dos cifras, nunca enteros gigantes", () => {
    expect(formatNdviTick(0.5)).toBe("0.50");
    expect(formatNdviTick(0.45)).toBe("0.45");
    expect(formatNdviTick(-0.2)).toBe("-0.20");
    // Lo que veía el usuario: el mismo número, ya imposible de producir.
    expect(formatNdviTick(0.41158156)).toBe("0.41");
  });
});

describe("qué se dibuja", () => {
  it("deja fuera lo que el NDVI no puede valer, y lo dice", () => {
    const { series, descartadas } = plottableNdvi(
      [
        { acquired_at: "2026-08-20", Guayabal: 0.501, "Tres Jotas": 41158156 },
        { acquired_at: "2026-08-25", Guayabal: 0.511, "Tres Jotas": 0.509 },
      ],
      ["Guayabal", "Tres Jotas"],
    );
    expect(descartadas).toBe(1);
    expect(series[0]["Tres Jotas"]).toBeUndefined();
    expect(series[0].Guayabal).toBe(0.501);
    expect(series[1]["Tres Jotas"]).toBe(0.509);
  });

  it("con datos sanos no descarta nada ni toca los valores", () => {
    const filas = [{ acquired_at: "2026-08-20", Guayabal: 0.501 }];
    const { series, descartadas } = plottableNdvi(filas, ["Guayabal"]);
    expect(descartadas).toBe(0);
    expect(series).toEqual(filas);
  });
});
