/** Acceso a datos del mapa del predio y sus capas de imagen (E6/E6b). */
import { request } from "./http";
import type { ImageryLayer, ImageryLayerCreate, ProjectMap } from "./types";

export function getProjectMap(projectId: number, signal?: AbortSignal): Promise<ProjectMap> {
  return request<ProjectMap>(`/projects/${projectId}/map`, { signal });
}

export function getImageryLayers(
  projectId: number,
  signal?: AbortSignal,
): Promise<ImageryLayer[]> {
  return request<ImageryLayer[]>(`/projects/${projectId}/imagery`, { signal });
}

export function addImageryLayer(
  projectId: number,
  layer: ImageryLayerCreate,
): Promise<ImageryLayer> {
  return request<ImageryLayer>(`/projects/${projectId}/imagery`, {
    method: "POST",
    body: layer,
  });
}

export function removeImageryLayer(projectId: number, layerId: number): Promise<void> {
  return request<void>(`/projects/${projectId}/imagery/${layerId}`, { method: "DELETE" });
}
