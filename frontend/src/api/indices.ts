/** Acceso a datos de los índices espectrales (E10a). */
import { request } from "./http";
import type { IndexRefresh, ProjectIndex } from "./types";

export function getProjectIndex(
  projectId: number,
  index = "NDVI",
  signal?: AbortSignal,
): Promise<ProjectIndex> {
  return request<ProjectIndex>(`/projects/${projectId}/indices/${index}`, { signal });
}

export function refreshProjectIndex(
  projectId: number,
  index = "NDVI",
  maxScenes = 6,
): Promise<IndexRefresh> {
  return request<IndexRefresh>(
    `/projects/${projectId}/indices/${index}/refresh?max_scenes=${maxScenes}`,
    { method: "POST" },
  );
}
