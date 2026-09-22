/**
 * Tabla tipo Excel de una tabla del análisis: encabezados agrupados, orden
 * por columna (clic en el encabezado), totales fijos al pie y filas de
 * muestra pequeña marcadas.
 *
 * Genérica a propósito: la forma (columnas, tipos, decimales) viene del
 * contrato, así que una tabla nueva en el backend se ve sin tocar esto.
 */
import { useMemo, useState } from "react";

import type { AnalysisColumn, AnalysisRow, AnalysisTable } from "../api/types";
import { formatValue } from "../analysis/format";

type Sort = { key: string; dir: 1 | -1 } | null;

function compare(a: AnalysisRow, b: AnalysisRow, key: string): number {
  const va = a[key];
  const vb = b[key];
  // Los vacíos siempre al final, en cualquier sentido
  if (va === null || va === undefined) return vb === null || vb === undefined ? 0 : 1;
  if (vb === null || vb === undefined) return -1;
  if (typeof va === "number" && typeof vb === "number") return va - vb;
  return String(va).localeCompare(String(vb), "es");
}

function isLowSample(row: AnalysisRow): boolean {
  const flags = row._flags;
  return Array.isArray(flags) && flags.includes("low_sample");
}

/** Encabezado de grupos: celdas consecutivas del mismo grupo se unen. */
function GroupRow({ columns }: { columns: AnalysisColumn[] }) {
  const cells: { group: string | null; span: number; key: string }[] = [];
  for (const col of columns) {
    const group = col.group ?? null;
    const last = cells[cells.length - 1];
    if (last && group !== null && last.group === group) last.span += 1;
    else cells.push({ group, span: 1, key: col.key });
  }
  return (
    <tr className="group-row">
      {cells.map((c) => (
        <th key={c.key} colSpan={c.span} scope="colgroup" className={c.group ? "grouped" : ""}>
          {c.group ?? ""}
        </th>
      ))}
    </tr>
  );
}

export function DataTable({ table }: { table: AnalysisTable }) {
  const [sort, setSort] = useState<Sort>(null);
  const rows = useMemo(() => {
    if (!sort) return table.rows;
    return [...table.rows].sort((a, b) => {
      const c = compare(a, b, sort.key);
      // los vacíos quedan al final también en orden descendente
      const empty = a[sort.key] === null || b[sort.key] === null;
      return empty ? c : c * sort.dir;
    });
  }, [table.rows, sort]);

  const hasGroups = table.columns.some((c) => c.group);
  const lowSample = table.rows.some(isLowSample);

  function toggle(key: string) {
    setSort((s) => (s?.key === key ? (s.dir === 1 ? { key, dir: -1 } : null) : { key, dir: 1 }));
  }

  return (
    <figure className="data-table">
      <figcaption>{table.title}</figcaption>
      <div className="table-scroll">
        <table>
          <thead>
            {hasGroups && <GroupRow columns={table.columns} />}
            <tr>
              {table.columns.map((c) => {
                const active = sort?.key === c.key;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    className={c.kind === "text" ? "text" : "num"}
                    aria-sort={active ? (sort!.dir === 1 ? "ascending" : "descending") : "none"}
                  >
                    <button type="button" onClick={() => toggle(c.key)} title="Ordenar">
                      {c.label}
                      <span className="sort-mark" aria-hidden>
                        {active ? (sort!.dir === 1 ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={table.columns.length} className="empty-cell">
                  Sin datos para este corte.
                </td>
              </tr>
            )}
            {rows.map((row, i) => (
              <tr key={i} className={isLowSample(row) ? "low-sample" : undefined}>
                {table.columns.map((c, j) => (
                  <td key={c.key} className={c.kind === "text" ? "text" : "num"}>
                    {formatValue(row[c.key], c)}
                    {j === 0 && isLowSample(row) && (
                      <span className="low-mark" title="Muestra pequeña: porcentaje poco robusto">
                        {" "}
                        ⚠
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {table.footer.length > 0 && (
            <tfoot>
              {table.footer.map((row, i) => (
                <tr key={i}>
                  {table.columns.map((c) => (
                    <td key={c.key} className={c.kind === "text" ? "text" : "num"}>
                      {c.kind === "text" && !row[c.key] ? "" : formatValue(row[c.key], c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tfoot>
          )}
        </table>
      </div>
      {(table.notes.length > 0 || lowSample) && (
        <ul className="table-notes">
          {table.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
          {lowSample && <li>⚠ Muestra pequeña: el porcentaje de esa fila es poco robusto.</li>}
        </ul>
      )}
    </figure>
  );
}
