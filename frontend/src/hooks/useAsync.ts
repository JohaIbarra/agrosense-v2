/**
 * Hook minimo de carga asincrona con cancelacion.
 *
 * No se trae react-query para tres llamadas de solo lectura sobre datos que
 * cambian cuando alguien ejecuta un script (AGENTS.md: "Prefer simple designs
 * over unnecessary abstractions"). Lo que si hace falta es el `AbortController`:
 * sin el, cambiar de gremio dos veces seguido deja que la respuesta lenta pise
 * a la rapida y el ranking muestre el filtro anterior.
 */
import { useEffect, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
}

export function useAsync<T>(
  run: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  useEffect(() => {
    const controller = new AbortController();
    setState((prev) => ({ ...prev, loading: true, error: null }));

    run(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setState({ data, loading: false, error: null });
        }
      })
      .catch((error: Error) => {
        // Una peticion cancelada no es un fallo que mostrar.
        if (controller.signal.aborted || error.name === "AbortError") return;
        setState({ data: null, loading: false, error });
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
