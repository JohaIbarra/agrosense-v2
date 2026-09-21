/**
 * Guarda de ruta: sin sesion, se va a /login recordando a donde se queria ir.
 *
 * Es comodidad de navegacion, NO seguridad: quien protege los datos es la API,
 * que exige el token en cada peticion (ADR-006).
 */
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./AuthProvider";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  const location = useLocation();

  if (loading) return <p className="state">Cargando…</p>;
  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
