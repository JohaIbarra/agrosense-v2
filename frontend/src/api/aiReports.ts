/** Acceso al borrador de informe con IA de un monitoreo (E9, UC-IA1/2/3). */
import { ApiError, request } from "./http";
import type { AIReport } from "./types";

/** `null` cuando el backend responde 404 AI_REPORT_NOT_FOUND: todavía no
 * hay borrador, no es un error que mostrar. */
export async function getAIReport(
  projectId: number,
  number: number,
  signal?: AbortSignal,
): Promise<AIReport | null> {
  try {
    return await request<AIReport>(`/projects/${projectId}/monitorings/${number}/ai-report`, {
      signal,
    });
  } catch (err) {
    if (err instanceof ApiError && err.code === "AI_REPORT_NOT_FOUND") return null;
    throw err;
  }
}

export function generateAIReport(projectId: number, number: number): Promise<AIReport> {
  return request<AIReport>(`/projects/${projectId}/monitorings/${number}/ai-report`, {
    method: "POST",
  });
}
