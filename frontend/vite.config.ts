/// <reference types="node" />
import react from "@vitejs/plugin-react";
// `defineConfig` de vitest/config y no de vite: es la que conoce la clave
// `test`. Con la de vite, la config de pruebas no tipa.
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// El backend corre en :8000 (uvicorn). El proxy evita configurar CORS en
// FastAPI solo para el desarrollo local: en produccion el frontend se sirve
// desde el mismo origen que la API.
const env = loadEnv(process.env.NODE_ENV ?? "development", process.cwd(), "");
const apiTarget = process.env.VITE_API_TARGET ?? env.VITE_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Las rutas de proyectos no llevan /api (deuda del slice 2). Las paginas
    // del frontend usan /proyectos, en espanol, asi que no chocan con /projects.
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/projects": { target: apiTarget, changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
    // e2e/ es de Playwright (npm run e2e), no de vitest.
    exclude: ["node_modules", "dist", "e2e"],
  },
});
