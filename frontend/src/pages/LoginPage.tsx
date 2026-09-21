/**
 * Inicio de sesión y registro con correo y contraseña (Supabase Auth).
 *
 * La contraseña va directo a Supabase: el backend de AgroSense nunca la ve.
 */
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { useAuth } from "../auth/AuthProvider";

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
      <form className="card auth-card" onSubmit={onSubmit}>
        <Link to="/" className="brand">
          AgroSense
        </Link>
        <h1>{registro ? "Crear cuenta" : "Iniciar sesión"}</h1>

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
  );
}
