# ADR-006 — Identidad con Supabase Auth y proyectos por ingeniero (E1)

- **Estado:** Aceptado
- **Fecha:** 2026-09-21
- **Contexto:** la visión de producto (`docs/04-vision-producto.md`) exige que
  cada ingeniero tenga sus propios proyectos y que ningún ingeniero vea los
  de otro. Hasta E1 la API no tenía autenticación: cualquiera que llegara a
  ella leía y escribía todo. La decisión D3 fijó Supabase Auth.

- **Opciones consideradas:**
  - *Autenticación propia* (usuarios y contraseñas en nuestra base):
    obliga a guardar hashes, gestionar recuperación de contraseña y correos.
    Superficie de seguridad innecesaria.
  - *Supabase Auth leyendo datos con `supabase-js` + políticas RLS*: mueve
    la autorización a SQL y crea un segundo camino a los datos que hay que
    mantener coherente con la API.
  - *Supabase Auth solo para la sesión; la API verifica el token y autoriza*
    (elegida).

- **Decisión:**
  - **Verificación**: el backend valida el token contra el **JWKS público**
    del proyecto. El Auth firma con **ES256** (verificado el 2026-09-21), así
    que no hay ningún secreto de JWT que guardar. Se exige firma válida,
    algoritmo en lista blanca (ES256/RS256: nunca `none` ni HS256 contra una
    clave pública), `iss` de este proyecto, `aud = authenticated`, `exp` y
    `sub`.
  - **Perfil**: tabla `engineers` con `id` = `sub`; se crea en la primera
    petición autenticada. Sin FK a `auth.users` (otro esquema, inexistente en
    los tests); la identidad la garantiza la firma.
  - **Autorización en `application/`**: todo proyecto tiene `owner_id`; los
    casos de uso filtran por propietario. Un proyecto ajeno responde
    **404**, igual que uno inexistente, para no revelar que existe.
  - **Toda la API exige sesión** (401), incluido el referente científico.
  - **`project_code`** lo asigna AgroSense (`AGS-{año}-{id:04d}`): único
    global y sin carreras, porque sale del id en la misma transacción.
  - **El nombre del proyecto es único por ingeniero**, no global.
  - **RLS**: se mantiene activo **sin políticas**, de forma deliberada. El
    frontend usa `supabase-js` solo para iniciar sesión, con la clave
    *publishable*; el único camino a los datos es la API. Aunque alguien use
    la clave directamente contra la base, no ve nada. Esto cierra como
    decisión la deuda de RLS abierta en la fase 6 del slice 5.
  - **`coordinate_srid`** en el proyecto, 9377 por defecto (ADR-005).

- **Consecuencias:**
  - El backend no custodia contraseñas ni secretos de sesión.
  - Probar la autenticación no requiere red ni cuentas reales: los tests
    firman tokens con una clave EC propia y el verificador es el mismo de
    producción, con otra fuente de claves.
  - Si algún día el frontend necesitara leer datos directamente de
    Supabase, habría que escribir políticas RLS y mantenerlas coherentes con
    la autorización de `application/`. Hoy no es necesario y no se hace.
  - La migración de E1 se niega a correr sobre proyectos sin propietario:
    asignarlos a ciegas regalaría datos de un ingeniero a otro.
  - Pendiente fuera del código: la **URL del sitio** en la configuración de
    Auth de Supabase debe apuntar al frontend para que los enlaces de
    confirmación de correo lleven a la app.
