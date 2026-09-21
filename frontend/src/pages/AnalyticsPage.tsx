/**
 * Página `/analytics` — analítica de crecimiento (slice 5).
 *
 * Orden deliberado: primero la descomposición de varianza, después los dos
 * rankings. Quien entra directo a los forest plots ve dos gráficos parecidos y
 * concluye lo mismo de ambos; la descomposición es lo que explica que en
 * estancamiento la especie pese 2.7× más que la parcela y en mortalidad pesen
 * casi igual — es decir, que uno se ataca eligiendo qué plantar y el otro
 * mejorando las condiciones del sitio.
 */
import { useCallback, useMemo, useState } from "react";

import {
  fetchPlots,
  fetchSpecies,
  fetchVarianceDecomposition,
} from "../api/client";
import type { PlotAnalytics } from "../api/types";
import { ComparisonPanel } from "../components/ComparisonPanel";
import { ForestPlot } from "../components/ForestPlot";
import { GuildFilter } from "../components/GuildFilter";
import { SpeciesDetail } from "../components/SpeciesDetail";
import { useAsync } from "../hooks/useAsync";

function countSignificantPlots(
  plots: PlotAnalytics[] | null,
  key: "stall_risk" | "mortality_risk",
): number | null {
  if (!plots) return null;
  return plots.filter((p) => p[key].significant === true).length;
}

export function AnalyticsPage() {
  const [gremio, setGremio] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  // Sin filtrar: alimenta el panel comparativo y el filtro de gremios, que
  // deben describir el dataset completo aunque el usuario esté filtrando.
  const all = useAsync((signal) => fetchSpecies({ sort: "stall_risk" }, signal), []);
  const filtered = useAsync(
    (signal) => fetchSpecies({ gremio, sort: "stall_risk" }, signal),
    [gremio],
  );
  const variance = useAsync((signal) => fetchVarianceDecomposition(signal), []);
  const plots = useAsync((signal) => fetchPlots(null, signal), []);

  const speciesAll = useMemo(() => all.data ?? [], [all.data]);
  const speciesShown = useMemo(() => filtered.data ?? [], [filtered.data]);

  const detail = useMemo(
    () => speciesAll.find((s) => s.species === selected) ?? null,
    [speciesAll, selected],
  );

  const handleSelect = useCallback((name: string) => setSelected(name), []);

  // Cada modelo corre sobre su propio panel: 1.335 observaciones el de
  // estancamiento y 1.405 el de mortalidad. Mostrar uno solo como si fuera
  // «el total» era lo que hacia antes esta cabecera, y hacia parecer que
  // ambos rankings salen del mismo conjunto de datos.
  const obsPorModelo = useCallback(
    (model: string) =>
      variance.data
        ?.find((m) => m.model === model)
        ?.components[0]?.n_observations?.toLocaleString("es") ?? "—",
    [variance.data],
  );

  if (all.loading && speciesAll.length === 0) {
    return <p className="state">Cargando analítica…</p>;
  }

  if (all.error) {
    return (
      <div className="state state-error">
        <h2>No se pudo cargar la analítica</h2>
        <p>{all.error.message}</p>
        <p className="muted">
          Si la base está vacía, ejecuta <code>python scripts/load_analytics.py</code>{" "}
          en <code>backend/</code>.
        </p>
      </div>
    );
  }

  if (speciesAll.length === 0) {
    return (
      <div className="state">
        <h2>Analítica no cargada</h2>
        <p>
          Las tablas existen pero están vacías. Ejecuta{" "}
          <code>python scripts/load_analytics.py</code> en <code>backend/</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="page-head">
        <h1>Analítica de crecimiento</h1>
        <p className="subtitle">
          Efectos por especie y parcela de dos modelos mixtos sobre paneles
          distintos: {obsPorModelo("stall")} observaciones árbol-intervalo para
          estancamiento y {obsPorModelo("mortality")} para mortalidad. Todas las
          cifras son <strong>odds ratio</strong>: 1.0 es «como el promedio».
        </p>
      </header>

      {variance.data && (
        <ComparisonPanel
          variance={variance.data}
          species={speciesAll}
          plotCount={{
            stall: countSignificantPlots(plots.data, "stall_risk"),
            mortality: countSignificantPlots(plots.data, "mortality_risk"),
          }}
        />
      )}

      <GuildFilter species={speciesAll} value={gremio} onChange={setGremio} />

      <div className="plots">
        <ForestPlot
          species={speciesShown}
          riskKey="stall_risk"
          title="Estancamiento por especie"
          subtitle="Qué tan probable es que la altura no crezca hasta el próximo monitoreo."
          onSelect={handleSelect}
          selected={selected}
        />
        <ForestPlot
          species={speciesShown}
          riskKey="mortality_risk"
          title="Mortalidad por especie"
          subtitle="Mismo formato, otra escala de efecto: aquí casi ninguna especie se distingue del promedio."
          onSelect={handleSelect}
          selected={selected}
        />
      </div>

      <SpeciesDetail species={detail} onClose={() => setSelected(null)} />

      <footer className="page-foot muted">
        Fuente: modelos mixtos <code>lme4::glmer</code> binomiales sobre el
        dataset de referencia (856 árboles, M1–M4). Los intervalos se estimaron
        en log-odds y se muestran exponenciados. Una especie cuyo intervalo
        cruza 1.0 no es «segura»: es indistinguible del promedio con los datos
        disponibles.
      </footer>
    </div>
  );
}
