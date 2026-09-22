/**
 * Marco de las páginas autenticadas: navegación y cierre de sesión.
 */
import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

export function AppLayout({ children }: { children: ReactNode }) {
  const { session, signOut } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/proyectos" className="brand">
          AgroSense
        </NavLink>
        <nav className="topnav" aria-label="Principal">
          <NavLink to="/proyectos">Proyectos</NavLink>
          <NavLink to="/perfil">Perfil</NavLink>
        </nav>
        <div className="topbar-user">
          <span className="muted">{session?.email}</span>
          <button
            type="button"
            className="btn btn-ghost"
            onClick={async () => {
              await signOut();
              navigate("/");
            }}
          >
            Salir
          </button>
        </div>
      </header>
      <main>{children}</main>
    </div>
  );
}
