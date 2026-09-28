/**
 * Árboles en riesgo de estancarse (E7, UC-AN4). Solo presenta lo que calculó
 * el backend: la probabilidad, quién entra en el presupuesto de alertas y la
 * regla observada vienen hechas (AGENTS.md: sin reglas de negocio aquí).
 */
import { useState } from "react";

import { getStallAssessment } from "../api/stall";
import type { StallTree } from "../api/types";
import { useAsync } from "../hooks/useAsync";

const nf = (value: number, digits: number) =>
  value.toLocaleString("es-CO", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const pct = (probability: number) => `${nf(probability * 100, 0)} %`;

function intervaloAnterior(t: StallTree): string {
  if (t.stalled_last_interval === null) return "Sin historia";
  return t.stalled_last_interval ? "No creció" : "Creció";
}

export function StallPanel({ projectId, number }: { projectId: number; number: number }) {
  const [verTodos, setVerTodos] = useState(false);
  const estado = useAsync(
    (signal) => getStallAssessment(projectId, number, !verTodos, signal),
    [projectId, number, verTodos],
  );
  const a = estado.data;

  return (
    <section className="card">
      <h2>Árboles en riesgo de estancarse</h2>
      <p className="muted">
        Probabilidad de que la altura no cambie hasta el próximo monitoreo, si el árbol sigue
        vivo. Se marcan para revisión en campo los árboles con mayor probabilidad, hasta el
        presupuesto de alertas.
      </p>

      {estado.loading && !a && <p className="muted">Calculando…</p>}
      {estado.error && (
        <p className="form-error" role="alert">
          {estado.error.message}
        </p>
      )}

      {a && (
        <>
          <p>
            {a.summary.flagged} de {a.summary.at_risk} árboles vivos marcados para revisión (
            {nf(a.alert_budget_pct, 0)} %). {a.summary.stalled_last_interval} no crecieron desde
            el monitoreo anterior y {a.summary.persistent} llevan{" "}
            {a.persistent_min_intervals} intervalos seguidos o más sin crecer.
          </p>
          <p className="warn">
            Señal sugestiva, no concluyente: PR-AUC {nf(a.model.pr_auc, 2)} (IC 95 %{" "}
            {nf(a.model.pr_auc_ci_low, 2)}–{nf(a.model.pr_auc_ci_high, 2)}) frente a una
            prevalencia de {nf(a.model.prevalence_pct, 1)} %. Con este presupuesto el modelo
            recuperó el {nf(a.model.recall_at_budget_pct, 0)} % de los estancados con una
            precisión del {nf(a.model.precision_at_budget_pct, 0)} % en su evaluación.
          </p>
          {a.summary.unknown_species > 0 && (
            <p className="warn">
              {a.summary.unknown_species} árboles son de especies que el modelo no vio al
              entrenar: su probabilidad se apoya solo en las demás variables.
            </p>
          )}
          {a.summary.without_history > 0 && (
            <p className="muted">
              {a.summary.without_history} árboles no tienen medición en el monitoreo anterior.
            </p>
          )}

          <label className="checkbox">
            <input
              type="checkbox"
              checked={verTodos}
              onChange={(e) => setVerTodos(e.target.checked)}
            />{" "}
            Ver todos los árboles vivos
          </label>

          <figure className="data-table">
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Árbol</th>
                    <th>Especie</th>
                    <th>Predio</th>
                    <th>Parcela</th>
                    <th>Probabilidad</th>
                    <th>Intervalo anterior</th>
                    <th>Intervalos sin crecer</th>
                    <th>Revisar</th>
                  </tr>
                </thead>
                <tbody>
                  {a.trees.map((t) => (
                    <tr key={t.tree_id}>
                      <td>{t.tree_id}</td>
                      <td>
                        {t.species}
                        {!t.known_species && " *"}
                      </td>
                      <td>{t.locality ?? "—"}</td>
                      <td>{t.plot ?? "—"}</td>
                      <td>{pct(t.probability)}</td>
                      <td>{intervaloAnterior(t)}</td>
                      <td>{t.stall_streak}</td>
                      <td>{t.flagged ? "Sí" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </figure>

          <p className="muted provenance">
            Modelo {a.model.model_version} · datos {a.input_hash.slice(0, 12)} · calculado{" "}
            {new Date(a.computed_at).toLocaleString("es-CO")}
          </p>
        </>
      )}
    </section>
  );
}
