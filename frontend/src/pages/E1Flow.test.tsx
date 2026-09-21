/**
 * Flujo de E1 con un proveedor de autenticación falso (sin red):
 * guarda de rutas, inicio de sesión, lista de proyectos y presentación.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { AuthProvider, type AuthClient, type AuthSession } from "../auth/AuthProvider";

function fakeAuth(inicial: AuthSession | null, opciones: Partial<AuthClient> = {}): AuthClient {
  let session = inicial;
  const listeners: ((s: AuthSession | null) => void)[] = [];
  const emit = () => listeners.forEach((l) => l(session));
  return {
    getSession: async () => session,
    onChange: (cb) => {
      listeners.push(cb);
      return () => {};
    },
    signIn: async (email) => {
      session = { accessToken: "tok", email };
      emit();
    },
    signUp: async () => true,
    signOut: async () => {
      session = null;
      emit();
    },
    ...opciones,
  };
}

function renderAt(path: string, auth: AuthClient) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider client={auth}>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

function mockApi(routes: Record<string, unknown>) {
  const spy = vi.fn().mockImplementation((url: string) => {
    const key = Object.keys(routes).find((k) => url.startsWith(k));
    return Promise.resolve({
      ok: key !== undefined,
      status: key !== undefined ? 200 : 404,
      json: async () => (key !== undefined ? routes[key] : { detail: { code: "X" } }),
    });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const PROYECTO = {
  id: 7, project_code: "AGS-2026-0007", name: "Restauración Guayabal", locality: null,
  description: null, created_at: "2026-09-21T00:00:00Z", campaigns_count: 0,
  contract_code: "UPME 04-2014", objective: null, executing_org: null,
  contracting_entity: null, department: "Antioquia", municipality: "La Unión",
  intervention_type: "rehabilitacion", area_ha: null, planted_individuals: null,
  planting_density: null, establishment_date: null, start_date: null, end_date: null,
  legal_framework: null, environmental_authority: null, status: "activo", coordinate_srid: 9377,
};

describe("E1 en la interfaz", () => {
  it("sin sesión, una página privada lleva al inicio de sesión", async () => {
    mockApi({});
    renderAt("/proyectos", fakeAuth(null));
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
  });

  it("la presentación es pública y ofrece entrar", async () => {
    renderAt("/", fakeAuth(null));
    expect(await screen.findByText(/sin hojas de cálculo a mano/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toBeInTheDocument();
  });

  it("la presentación marca lo que aún no existe como en construcción", async () => {
    renderAt("/", fakeAuth(null));
    await screen.findByText(/sin hojas de cálculo a mano/);
    expect(screen.getAllByText("En construcción").length).toBeGreaterThan(0);
  });

  it("iniciar sesión lleva a mis proyectos y la API recibe el token", async () => {
    const spy = mockApi({ "/projects": [PROYECTO] });
    const user = userEvent.setup();
    renderAt("/login", fakeAuth(null));

    await user.type(await screen.findByLabelText("Correo"), "ana@example.com");
    await user.type(screen.getByLabelText("Contraseña"), "secreto123");
    await user.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("Restauración Guayabal")).toBeInTheDocument();
    const llamada = spy.mock.calls.find((c) => String(c[0]).startsWith("/projects"));
    expect(llamada?.[1].headers.Authorization).toBe("Bearer tok");
  });

  it("un error de credenciales se muestra al ingeniero", async () => {
    mockApi({});
    const user = userEvent.setup();
    const auth = fakeAuth(null, {
      signIn: async () => {
        throw new Error("Correo o contraseña incorrectos.");
      },
    });
    renderAt("/login", auth);
    await user.type(await screen.findByLabelText("Correo"), "ana@example.com");
    await user.type(screen.getByLabelText("Contraseña"), "malamala");
    await user.click(screen.getByRole("button", { name: "Entrar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Correo o contraseña incorrectos.");
  });

  it("registrarse con confirmación pendiente lo explica", async () => {
    mockApi({});
    const user = userEvent.setup();
    renderAt("/login?modo=registro", fakeAuth(null));
    await user.type(await screen.findByLabelText("Correo"), "nuevo@example.com");
    await user.type(screen.getByLabelText("Contraseña"), "secreto123");
    await user.click(screen.getByRole("button", { name: "Crear cuenta" }));
    expect(await screen.findByText(/confirme la dirección/)).toBeInTheDocument();
  });

  it("con sesión, la lista muestra los proyectos del ingeniero", async () => {
    mockApi({ "/projects": [PROYECTO] });
    renderAt("/proyectos", fakeAuth({ accessToken: "tok", email: "ana@example.com" }));
    expect(await screen.findByText("Restauración Guayabal")).toBeInTheDocument();
    expect(screen.getByText(/AGS-2026-0007/)).toBeInTheDocument();
    expect(screen.getByText(/La Unión, Antioquia/)).toBeInTheDocument();
  });

  it("sin proyectos invita a crear el primero", async () => {
    mockApi({ "/projects": [] });
    renderAt("/proyectos", fakeAuth({ accessToken: "tok", email: "ana@example.com" }));
    expect(await screen.findByText("Aún no tiene proyectos")).toBeInTheDocument();
  });

  it("la ficha sin monitoreos lo dice en vez de mostrar una tabla vacía", async () => {
    mockApi({ "/projects/7/monitorings": [], "/projects/7": PROYECTO });
    renderAt("/proyectos/7", fakeAuth({ accessToken: "tok", email: "ana@example.com" }));
    expect(await screen.findByText(/Aún no hay monitoreos cargados/)).toBeInTheDocument();
    expect(screen.getByText("Rehabilitación")).toBeInTheDocument();
  });

  it("salir cierra la sesión y vuelve a la presentación", async () => {
    mockApi({ "/projects": [] });
    const user = userEvent.setup();
    renderAt("/proyectos", fakeAuth({ accessToken: "tok", email: "ana@example.com" }));
    await user.click(await screen.findByRole("button", { name: "Salir" }));
    await waitFor(() => expect(screen.getByText(/sin hojas de cálculo a mano/)).toBeInTheDocument());
  });

  it("la ruta vieja /analytics lleva al referente", async () => {
    mockApi({});
    renderAt("/analytics", fakeAuth(null));
    // sin sesión, el referente también pide iniciar sesión
    expect(await screen.findByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
  });
});
