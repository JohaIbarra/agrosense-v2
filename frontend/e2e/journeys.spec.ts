/**
 * Recorridos criticos de AgroSense (AGENTS.md §Testing: "Critical user
 * journeys require E2E tests"). Corren contra la API real (SQLite nueva) y un
 * Supabase Auth falso: ver playwright.config.ts.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const FIXTURE = path.join(path.dirname(fileURLToPath(import.meta.url)), ".tmp", "campo.xlsx");
const PASSWORD = "clave-e2e-123";

async function signUp(page: Page, email: string) {
  await page.goto("/login?modo=registro");
  await page.getByLabel("Correo").fill(email);
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByRole("button", { name: "Crear cuenta" }).click();
  await expect(page.getByRole("heading", { name: "Mis proyectos" })).toBeVisible();
}

async function createProject(page: Page, name: string): Promise<string> {
  await page.getByRole("link", { name: /nuevo proyecto|crear.*proyecto/i }).first().click();
  await page.getByLabel("Nombre del proyecto *").fill(name);
  await page.locator("form").getByRole("button", { name: /crear|guardar/i }).click();
  await expect(page.getByRole("heading", { level: 1, name })).toBeVisible();
  return page.url();
}

test("ingeniero: registro → proyecto → carga → análisis → comparación → salir y volver", async ({
  page,
}) => {
  const email = `ana-${Date.now()}@e2e.test`;
  await signUp(page, email);
  const projectUrl = await createProject(page, "Restauración Guayabal E2E");

  // Carga del monitoreo con su fecha
  await page.getByLabel("Archivo Excel (.xlsx)").setInputFiles(FIXTURE);
  await page.getByLabel("Fecha del monitoreo").fill("2023-10-03");
  await page.getByRole("button", { name: "Cargar y analizar" }).click();
  await expect(page.getByRole("link", { name: "Ver análisis de M3" })).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByRole("link", { name: "Ver análisis de M1" })).toBeVisible();

  // Análisis exploratorio: las pestañas se recorren sin errores
  await page.getByRole("link", { name: "Ver análisis de M3" }).click();
  await expect(page.getByRole("heading", { name: "Análisis del monitoreo M3" })).toBeVisible();
  const tabs = page.getByRole("tablist", { name: "Análisis" }).getByRole("tab");
  const count = await tabs.count();
  expect(count).toBeGreaterThan(3);
  // E4: la comparación temporal es una sección más del análisis (ADR-008)
  await expect(tabs.filter({ hasText: /compar|M2.*M3|cambio/i }).first()).toBeVisible();
  for (let i = 0; i < count; i++) {
    await tabs.nth(i).click();
    await expect(tabs.nth(i)).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("alert")).toHaveCount(0);
  }

  // La sesión persiste al recargar y se cierra al salir
  await page.reload();
  await expect(page.getByRole("heading", { name: "Análisis del monitoreo M3" })).toBeVisible();
  await page.getByRole("button", { name: /salir|cerrar sesión/i }).click();
  await page.goto(projectUrl);
  await expect(page).toHaveURL(/\/login/);

  // Volver a entrar con la misma cuenta recupera el proyecto
  await page.getByLabel("Correo").fill(email);
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Restauración Guayabal E2E" })).toBeVisible();
});

test("autorización: un ingeniero no ve ni abre el proyecto de otro", async ({ browser }) => {
  const a = await browser.newPage();
  await signUp(a, `duenia-${Date.now()}@e2e.test`);
  const projectUrl = await createProject(a, "Proyecto privado E2E");
  await a.close();

  const b = await browser.newPage();
  await signUp(b, `intruso-${Date.now()}@e2e.test`);
  await expect(b.getByText("Proyecto privado E2E")).toHaveCount(0);
  await b.goto(projectUrl);
  await expect(b.getByRole("heading", { name: "No se encontró el proyecto" })).toBeVisible();
  await b.close();
});

test("login con contraseña incorrecta muestra el error en español", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Correo").fill("nadie@e2e.test");
  await page.getByLabel("Contraseña").fill("incorrecta");
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page.getByRole("alert")).toHaveText("Correo o contraseña incorrectos.");
});
