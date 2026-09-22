/**
 * Rutas de la aplicación.
 *
 *   /                       presentación (pública)
 *   /login                  inicio de sesión y registro (pública)
 *   /proyectos              mis proyectos
 *   /proyectos/nuevo        crear proyecto
 *   /proyectos/:id          ficha del proyecto
 *   /proyectos/:id/editar   editar proyecto
 *   /proyectos/:id/monitoreos/:numero   análisis del monitoreo (E3)
 *   /proyectos/:id/mapa     mapa del predio (E6, carga diferida)
 *   /proyectos/:id/ndvi     verdor del predio (E10a)
 *   /referente              referente científico (antes /analytics)
 *   /perfil                 perfil del ingeniero
 *
 * Las rutas en español no chocan con la API (/projects, /api/...), que el
 * proxy de desarrollo reenvía al backend.
 */
import { Navigate, Route, Routes } from "react-router-dom";
import { Suspense, lazy, type ReactNode } from "react";

import { RequireAuth } from "./auth/RequireAuth";
import { AppLayout } from "./components/AppLayout";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { LandingPage } from "./pages/LandingPage";
import { LoginPage } from "./pages/LoginPage";
import { IndexPage } from "./pages/IndexPage";
import { MonitoringAnalysisPage } from "./pages/MonitoringAnalysisPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ProjectFormPage } from "./pages/ProjectFormPage";
import { ProjectsPage } from "./pages/ProjectsPage";

// Leaflet y el mapa solo se descargan cuando alguien abre el mapa: son ~150 kB
// que no tienen por qué entrar en la ruta de proyectos (deuda #O).
const MapPage = lazy(() =>
  import("./map/MapPage").then((m) => ({ default: m.MapPage })),
);

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
      <Route
        path="/proyectos/:id/monitoreos/:numero"
        element={<Privada><MonitoringAnalysisPage /></Privada>}
      />
      <Route
        path="/proyectos/:id/mapa"
        element={
          <Privada>
            <Suspense fallback={<p className="state">Cargando el mapa…</p>}>
              <MapPage />
            </Suspense>
          </Privada>
        }
      />
      <Route path="/proyectos/:id/ndvi" element={<Privada><IndexPage /></Privada>} />
      <Route path="/referente" element={<Privada><AnalyticsPage /></Privada>} />
      <Route path="/perfil" element={<Privada><ProfilePage /></Privada>} />
      <Route path="/analytics" element={<Navigate to="/referente" replace />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
