/**
 * Raíz de la aplicación.
 *
 * Una sola ruta por ahora (`/analytics`) y sin react-router: el slice 5 es la
 * primera pantalla del frontend. Cuando el slice 4 traiga la suya, entra el
 * router — no antes (AGENTS.md: "Prefer simple designs over unnecessary
 * abstractions").
 */
import { AnalyticsPage } from "./pages/AnalyticsPage";

export function App() {
  return <AnalyticsPage />;
}
