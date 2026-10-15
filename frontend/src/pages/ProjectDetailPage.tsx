/**
 * Ficha de un proyecto: carga de monitoreos, sus monitoreos (con acceso al
 * análisis) y sus datos.
 */
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { IconChart, IconEdit, IconLeaf, IconMap, IconSpecies } from "../components/icons";
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

  if (project.loading) return <p className="state loading">Cargando proyecto…</p>;
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
  const list = monitorings.data ?? [];
  const latest = list.length > 0 ? Math.max(...list.map((m) => m.number)) : null;
  const ubicacion = [p.municipality, p.department].filter(Boolean).join(", ");

  return (
    <div className="page">
      <header className="page-head page-head-row">
        <div>
          <nav className="crumbs" aria-label="Ruta">
            <Link to="/proyectos">Mis proyectos</Link>
            <span aria-hidden="true">/</span>
            <span aria-current="page">{p.project_code}</span>
          </nav>
          <div className="title-row">
            <h1>{p.name}</h1>
            <span className={p.status === "activo" ? "badge badge-sig" : "badge badge-nosig"}>
              {label(p.status)}
            </span>
          </div>
          <p className="subtitle">
            {[
              p.contract_code && `Contrato ${p.contract_code}`,
              ubicacion,
              p.area_ha !== null && `${p.area_ha} ha`,
            ]
              .filter(Boolean)
              .join(" · ") || "Complete los datos del proyecto en Editar."}
          </p>
        </div>
        <div className="head-actions head-actions-row">
          <Link to={`/proyectos/${p.id}/editar`} className="btn btn-ghost">
            <IconEdit />
            Editar
          </Link>
          {latest !== null && (
            <Link to={`/proyectos/${p.id}/monitoreos/${latest}`} className="btn btn-primary">
              Abrir análisis de M{latest}
            </Link>
          )}
        </div>
      </header>

      <nav className="quick-grid" aria-label="Secciones del proyecto">
        {latest !== null && (
          <Link to={`/proyectos/${p.id}/monitoreos/${latest}`} className="card quick">
            <span className="quick-icon">
              <IconChart />
            </span>
            <strong>Análisis del monitoreo M{latest}</strong>
            <span>Composición, crecimiento, supervivencia y árboles en riesgo.</span>
          </Link>
        )}
        {list.length > 0 && (
          <>
            <Link to={`/proyectos/${p.id}/mapa`} className="card quick">
              <span className="quick-icon blue">
                <IconMap />
              </span>
              <strong>Mapa del predio</strong>
              <span>Cada árbol sobre imagen satelital, con su historial.</span>
            </Link>
            <Link to={`/proyectos/${p.id}/ndvi`} className="card quick">
              <span className="quick-icon olive">
                <IconLeaf />
              </span>
              <strong>Verdor (NDVI)</strong>
              <span>Serie de Sentinel-2 sobre cada predio.</span>
            </Link>
          </>
        )}
        <Link to={`/proyectos/${p.id}/referente-contraste`} className="card quick">
          <span className="quick-icon clay">
            <IconSpecies />
          </span>
          <strong>Especies</strong>
          <span>Cómo se comportan las especies plantadas frente al referente.</span>
        </Link>
      </nav>

      <div className="project-grid">
        <div>
          {monitorings.loading && !monitorings.data && (
            <p className="muted loading">Cargando monitoreos…</p>
          )}
          {monitorings.error && (
            <p className="form-error" role="alert">
              {monitorings.error.message}
            </p>
          )}
          {monitorings.data && (
            <MonitoringsCard projectId={p.id} monitorings={monitorings.data} onChanged={reload} />
          )}
        </div>
        <UploadPanel projectId={p.id} onUploaded={reload} />
      </div>

      <Datos p={p} />
    </div>
  );
}
