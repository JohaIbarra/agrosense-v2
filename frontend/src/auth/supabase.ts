/**
 * Cliente de Supabase — SOLO para iniciar y cerrar sesion (E1, ADR-006).
 *
 * Los datos nunca se leen con este cliente: el unico camino a los datos es la
 * API de AgroSense, que verifica el token y aplica la autorizacion. Por eso la
 * clave es la "publishable" (publica por diseño) y las tablas tienen RLS sin
 * politicas: aunque alguien la use directamente, no ve nada.
 */
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

/** `null` si falta la configuracion: la app lo explica en vez de romperse. */
export const supabase: SupabaseClient | null =
  url && key ? createClient(url, key, { auth: { persistSession: true } }) : null;
