/**
 * Contraste de las especies plantadas del proyecto con el Referente
 * cientifico (E5, UC-AN3): "plantaste X, que segun el referente se estanca
 * ~4.9x mas de lo esperado".
 *
 * Una especie sin fila en el referente no se omite: se marca como "sin
 * referencia" para que el ingeniero sepa que la comparacion no existe
 * todavia, en vez de asumir que no hay riesgo.
 */
import { Link, useParams } from "react-router-dom";

import { getReferenceContrast } from "../api/contrast";
import { getProject } from "../api/projects";
import type { SpeciesContrast } from "../api/types";
import { RiskBlock } from "../components/RiskBlock";
import { useAsync } from "../hooks/useAsync";

function ContrastCard({ item }: { item: SpeciesContrast }) {
  return (
    <section className="card">
      <header className="card-head">
        <div>
          <h2 className="species-name">{item.species}</h2>
          <p className="muted">
            {item.n_trees_in_project} {item.n_trees_in_project === 1 ? "árbol" : "árboles"}
            {item.gremio && ` · ${item.gremio}`}
          </p>
        </div>
      </header>

      {item.has_reference ? (
        <div className="risk-grid">
          {item.stall_risk && <RiskBlock label="Estancamiento" risk={item.stall_risk} />}
          {item.mortality_risk && <RiskBlock label="Mortalidad" risk={item.mortality_risk} />}
        </div>
      ) : (
        <p className="muted">{item.narrative}</p>
      )}
    </section>
  );
}

export function ContrastPage() {
  const { id } = useParams();
  const projectId = Number(id);

  const project = useAsync((signal) => getProject(projectId, signal), [projectId]);
  const contraste = useAsync(
    (signal) => getReferenceContrast(projectId, signal),
    [projectId],
  );

  const volver = (
    <Link to={`/proyectos/${projectId}`}>{project.data?.name ?? "Volver al proyecto"}</Link>
  );

  if (contraste.loading && !contraste.data) {
    return <p className="state">Cargando el contraste…</p>;
  }
  if (contraste.error) {
    return (
      <div className="state">
        <h2>No se pudo abrir el contraste</h2>
        <p className="muted">{contraste.error.message}</p>
        {volver}
      </div>
    );
  }

  const items = contraste.data ?? [];

  return (
    <div className="page page-wide">
      <header className="page-head">
        <p className="muted">
          <Link to="/proyectos">Mis proyectos</Link> / {volver} / Contraste con el referente
        </p>
        <h1>Contraste con el Referente científico</h1>
        <p className="subtitle">
          Las especies plantadas en este proyecto, frente a los efectos estimados sobre el
          dataset de referencia.
        </p>
      </header>

      {items.length === 0 ? (
        <div className="state">
          <h2>Todavía no hay especies</h2>
          <p className="muted">Cargue un monitoreo con árboles para ver el contraste.</p>
        </div>
      ) : (
        items.map((item) => <ContrastCard key={item.species} item={item} />)
      )}
    </div>
  );
}
