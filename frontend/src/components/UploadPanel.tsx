/**
 * Carga del Excel de campo desde la ficha del proyecto (E2).
 *
 * El ingeniero elige el archivo (un monitoreo o acumulado) y la fecha del
 * monitoreo que entrega. El resultado muestra qué trajo el archivo y los
 * avisos de la ingesta agrupados por tipo. Los mensajes se muestran como
 * texto (React escapa): vienen del archivo del usuario (deuda #J).
 */
import { useState, type FormEvent } from "react";

import { uploadCampaign } from "../api/projects";
import type { IngestWarning, UploadResult, WarningType } from "../api/types";

const WARNING_LABELS: Record<WarningType, string> = {
  contraction: "Contracciones de altura mayores a 5 cm",
  revival: "Árboles que figuran vivos tras registrarse muertos",
  census_gap: "Huecos de censo",
  event_mismatch: "La columna «Evento» no coincide con los monitoreos del archivo",
  project_mismatch: "El archivo nombra otro proyecto que las cargas anteriores",
  unknown_columns: "Columnas no reconocidas",
};

const SHOWN_PER_TYPE = 8;

function groupWarnings(warnings: IngestWarning[]): [WarningType, IngestWarning[]][] {
  const groups = new Map<WarningType, IngestWarning[]>();
  for (const w of warnings) groups.set(w.type, [...(groups.get(w.type) ?? []), w]);
  return [...groups.entries()];
}

function Resultado({ result }: { result: UploadResult }) {
  const monitoreos = result.monitorings.map((n) => `M${n}`).join(", ");
  return (
    <div className="upload-result" role="status">
      <p className="form-ok">
        Carga completa: {result.trees} árboles y {result.observations} observaciones
        {monitoreos ? ` de ${monitoreos}` : ""}.
        {result.analyzed.length > 0
          ? " El análisis quedó calculado."
          : " El análisis se calculará al abrirlo."}
      </p>
      {result.warnings.length === 0 ? (
        <p className="muted">Sin avisos de ingesta.</p>
      ) : (
        <div className="warnings">
          <h3>Avisos de la ingesta ({result.warnings.length})</h3>
          <p className="muted">
            No impiden la carga: son datos para revisar en campo o en el archivo.
          </p>
          {groupWarnings(result.warnings).map(([type, items]) => (
            <details key={type} open={items.length <= 3}>
              <summary>
                {WARNING_LABELS[type] ?? type} <span className="count">{items.length}</span>
              </summary>
              <ul>
                {items.slice(0, SHOWN_PER_TYPE).map((w, i) => (
                  <li key={i}>
                    {w.tree_id && <code>{w.tree_id}</code>} {w.message}
                  </li>
                ))}
                {items.length > SHOWN_PER_TYPE && (
                  <li className="muted">… y {items.length - SHOWN_PER_TYPE} más.</li>
                )}
              </ul>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

export function UploadPanel({
  projectId,
  onUploaded,
}: {
  projectId: number;
  onUploaded: (result: UploadResult) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [fecha, setFecha] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await uploadCampaign(projectId, file, fecha || null);
      setResult(r);
      onUploaded(r);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h2>Cargar monitoreo</h2>
      <p className="muted">
        Suba el Excel de campo: una fila por árbol, con las columnas del formato (ID_MUEST,
        Especie_M1, Altura total (m)_M1…). Puede traer un solo monitoreo o todos los anteriores.
        AgroSense calcula el análisis a partir de estos datos.
      </p>
      <form className="upload-form" onSubmit={submit}>
        <label className="field">
          <span>Archivo Excel (.xlsx)</span>
          <input
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            disabled={busy}
          />
        </label>
        <label className="field">
          <span>Fecha del monitoreo</span>
          <input
            type="date"
            value={fecha}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setFecha(e.target.value)}
            disabled={busy}
          />
        </label>
        <button type="submit" className="btn btn-primary" disabled={!file || busy}>
          {busy ? "Procesando…" : "Cargar y analizar"}
        </button>
      </form>
      <p className="muted">
        La fecha se asigna al monitoreo más reciente del archivo; la de los anteriores se edita
        en la tabla de monitoreos.
      </p>
      {busy && (
        <p className="muted" role="status">
          Leyendo el archivo, validando los datos y calculando el análisis. Puede tardar hasta un
          minuto con archivos grandes.
        </p>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {result && <Resultado result={result} />}
    </section>
  );
}
