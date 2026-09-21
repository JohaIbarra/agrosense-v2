/**
 * Capa de acceso a datos. Ningun componente hace `fetch` (AGENTS.md).
 *
 * Todo pasa por `request`, que centraliza dos cosas que si se duplican acaban
 * divergiendo: como se construye la URL y como se traduce un error del backend
 * a algo que la UI puede mostrar.
 */
import type {
  ModelKey,
  ModelVariance,
  PlotAnalytics,
  SpeciesAnalytics,
  SpeciesSort,
} from "./types";

const BASE = "/api/v1/analytics";

/** Error con el `code` del contrato, para que la UI distinga los casos. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

type Query = Record<string, string | number | undefined | null>;

function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `${BASE}${path}?${qs}` : `${BASE}${path}`;
}

async function request<T>(
  path: string,
  query?: Query,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(buildUrl(path, query), {
    signal,
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    // El backend siempre responde {detail: {code, message}}; si algo se cuela
    // sin esa forma (un 502 del proxy, por ejemplo), no se muestra el cuerpo
    // crudo al usuario.
    let code = "UNKNOWN";
    let message = `La petición falló (HTTP ${response.status}).`;
    try {
      const body = await response.json();
      if (body?.detail?.code) code = body.detail.code;
      if (body?.detail?.message) message = body.detail.message;
    } catch {
      /* respuesta sin JSON: se conserva el mensaje genérico */
    }
    throw new ApiError(response.status, code, message);
  }

  return (await response.json()) as T;
}

export function fetchSpecies(
  options: { gremio?: string | null; sort?: SpeciesSort } = {},
  signal?: AbortSignal,
): Promise<SpeciesAnalytics[]> {
  return request<SpeciesAnalytics[]>(
    "/species",
    { gremio: options.gremio, sort: options.sort },
    signal,
  );
}

export function fetchSpeciesDetail(
  name: string,
  signal?: AbortSignal,
): Promise<SpeciesAnalytics> {
  // `encodeURIComponent` no es opcional: los nombres llevan espacios.
  return request<SpeciesAnalytics>(
    `/species/${encodeURIComponent(name)}`,
    undefined,
    signal,
  );
}

export function fetchTopRiskStall(
  limit = 5,
  signal?: AbortSignal,
): Promise<SpeciesAnalytics[]> {
  return request<SpeciesAnalytics[]>("/species/top-risk-stall", { limit }, signal);
}

export function fetchTopProtective(
  model: ModelKey = "stall",
  limit = 5,
  signal?: AbortSignal,
): Promise<SpeciesAnalytics[]> {
  return request<SpeciesAnalytics[]>(
    "/species/top-protective",
    { model, limit },
    signal,
  );
}

export function fetchPlots(
  localidad?: string | null,
  signal?: AbortSignal,
): Promise<PlotAnalytics[]> {
  return request<PlotAnalytics[]>("/plots", { localidad }, signal);
}

export function fetchVarianceDecomposition(
  signal?: AbortSignal,
): Promise<ModelVariance[]> {
  return request<ModelVariance[]>("/variance-decomposition", undefined, signal);
}
