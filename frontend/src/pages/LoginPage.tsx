/**
 * Inicio de sesión y registro con correo y contraseña (Supabase Auth).
 *
 * La contraseña va directo a Supabase: el backend de Dendrova nunca la ve.
 */
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";
import { BrandMark, IconCheck } from "../components/icons";

export function LoginPage() {
  const { session, configured, signIn, signUp } = useAuth();
  const [params] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [registro, setRegistro] = useState(params.get("modo") === "registro");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const destino = (location.state as { from?: string } | null)?.from ?? "/proyectos";

  if (session) return <Navigate to={destino} replace />;

  if (!configured) {
    return (
      <div className="state state-error">
        <h2>Inicio de sesión no configurado</h2>
        <p>
          Faltan <code>VITE_SUPABASE_URL</code> y <code>VITE_SUPABASE_PUBLISHABLE_KEY</code> en{" "}
          <code>frontend/.env.local</code> (ver <code>.env.example</code>).
        </p>
      </div>
    );
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setAviso(null);
    setEnviando(true);
    try {
      if (registro) {
        const pideConfirmacion = await signUp(email, password);
        if (pideConfirmacion) {
          setAviso("Cuenta creada. Revise su correo y confirme la dirección para poder entrar.");
          setRegistro(false);
        } else {
          navigate(destino, { replace: true });
        }
      } else {
        await signIn(email, password);
        navigate(destino, { replace: true });
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="auth-page">
      <section className="auth-aside" aria-label="Dendrova">
        <svg className="auth-rings" viewBox="0 0 200 200" fill="none" aria-hidden="true">
          <circle cx="100" cy="100" r="96" stroke="#24493A" strokeWidth="1.2" />
          <circle cx="103" cy="98" r="84" stroke="#24493A" strokeWidth="1.1" />
          <circle cx="106" cy="96" r="70" stroke="#2B5544" />
          <circle cx="108" cy="95" r="57" stroke="#2B5544" />
          <circle cx="110" cy="94" r="45" stroke="#336352" />
          <circle cx="112" cy="93" r="33" stroke="#336352" />
          <circle cx="113" cy="92" r="22" stroke="#3D7360" />
          <circle cx="114" cy="92" r="12" stroke="#3D7360" />
          <circle cx="114.5" cy="92" r="4" fill="#3D7360" />
        </svg>
        <Link to="/" className="brand">
          <BrandMark size={32} />
          Dendrova
        </Link>
        <div>
          <h2>Monitoreo de restauración ecológica, árbol por árbol.</h2>
          <p>
            Carga el Excel de campo y obtén supervivencia, crecimiento, estado fitosanitario y
            riesgo de mortalidad por árbol, parcela y predio.
          </p>
          <ul>
            <li>
              <IconCheck />
              Análisis dasométrico y fitosanitario por monitoreo
            </li>
            <li>
              <IconCheck />
              Árboles priorizados para la próxima visita de campo
            </li>
            <li>
              <IconCheck />
              Mapa satelital y verdor (NDVI) de cada predio
            </li>
          </ul>
        </div>
        <p className="auth-note">
          Cada cifra es trazable al archivo y a la versión del cálculo que la produjo.
        </p>
      </section>

      <div className="auth-main">
        <form className="auth-card" onSubmit={onSubmit}>
          <div>
            <h1>{registro ? "Crear cuenta" : "Iniciar sesión"}</h1>
            <p className="subtitle">
              {registro
                ? "Crea tu cuenta con correo y contraseña."
                : "Entra con tu correo para ver tus proyectos."}
            </p>
          </div>

          <label className="field">
            <span>Correo</span>
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Contraseña</span>
            <input
              type="password"
              autoComplete={registro ? "new-password" : "current-password"}
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          {aviso && <p className="form-ok">{aviso}</p>}

          <button type="submit" className="btn btn-primary" disabled={enviando}>
            {enviando ? "Enviando…" : registro ? "Crear cuenta" : "Entrar"}
          </button>
          <button type="button" className="link-button" onClick={() => setRegistro(!registro)}>
            {registro ? "¿Ya tiene cuenta? Inicie sesión" : "¿No tiene cuenta? Créela"}
          </button>
        </form>
      </div>
    </div>
  );
}
