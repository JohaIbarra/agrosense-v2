/** Acceso al riesgo de mortalidad de un monitoreo (E8, S9 · contrato en el plan). */
import { request } from "./http";
import type { MortalityRisk } from "./types";

export function getMortalityRisk(
  projectId: number,
  number: number,
  onlyFlagged: boolean,
  signal?: AbortSignal,
): Promise<MortalityRisk> {
  return request<MortalityRisk>(`/projects/${projectId}/monitorings/${number}/mortality-risk`, {
    query: { only_flagged: onlyFlagged ? "true" : undefined },
    signal,
  });
}
