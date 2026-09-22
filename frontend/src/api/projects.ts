/**
 * Acceso a datos de proyectos y perfil (E1).
 *
 * Las rutas de proyectos no llevan el prefijo /api/v1 (deuda del slice 2,
 * docs/deuda-tecnica.md); el proxy de Vite las reenvia igual.
 */
import { request, requestFile } from "./http";
import type {
  Catalogs,
  Engineer,
  EngineerInput,
  Monitoring,
  MonitoringAnalysis,
  MonitoringUpdate,
  Project,
  ProjectInput,
  UploadResult,
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

// ── E2/E3 ─────────────────────────────────────────────────────────────────

/** Sube el Excel de campo. `monitoringDate` (AAAA-MM-DD) fecha el monitoreo más reciente. */
export function uploadCampaign(
  projectId: number,
  file: File,
  monitoringDate: string | null,
): Promise<UploadResult> {
  const form = new FormData();
  form.append("file", file);
  if (monitoringDate) form.append("monitoring_date", monitoringDate);
  return request<UploadResult>(`/projects/${projectId}/campaigns`, { method: "POST", body: form });
}

export function updateMonitoring(
  projectId: number,
  number: number,
  input: MonitoringUpdate,
): Promise<Monitoring> {
  return request<Monitoring>(`/projects/${projectId}/monitorings/${number}`, {
    method: "PATCH",
    body: input,
  });
}

export function getMonitoringAnalysis(
  projectId: number,
  number: number,
  signal?: AbortSignal,
): Promise<MonitoringAnalysis> {
  return request<MonitoringAnalysis>(`/projects/${projectId}/monitorings/${number}/analysis`, {
    signal,
  });
}

/** Descarga el reporte .xlsx: lo pide con el token y lo entrega al navegador. */
export async function downloadReport(projectId: number, number: number): Promise<void> {
  const { blob, filename } = await requestFile(
    `/projects/${projectId}/monitorings/${number}/report.xlsx`,
  );
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename ?? `AgroSense_M${number}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
