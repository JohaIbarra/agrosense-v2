/**
 * Análisis exploratorio de un monitoreo (E3): las 7 hojas del Anexo 1
 * calculadas por el backend, como tablas ordenables y gráficas.
 *
 * Navegación: monitoreo (M1…Mn) → análisis (pestañas) → predio (filtro).
 * «Descargar reporte» baja el .xlsx que sale del MISMO cálculo.
 */
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { downloadReport, getMonitoringAnalysis, getProject } from "../api/projects";
import type { AnalysisSection, MonitoringAnalysis } from "../api/types";
import { formatDate, formatSummary } from "../analysis/format";
import { AIReportPanel } from "../components/AIReportPanel";
import { AnalysisBarChart } from "../components/AnalysisBarChart";
import { DataTable } from "../components/DataTable";
import { MortalityPanel } from "../components/MortalityPanel";
import { StallPanel } from "../components/StallPanel";
import { useAsync } from "../hooks/useAsync";

const ALL = "__todos__";

function Summary({ analysis }: { analysis: MonitoringAnalysis }) {
  return (
    <dl className="stat-grid">
      {analysis.summary.map((item) => (
        <div key={item.key} className="stat">
          <dt>{item.label}</dt>
          <dd>{formatSummary(item)}</dd>
        </div>
      ))}
    </dl>
  );
}

function Section({ section, property }: { section: AnalysisSection; property: string }) {
  const visible = (p: string | null) => property === ALL || p === null || p === property;
  const tables = section.tables.filter((t) => visible(t.property));
  const byId = new Map(section.tables.map((t) => [t.id, t]));
  const charts = section.charts.filter((c) => visible(c.property) && byId.has(c.table));

  return (
    <section className="analysis-section" aria-labelledby={`sec-${section.id}`}>
      <h2 id={`sec-${section.id}`}>{section.title}</h2>
      <p className="muted">{section.description}</p>
      {section.notes.map((n) => (
        <p key={n} className="warn">
          {n}
        </p>
      ))}
      {charts.length > 0 && (
        <div className="chart-grid">
          {charts.map((c) => (
            <AnalysisBarChart key={c.id} chart={c} table={byId.get(c.table)!} />
          ))}
        </div>
      )}
      {tables.map((t) => (
        <DataTable key={t.id} table={t} />
      ))}
    </section>
  );
}

export function MonitoringAnalysisPage() {
  const { id, numero } = useParams();
  const projectId = Number(id);
  const number = Number(numero);
  const navigate = useNavigate();
  const [sectionId, setSectionId] = useState("composicion");
  const [property, setProperty] = useState(ALL);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const project = useAsync((signal) => getProject(projectId, signal), [projectId]);
  const analysis = useAsync(
    (signal) => getMonitoringAnalysis(projectId, number, signal),
    [projectId, number],
  );

  async function download() {
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadReport(projectId, number);
    } catch (err) {
      setDownloadError((err as Error).message);
    } finally {
      setDownloading(false);
    }
  }

  const back = (
    <Link to={`/proyectos/${projectId}`}>{project.data?.name ?? "Volver al proyecto"}</Link>
  );

  if (analysis.loading && !analysis.data) {
    return <p className="state">Calculando el análisis del monitoreo M{number}…</p>;
  }
  if (analysis.error) {
    return (
      <div className="state">
        <h2>No se pudo abrir el análisis</h2>
        <p className="muted">{analysis.error.message}</p>
        {back}
      </div>
    );
  }
  const a = analysis.data!;
  const section = a.sections.find((s) => s.id === sectionId) ?? a.sections[0];

  return (
    <div className="page page-wide">
      <header className="page-head page-head-row">
        <div>
          <p className="muted">
            <Link to="/proyectos">Mis proyectos</Link> / {back} / M{a.monitoring}
          </p>
          <h1>Análisis del monitoreo M{a.monitoring}</h1>
          <p className="subtitle">
            {a.monitoring_date ? `Fecha: ${formatDate(a.monitoring_date)}` : "Sin fecha registrada"}
            {a.previous !== null
              ? ` · Comparado con M${a.previous}`
              : " · Primer monitoreo: sin comparación"}
          </p>
        </div>
        <div className="head-actions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={download}
            disabled={downloading}
          >
            {downloading ? "Generando…" : "Descargar reporte (.xlsx)"}
          </button>
          {downloadError && (
            <p className="form-error" role="alert">
              {downloadError}
            </p>
          )}
        </div>
      </header>

      <nav className="filter" aria-label="Monitoreo">
        <span className="filter-label">Monitoreo</span>
        {a.monitorings.map((n) => (
          <button
            key={n}
            type="button"
            className={n === a.monitoring ? "chip chip-on" : "chip"}
            aria-pressed={n === a.monitoring}
            onClick={() => navigate(`/proyectos/${projectId}/monitoreos/${n}`)}
          >
            M{n}
          </button>
        ))}
      </nav>

      <Summary analysis={a} />

      <div className="tabs" role="tablist" aria-label="Análisis">
        {a.sections.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={s.id === section.id}
            className={s.id === section.id ? "tab tab-on" : "tab"}
            onClick={() => setSectionId(s.id)}
          >
            {s.title}
          </button>
        ))}
      </div>

      {a.properties.length > 1 && (
        <div className="filter" role="group" aria-label="Predio">
          <span className="filter-label">Predio</span>
          {[ALL, ...a.properties].map((p) => (
            <button
              key={p}
              type="button"
              className={p === property ? "chip chip-on" : "chip"}
              aria-pressed={p === property}
              onClick={() => setProperty(p)}
            >
              {p === ALL ? "Todos" : p}
            </button>
          ))}
        </div>
      )}

      <Section section={section} property={property} />

      {/* key: fuerza un panel nuevo por monitoreo. Sin esto, el estado
          `generado` del panel anterior (cargado por proyecto+numero, pero
          nunca reiniciado) seguia mostrandose al cambiar de monitoreo con
          los botones M1..Mn, que NO desmontan esta pagina. */}
      <AIReportPanel key={`${projectId}-${number}`} projectId={projectId} number={number} />

      {/* key: un panel nuevo por monitoreo, como el del borrador de IA. */}
      <StallPanel key={`stall-${projectId}-${number}`} projectId={projectId} number={number} />

      <MortalityPanel
        key={`mortality-${projectId}-${number}`}
        projectId={projectId}
        number={number}
      />

      <p className="muted provenance">
        Cálculo {a.analysis_version} · datos {a.input_hash.slice(0, 12)} · calculado{" "}
        {new Date(a.computed_at).toLocaleString("es-CO")}
      </p>
    </div>
  );
}
