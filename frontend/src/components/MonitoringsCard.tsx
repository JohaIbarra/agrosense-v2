/**
 * Monitoreos del proyecto: fecha editable y acceso a su análisis (E2/E3).
 *
 * La regla de fechas (en orden, no futuras) la valida el backend; aquí solo
 * se muestra su mensaje si la rechaza.
 */
import { useState } from "react";
import { Link } from "react-router-dom";

import { updateMonitoring } from "../api/projects";
import type { Monitoring } from "../api/types";
import { formatDate } from "../analysis/format";

function FechaEditable({
  projectId,
  monitoring,
  onSaved,
}: {
  projectId: number;
  monitoring: Monitoring;
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(monitoring.monitoring_date ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await updateMonitoring(projectId, monitoring.number, { monitoring_date: value || null });
      setEditing(false);
      onSaved();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <span className="date-cell">
        {formatDate(monitoring.monitoring_date) ?? <span className="muted">Sin fecha</span>}{" "}
        <button
          type="button"
          className="link-button"
          onClick={() => setEditing(true)}
          aria-label={`Editar la fecha del M${monitoring.number}`}
        >
          Editar
        </button>
      </span>
    );
  }
  return (
    <span className="date-cell">
      <input
        type="date"
        value={value}
        max={new Date().toISOString().slice(0, 10)}
        onChange={(e) => setValue(e.target.value)}
        aria-label={`Fecha del M${monitoring.number}`}
        disabled={busy}
      />
      <button type="button" className="link-button" onClick={save} disabled={busy}>
        Guardar
      </button>
      <button type="button" className="link-button" onClick={() => setEditing(false)}>
        Cancelar
      </button>
      {error && (
        <span className="form-error inline" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}

export function MonitoringsCard({
  projectId,
  monitorings,
  onChanged,
}: {
  projectId: number;
  monitorings: Monitoring[];
  onChanged: () => void;
}) {
  return (
    <section className="card">
      <h2>Monitoreos</h2>
      {monitorings.length === 0 ? (
        <p className="empty">
          Aún no hay monitoreos cargados. Suba el Excel del primer monitoreo para ver su análisis.
        </p>
      ) : (
        <table className="comparison">
          <thead>
            <tr>
              <th scope="col">Monitoreo</th>
              <th scope="col">Fecha</th>
              <th scope="col">Cuadrilla</th>
              <th scope="col">Observaciones</th>
              <th scope="col">Análisis</th>
            </tr>
          </thead>
          <tbody>
            {monitorings.map((m) => (
              <tr key={m.number}>
                <th scope="row">M{m.number}</th>
                <td>
                  <FechaEditable projectId={projectId} monitoring={m} onSaved={onChanged} />
                </td>
                <td>{m.field_crew ?? "—"}</td>
                <td>{m.observations}</td>
                <td>
                  <Link to={`/proyectos/${projectId}/monitoreos/${m.number}`}>
                    Ver análisis de M{m.number}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
