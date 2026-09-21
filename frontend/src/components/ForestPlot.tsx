/**
 * Forest plot horizontal: un OR por especie con su IC 95%.
 *
 * Decisiones de lectura, todas deliberadas:
 *
 *  - **Eje logaritmico.** El OR es multiplicativo: "5x mas" y "5x menos" son
 *    4.94 y 0.20. En eje lineal el segundo queda aplastado contra el cero y
 *    las especies protectoras — que son la mitad del hallazgo — desaparecen.
 *  - **Linea de referencia en 1.0**, no en 0. Es el "como el promedio".
 *  - **Color solo para lo concluyente.** Las especies cuyo IC cruza 1 se
 *    dibujan en gris. Sin eso, un OR puntual de 1.9 con IC [0.82, 4.44] se ve
 *    igual de alarmante que uno de 4.94 con IC [2.25, 10.86].
 *  - **La barra es el IC, no un error simetrico.** Se dibuja como segmento
 *    explicito porque exp() no conserva la simetria del log-odds.
 */
import {
  CartesianGrid,
  Cell,
  ErrorBar,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { Risk, SpeciesAnalytics } from "../api/types";
import { COLORS } from "../theme";

export type RiskKey = "stall_risk" | "mortality_risk";

interface Props {
  species: SpeciesAnalytics[];
  riskKey: RiskKey;
  title: string;
  subtitle?: string;
  onSelect?: (name: string) => void;
  selected?: string | null;
}

export interface Point {
  name: string;
  or: number;
  /** [distancia hacia abajo, distancia hacia arriba] — lo que espera ErrorBar. */
  errorX: [number, number];
  lo: number;
  hi: number;
  significant: boolean;
  interpretation: string;
  n: number | null;
}

/**
 * Convierte una especie en el punto que dibuja el grafico.
 *
 * Se exporta para poder probarla: en jsdom el SVG se renderiza con tamano 0 y
 * no emite texto, asi que un test sobre el componente montado no puede
 * verificar que la barra use la escala correcta. Aqui si.
 */
export function toPoint(s: SpeciesAnalytics, riskKey: RiskKey): Point | null {
  const risk: Risk = s[riskKey];
  if (risk.odds_ratio === null || risk.or_ci95 === null) return null;
  const [lo, hi] = risk.or_ci95;
  return {
    name: s.species,
    or: risk.odds_ratio,
    errorX: [risk.odds_ratio - lo, hi - risk.odds_ratio],
    lo,
    hi,
    significant: risk.significant === true,
    interpretation: risk.interpretation,
    n: s.n_trees,
  };
}

/**
 * Serie lista para el grafico, ordenada de MAYOR a MENOR riesgo de arriba
 * hacia abajo.
 *
 * El `sort` es ASCENDENTE aunque la lectura sea descendente, y no es un
 * error: `YAxis type="category"` de Recharts pinta el array de abajo hacia
 * arriba, asi que el orden visual es el inverso del orden del array. Con un
 * sort descendente (lo "natural") el dashboard mostraba *Verbesina arborea*
 * — la especie MAS protectora, OR 0.24 — encabezando un panel titulado
 * "Estancamiento por especie", y *Lafoensia speciosa* (OR 4.94) al fondo.
 *
 * Lo encontro una revision visual en navegador, no los tests: en jsdom el
 * SVG se renderiza con tamano 0 y no emite texto, asi que ninguna asercion
 * sobre el DOM podia verlo. De ahi que el orden se pruebe AQUI.
 */
export function toPoints(species: SpeciesAnalytics[], riskKey: RiskKey): Point[] {
  return species
    .map((s) => toPoint(s, riskKey))
    .filter((p): p is Point => p !== null)
    .sort((a, b) => a.or - b.or);
}

/** Ticks fijos en escala log: se leen como "2x mas", "2x menos". */
const LOG_TICKS = [0.1, 0.25, 0.5, 1, 2, 4, 8, 16];

function PointTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p: Point = payload[0].payload;
  return (
    <div className="tooltip">
      <strong>{p.name}</strong>
      <div className="tooltip-or">
        OR {p.or.toFixed(2)}{" "}
        <span className="muted">
          IC 95% [{p.lo.toFixed(2)}, {p.hi.toFixed(2)}]
        </span>
      </div>
      <p>{p.interpretation}</p>
      {p.n !== null && <p className="muted">{p.n} árboles</p>}
    </div>
  );
}

export function ForestPlot({
  species,
  riskKey,
  title,
  subtitle,
  onSelect,
  selected,
}: Props) {
  const points = toPoints(species, riskKey);

  if (points.length === 0) {
    return (
      <section className="card">
        <h2>{title}</h2>
        <p className="empty">Sin datos para mostrar con el filtro actual.</p>
      </section>
    );
  }

  const nSignificant = points.filter((p) => p.significant).length;
  // 26px por especie deja el nombre legible sin scroll interno.
  const height = Math.max(240, points.length * 26 + 60);

  return (
    <section className="card">
      <header className="card-head">
        <h2>{title}</h2>
        {subtitle && <p className="subtitle">{subtitle}</p>}
        <p className="legend">
          <span className="swatch" style={{ background: COLORS.risk }} /> riesgo
          significativo
          <span className="swatch" style={{ background: COLORS.protective }} />{" "}
          protector significativo
          <span className="swatch" style={{ background: COLORS.inconclusive }} />{" "}
          IC cruza 1 (no concluyente)
        </p>
        <p className="muted">
          {nSignificant} de {points.length} con intervalo concluyente
        </p>
      </header>

      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 8, right: 24, bottom: 28, left: 150 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={COLORS.grid} />
          <XAxis
            type="number"
            dataKey="or"
            scale="log"
            domain={[0.08, 20]}
            ticks={LOG_TICKS}
            tickFormatter={(v: number) => (v < 1 ? `${v}` : `${v}x`)}
            label={{
              value: "Odds ratio (escala logarítmica) — 1.0 = como el promedio",
              position: "insideBottom",
              offset: -16,
              fill: COLORS.axis,
              fontSize: 12,
            }}
            stroke={COLORS.axis}
            fontSize={12}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={150}
            stroke={COLORS.axis}
            fontSize={12}
            interval={0}
            tick={{ fontStyle: "italic" }}
          />
          {/* El "sin efecto" del odds ratio es 1, no 0. */}
          <ReferenceLine x={1} stroke={COLORS.reference} strokeWidth={1.5} />
          <Tooltip content={<PointTooltip />} cursor={{ strokeDasharray: "3 3" }} />
          <Scatter
            data={points}
            onClick={(p: any) => onSelect?.(p.name)}
            cursor={onSelect ? "pointer" : "default"}
          >
            <ErrorBar
              dataKey="errorX"
              direction="x"
              width={4}
              strokeWidth={1.5}
              stroke={COLORS.interval}
            />
            {points.map((p) => (
              <Cell
                key={p.name}
                fill={
                  !p.significant
                    ? COLORS.inconclusive
                    : p.or > 1
                      ? COLORS.risk
                      : COLORS.protective
                }
                stroke={p.name === selected ? COLORS.selected : "none"}
                strokeWidth={p.name === selected ? 3 : 0}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </section>
  );
}
