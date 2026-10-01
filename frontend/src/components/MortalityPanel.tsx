/**
 * Árboles en riesgo de morir (E8, S10). Solo presenta lo que calculó el
 * backend: qué modelo se usó y por qué, el puntaje y quién entra en el
 * presupuesto de alertas vienen hechos (AGENTS.md: sin reglas de negocio aquí).
 */
import { useState } from "react";

import { getMortalityRisk } from "../api/mortality";
import type { MortalityDecision, MortalityRisk } from "../api/types";
import { useAsync } from "../hooks/useAsync";

const nf = (value: number, digits: number) =>
  value.toLocaleString("es-CO", { minimumFractionDigits: digits, maximumFractionDigits: digits });

function motivo(d: MortalityDecision): string {
  switch (d.reason) {
    case "sin_intervalos_cerrados":
      return "Primer monitoreo: se usa el modelo general (tamaño relativo), validado en 3 proyectos.";
    case "pocos_eventos":
      return "El proyecto aún tiene pocas muertes registradas para entrenar su propio modelo; se usa el modelo general.";
    case "general_mejor":
      return `Se probó un modelo propio del proyecto, pero el general predijo mejor el último intervalo (${d.holdout_interval ?? "—"}).`;
    case "propio_mejor":
      return `Se usa un modelo entrenado con la historia de este proyecto: predijo mejor que el general el último intervalo (lift ${nf(d.holdout_lift_project ?? 0, 2)} vs ${nf(d.holdout_lift_general ?? 0, 2)}).`;
  }
}

function riesgo(r: MortalityRisk, score: number, percentil: number): string {
  return r.score_kind === "relative_risk"
    ? `percentil ${nf(percentil, 0)}`
    : `${nf(score * 100, 0)} %`;
}

export function MortalityPanel({ projectId, number }: { projectId: number; number: number }) {
  const [verTodos, setVerTodos] = useState(false);
  const estado = useAsync(
    (signal) => getMortalityRisk(projectId, number, !verTodos, signal),
    [projectId, number, verTodos],
  );
  const r = estado.data;

  return (
    <section className="card">
      <h2>Árboles en riesgo de morir</h2>
      <p className="muted">
        Qué árboles vivos tienen más riesgo de morir hasta el próximo monitoreo. Se marcan para
        revisión en campo los de mayor riesgo, hasta el presupuesto de alertas.
      </p>

      {estado.loading && !r && <p className="muted">Calculando…</p>}
      {estado.error && (
        <p className="form-error" role="alert">
          {estado.error.message}
        </p>
      )}

      {r && (
        <>
          <p>
            <strong>
              {r.model_kind === "project" ? "Modelo propio del proyecto" : "Modelo general"}
            </strong>
            . {motivo(r.decision)}
          </p>
          <p>
            {r.summary.flagged} de {r.summary.at_risk} árboles vivos marcados para revisión (
            {nf(r.alert_budget_pct, 0)} %). {r.summary.stalled_last_interval} no crecieron desde
            el monitoreo anterior.
          </p>
          {r.summary.without_history > 0 && (
            <p className="muted">
              {r.summary.without_history} árboles no tienen medición en el monitoreo anterior.
            </p>
          )}
          {r.score_kind === "relative_risk" && (
            <p className="warn">
              El percentil es un ranking relativo, no una probabilidad de morir: 100 es el árbol
              de mayor riesgo de este monitoreo.
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

          {r.trees.length === 0 ? (
            <p className="muted">No hay árboles marcados en este monitoreo.</p>
          ) : (
            <figure className="data-table">
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Árbol</th>
                      <th>Especie</th>
                      <th>Predio</th>
                      <th>Parcela</th>
                      <th>Altura (m)</th>
                      <th>Riesgo</th>
                      <th>Revisar</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.trees.map((t) => (
                      <tr key={t.tree_id}>
                        <td>{t.tree_id}</td>
                        <td>{t.species}</td>
                        <td>{t.locality ?? "—"}</td>
                        <td>{t.plot ?? "—"}</td>
                        <td>{nf(t.height_m, 2)}</td>
                        <td>{riesgo(r, t.score, t.risk_percentile)}</td>
                        <td>{t.flagged ? "Sí" : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </figure>
          )}

          <p className="muted provenance">
            Modelo {r.model_version} · datos {r.input_hash.slice(0, 12)} · calculado{" "}
            {new Date(r.computed_at).toLocaleString("es-CO")}
          </p>
        </>
      )}
    </section>
  );
}
