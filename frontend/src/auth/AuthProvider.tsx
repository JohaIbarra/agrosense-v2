/**
 * Estado de la sesion del ingeniero (E1).
 *
 * Una sola responsabilidad: saber si hay sesion, y ofrecer entrar, registrarse
 * y salir. Conecta ademas la capa HTTP: cada peticion a la API lleva el token
 * vigente, y un 401 (sesion vencida o revocada) cierra la sesion local.
 *
 * El cliente de autenticacion se INYECTA (`client`) para poder probar la UI sin
 * red; en la app real es el de Supabase.
 */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { configureHttp } from "../api/http";
import { supabase } from "./supabase";

export interface AuthSession {
  accessToken: string;
  email: string | null;
}

/** Lo minimo que la UI necesita del proveedor de autenticacion. */
export interface AuthClient {
  getSession(): Promise<AuthSession | null>;
  onChange(callback: (session: AuthSession | null) => void): () => void;
  signIn(email: string, password: string): Promise<void>;
  /** Devuelve `true` si el proveedor pide confirmar el correo antes de entrar. */
  signUp(email: string, password: string): Promise<boolean>;
  signOut(): Promise<void>;
}

interface AuthState {
  session: AuthSession | null;
  loading: boolean;
  configured: boolean;
  signIn: AuthClient["signIn"];
  signUp: AuthClient["signUp"];
  signOut: AuthClient["signOut"];
}

const AuthContext = createContext<AuthState | null>(null);

/** Adaptador del cliente de Supabase a `AuthClient`. */
export function supabaseAuthClient(): AuthClient | null {
  if (!supabase) return null;
  const toSession = (s: { access_token: string; user?: { email?: string } } | null) =>
    s ? { accessToken: s.access_token, email: s.user?.email ?? null } : null;
  return {
    async getSession() {
      const { data } = await supabase!.auth.getSession();
      return toSession(data.session);
    },
    onChange(callback) {
      const { data } = supabase!.auth.onAuthStateChange((_event, s) => callback(toSession(s)));
      return () => data.subscription.unsubscribe();
    },
    async signIn(email, password) {
      const { error } = await supabase!.auth.signInWithPassword({ email, password });
      if (error) throw new Error(traducirError(error.message));
    },
    async signUp(email, password) {
      const { data, error } = await supabase!.auth.signUp({ email, password });
      if (error) throw new Error(traducirError(error.message));
      return data.session === null;
    },
    async signOut() {
      await supabase!.auth.signOut();
    },
  };
}

/** Mensajes de Supabase Auth en lenguaje del ingeniero. */
function traducirError(message: string): string {
  const m = message.toLowerCase();
  if (m.includes("invalid login credentials")) return "Correo o contraseña incorrectos.";
  if (m.includes("email not confirmed"))
    return "Confirme su correo antes de entrar: revise su bandeja de entrada.";
  if (m.includes("already registered")) return "Ya existe una cuenta con ese correo.";
  if (m.includes("password should be at least"))
    return "La contraseña es demasiado corta (mínimo 6 caracteres).";
  if (m.includes("rate limit")) return "Demasiados intentos. Espere unos minutos.";
  return message;
}

export function AuthProvider({
  children,
  client,
}: {
  children: ReactNode;
  client?: AuthClient | null;
}) {
  const auth = useMemo(() => (client === undefined ? supabaseAuthClient() : client), [client]);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(auth !== null);

  useEffect(() => {
    if (!auth) return;
    let vivo = true;
    auth.getSession().then((s) => {
      if (vivo) {
        setSession(s);
        setLoading(false);
      }
    });
    const unsubscribe = auth.onChange((s) => vivo && setSession(s));
    configureHttp({
      getAccessToken: async () => (await auth.getSession())?.accessToken ?? null,
      onUnauthorized: () => {
        void auth.signOut();
      },
    });
    return () => {
      vivo = false;
      unsubscribe();
    };
  }, [auth]);

  const value = useMemo<AuthState>(
    () => ({
      session,
      loading,
      configured: auth !== null,
      signIn: (e, p) => auth!.signIn(e, p),
      signUp: (e, p) => auth!.signUp(e, p),
      signOut: () => auth!.signOut(),
    }),
    [session, loading, auth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth fuera de <AuthProvider>");
  return ctx;
}
