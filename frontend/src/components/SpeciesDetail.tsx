/**
 * Detalle de una especie: las dos métricas y su lectura.
 *
 * El texto sale de `interpretation`, que lo arma el backend. El frontend NO
 * decide qué significa un OR ni cuándo un efecto es concluyente (AGENTS.md:
 * "Business rules must not be duplicated in the frontend"). Si esa frase
 * cambiara aquí, la API y el dashboard dirían cosas distintas del mismo dato.
 */
import type { SpeciesAnalytics } from "../api/types";
import { RiskBlock } from "./RiskBlock";

interface Props {
  species: SpeciesAnalytics | null;
  onClose: () => void;
}

export function SpeciesDetail({ species, onClose }: Props) {
  if (!species) {
    return (
      <section className="card detail">
        <h2>Detalle de especie</h2>
        <p className="empty">
          Haz clic en una especie de cualquiera de los dos rankings para ver su
          lectura completa.
        </p>
      </section>
    );
  }

  return (
    <section className="card detail">
      <header className="card-head detail-head">
        <div>
          <h2 className="species-name">{species.species}</h2>
          <p className="muted">
            {species.gremio ?? "gremio desconocido"}
            {species.n_trees !== null && ` · ${species.n_trees} árboles`}
            {species.n_observations !== null &&
              ` · ${species.n_observations} observaciones árbol-intervalo`}
          </p>
        </div>
        <button type="button" onClick={onClose} className="close" aria-label="Cerrar">
          ×
        </button>
      </header>

      <div className="risk-grid">
        <RiskBlock label="Estancamiento" risk={species.stall_risk} />
        <RiskBlock label="Mortalidad" risk={species.mortality_risk} />
      </div>

      {species.n_trees !== null && species.n_trees < 15 && (
        <p className="warn">
          Con {species.n_trees} árboles, el intervalo de esta especie es ancho.
          Trátala como una señal a confirmar, no como un resultado.
        </p>
      )}
    </section>
  );
}
