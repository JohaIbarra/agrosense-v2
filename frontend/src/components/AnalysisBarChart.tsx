/**
 * Gráfica de barras de una tabla del análisis.
 *
 * La especificación (qué tabla, qué columna es la categoría, qué columnas son
 * series, si se apilan) la manda el backend; aquí solo se dibuja con los
 * valores de ESA tabla. Nada se recalcula.
 *
 * Decisiones de lectura:
 *  - Con muchas categorías (especies) las barras van en horizontal: los
 *    nombres científicos no caben bajo un eje X.
 *  - Colores categóricos en orden fijo (paleta validada para daltonismo);
 *    el estado fitosanitario usa la paleta de ESTADO (bueno / regular / malo),
 *    siempre con leyenda y etiqueta, nunca solo color.
 *  - Leyenda siempre que haya 2 o más series; tooltip con el valor formateado.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AnalysisChart, AnalysisTable } from "../api/types";
import { columnLabel, formatValue } from "../analysis/format";

/**
 * Paleta categórica de Dendrova (orden fijo): tonos sobrios que se separan por
 * matiz Y luminosidad, para que dos series adyacentes no se confundan con
 * daltonismo. Las dos primeras (azul acero / ocre) son «monitoreo anterior» y
 * «actual» en las gráficas comparativas.
 */
export const SERIES_COLORS = [
  "#3f6f9f",
  "#d08a2e",
  "#2e7d5b",
  "#8a6bb5",
  "#b5677d",
  "#7d8f2b",
  "#4f5f6e",
  "#5a9aa8",
];

/** Estados reservados: nunca se reutilizan como «serie 4». */
const STATUS_COLORS: Record<string, string> = {
  pct_good: "#2e7d4f",
  pct_fair: "#d4a23c",
  pct_poor: "#b42318",
  // Comparación entre monitoreos (E4): el estado al que llegó cada árbol, y
  // la mortalidad, llevan los mismos colores que en el resto del producto.
  to_bueno: "#2e7d4f",
  to_regular: "#d4a23c",
  to_malo: "#b42318",
  to_muerto: "#5f6762",
  to_sin_dato: "#c4cac5",
  mortality: "#b42318",
  stagnant_pct: "#d4a23c",
};

const HORIZONTAL_FROM = 7;
// Caracteres de etiqueta que caben bajo las columnas de una tarjeta de media
// pantalla; con más, los nombres (p. ej. de especie) se enciman.
const MAX_COLUMN_LABEL_CHARS = 40;

/** Barras horizontales cuando hay muchas categorías o sus nombres no caben en columnas. */
export function isHorizontal(rows: Record<string, unknown>[], key: string): boolean {
  if (rows.length >= HORIZONTAL_FROM) return true;
  const chars = rows.reduce((sum, row) => sum + String(row[key] ?? "").length, 0);
  return chars > MAX_COLUMN_LABEL_CHARS;
}

export function seriesColor(key: string, index: number): string {
  return STATUS_COLORS[key] ?? SERIES_COLORS[index % SERIES_COLORS.length];
}

export function AnalysisBarChart({ chart, table }: { chart: AnalysisChart; table: AnalysisTable }) {
  const columns = new Map(table.columns.map((c) => [c.key, c]));
  const data = table.rows;
  if (data.length === 0) return null;

  const horizontal = isHorizontal(data, chart.x);
  const height = horizontal ? Math.max(220, data.length * (chart.stacked ? 22 : 30) + 70) : 300;
  const valueAxis = {
    type: "number" as const,
    domain: chart.percent ? ([0, 100] as [number, number]) : undefined,
    tickFormatter: (v: number) => (chart.percent ? `${v} %` : v.toLocaleString("es-CO")),
    tick: { fontSize: 12, fill: "#55625b" },
    stroke: "#cbd3cb",
  };
  const categoryAxis = {
    type: "category" as const,
    dataKey: chart.x,
    tick: { fontSize: 12, fill: "#55625b" },
    stroke: "#cbd3cb",
    interval: 0,
  };

  return (
    <figure className="chart-card">
      <figcaption>{chart.title}</figcaption>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={data}
          layout={horizontal ? "vertical" : "horizontal"}
          margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
          barGap={2}
        >
          <CartesianGrid
            stroke="#eef1ed"
            horizontal={!horizontal}
            vertical={horizontal}
          />
          {horizontal ? (
            <>
              <XAxis {...valueAxis} />
              <YAxis {...categoryAxis} width={190} />
            </>
          ) : (
            <>
              <XAxis {...categoryAxis} height={48} />
              <YAxis {...valueAxis} width={56} />
            </>
          )}
          <Tooltip
            cursor={{ fill: "rgba(15, 118, 110, 0.06)" }}
            formatter={(value, name) => {
              const col = table.columns.find((c) => columnLabel(c) === name);
              return [
                col ? formatValue(value as number, col) : String(value),
                name as string,
              ];
            }}
          />
          {chart.series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
          {chart.series.map((key, i) => {
            const col = columns.get(key);
            return (
              <Bar
                key={key}
                dataKey={key}
                name={col ? columnLabel(col) : key}
                fill={seriesColor(key, i)}
                stackId={chart.stacked ? "s" : undefined}
                radius={chart.stacked ? 0 : horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]}
                maxBarSize={28}
                stroke="#ffffff"
                strokeWidth={chart.stacked ? 1 : 0}
                isAnimationActive={false}
              />
            );
          })}
        </BarChart>
      </ResponsiveContainer>
      {chart.y_label && <p className="chart-unit">Eje de valores: {chart.y_label}</p>}
    </figure>
  );
}
