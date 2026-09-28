/**
 * Tipos del contrato de `/api/v1/reference/*`.
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

// ── E6: mapa del predio ───────────────────────────────────────────────────

export type TreeState = "bueno" | "regular" | "malo" | "muerto" | "sin_dato";

export interface MapBounds {
  south: number;
  west: number;
  north: number;
  east: number;
}

export interface MapTree {
  id: string;
  species: string | null;
  property: string | null;
  plot: string | null;
  plot_key: string | null;
  lat: number;
  lon: number;
  elevation_m: number | null;
  /** Indexado por número de monitoreo como cadena: JSON no tiene claves numéricas. */
  states: Record<string, TreeState>;
  heights: Record<string, number | null>;
}

export interface PlotMetric {
  n: number;
  survival: number;
  mean_height: number | null;
}

export interface MapPlot {
  key: string;
  property: string | null;
  plot: string | null;
  n: number;
  low_sample: boolean;
  centroid: { lat: number; lon: number };
  hull: number[][];
  metrics: Record<string, PlotMetric>;
}

export interface ProjectMap {
  project_id: number;
  version: string;
  srid: number;
  monitorings: number[];
  properties: string[];
  bounds: MapBounds | null;
  without_coordinates: number;
  trees: MapTree[];
  plots: MapPlot[];
  imagery: ImageryLayer[];
}

export interface ImageryLayer {
  id: number;
  name: string;
  tile_template: string;
  attribution: string | null;
  min_zoom: number | null;
  max_zoom: number | null;
  opacity: number;
}

export interface ImageryLayerCreate {
  name: string;
  tile_template: string;
  attribution?: string | null;
  min_zoom?: number | null;
  max_zoom?: number | null;
  opacity?: number | null;
}

// ── E10a: índices espectrales por predio ──────────────────────────────────

export interface IndexReading {
  property_name: string;
  index: string;
  scene_id: string;
  acquired_at: string;
  cloud_cover: number | null;
  mean: number;
  median: number | null;
  minimum: number | null;
  maximum: number | null;
  std: number | null;
  valid_pixels: number;
  reliable: boolean;
  reading: string | null;
  source: string;
}

export interface ProjectIndex {
  project_id: number;
  index: string;
  properties: string[];
  last_refreshed_at: string | null;
  readings: IndexReading[];
}

export interface IndexRefreshSummary {
  scenes_found: number;
  readings_added: number;
  without_data: number;
  interrupted: boolean;
  properties: string[];
}

export interface IndexRefresh extends ProjectIndex {
  summary: IndexRefreshSummary;
}

// ── E5: contraste de especies del proyecto con el referente (UC-AN3) ──────

export interface SpeciesContrast {
  species: string;
  n_trees_in_project: number;
  has_reference: boolean;
  gremio: string | null;
  stall_risk: Risk | null;
  mortality_risk: Risk | null;
  narrative: string;
}

// ── E9: borrador de informe con IA ──────────────────────────────────────

export interface AIReport {
  project_id: number;
  monitoring: number;
  model_name: string;
  prompt_version: string;
  content: string;
  unverified_numbers: string[];
  created_at: string;
  stale: boolean;
}

// ── E7: detección de estancados (UC-AN4) ──────────────────────────────────

/** E7 · Detección de estancados (UC-AN4). Espejo de `StallAssessmentResponse`. */
export interface StallTree {
  tree_id: string;
  species: string;
  locality: string | null;
  plot: string | null;
  /** Probabilidad 0–1 de que la altura no cambie hasta el próximo monitoreo. */
  probability: number;
  flagged: boolean;
  /** null = el árbol no tiene medición en el monitoreo anterior. */
  stalled_last_interval: boolean | null;
  stall_streak: number;
  persistent: boolean;
  known_species: boolean;
  /** Features categóricas (especie incluida) con un valor no visto en entrenamiento. */
  unknown_categories: string[];
}

export interface StallSummary {
  at_risk: number;
  flagged: number;
  stalled_last_interval: number;
  persistent: number;
  without_history: number;
  unknown_species: number;
  /** Árboles con al menos una categoría (no solo especie) no vista en entrenamiento. */
  unknown_category_trees: number;
  /** `without_history` es al menos la mitad de los árboles: predicciones en extrapolación. */
  mostly_without_history: boolean;
}

export interface StallModelCard {
  model_version: string;
  artifact_sha256: string;
  dataset_sha256: string;
  trained_on: string;
  pr_auc: number;
  pr_auc_ci_low: number;
  pr_auc_ci_high: number;
  roc_auc: number;
  prevalence_pct: number;
  recall_at_budget_pct: number;
  precision_at_budget_pct: number;
}

export interface StallAssessment {
  project_id: number;
  monitoring: number;
  input_hash: string;
  computed_at: string;
  alert_budget_pct: number;
  persistent_min_intervals: number;
  model: StallModelCard;
  summary: StallSummary;
  trees: StallTree[];
}
