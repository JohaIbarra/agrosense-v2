/**
 * Panel comparativo: estancamiento y mortalidad lado a lado.
 *
 * Reproduce la tabla de `comparacion_estancamiento_mortalidad.csv`, pero las
 * cifras se DERIVAN de la API en vez de copiarse del CSV: una tabla con
 * números escritos a mano en el frontend deja de cuadrar con la base en la
 * primera recarga y nadie se entera (AGENTS.md, data provenance).
 *
 * Dos filas del CSV original no se muestran — "Efecto más fuerte (fijo)" y su
 * OR — porque salen de `efectos_fijos*.csv`, que el slice 5 no persiste ni
 * expone. Inventarlas aquí sería peor que omitirlas; se declaran como
 * pendientes al pie de la tabla.
 *
 * Es el panel que impide el malentendido central: los dos rankings se ven
 * iguales, pero implican estrategias opuestas.
 */
import type { ModelVariance, SpeciesAnalytics } from "../api/types";

interface Props {
  variance: ModelVariance[];
  species: SpeciesAnalytics[];
  plotCount: { stall: number | null; mortality: number | null };
}

type Row = { label: string; stall: string; mortality: string; strong?: boolean };

function component(model: ModelVariance | undefined, grouping: string) {
  return model?.components.find((c) => c.grouping === grouping);
}

function fmt(value: number | null | undefined, digits = 3): string {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

/** Rango de OR y factor de variación entre la especie más y menos afectada. */
function orRange(species: SpeciesAnalytics[], key: "stall_risk" | "mortality_risk") {
  const ors = species
    .map((s) => s[key].odds_ratio)
    .filter((v): v is number => v !== null);
  if (ors.length === 0) return { range: "—", factor: "—" };
  const min = Math.min(...ors);
  const max = Math.max(...ors);
  return {
    range: `${min.toFixed(2)} – ${max.toFixed(2)}`,
    factor: `${(max / min).toFixed(1)}×`,
  };
}

export function ComparisonPanel({ variance, species, plotCount }: Props) {
  const stall = variance.find((m) => m.model === "stall");
  const mort = variance.find((m) => m.model === "mortality");

  const sEsp = component(stall, "especie");
  const sPar = component(stall, "parcela");
  const mEsp = component(mort, "especie");
  const mPar = component(mort, "parcela");

  const sRange = orRange(species, "stall_risk");
  const mRange = orRange(species, "mortality_risk");

  const sigStall = species.filter((s) => s.stall_risk.significant).length;
  const sigMort = species.filter((s) => s.mortality_risk.significant).length;

  const prevalence = (c?: { n_events: number | null; n_observations: number | null }) =>
    c?.n_events != null && c?.n_observations
      ? (c.n_events / c.n_observations).toFixed(3)
      : "—";

  const events = (c?: { n_events: number | null; n_observations: number | null }) =>
    c?.n_events != null && c?.n_observations
      ? `${c.n_events} (${Math.round((c.n_events / c.n_observations) * 100)}%)`
      : "—";

  const rows: Row[] = [
    {
      label: "Observaciones árbol-intervalo",
      stall: sEsp?.n_observations?.toLocaleString("es") ?? "—",
      mortality: mEsp?.n_observations?.toLocaleString("es") ?? "—",
    },
    { label: "Eventos positivos", stall: events(sEsp), mortality: events(mEsp) },
    { label: "Prevalencia", stall: prevalence(sEsp), mortality: prevalence(mEsp) },
    { label: "Varianza especie", stall: fmt(sEsp?.variance), mortality: fmt(mEsp?.variance) },
    { label: "Varianza parcela", stall: fmt(sPar?.variance), mortality: fmt(mPar?.variance) },
    {
      label: "Razón (especie/parcela)",
      stall: stall?.species_to_plot_ratio ? `${stall.species_to_plot_ratio.toFixed(1)}×` : "—",
      mortality: mort?.species_to_plot_ratio ? `${mort.species_to_plot_ratio.toFixed(1)}×` : "—",
      strong: true,
    },
    { label: "ICC especie", stall: fmt(sEsp?.icc), mortality: fmt(mEsp?.icc) },
    { label: "ICC parcela", stall: fmt(sPar?.icc), mortality: fmt(mPar?.icc) },
    { label: "Rango OR (especies)", stall: sRange.range, mortality: mRange.range },
    {
      label: "Factor de variación",
      stall: sRange.factor,
      mortality: mRange.factor,
      strong: true,
    },
    {
      label: "Especies con IC significativo",
      stall: `${sigStall} (de ${sEsp?.n_levels ?? species.length})`,
      mortality: `${sigMort} (de ${mEsp?.n_levels ?? species.length})`,
    },
    {
      label: "Parcelas con IC significativo",
      stall:
        plotCount.stall !== null ? `${plotCount.stall} (de ${sPar?.n_levels ?? "—"})` : "—",
      mortality:
        plotCount.mortality !== null
          ? `${plotCount.mortality} (de ${mPar?.n_levels ?? "—"})`
          : "—",
    },
  ];

  return (
    <section className="card">
      <header className="card-head">
        <h2>Estancamiento vs. mortalidad</h2>
        <p className="subtitle">
          Los dos rankings se parecen, pero no piden la misma decisión.
        </p>
      </header>

      <table className="comparison">
        <thead>
          <tr>
            <th scope="col">Métrica</th>
            <th scope="col">Estancamiento</th>
            <th scope="col">Mortalidad</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className={r.strong ? "row-strong" : undefined}>
              <th scope="row">{r.label}</th>
              <td>{r.stall}</td>
              <td>{r.mortality}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="readings">
        {stall && (
          <p className="reading">
            <strong>Estancamiento:</strong> {stall.interpretation}
          </p>
        )}
        {mort && (
          <p className="reading">
            <strong>Mortalidad:</strong> {mort.interpretation}
          </p>
        )}
      </div>

      <p className="muted footnote">
        Pendiente: las filas «efecto fijo más fuerte» del informe salen de
        <code> efectos_fijos*.csv</code>, que aún no se persiste ni se expone por
        la API. No se muestran para no publicar cifras que la base no respalda.
      </p>
    </section>
  );
}
