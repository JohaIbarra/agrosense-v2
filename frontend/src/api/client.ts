/**
 * Acceso a datos del Referente cientifico (`/api/v1/analytics`).
 *
 * El transporte (URL, token de sesion, errores) vive en `http.ts`.
 */
import type {
  ModelKey,
  ModelVariance,
  PlotAnalytics,
  SpeciesAnalytics,
  SpeciesSort,
} from "./types";

import { ApiError, request as http, type Query } from "./http";

export { ApiError };

const BASE = "/api/v1/analytics";

function request<T>(path: string, query?: Query, signal?: AbortSignal): Promise<T> {
  return http<T>(`${BASE}${path}`, { query, signal });
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
