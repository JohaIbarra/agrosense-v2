/**
 * Presentación de los valores del análisis.
 *
 * Solo FORMATEA: el tipo y los decimales de cada columna los declara el
 * backend (AGENTS.md: el frontend no recalcula ni duplica reglas). Mismo
 * criterio que el reporte .xlsx: porcentajes en escala 0–100.
 */
import type { AnalysisColumn, AnalysisValue, SummaryItem } from "../api/types";

const LOCALE = "es-CO";

export function formatNumber(value: number, decimals: number): string {
  return value.toLocaleString(LOCALE, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatValue(
  value: AnalysisValue | undefined,
  column: Pick<AnalysisColumn, "kind" | "decimals">,
): string {
  if (value === null || value === undefined || value === "") return "—";
  if (column.kind === "text" || typeof value !== "number") return String(value);
  const decimals = column.decimals ?? (column.kind === "int" ? 0 : 2);
  const text = formatNumber(value, decimals);
  return column.kind === "percent" ? `${text} %` : text;
}

export function formatSummary(item: SummaryItem): string {
  const text = formatValue(item.value, item);
  return item.unit && item.value !== null ? `${text} ${item.unit}` : text;
}

/** Etiqueta completa de una columna: «Diseño · M4» si pertenece a un grupo. */
export function columnLabel(column: AnalysisColumn): string {
  return column.group ? `${column.group} · ${column.label}` : column.label;
}

/** Fecha ISO (AAAA-MM-DD) como DD/MM/AAAA. */
export function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}
