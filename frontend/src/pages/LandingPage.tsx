/**
 * Página de presentación: qué es AgroSense y por dónde empezar.
 *
 * Solo promete lo que existe. Lo que está en construcción se marca como tal:
 * un ingeniero que entra buscando la carga de Excel y no la encuentra pierde
 * la confianza en todo lo demás.
 */
import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

const CAPACIDADES = [
  {
    titulo: "Tus proyectos, separados",
    texto:
      "Cada proyecto con su contrato, predios, intervención y marco legal. Solo tú ves los tuyos.",
    estado: "Disponible",
  },
  {
    titulo: "Referente científico",
    texto:
      "Qué especies se estancan o mueren más que el promedio, estimado con modelos mixtos sobre 856 árboles monitoreados cuatro veces.",
    estado: "Disponible",
  },
  {
    titulo: "Carga del Excel de monitoreo",
    texto:
      "Sube el Excel de campo — de un monitoreo o acumulado — y AgroSense reconoce cada monitoreo, parcela y árbol.",
    estado: "En construcción",
  },
  {
    titulo: "Análisis y comparación entre monitoreos",
    texto:
      "Composición, alturas, supervivencia y fitosanidad desde el primer monitoreo; crecimiento y mortalidad de M1 → M2 → M3.",
    estado: "En construcción",
  },
];

export function LandingPage() {
  const { session } = useAuth();

  return (
    <div className="landing">
      <header className="landing-hero">
        <p className="eyebrow">AgroSense</p>
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
              <Link to="/login" className="btn btn-primary">
                Iniciar sesión
              </Link>
              <Link to="/login?modo=registro" className="btn btn-ghost">
                Crear cuenta
              </Link>
            </>
          )}
        </div>
      </header>

      <section className="capacidades" aria-label="Qué hace AgroSense">
        {CAPACIDADES.map((c) => (
          <article key={c.titulo} className="card capacidad">
            <span className={c.estado === "Disponible" ? "badge badge-sig" : "badge badge-nosig"}>
              {c.estado}
            </span>
            <h2>{c.titulo}</h2>
            <p>{c.texto}</p>
          </article>
        ))}
      </section>

      <footer className="page-foot muted">
        AgroSense calcula; los modelos de lenguaje, cuando lleguen, solo redactan sobre resultados
        ya calculados.
      </footer>
    </div>
  );
}
