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

// Nombre visible de cada feature categórica (fix wave, item 1b): la API
// nombra los campos con su identificador interno; aquí solo se traducen.
const NOMBRE_CAMPO: Record<string, string> = {
  species: "especie",
  locality: "localidad",
  monitoring_unit: "unidad de monitoreo",
  fito_t: "estado fitosanitario",
};

function camposDesconocidos(trees: StallTree[]): string[] {
  const vistos = new Set<string>();
  for (const t of trees) {
    for (const campo of t.unknown_categories) vistos.add(NOMBRE_CAMPO[campo] ?? campo);
  }
  return [...vistos].sort();
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
          {a.summary.unknown_category_trees > 0 && (
            <p className="warn">
              {a.summary.unknown_category_trees} árboles tienen valores no vistos en el
              entrenamiento en: {camposDesconocidos(a.trees).join(", ")}.
            </p>
          )}
          {a.summary.mostly_without_history && (
            <p className="warn" role="alert">
              <strong>
                La mayoría de los árboles de este monitoreo no tiene medición en el intervalo
                anterior: esta predicción es una extrapolación del modelo, no una evaluación
                equivalente a la reportada arriba.
              </strong>
            </p>
          )}
          {a.summary.without_history > 0 && (
            <p className="muted">
              {a.summary.without_history} árboles no tienen medición en el monitoreo anterior.
            </p>
          )}
          <p className="muted">
            El modelo se entrenó con un solo proyecto: la transferencia a otros proyectos no
            está evaluada. En este proyecto (el de referencia), las predicciones de M2 y M3 son
            sobre datos de entrenamiento (in-sample), no una evaluación honesta. La etiqueta mide
            crecimiento no detectable por el protocolo de campo (altura sin cambio, a precisión
            de milímetros), no crecimiento nulo.
          </p>

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
