# Imagen unica de AgroSense (ADR-015): la API sirve tambien el frontend
# compilado, desde el mismo origen (sin CORS). Funciona en cualquier host de
# contenedores (Render, Railway, Fly.io, Cloud Run...).
#
#   docker build \
#     --build-arg VITE_SUPABASE_URL=https://<ref>.supabase.co \
#     --build-arg VITE_SUPABASE_PUBLISHABLE_KEY=<clave publicable> \
#     -t agrosense .
#   docker run -p 8000:8000 -e DATABASE_URL=... -e SUPABASE_URL=... agrosense
#
# Las VITE_* son PUBLICAS por diseno (la clave publicable de Supabase): se
# hornean en el bundle. Los secretos (DATABASE_URL) solo entran en tiempo de
# ejecucion, nunca en la imagen.

FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/frontend/dist PORT=8000
WORKDIR /app/backend
COPY backend/requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY backend/ ./
RUN pip install --no-cache-dir --no-deps . && useradd --create-home agrosense
COPY --from=frontend /app/frontend/dist /app/frontend/dist
USER agrosense
EXPOSE 8000
# Migraciones antes de servir: el esquema solo cambia por Alembic (AGENTS.md).
CMD ["sh", "-c", "alembic upgrade head && uvicorn agrosense.adapters.api.app:create_app --factory --host 0.0.0.0 --port ${PORT}"]
