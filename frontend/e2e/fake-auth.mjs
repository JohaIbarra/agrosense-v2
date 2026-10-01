/**
 * Supabase Auth FALSO, solo para las pruebas E2E (nunca en produccion).
 *
 * Por que existe: el E2E debe recorrer el camino real de la sesion —el
 * frontend inicia sesion con supabase-js y el backend verifica el JWT contra
 * un JWKS (ADR-006)— sin crear cuentas en el proyecto Supabase real. Este
 * servidor implementa el minimo de GoTrue que usa la app (signup, token por
 * contrasena, logout, user) y publica su JWKS. Las claves se generan en cada
 * arranque y los usuarios viven en memoria.
 */
import { createServer } from "node:http";
import { createPrivateKey, generateKeyPairSync, randomUUID, sign } from "node:crypto";

const PORT = Number(process.env.FAKE_AUTH_PORT ?? 54321);
const BASE = `http://127.0.0.1:${PORT}`;
const ISSUER = `${BASE}/auth/v1`;
const KID = "e2e-key";

const { privateKey, publicKey } = generateKeyPairSync("ec", { namedCurve: "P-256" });
const jwk = { ...publicKey.export({ format: "jwk" }), kid: KID, alg: "ES256", use: "sig" };
const users = new Map(); // email -> { id, password }

const b64url = (buf) => Buffer.from(buf).toString("base64url");

function jwt(user) {
  const now = Math.floor(Date.now() / 1000);
  const header = b64url(JSON.stringify({ alg: "ES256", typ: "JWT", kid: KID }));
  const payload = b64url(
    JSON.stringify({
      sub: user.id, email: user.email, aud: "authenticated", role: "authenticated",
      iss: ISSUER, iat: now, exp: now + 3600,
    }),
  );
  const sig = sign("sha256", Buffer.from(`${header}.${payload}`), {
    key: createPrivateKey(privateKey.export({ format: "pem", type: "pkcs8" })),
    dsaEncoding: "ieee-p1363",
  });
  return `${header}.${payload}.${b64url(sig)}`;
}

function session(user) {
  const expires_in = 3600;
  return {
    access_token: jwt(user), token_type: "bearer", expires_in,
    expires_at: Math.floor(Date.now() / 1000) + expires_in,
    refresh_token: `${user.id}:${randomUUID()}`,
    user: { id: user.id, aud: "authenticated", role: "authenticated", email: user.email,
            email_confirmed_at: new Date().toISOString(), app_metadata: {}, user_metadata: {},
            created_at: new Date().toISOString() },
  };
}

function send(res, status, body) {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
  });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

const err = (res, status, msg) => send(res, status, { error: msg, error_description: msg, msg });

createServer(async (req, res) => {
  if (req.method === "OPTIONS") return send(res, 204);
  const url = new URL(req.url, BASE);
  let body = {};
  if (req.method === "POST") {
    let raw = "";
    for await (const chunk of req) raw += chunk;
    body = raw ? JSON.parse(raw) : {};
  }
  const path = url.pathname;
  if (path === "/auth/v1/.well-known/jwks.json") return send(res, 200, { keys: [jwk] });
  if (path === "/auth/v1/signup" && req.method === "POST") {
    if (users.has(body.email)) return err(res, 422, "User already registered");
    const user = { id: randomUUID(), email: body.email, password: body.password };
    users.set(body.email, user);
    return send(res, 200, session(user));
  }
  if (path === "/auth/v1/token" && url.searchParams.get("grant_type") === "password") {
    const user = users.get(body.email);
    if (!user || user.password !== body.password) return err(res, 400, "Invalid login credentials");
    return send(res, 200, session(user));
  }
  if (path === "/auth/v1/token" && url.searchParams.get("grant_type") === "refresh_token") {
    const id = String(body.refresh_token ?? "").split(":")[0];
    const user = [...users.values()].find((u) => u.id === id);
    return user ? send(res, 200, session(user)) : err(res, 400, "Invalid Refresh Token");
  }
  if (path === "/auth/v1/logout") return send(res, 204);
  if (path === "/auth/v1/user") {
    const token = (req.headers.authorization ?? "").replace("Bearer ", "");
    const sub = token ? JSON.parse(Buffer.from(token.split(".")[1], "base64url")).sub : null;
    const user = [...users.values()].find((u) => u.id === sub);
    return user ? send(res, 200, session(user).user) : err(res, 401, "invalid JWT");
  }
  if (path === "/health") return send(res, 200, { ok: true });
  return err(res, 404, `fake-auth: ruta no implementada ${req.method} ${path}`);
}).listen(PORT, "127.0.0.1", () => console.log(`fake-auth en ${BASE}`));
