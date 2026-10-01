/** Capacidades opcionales de ESTE servidor (ADR-015): lo apagado no se muestra. */
import { request } from "./http";

export interface Features {
  ai_reports: boolean;
}

export function getFeatures(signal?: AbortSignal): Promise<Features> {
  return request<Features>("/api/v1/features", { signal });
}
