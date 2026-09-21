/**
 * Tipos del contrato de `/api/v1/analytics/*`.
 *
 * Se derivan del OpenAPI que publica FastAPI (AGENTS.md: "The frontend
 * consumes the contract; it never invents its own structure"). Si el contrato
 * cambia, esto se regenera desde `/openapi.json`, no se parchea a mano.
 *
 * **La escala importa y esta en los nombres.** `oddsRatio` y `orCi95` estan en
 * odds ratio y son lo unico que se muestra. `ci95LogOdds` esta en log-odds y
 * existe solo para cotejar contra los CSV del modelo mixto: no se renderiza
 * nunca. Confundirlos significa dibujar la barra [0.81, 2.38] alrededor de un
 * OR de 4.94 — fuera de su propio intervalo.
 */

/** Efecto de una especie o parcela sobre un desenlace. */
export interface Risk {
  /** exp(efecto aleatorio). 1.0 = como el promedio. `null` = sin estimacion. */
  odds_ratio: number | null;
  /** IC 95% del ODDS RATIO, ya exponenciado. Es lo que dibuja la UI. */
  or_ci95: [number, number] | null;
  /** IC 95% en LOG-ODDS. Trazabilidad; NO renderizar. */
  ci95_log_odds: [number, number] | null;
  /** `false` significa "no distinguible del promedio", no "sin efecto". */
  significant: boolean | null;
  /** Frase ya resuelta en el backend. El frontend no la reescribe. */
  interpretation: string;
}

export interface SpeciesAnalytics {
  species: string;
  stall_risk: Risk;
  mortality_risk: Risk;
  n_observations: number | null;
  n_trees: number | null;
  gremio: string | null;
}

export interface PlotAnalytics {
  plot_code: string;
  localidad: string | null;
  stall_risk: Risk;
  mortality_risk: Risk;
  n_trees: number | null;
}

export interface VarianceComponent {
  grouping: string;
  variance: number;
  sd: number;
  icc: number;
  n_levels: number | null;
  n_observations: number | null;
  n_events: number | null;
}

export interface ModelVariance {
  model: ModelKey;
  components: VarianceComponent[];
  species_to_plot_ratio: number | null;
  interpretation: string;
}

export type ModelKey = "stall" | "mortality";

export type SpeciesSort =
  | "stall_risk"
  | "mortality_risk"
  | "name"
  | "n_observations";

/** Forma de error del backend: `{"detail": {"code", "message"}}`. */
export interface ApiErrorBody {
  detail?: { code?: string; message?: string };
}
