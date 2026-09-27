/** Acceso al contraste de especies del proyecto con el referente (E5, UC-AN3). */
import { request } from "./http";
import type { SpeciesContrast } from "./types";

export function getReferenceContrast(
  projectId: number,
  signal?: AbortSignal,
): Promise<SpeciesContrast[]> {
  return request<SpeciesContrast[]>(`/projects/${projectId}/reference-contrast`, { signal });
}
