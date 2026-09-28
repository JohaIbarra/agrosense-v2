/** Acceso a la detección de estancados de un monitoreo (E7, UC-AN4). */
import { request } from "./http";
import type { StallAssessment } from "./types";

export function getStallAssessment(
  projectId: number,
  number: number,
  onlyFlagged: boolean,
  signal?: AbortSignal,
): Promise<StallAssessment> {
  return request<StallAssessment>(`/projects/${projectId}/monitorings/${number}/stall-assessment`, {
    query: { only_flagged: onlyFlagged ? "true" : undefined },
    signal,
  });
}
