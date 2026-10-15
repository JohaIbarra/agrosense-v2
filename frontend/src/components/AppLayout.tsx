/**
 * Marco de las páginas autenticadas: barra lateral con la navegación y el
 * cierre de sesión.
 *
 * Dentro de un proyecto (/proyectos/:id/...) la barra muestra sus secciones.
 * El nombre del proyecto y su último monitoreo se piden aquí aparte de la
 * página: son dos lecturas baratas y evitan acoplar cada página al marco. Si
 * el proyecto no existe o no es del usuario, la API responde 404 y la barra
 * simplemente no muestra el bloque del proyecto.
 *
 * En pantallas angostas la barra se pliega en una franja superior con un botón
 * de menú.
 */
import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useMatch, useNavigate } from "react-router-dom";

import { getProject, listMonitorings } from "../api/projects";
import { useAuth } from "../auth/AuthProvider";
import { useAsync } from "../hooks/useAsync";
import {
  BrandMark,
  IconChart,
  IconLeaf,
  IconLogout,
  IconMap,
  IconMenu,
  IconOverview,
  IconProjects,
  IconSpecies,
  IconUser,
} from "./icons";

function useProjectId(): number | null {
  const match = useMatch("/proyectos/:id/*");
  const raw = match?.params.id ?? "";
  return /^\d+$/.test(raw) ? Number(raw) : null;
}

function ProjectNav({ projectId }: { projectId: number }) {
  const { pathname } = useLocation();
  const project = useAsync((signal) => getProject(projectId, signal), [projectId]);
  // Se relee al cambiar de ruta: tras la primera carga del Excel aparece «Análisis».
  const monitorings = useAsync(
    (signal) => listMonitorings(projectId, signal),
    [projectId, pathname],
  );

  if (!project.data) return null;
  const list = Array.isArray(monitorings.data) ? monitorings.data : [];
  const latest = list.length > 0 ? Math.max(...list.map((m) => m.number)) : null;
  const base = `/proyectos/${projectId}`;
  const inAnalysis = pathname.startsWith(`${base}/monitoreos/`);

  return (
    <>
      <div className="side-group">
        <span className="side-label">Proyecto</span>
        <NavLink to={base} end className="side-project">
          <span className="side-project-name">{project.data.name}</span>
          <span className="side-project-code">{project.data.project_code}</span>
        </NavLink>
      </div>
      <div className="side-group">
        <NavLink to={base} end className="side-link">
          <IconOverview />
          Resumen y monitoreos
        </NavLink>
        {latest !== null && (
          <NavLink
            to={`${base}/monitoreos/${latest}`}
            className={inAnalysis ? "side-link active" : "side-link"}
          >
            <IconChart />
            Análisis
          </NavLink>
        )}
        <NavLink to={`${base}/mapa`} className="side-link">
          <IconMap />
          Mapa del predio
        </NavLink>
        <NavLink to={`${base}/ndvi`} className="side-link">
          <IconLeaf />
          Verdor (NDVI)
        </NavLink>
        <NavLink to={`${base}/referente-contraste`} className="side-link">
          <IconSpecies />
          Especies
        </NavLink>
      </div>
    </>
  );
}

export function AppLayout({ children }: { children: ReactNode }) {
  const { session, signOut } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const projectId = useProjectId();
  const [open, setOpen] = useState(false);

  // Navegar cierra el menú plegado.
  useEffect(() => setOpen(false), [pathname]);

  return (
    <div className="app">
      <aside className={open ? "sidebar sidebar-open" : "sidebar"}>
        <div className="side-top">
          <NavLink to="/proyectos" className="side-brand">
            <BrandMark size={28} />
            <span>Dendrova</span>
          </NavLink>
          <button
            type="button"
            className="side-toggle"
            aria-expanded={open}
            aria-controls="side-nav"
            aria-label={open ? "Cerrar menú" : "Abrir menú"}
            onClick={() => setOpen((v) => !v)}
          >
            <IconMenu />
          </button>
        </div>

        <nav id="side-nav" className="side-nav" aria-label="Principal">
          {projectId !== null && <ProjectNav key={projectId} projectId={projectId} />}

          <div className="side-group">
            <span className="side-label">Espacio de trabajo</span>
            <NavLink to="/proyectos" end className="side-link">
              <IconProjects />
              Proyectos
            </NavLink>
          </div>

          <div className="side-group side-foot">
            <NavLink to="/perfil" className="side-link">
              <IconUser />
              Perfil
            </NavLink>
            {session?.email && <span className="side-email">{session.email}</span>}
            <button
              type="button"
              className="side-link"
              onClick={async () => {
                await signOut();
                navigate("/");
              }}
            >
              <IconLogout />
              Cerrar sesión
            </button>
          </div>
        </nav>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
