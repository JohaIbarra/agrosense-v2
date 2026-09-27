/**
 * Ficha de un proyecto: carga de monitoreos, sus monitoreos (con acceso al
 * análisis) y sus datos.
 */
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { MonitoringsCard } from "../components/MonitoringsCard";
import { UploadPanel } from "../components/UploadPanel";
import { getProject, listMonitorings } from "../api/projects";
import type { Project } from "../api/types";
import { useAsync } from "../hooks/useAsync";
import { label } from "../labels";

function Dato({ titulo, valor }: { titulo: string; valor: string | number | null }) {
  return (
    <div className="dato">
      <dt>{titulo}</dt>
      <dd>{valor === null || valor === "" ? "—" : valor}</dd>
    </div>
  );
}

function fecha(iso: string | null): string | null {
  if (!iso) return null;
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

function Datos({ p }: { p: Project }) {
  return (
    <div className="ficha">
      <section className="card">
        <h2>Identificación y responsable</h2>
        <dl>
          <Dato titulo="Código interno" valor={p.project_code} />
          <Dato titulo="Código de contrato" valor={p.contract_code} />
          <Dato titulo="Ejecutora" valor={p.executing_org} />
          <Dato titulo="Contratante" valor={p.contracting_entity} />
        </dl>
        {p.objective && <p className="objetivo">{p.objective}</p>}
      </section>
      <section className="card">
        <h2>Ubicación</h2>
        <dl>
          <Dato titulo="Departamento" valor={p.department} />
          <Dato titulo="Municipio" valor={p.municipality} />
          <Dato titulo="Vereda / referencia" valor={p.locality} />
          <Dato titulo="Coordenadas" valor={`EPSG:${p.coordinate_srid}`} />
        </dl>
      </section>
      <section className="card">
        <h2>Intervención</h2>
        <dl>
          <Dato titulo="Tipo" valor={label(p.intervention_type)} />
          <Dato titulo="Área" valor={p.area_ha !== null ? `${p.area_ha} ha` : null} />
          <Dato titulo="Individuos plantados" valor={p.planted_individuals} />
          <Dato
            titulo="Densidad"
            valor={p.planting_density !== null ? `${p.planting_density} ind/ha` : null}
          />
          <Dato titulo="Siembra" valor={fecha(p.establishment_date)} />
          <Dato
            titulo="Período"
            valor={
              p.start_date || p.end_date
                ? `${fecha(p.start_date) ?? "—"} → ${fecha(p.end_date) ?? "—"}`
                : null
            }
          />
        </dl>
      </section>
      <section className="card">
        <h2>Marco</h2>
        <dl>
          <Dato titulo="Marco legal" valor={label(p.legal_framework)} />
          <Dato titulo="Autoridad ambiental" valor={p.environmental_authority} />
        </dl>
      </section>
    </div>
  );
}

export function ProjectDetailPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const project = useAsync((signal) => getProject(projectId, signal), [projectId]);
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((v) => v + 1);
  const monitorings = useAsync(
    (signal) => listMonitorings(projectId, signal),
    [projectId, version],
  );

  if (project.loading) return <p className="state">Cargando proyecto…</p>;
  if (project.error) {
    return (
      <div className="state">
        <h2>No se encontró el proyecto</h2>
        <p className="muted">{project.error.message}</p>
        <Link to="/proyectos">Volver a mis proyectos</Link>
      </div>
    );
  }
  const p = project.data!;

  return (
    <div className="page">
      <header className="page-head page-head-row">
        <div>
          <p className="muted">
            <Link to="/proyectos">Mis proyectos</Link> / {p.project_code}
          </p>
          <h1>{p.name}</h1>
          <span className={p.status === "activo" ? "badge badge-sig" : "badge badge-nosig"}>
            {label(p.status)}
          </span>
        </div>
        <div className="head-actions head-actions-row">
          {(monitorings.data?.length ?? 0) > 0 && (
            <>
              <Link to={`/proyectos/${p.id}/mapa`} className="btn btn-ghost">
                Ver mapa
              </Link>
              <Link to={`/proyectos/${p.id}/ndvi`} className="btn btn-ghost">
                Ver NDVI
              </Link>
            </>
          )}
          <Link to={`/proyectos/${p.id}/referente-contraste`} className="btn btn-ghost">
            Contraste con el referente
          </Link>
          <Link to={`/proyectos/${p.id}/editar`} className="btn btn-ghost">
            Editar
          </Link>
        </div>
      </header>

      <UploadPanel projectId={p.id} onUploaded={reload} />

      {monitorings.loading && !monitorings.data && <p className="muted">Cargando monitoreos…</p>}
      {monitorings.error && (
        <p className="form-error" role="alert">
          {monitorings.error.message}
        </p>
      )}
      {monitorings.data && (
        <MonitoringsCard projectId={p.id} monitorings={monitorings.data} onChanged={reload} />
      )}

      <Datos p={p} />
    </div>
  );
}
