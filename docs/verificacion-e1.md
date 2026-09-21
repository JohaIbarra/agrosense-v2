# Verificación — E1 · Identidad y proyectos

Fecha: 2026-09-21. Plan: `docs/superpowers/plans/2026-09-21-e1-identidad-proyectos.md`.
Decisión: `docs/adr/006-identidad-y-proyectos.md`.

**Criterio de salida**: sin token → 401; con el de otro ingeniero → 404; con
el propio → acceso. **Cumplido y probado.** El flujo en navegador con una
cuenta real queda pendiente del ingeniero (ver abajo).

## Gates

| # | Gate | Resultado |
|---|---|---|
| 1 | `pytest` local | ✅ 342 passed |
| 2 | `pytest -m supabase` | ✅ 33 passed (dos corridas seguidas) |
| 3 | `ruff check src tests` | ✅ limpio |
| 4 | Frontend: `npm test` | ✅ 52 passed |
| 5 | Frontend: `tsc -b`, `npm run build`, `npm run lint` | ✅ (0 errores; 4 avisos previos de `any` en Recharts) |
| 6 | `pip-audit` del cierre | ✅ sin vulnerabilidades conocidas (tras subir cryptography) |
| 7 | `npm audit --omit=dev` | ✅ 0 vulnerabilidades |
| 8 | Migración `d9a3b7c15e24` en Supabase | ✅ aplicada (0 proyectos antes) |
| 9 | Advisors de seguridad | ✅ sin regresión (`engineers` con RLS sin políticas, como las demás) |

## Autenticación

`tests/auth/test_tokens.py` — el verificador rechaza: token expirado, `iss`
de otro proyecto, audiencia anónima, firma con otra clave, `alg=none`,
confusión HS256 con la clave pública, token sin `sub` y basura. La clave de
prueba es EC P-256, el mismo tipo que usa el Auth del proyecto.

`tests/api/test_e1_auth.py`:
- **13 rutas** devuelven 401 sin token, con `WWW-Authenticate: Bearer`.
- Token malo, vencido, de otro proyecto o sin prefijo: mismo 401 y **mismo
  mensaje** (no distinguirlos solo ayuda a quien prueba tokens).
- Proyecto de otro ingeniero: **404 en las 6 rutas** que lo tocan, incluida
  la carga de un Excel; el propietario lo sigue viendo intacto.
- La lista devuelve solo los proyectos propios.

Contra el servidor real (uvicorn + `SUPABASE_URL`, verificando contra el
JWKS del proyecto): `GET /projects` sin token → 401; con un token falso →
401; ambos directo y a través del proxy de Vite.

## Proyectos

- `project_code` `AGS-{año}-{id:04d}` asignado por el sistema; no editable.
- Nombre único por ingeniero: dos ingenieros pueden repetirlo; el mismo no.
- Reglas del dominio → 422 `INVALID_PROJECT`: tipo de intervención y marco
  legal fuera de vocabulario, área 0, individuos negativos, fin antes que el
  inicio. El PATCH valida contra lo **ya guardado**, no solo lo enviado.
- `GET /api/v1/catalogs` entrega los vocabularios del dominio: el formulario
  no los duplica.

## Frontend

Rutas: `/` (presentación), `/login`, `/proyectos`, `/proyectos/nuevo`,
`/proyectos/:id`, `/proyectos/:id/editar`, `/referente`, `/perfil`.

`src/pages/E1Flow.test.tsx` (proveedor de autenticación falso, sin red):
página privada sin sesión → login; login lleva a los proyectos y **la API
recibe el token**; error de credenciales visible; registro con confirmación
pendiente explicado; lista, lista vacía, ficha sin monitoreos; salir vuelve
a la presentación. La presentación marca como «En construcción» lo que aún
no existe (carga de Excel, análisis).

## Pendiente del ingeniero

1. **Crear su cuenta y entrar** en `http://localhost:5173`. No se hizo en
   esta verificación: crear cuentas o escribir contraseñas no es algo que
   deba hacer el asistente.
2. **Configurar la URL del sitio** en Supabase (Authentication → URL
   Configuration → Site URL = `http://localhost:5173`), para que el enlace
   de confirmación de correo lleve a la app.
3. La revisión visual en navegador quedó pendiente: la extensión de Chrome
   no estaba conectada tras el reinicio.

## Hallazgo operativo

El `getaddrinfo` intermitente reapareció en racha: tumbó dos corridas del
smoke (siempre en la primera conexión, lo que arrastra a todos los tests) y
un `pip install` contra PyPI. Que afecte también a PyPI confirma que es la
red de la máquina, no el código. Las corridas siguientes pasaron completas.
