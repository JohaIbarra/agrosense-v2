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

// ── E1: proyectos, perfil y catálogos ─────────────────────────────────────
// Espejo de los schemas de `backend/src/agrosense/adapters/api/schemas.py`.

export interface Project {
  id: number;
  project_code: string | null;
  name: string;
  locality: string | null;
  description: string | null;
  created_at: string;
  campaigns_count: number;
  contract_code: string | null;
  objective: string | null;
  executing_org: string | null;
  contracting_entity: string | null;
  department: string | null;
  municipality: string | null;
  intervention_type: string | null;
  area_ha: number | null;
  planted_individuals: number | null;
  planting_density: number | null;
  establishment_date: string | null;
  start_date: string | null;
  end_date: string | null;
  legal_framework: string | null;
  environmental_authority: string | null;
  status: string;
  coordinate_srid: number;
}

/** Cuerpo de POST /projects y PATCH /projects/{id}. */
export type ProjectInput = Partial<
  Omit<Project, "id" | "project_code" | "created_at" | "campaigns_count">
> & { name?: string };

export interface Engineer {
  id: string;
  email: string | null;
  full_name: string | null;
  professional_license: string | null;
  organization: string | null;
}

export type EngineerInput = Partial<
  Pick<Engineer, "full_name" | "professional_license" | "organization">
>;

export interface Catalogs {
  intervention_types: string[];
  legal_frameworks: string[];
  project_statuses: string[];
  default_srid: number;
}

export interface Monitoring {
  number: number;
  monitoring_date: string | null;
  field_crew: string | null;
  recorder: string | null;
  notes: string | null;
  observations: number;
}

// ── E2/E3: carga, monitoreos y análisis exploratorio ─────────────────────

export type WarningType =
  | "contraction"
  | "revival"
  | "census_gap"
  | "event_mismatch"
  | "project_mismatch"
  | "unknown_columns";

export interface IngestWarning {
  type: WarningType;
  tree_id: string;
  message: string;
}

export interface UploadResult {
  valid: boolean;
  campaign_id: number | null;
  trees: number;
  observations: number;
  deaths: number;
  warnings: IngestWarning[];
  errors: { code: string; message: string }[];
  monitorings: number[];
  analyzed: number[];
}

export interface MonitoringUpdate {
  monitoring_date?: string | null;
  notes?: string | null;
}

export type ColumnKind = "text" | "int" | "decimal" | "percent";

export interface AnalysisColumn {
  key: string;
  label: string;
  kind: ColumnKind;
  decimals?: number | null;
  group?: string | null;
}

export type AnalysisValue = string | number | null | string[];
export type AnalysisRow = Record<string, AnalysisValue>;

export interface AnalysisTable {
  id: string;
  title: string;
  property: string | null;
  columns: AnalysisColumn[];
  rows: AnalysisRow[];
  footer: AnalysisRow[];
  notes: string[];
}

export interface AnalysisChart {
  id: string;
  title: string;
  table: string;
  kind: "bar";
  x: string;
  series: string[];
  stacked: boolean;
  percent: boolean;
  y_label: string;
  property: string | null;
}

export interface AnalysisSection {
  id: string;
  title: string;
  description: string;
  tables: AnalysisTable[];
  charts: AnalysisChart[];
  notes: string[];
}

export interface SummaryItem {
  key: string;
  label: string;
  kind: "int" | "decimal" | "percent";
  decimals?: number | null;
  unit?: string | null;
  value: number | null;
}

export interface MonitoringAnalysis {
  project_id: number;
  monitoring: number;
  monitoring_date: string | null;
  previous: number | null;
  monitorings: number[];
  properties: string[];
  analysis_version: string;
  input_hash: string;
  computed_at: string;
  summary: SummaryItem[];
  sections: AnalysisSection[];
}
