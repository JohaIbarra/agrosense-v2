/**
 * Lista de proyectos del ingeniero. El backend ya filtra por propietario: esta
 * página no decide qué proyectos se ven.
 */
import { Link } from "react-router-dom";

import { listProjects } from "../api/projects";
import { useAsync } from "../hooks/useAsync";
import { label } from "../labels";

export function ProjectsPage() {
  const { data, loading, error } = useAsync((signal) => listProjects(signal), []);

  return (
    <div className="page">
      <header className="page-head page-head-row">
        <div>
          <h1>Mis proyectos</h1>
          <p className="subtitle">Cada proyecto guarda sus propios monitoreos y análisis.</p>
        </div>
        <Link to="/proyectos/nuevo" className="btn btn-primary">
          Nuevo proyecto
        </Link>
      </header>

      {loading && <p className="state">Cargando proyectos…</p>}
      {error && (
        <p className="form-error" role="alert">
          {error.message}
        </p>
      )}

      {data && data.length === 0 && (
        <section className="card empty-card">
          <h2>Aún no tiene proyectos</h2>
          <p>Cree el primero con los datos del contrato y la intervención.</p>
          <Link to="/proyectos/nuevo" className="btn btn-primary">
            Crear proyecto
          </Link>
        </section>
      )}

      {data && data.length > 0 && (
        <ul className="project-list">
          {data.map((p) => (
            <li key={p.id}>
              <Link to={`/proyectos/${p.id}`} className="card project-card">
                <div className="project-card-head">
                  <h2>{p.name}</h2>
                  <span
                    className={p.status === "activo" ? "badge badge-sig" : "badge badge-nosig"}
                  >
                    {label(p.status)}
                  </span>
                </div>
                <p className="muted">
                  {p.project_code}
                  {p.contract_code && ` · Contrato ${p.contract_code}`}
                </p>
                <p>
                  {[p.municipality, p.department].filter(Boolean).join(", ") ||
                    "Ubicación sin registrar"}
                  {p.intervention_type && ` · ${label(p.intervention_type)}`}
                </p>
                <p className="muted">
                  {p.campaigns_count === 0
                    ? "Sin monitoreos cargados"
                    : `${p.campaigns_count} archivo(s) de monitoreo`}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
