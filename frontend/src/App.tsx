/**
 * Rutas de la aplicación.
 *
 *   /                       presentación (pública)
 *   /login                  inicio de sesión y registro (pública)
 *   /proyectos              mis proyectos
 *   /proyectos/nuevo        crear proyecto
 *   /proyectos/:id          ficha del proyecto
 *   /proyectos/:id/editar   editar proyecto
 *   /referente              referente científico (antes /analytics)
 *   /perfil                 perfil del ingeniero
 *
 * Las rutas en español no chocan con la API (/projects, /api/...), que el
 * proxy de desarrollo reenvía al backend.
 */
import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import { RequireAuth } from "./auth/RequireAuth";
import { AppLayout } from "./components/AppLayout";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ProjectFormPage } from "./pages/ProjectFormPage";
import { ProjectsPage } from "./pages/ProjectsPage";

function Privada({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AppLayout>{children}</AppLayout>
    </RequireAuth>
  );
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/proyectos" element={<Privada><ProjectsPage /></Privada>} />
      <Route path="/proyectos/nuevo" element={<Privada><ProjectFormPage /></Privada>} />
      <Route path="/proyectos/:id" element={<Privada><ProjectDetailPage /></Privada>} />
      <Route path="/proyectos/:id/editar" element={<Privada><ProjectFormPage /></Privada>} />
      <Route path="/referente" element={<Privada><AnalyticsPage /></Privada>} />
      <Route path="/perfil" element={<Privada><ProfilePage /></Privada>} />
      <Route path="/analytics" element={<Navigate to="/referente" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
