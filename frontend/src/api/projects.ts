/**
 * Acceso a datos de proyectos y perfil (E1).
 *
 * Las rutas de proyectos no llevan el prefijo /api/v1 (deuda del slice 2,
 * docs/deuda-tecnica.md); el proxy de Vite las reenvia igual.
 */
import { request } from "./http";
import type {
  Catalogs,
  Engineer,
  EngineerInput,
  Monitoring,
  Project,
  ProjectInput,
} from "./types";

export function listProjects(signal?: AbortSignal): Promise<Project[]> {
  return request<Project[]>("/projects", { signal });
}

export function getProject(id: number, signal?: AbortSignal): Promise<Project> {
  return request<Project>(`/projects/${id}`, { signal });
}

export function createProject(input: ProjectInput): Promise<Project> {
  return request<Project>("/projects", { method: "POST", body: input });
}

export function updateProject(id: number, input: ProjectInput): Promise<Project> {
  return request<Project>(`/projects/${id}`, { method: "PATCH", body: input });
}

export function listMonitorings(id: number, signal?: AbortSignal): Promise<Monitoring[]> {
  return request<Monitoring[]>(`/projects/${id}/monitorings`, { signal });
}

export function getMe(signal?: AbortSignal): Promise<Engineer> {
  return request<Engineer>("/api/v1/me", { signal });
}

export function updateMe(input: EngineerInput): Promise<Engineer> {
  return request<Engineer>("/api/v1/me", { method: "PUT", body: input });
}

export function getCatalogs(signal?: AbortSignal): Promise<Catalogs> {
  return request<Catalogs>("/api/v1/catalogs", { signal });
}
