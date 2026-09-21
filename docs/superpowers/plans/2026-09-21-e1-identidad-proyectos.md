# Plan E1 — Identidad y proyectos

Fecha: 2026-09-21. Estado: **implementado y verificado** (`docs/verificacion-e1.md`). Origen: `docs/04-vision-producto.md` §9 (E1), decisiones
D3 (Supabase Auth) y D7 (campos del proyecto).

**Objetivo**: un ingeniero inicia sesión, ve **solo sus** proyectos, crea
proyectos con los campos aprobados y entra a cada uno. Ningún ingeniero puede
leer ni escribir el proyecto de otro.

## Decisiones técnicas (delegadas, registradas en ADR-006)

| Decisión | Elección | Por qué |
|---|---|---|
| Verificación del token | JWKS público del proyecto (ES256) con PyJWT | El Auth firma con clave asimétrica (verificado): el backend no guarda ningún secreto |
| Perfil del ingeniero | Tabla `engineers`, `id` = `sub` del token; se crea en la primera petición autenticada | Supabase gestiona usuario y contraseña; AgroSense solo guarda el perfil |
| Proyecto ajeno | **404**, no 403 | No revelar que el proyecto existe |
| `project_code` | Lo **genera el sistema**: `AGS-{año}-{n:04d}`, único global | «Identificador interno único, obligatorio»: si lo asigna AgroSense, siempre existe y nunca choca |
| `name` único | Por **ingeniero**, no global | Dos ingenieros pueden tener «Restauración Guayabal» |
| SRID | `projects.coordinate_srid`, 9377 por defecto | ADR-005: el sistema de coordenadas es del proyecto |
| RLS | Se mantiene **deny-all sin políticas**, de forma deliberada | El único camino a los datos es la API; `supabase-js` en el frontend solo hace login. Cierra la deuda de RLS como decisión |
| Referente científico | También exige sesión | Coherencia: toda la API es para usuarios autenticados |

## Tareas

- **T1** Verificador de tokens (`adapters/auth`) + dependencia
  `get_current_engineer`. Tests con claves EC generadas en el test.
- **T2** Dominio y migración: `engineers`, campos nuevos de `projects`,
  `owner_id` NOT NULL, `project_code`, unicidad `(owner_id, name)`.
- **T3** Casos de uso: crear, listar, obtener, editar proyecto; perfil
  (obtener/editar). Autorización por propietario en `application/`.
- **T4** API: `GET/PUT /api/v1/me`, `GET /projects`, `PATCH /projects/{id}`;
  todas las rutas existentes exigen sesión y propiedad.
- **T5** Frontend: router, sesión con `supabase-js`, página de inicio,
  login/registro, lista de proyectos, crear proyecto, detalle; el referente
  pasa a `/referente`.
- **T6** Verificación: suites, smoke, navegador; `docs/verificacion-e1.md`.

## Criterio de salida

Sin token → 401. Con token de otro ingeniero → 404. Con el propio → acceso.
El flujo inicio → login → crear proyecto → ver proyecto funciona en navegador.
