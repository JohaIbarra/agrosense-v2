/// <reference types="node" />
import react from "@vitejs/plugin-react";
// `defineConfig` de vitest/config y no de vite: es la que conoce la clave
// `test`. Con la de vite, la config de pruebas no tipa.
import { defineConfig } from "vitest/config";

// El backend corre en :8000 (uvicorn). El proxy evita configurar CORS en
// FastAPI solo para el desarrollo local: en produccion el frontend se sirve
// desde el mismo origen que la API.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
  },
});
