/**
 * Filtro por gremio ecológico.
 *
 * Los gremios se derivan de los datos recibidos, no de una lista fija: si el
 * dataset incorpora un gremio nuevo, el filtro lo ofrece sin tocar código.
 */
import type { SpeciesAnalytics } from "../api/types";

interface Props {
  species: SpeciesAnalytics[];
  value: string | null;
  onChange: (gremio: string | null) => void;
}

export function GuildFilter({ species, value, onChange }: Props) {
  const gremios = Array.from(
    new Set(species.map((s) => s.gremio).filter((g): g is string => !!g)),
  ).sort();

  return (
    <div className="filter" role="group" aria-label="Filtrar por gremio ecológico">
      <span className="filter-label">Gremio</span>
      <button
        type="button"
        className={value === null ? "chip chip-on" : "chip"}
        onClick={() => onChange(null)}
        aria-pressed={value === null}
      >
        Todos
      </button>
      {gremios.map((g) => (
        <button
          key={g}
          type="button"
          className={value === g ? "chip chip-on" : "chip"}
          onClick={() => onChange(g)}
          aria-pressed={value === g}
        >
          {g}
        </button>
      ))}
    </div>
  );
}
