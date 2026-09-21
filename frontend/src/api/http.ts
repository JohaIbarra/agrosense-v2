/**
 * Transporte HTTP comun. Ningun componente hace `fetch` (AGENTS.md).
 *
 * Centraliza lo que, duplicado, acaba divergiendo:
 *  - como se construye la URL;
 *  - el token de sesion (E1): cada peticion lleva `Authorization: Bearer`;
 *  - que hacer ante un 401 (sesion vencida): avisar a quien gestiona la sesion;
 *  - como se traduce un error del backend a algo que la UI puede mostrar.
 *
 * El token y la reaccion al 401 se INYECTAN (`configureHttp`) en vez de
 * importar el cliente de Supabase aqui: asi esta capa se prueba sin red.
 */

/** Error con el `code` del contrato, para que la UI distinga los casos. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export type Query = Record<string, string | number | undefined | null>;

type TokenProvider = () => Promise<string | null>;

let tokenProvider: TokenProvider = async () => null;
let onUnauthorized: () => void = () => {};

export function configureHttp(options: {
  getAccessToken?: TokenProvider;
  onUnauthorized?: () => void;
}): void {
  if (options.getAccessToken) tokenProvider = options.getAccessToken;
  if (options.onUnauthorized) onUnauthorized = options.onUnauthorized;
}

export function buildUrl(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export async function request<T>(
  path: string,
  options: {
    method?: string;
    query?: Query;
    body?: unknown;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = await tokenProvider();
  if (token) headers.Authorization = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (options.body instanceof FormData) {
    body = options.body; // el navegador pone el boundary del multipart
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body,
    signal: options.signal,
  });

  if (!response.ok) {
    // El backend siempre responde {detail: {code, message}}; si algo se cuela
    // sin esa forma (un 502 del proxy, por ejemplo), no se muestra el cuerpo
    // crudo al usuario.
    let code = "UNKNOWN";
    let message = `La petición falló (HTTP ${response.status}).`;
    try {
      const data = await response.json();
      const detail = data?.detail;
      if (detail?.code) code = detail.code;
      if (detail?.message) message = detail.message;
      // Errores de validacion de FastAPI (422 sin nuestra forma)
      if (Array.isArray(detail) && detail[0]?.msg) {
        code = "VALIDATION";
        message = `Revise el campo «${detail[0].loc?.slice(-1)[0] ?? ""}»: ${detail[0].msg}`;
      }
    } catch {
      /* respuesta sin JSON: se conserva el mensaje genérico */
    }
    if (response.status === 401) onUnauthorized();
    throw new ApiError(response.status, code, message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
