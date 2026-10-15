/**
 * Lista de proyectos del ingeniero. El backend ya filtra por propietario: esta
 * página no decide qué proyectos se ven.
 */
import { Link } from "react-router-dom";

import { listProjects } from "../api/projects";
import { IconPlus, IconProjects } from "../components/icons";
import { useAsync } from "../hooks/useAsync";
import { label } from "../labels";

export function ProjectsPage() {
  const { data, loading, error } = useAsync((signal) => listProjects(signal), []);

  return (
    <div className="page">
      <header className="page-head page-head-row">
        <div>
          <h1>Mis proyectos</h1>
          <p className="subtitle">
            Cada proyecto guarda sus monitoreos, análisis y modelos de riesgo. Solo tú ves los tuyos.
          </p>
        </div>
        <Link to="/proyectos/nuevo" className="btn btn-primary">
          <IconPlus />
          Nuevo proyecto
        </Link>
      </header>

      {loading && <p className="state loading">Cargando proyectos…</p>}
      {error && (
        <p className="form-error" role="alert">
          {error.message}
        </p>
      )}

      {data && data.length === 0 && (
        <section className="card empty-card">
          <span className="empty-icon">
            <IconProjects />
          </span>
          <h2>Aún no tiene proyectos</h2>
          <p>Cree el primero: solo necesita el nombre, el resto se completa después.</p>
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
                  <div>
                    <h2>{p.name}</h2>
                    <span className="project-card-code">{p.project_code}</span>
                  </div>
                  <span
                    className={p.status === "activo" ? "badge badge-sig" : "badge badge-nosig"}
                  >
                    {label(p.status)}
                  </span>
                </div>
                <p className="muted">
                  {[p.municipality, p.department].filter(Boolean).join(", ") ||
                    "Ubicación sin registrar"}
                  {p.intervention_type && ` · ${label(p.intervention_type)}`}
                  {p.area_ha !== null && ` · ${p.area_ha} ha`}
                </p>
                <div className="project-card-foot">
                  <span>{p.contract_code ? `Contrato ${p.contract_code}` : "Sin contrato registrado"}</span>
                  <span>
                    {p.campaigns_count === 0
                      ? "Sin monitoreos cargados"
                      : `${p.campaigns_count} archivo(s) de monitoreo`}
                  </span>
                </div>
              </Link>
            </li>
          ))}
          <li>
            <Link to="/proyectos/nuevo" className="card project-card project-card-new">
              <span className="empty-icon">
                <IconPlus />
              </span>
              <strong>Crear otro proyecto</strong>
              <span>Solo necesitas el nombre; el resto se completa después.</span>
            </Link>
          </li>
        </ul>
      )}
    </div>
  );
}
