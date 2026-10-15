/**
 * Página de presentación: qué es Dendrova y por dónde empezar.
 *
 * Solo promete lo que existe: cada capacidad listada está implementada. Un
 * ingeniero que entra buscando algo anunciado y no lo encuentra pierde la
 * confianza en todo lo demás.
 */
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { BrandMark } from "../components/icons";

const CAPACIDADES = [
  {
    titulo: "Carga del Excel de campo",
    texto:
      "Una fila por árbol, de un monitoreo o acumulado: Dendrova reconoce cada monitoreo, predio, parcela y árbol, y avisa lo que no cuadra.",
  },
  {
    titulo: "Análisis de cada monitoreo",
    texto:
      "Composición, altura, copa, supervivencia, estado fitosanitario, edades y DAP por especie, diseño, cobertura y predio, con reporte .xlsx.",
  },
  {
    titulo: "Comparación entre monitoreos",
    texto:
      "Quién murió, quién creció y quién se quedó igual entre M3 y M4, por predio, especie y parcela.",
  },
  {
    titulo: "Árboles a revisar en campo",
    texto:
      "Riesgo de estancarse y de morir por árbol, con la confiabilidad del modelo declarada y sin promesas que los datos no respaldan.",
  },
  {
    titulo: "Mapa y verdor satelital",
    texto:
      "Cada árbol sobre imagen satelital u ortofoto propia, con su historial, y la serie NDVI de Sentinel-2 por predio.",
  },
  {
    titulo: "Tus proyectos, separados",
    texto: "Crea un proyecto con solo su nombre y organiza ahí tus monitoreos. Solo tú ves los tuyos.",
  },
];

export function LandingPage() {
  const { session } = useAuth();

  return (
    <>
      <header className="public-bar">
        <Link to="/" className="brand">
          <BrandMark size={30} />
          Dendrova
        </Link>
        {session ? (
          <Link to="/proyectos" className="btn btn-ghost">
            Mis proyectos
          </Link>
        ) : (
          <Link to="/login" className="btn btn-ghost">
            Iniciar sesión
          </Link>
        )}
      </header>

      <div className="landing">
        <section className="landing-hero">
          <p className="eyebrow">Monitoreo de restauración ecológica</p>
          <h1>El seguimiento de tu restauración ecológica, sin hojas de cálculo a mano.</h1>
          <p className="lead">
            Carga los monitoreos de campo de tus proyectos y obtén el análisis que hoy haces pivote
            por pivote: especies, parcelas, crecimiento, supervivencia y su evolución en el tiempo.
          </p>
          <div className="cta">
            {session ? (
              <Link to="/proyectos" className="btn btn-primary">
                Ir a mis proyectos
              </Link>
            ) : (
              <>
                <Link to="/login?modo=registro" className="btn btn-primary">
                  Crear cuenta
                </Link>
                <Link to="/login" className="btn btn-ghost">
                  Iniciar sesión
                </Link>
              </>
            )}
          </div>
        </section>

        <section className="capacidades" aria-label="Qué hace Dendrova">
          {CAPACIDADES.map((c) => (
            <article key={c.titulo} className="card capacidad">
              <h2>{c.titulo}</h2>
              <p>{c.texto}</p>
            </article>
          ))}
        </section>

        <footer className="page-foot muted">
          Dendrova calcula; el borrador de informe con IA, donde está disponible, solo redacta sobre
          resultados ya calculados.
        </footer>
      </div>
    </>
  );
}
