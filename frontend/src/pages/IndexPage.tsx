/**
 * NDVI por predio (E10a): cómo ha cambiado el verdor del predio en el tiempo.
 *
 * Separación deliberada: abrir la página muestra lo que ya está guardado y es
 * instantáneo; «Buscar imágenes nuevas» es una acción que el ingeniero pide a
 * propósito, porque sale a un proveedor externo y puede tardar.
 *
 * La página no calcula: el valor, su lectura en palabras y la marca de poca
 * superficie vienen del backend (dominio en `satellite_rules.py`).
 */
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getProjectIndex, refreshProjectIndex } from "../api/indices";
import { getProject } from "../api/projects";
import type { IndexReading, IndexRefreshSummary, ProjectIndex } from "../api/types";
import { formatDate } from "../analysis/format";
import { SERIES_COLORS } from "../components/AnalysisBarChart";
import { useAsync } from "../hooks/useAsync";

/** Una fila por fecha, una columna por predio: es lo que dibuja la línea. */
function toSeries(data: ProjectIndex) {
  const porFecha = new Map<string, Record<string, number | string>>();
  for (const r of data.readings) {
    const fila = porFecha.get(r.acquired_at) ?? { acquired_at: r.acquired_at };
    fila[r.property_name] = r.mean;
    porFecha.set(r.acquired_at, fila);
  }
  return [...porFecha.values()].sort((a, b) =>
    String(a.acquired_at).localeCompare(String(b.acquired_at)),
  );
}

function Resumen({ summary }: { summary: IndexRefreshSummary }) {
  const partes = [
    `${summary.scenes_found} ${summary.scenes_found === 1 ? "imagen encontrada" : "imágenes encontradas"}`,
    `${summary.readings_added} ${summary.readings_added === 1 ? "medición nueva" : "mediciones nuevas"}`,
  ];
  if (summary.without_data > 0) {
    partes.push(`${summary.without_data} sin datos (nubes sobre el predio)`);
  }
  return (
    <p className={summary.interrupted ? "warn" : "muted"} role="status">
      {partes.join(" · ")}
      {summary.interrupted &&
        " · el proveedor dejó de responder: se guardó lo conseguido, vuelva a intentarlo."}
    </p>
  );
}

function Tabla({ readings }: { readings: IndexReading[] }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Fecha</th>
          <th scope="col">Predio</th>
          <th scope="col">NDVI medio</th>
          <th scope="col">Lectura</th>
          <th scope="col">Píxeles</th>
          <th scope="col">Nubes de la escena</th>
        </tr>
      </thead>
      <tbody>
        {[...readings].reverse().map((r) => (
          <tr key={`${r.scene_id}-${r.property_name}`} className={r.reliable ? "" : "low-sample"}>
            <td>{formatDate(r.acquired_at)}</td>
            <td>{r.property_name}</td>
            <td className="num">{r.mean.toFixed(3)}</td>
            <td>
              {r.reading}
              {!r.reliable && <span className="muted"> · superficie muy pequeña</span>}
            </td>
            <td className="num">{r.valid_pixels}</td>
            <td className="num">
              {r.cloud_cover === null ? "—" : `${r.cloud_cover.toFixed(0)} %`}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function IndexPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const [recarga, setRecarga] = useState(0);
  const [buscando, setBuscando] = useState(false);
  const [summary, setSummary] = useState<IndexRefreshSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const project = useAsync((signal) => getProject(projectId, signal), [projectId]);
  const indice = useAsync(
    (signal) => getProjectIndex(projectId, "NDVI", signal),
    [projectId, recarga],
  );

  async function buscar() {
    setBuscando(true);
    setError(null);
    setSummary(null);
    try {
      const r = await refreshProjectIndex(projectId, "NDVI");
      setSummary(r.summary);
      setRecarga((n) => n + 1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBuscando(false);
    }
  }

  const volver = (
    <Link to={`/proyectos/${projectId}`}>{project.data?.name ?? "Volver al proyecto"}</Link>
  );

  if (indice.loading && !indice.data) return <p className="state">Cargando el NDVI…</p>;
  if (indice.error) {
    return (
      <div className="state">
        <h2>No se pudo abrir el NDVI</h2>
        <p className="muted">{indice.error.message}</p>
        {volver}
      </div>
    );
  }

  const data = indice.data!;
  const series = toSeries(data);

  return (
    <div className="page page-wide">
      <header className="page-head page-head-row">
        <div>
          <p className="muted">
            <Link to="/proyectos">Mis proyectos</Link> / {volver} / NDVI
          </p>
          <h1>Verdor del predio (NDVI)</h1>
          <p className="subtitle">
            Índice de vegetación de Sentinel-2 (10 m por píxel), medido sobre el polígono de
            lo plantado.
            {data.last_refreshed_at && ` Última consulta: ${formatDate(data.last_refreshed_at)}.`}
          </p>
        </div>
        <div className="head-actions">
          <button type="button" className="btn btn-primary" onClick={buscar} disabled={buscando}>
            {buscando ? "Buscando imágenes…" : "Buscar imágenes nuevas"}
          </button>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
        </div>
      </header>

      {summary && <Resumen summary={summary} />}

      {data.readings.length === 0 ? (
        <div className="state">
          <h2>Todavía no hay mediciones</h2>
          <p className="muted">
            Pulse «Buscar imágenes nuevas» para consultar las escenas de Sentinel-2 del último
            año sobre sus predios. La consulta tarda unos segundos por imagen.
          </p>
        </div>
      ) : (
        <>
          <figure className="chart-card">
            <figcaption>NDVI medio por predio</figcaption>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={series} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="#e7e5e1" vertical={false} />
                <XAxis
                  dataKey="acquired_at"
                  tickFormatter={(v: string) => formatDate(v) ?? v}
                  tick={{ fontSize: 12, fill: "#52514e" }}
                  stroke="#d1d5db"
                />
                <YAxis
                  domain={[0, 1]}
                  tick={{ fontSize: 12, fill: "#52514e" }}
                  stroke="#d1d5db"
                />
                <Tooltip
                  formatter={(v: number) => v.toFixed(3)}
                  labelFormatter={(v: string) => formatDate(v) ?? v}
                />
                <Legend />
                {data.properties.map((p, i) => (
                  <Line
                    key={p}
                    type="monotone"
                    dataKey={p}
                    stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                    strokeWidth={2}
                    dot={{ r: 4 }}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </figure>

          <Tabla readings={data.readings} />

          <p className="muted small">
            Fuente: {data.readings[0].source}. Cada punto es la media del índice dentro del
            contorno del predio en esa fecha; las filas marcadas cubren muy pocos píxeles para
            promediar con confianza.
          </p>
        </>
      )}
    </div>
  );
}
