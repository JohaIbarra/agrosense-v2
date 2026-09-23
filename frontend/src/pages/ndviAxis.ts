/**
 * El eje Y de la gráfica del NDVI (E10a).
 *
 * Vive aparte de la página porque es cálculo puro y se prueba solo, sin
 * montar la gráfica. NO es lógica de negocio: qué SIGNIFICA un NDVI lo dice
 * el dominio (`backend/src/agrosense/domain/satellite_rules.py`); aquí solo
 * se decide cómo se dibuja un número que ya viene interpretado.
 *
 * El rango [-1, 1] sí es conocimiento del dominio, y está duplicado aquí a
 * sabiendas: es la definición matemática del índice —(NIR−R)/(NIR+R) no
 * puede salirse— y no una regla de negocio que vaya a cambiar. Servirlo
 * desde la API para no repetir dos constantes sería peor negocio.
 */

/** Límites teóricos del NDVI: el cociente no puede salir de aquí. */
export const NDVI_MIN = -1;
export const NDVI_MAX = 1;

/** Escalón del eje. 0,05 da etiquetas limpias (0.40, 0.45…) a dos decimales. */
const STEP = 0.05;

/** Margen mínimo del eje: una serie plana no debe quedar pegada al borde. */
const MIN_SPAN = 0.1;

/** ¿Es un NDVI que puede existir? Descarta NaN, infinitos y lo imposible. */
export function isPlottableNdvi(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isFinite(value) &&
    value >= NDVI_MIN &&
    value <= NDVI_MAX
  );
}

/** Quita el ruido binario de multiplicar y dividir por 0,05. */
function limpio(value: number): number {
  return Math.round(value * 1000) / 1000;
}

/**
 * El dominio del eje Y: ajustado a los datos, nunca fuera del rango teórico.
 *
 * Se calcula desde los valores —no se fija a mano— para que un proyecto seco
 * (NDVI 0,15–0,25) se lea igual de bien que uno denso (0,60–0,80). Los
 * valores imposibles se ignoran ANTES de medir, que es lo que impide que una
 * lectura corrupta secuestre el eje.
 */
export function ndviDomain(values: readonly unknown[]): [number, number] {
  const reales = values.filter(isPlottableNdvi);
  if (reales.length === 0) return [0, 1];

  let lo = Math.floor(Math.min(...reales) / STEP) * STEP;
  let hi = Math.ceil(Math.max(...reales) / STEP) * STEP;

  // Serie plana o casi: se abre hasta el margen mínimo, repartido a los dos
  // lados, para que la línea no salga pegada al borde del recuadro.
  if (hi - lo < MIN_SPAN) {
    const falta = (MIN_SPAN - (hi - lo)) / 2;
    lo -= falta;
    hi += falta;
  }

  return [limpio(Math.max(NDVI_MIN, lo)), limpio(Math.min(NDVI_MAX, hi))];
}

/** La etiqueta de un tick: siempre decimal, nunca un entero gigante. */
export function formatNdviTick(value: number): string {
  return value.toFixed(2);
}

type Fila = Record<string, number | string>;

/**
 * Las filas que se pueden dibujar, y cuántos valores se dejaron fuera.
 *
 * Un NDVI imposible no se dibuja: una línea que sube a 41 millones no
 * informa de nada y destruye la escala de las demás. No se OCULTA: sigue en
 * la tabla, con su procedencia, y la página avisa de cuántos hubo.
 */
export function plottableNdvi(
  series: readonly Fila[],
  properties: readonly string[],
): { series: Fila[]; descartadas: number } {
  let descartadas = 0;
  const limpias = series.map((fila) => {
    let copia: Fila | null = null;
    for (const p of properties) {
      if (p in fila && !isPlottableNdvi(fila[p])) {
        copia ??= { ...fila };
        delete copia[p];
        descartadas += 1;
      }
    }
    return copia ?? fila;
  });
  return { series: limpias, descartadas };
}
