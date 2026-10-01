# ADR-014 — Mortalidad: modelo general transferible + modelo propio por proyecto con gate automático (E8)

- **Estado:** Aceptado
- **Fecha:** 2026-09-30
- **Contexto:** el objetivo del producto cambió (2026-09-30): el ML debe servir para
  cualquier proyecto de restauración, no solo para el Anexo 1. ADR-013 rechazó entrenar por
  proyecto («~100 árboles sería ruido» y «el gate exige revisión humana antes de servir un
  modelo nuevo»). La evidencia nueva reabre esa decisión:
  - exp_c: la especie no transfiere (otro proyecto tiene otras especies) y el gremio no aporta
    sobre el tamaño; un modelo de solo tamaño rinde como el de E7.
  - exp_d (Werden 2018, 13 censos): el modelo propio supera al general desde el primer
    intervalo cerrado (hasta 3.5× el azar con especie y tratamiento); el general transfiere
    1.2–2.5× sin reentrenar.
  - exp_e (LOPO con Anexo 1, Werden 2018, Werden 2020): el percentil de altura tiene
    coeficiente estable en los tres cortes y 1.2–2.9× en todos los intervalos fuera de muestra;
    «no creció en el intervalo previo» cambia de signo entre proyectos.
  - Anexo 1: el propio gana en M2→M3 (2.65× vs 1.68×) y pierde en M3→M4 (2.53× vs 2.88×).
  - Las fechas de monitoreo del Anexo 1 no se pueden confirmar: el diseño no puede depender
    de la duración del intervalo.

- **Opciones consideradas:**
  - *Solo modelo general (offline, como E7).* Rechazada: desperdicia la señal propia del
    proyecto cuando ya tiene historia (exp_d).
  - *Solo modelo propio.* Rechazada: no existe antes del primer intervalo cerrado y con pocos
    eventos es inestable.
  - *Promediar ambos siempre.* Rechazada por YAGNI: no hay evidencia de que mejore y oculta qué
    modelo produjo cada cifra.
  - **Híbrido con gate automático** (elegida).

- **Decisión:**
  1. Modelo general offline de una variable (`h_pct`), entrenado con los tres proyectos,
     artefacto JSON versionado y gate pre-registrado (plan E8, D6). Se muestra como **riesgo
     relativo**, nunca como probabilidad absoluta.
  2. Modelo propio entrenado **en el servidor, en Python puro** (Newton-IRLS con L2), al pedir
     la evaluación de un monitoreo, con los intervalos cerrados del proyecto. Es barato (cientos
     de filas, < 10 variables) y no reintroduce el error de v1 porque no es un pipeline pesado ni
     `async`. scikit-learn sigue fuera de producción; un test de paridad lo usa como referencia.
  3. Gate automático: se sirve el propio solo si supera al general en el último intervalo
     cerrado, con ≥ 10 muertes de entrenamiento y ≥ 5 de prueba. La decisión, sus cifras y el
     modelo servido se guardan en el snapshot `mortality_assessments`.
  4. El snapshot se invalida por modelo general, datos (≤ t) y versión de reglas; como el
     propio se entrena con esos mismos datos, la huella de datos también lo versiona.

- **Consecuencias:**
  - El modelo propio no tiene revisión humana: se acepta porque el gate lo compara contra un
    modelo que sí la tuvo y porque el usuario ve qué modelo se usó y por qué.
  - La elección con un solo intervalo de prueba es ruidosa (Anexo 1, M3→M4): se documenta.
  - Se cierra la deuda D (archivo crudo), requisito de reproducibilidad de un modelo entrenado
    con datos del usuario.
  - Impacto en slices existentes: ninguno; E7 no cambia. `select_alerts` se reutiliza.
