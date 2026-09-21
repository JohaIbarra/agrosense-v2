import "@testing-library/jest-dom/vitest";

/**
 * jsdom no implementa `ResizeObserver`, y `ResponsiveContainer` de Recharts lo
 * usa para medirse. Sin este stub, cualquier test que monte un gráfico revienta
 * con "ResizeObserver is not defined" — un fallo del entorno de pruebas, no del
 * componente.
 *
 * El stub no mide nada: en jsdom todo elemento tiene tamaño 0, así que el SVG
 * no se dibuja igualmente. Lo que estos tests verifican es el texto y las
 * llamadas a la API, no la geometría del gráfico (eso requeriría un navegador
 * real).
 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
