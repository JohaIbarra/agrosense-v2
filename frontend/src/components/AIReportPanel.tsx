/**
 * Borrador de informe con IA (E9, UC-IA1/2/3): resumen + comparación del
 * monitoreo, redactados por un modelo local (Ollama) a partir de las
 * cifras que YA calculó el backend. El modelo nunca calcula nada
 * (docs/04-vision-producto.md, principio 2): esta pantalla solo pide,
 * muestra y avisa.
 */
import { useState } from "react";

import { generateAIReport, getAIReport } from "../api/aiReports";
import type { AIReport } from "../api/types";
import { useAsync } from "../hooks/useAsync";

function descargar(report: AIReport) {
  const blob = new Blob([report.content], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `AgroSense_M${report.monitoring}_borrador.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function AIReportPanel({ projectId, number }: { projectId: number; number: number }) {
  const existente = useAsync(
    (signal) => getAIReport(projectId, number, signal),
    [projectId, number],
  );
  const [generado, setGenerado] = useState<AIReport | null>(null);
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const actual = generado ?? existente.data;

  async function generar() {
    setGenerando(true);
    setError(null);
    try {
      setGenerado(await generateAIReport(projectId, number));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGenerando(false);
    }
  }

  return (
    <section className="card">
      <h2>Borrador de informe (IA)</h2>
      <p className="muted">
        Redactado por un modelo de IA local a partir de las cifras que ya calculó AgroSense.
        Borrador generado por IA — revíselo antes de usarlo.
      </p>

      {existente.loading && !actual && <p className="muted">Buscando un borrador…</p>}

      {actual && (
        <>
          {actual.stale && (
            <p className="warn" role="alert">
              El análisis cambió desde que se generó este borrador. Regénerelo para que
              refleje los datos actuales.
            </p>
          )}
          {actual.unverified_numbers.length > 0 && (
            <p className="warn" role="alert">
              Revise estas cifras: no aparecen entre los datos que recibió el modelo —{" "}
              {actual.unverified_numbers.join(", ")}.
            </p>
          )}
          <div className="ai-report-content">{actual.content}</div>
          <button type="button" className="btn btn-ghost" onClick={() => descargar(actual)}>
            Descargar .md
          </button>
        </>
      )}

      <button type="button" className="btn btn-primary" onClick={generar} disabled={generando}>
        {generando
          ? "Generando… puede tardar hasta un par de minutos"
          : actual
            ? "Regenerar"
            : "Generar borrador"}
      </button>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
