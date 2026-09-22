/** Acceso a datos del mapa del predio (E6). */
import { request } from "./http";
import type { ProjectMap } from "./types";

export function getProjectMap(projectId: number, signal?: AbortSignal): Promise<ProjectMap> {
  return request<ProjectMap>(`/projects/${projectId}/map`, { signal });
}
