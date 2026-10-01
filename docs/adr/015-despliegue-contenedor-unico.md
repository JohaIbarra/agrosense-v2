# ADR-015 — Despliegue: un contenedor que sirve API y frontend desde el mismo origen

- **Estado:** Aceptado
- **Fecha:** 2026-09-30
- **Contexto:** fase 9 (deploy). `frontend/vite.config.ts` ya asumía que «en producción el
  frontend se sirve desde el mismo origen que la API», pero nada lo implementaba: la API no
  servía archivos estáticos ni tenía CORS. El proveedor de hosting aún no está elegido, y la
  base (Supabase PostgreSQL) y la autenticación (Supabase Auth) son externas.

- **Opciones consideradas:**
  - *Frontend en un host estático (Vercel/Netlify) + API en otro host.* Rechazada por ahora:
    obliga a CORS con credenciales, dos despliegues, dos dominios y a sincronizar la URL de la
    API en el build.
  - *Servidor web delante (nginx) + API.* Rechazada por YAGNI: un proceso más que configurar sin
    necesidad demostrada a esta escala.
  - **Una imagen Docker: la API sirve el `dist/` del frontend** (elegida). Un servicio, una URL,
    sin CORS; corre en cualquier host de contenedores.

- **Decisión:**
  1. `Dockerfile` multi-etapa: Node compila el frontend (las `VITE_*` públicas entran como
     `--build-arg`); Python 3.12-slim instala el cierre fijado (`requirements.lock.txt`) y el
     paquete, copia `dist/` y corre como usuario sin privilegios.
  2. Si `FRONTEND_DIST` apunta a un directorio existente, la app monta sus archivos y devuelve
     `index.html` para las rutas del SPA que no son de la API. Sin la variable (desarrollo y
     tests) no cambia nada.
  3. El contenedor aplica `alembic upgrade head` antes de servir: el esquema de producción solo
     cambia por migraciones (AGENTS.md).
  4. Secretos (`DATABASE_URL`) solo en tiempo de ejecución, como variables del host; nunca en la
     imagen ni en el repositorio. `SUPABASE_URL` y la clave publicable no son secretos.

- **Consecuencias:**
  - E9 (IA con Ollama) no tiene un Ollama en el host: el endpoint responde con su error
    controlado de transporte hasta que se configure `OLLAMA_URL`.
  - El modelo de mortalidad y el de estancados viajan dentro del paquete (`ml/artifacts/*.json`).
  - Cambiar de host no exige cambios de código.
