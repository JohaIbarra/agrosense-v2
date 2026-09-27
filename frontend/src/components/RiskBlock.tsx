/**
 * Bloque de una metrica de riesgo (estancamiento o mortalidad).
 *
 * Extraido de `SpeciesDetail.tsx` (Slice 5) para reutilizarlo en el
 * contraste de especies del proyecto (E5, UC-AN3): la misma regla de
 * "IC que cruza 1 no es un hallazgo" aplica en los dos sitios, y AGENTS.md
 * prohibe duplicar la logica de negocio en el frontend — aqui ademas se
 * duplicaria el MARKUP, que es peor.
 */
import type { Risk } from "../api/types";
import { COLORS } from "../theme";

interface Props {
  label: string;
  risk: Risk;
}

export function RiskBlock({ label, risk }: Props) {
  const color =
    risk.significant !== true
      ? COLORS.inconclusive
      : (risk.odds_ratio ?? 1) > 1
        ? COLORS.risk
        : COLORS.protective;

  return (
    <div className="risk-block">
      <h4>{label}</h4>
      {risk.odds_ratio === null ? (
        <p className="muted">Sin estimación disponible.</p>
      ) : (
        <>
          <p className="risk-or" style={{ color }}>
            OR {risk.odds_ratio.toFixed(2)}
            {risk.significant === true ? (
              <span className="badge badge-sig">IC concluyente</span>
            ) : (
              <span className="badge badge-nosig">IC cruza 1</span>
            )}
          </p>
          {risk.or_ci95 && (
            <p className="muted">
              IC 95%: [{risk.or_ci95[0].toFixed(2)}, {risk.or_ci95[1].toFixed(2)}]
            </p>
          )}
          <p>{risk.interpretation}</p>
        </>
      )}
    </div>
  );
}
