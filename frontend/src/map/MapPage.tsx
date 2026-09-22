/**
 * Mapa del predio (E6): los árboles del proyecto sobre imagen satelital.
 *
 * Qué hace la página: elegir monitoreo (línea de tiempo), predio y capa
 * (árboles o calor por parcela), y mostrar la historia de un árbol al
 * pincharlo. Qué NO hace: calcular. Estados, supervivencias y contornos
 * llegan hechos del backend, igual que en el análisis (E3).
 *
 * Leaflet se usa directo, sin react-leaflet: su versión 5 exige React 19 y
 * aquí hay React 18, y para una sola pantalla el envoltorio no aporta —
 * crear el mapa y repintar dos capas cabe en dos efectos.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Link, useParams } from "react-router-dom";

import { getProjectMap } from "../api/map";
import { ImageryPanel } from "./ImageryPanel";
import { getProject } from "../api/projects";
import type { ImageryLayer, MapTree, ProjectMap } from "../api/types";
import { useAsync } from "../hooks/useAsync";
import {
  ALL_PROPERTIES,
  STATE_COLORS,
  STATE_LABELS,
  stateAt,
  stateCounts,
  survivalColor,
  treeHistory,
  visiblePlots,
  visibleTrees,
} from "./model";

const SATELITE_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const SATELITE_ATTR =
  "Imagen: Esri, Maxar, Earthstar Geographics · Datos: AgroSense";

type Layer = "trees" | "plots";

function TreeCard({ tree, monitorings }: { tree: MapTree; monitorings: number[] }) {
  const history = treeHistory(tree, monitorings).filter((p) => p.state !== null);
  return (
    <aside className="map-card" aria-label={`Historial del árbol ${tree.id}`}>
      <h2>{tree.id}</h2>
      <p className="muted">
        <em>{tree.species ?? "Especie sin registrar"}</em>
        {tree.property ? ` · ${tree.property}` : ""}
        {tree.plot ? ` · parcela ${tree.plot}` : ""}
        {tree.elevation_m !== null ? ` · ${tree.elevation_m} m s. n. m.` : ""}
      </p>
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Monitoreo</th>
            <th scope="col">Estado</th>
            <th scope="col">Altura (m)</th>
            <th scope="col">Crecimiento (m)</th>
          </tr>
        </thead>
        <tbody>
          {history.map((p) => (
            <tr key={p.monitoring}>
              <th scope="row">M{p.monitoring}</th>
              <td>
                <span
                  className="state-dot"
                  style={{ background: STATE_COLORS[p.state!] }}
                  aria-hidden="true"
                />
                {STATE_LABELS[p.state!]}
              </td>
              <td className="num">{p.height !== null ? p.height.toFixed(2) : "—"}</td>
              <td className="num">
                {p.growth !== null ? (p.growth > 0 ? `+${p.growth.toFixed(2)}` : p.growth.toFixed(2)) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </aside>
  );
}

export function MapPage() {
  const { id } = useParams();
  const projectId = Number(id);
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const [monitoring, setMonitoring] = useState<number | null>(null);
  const [property, setProperty] = useState(ALL_PROPERTIES);
  const [layer, setLayer] = useState<Layer>("trees");
  const [selected, setSelected] = useState<MapTree | null>(null);
  const [imageryId, setImageryId] = useState<number | null>(null);
  const [imageryOpacity, setImageryOpacity] = useState(1);
  const [recarga, setRecarga] = useState(0);
  const orthoRef = useRef<L.TileLayer | null>(null);

  const project = useAsync((signal) => getProject(projectId, signal), [projectId]);
  const map = useAsync((signal) => getProjectMap(projectId, signal), [projectId, recarga]);
  const data: ProjectMap | null = map.data;

  // Al llegar los datos, el monitoreo más reciente es el que se muestra
  useEffect(() => {
    if (data && monitoring === null && data.monitorings.length > 0) {
      setMonitoring(data.monitorings[data.monitorings.length - 1]);
    }
  }, [data, monitoring]);

  // Crear el mapa una sola vez, cuando hay contenedor y extensión que encuadrar
  useEffect(() => {
    if (!container.current || mapRef.current || !data?.bounds) return;
    const b = data.bounds;
    const instance = L.map(container.current, { scrollWheelZoom: true });
    L.tileLayer(SATELITE_URL, { attribution: SATELITE_ATTR, maxZoom: 19 }).addTo(instance);
    instance.fitBounds([
      [b.south, b.west],
      [b.north, b.east],
    ]);
    layerRef.current = L.layerGroup().addTo(instance);
    mapRef.current = instance;
    return () => {
      instance.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
  }, [data]);

  // La ortofoto elegida, encima del satélite y debajo de los árboles
  // (Leaflet pinta los marcadores en otro panel, así que nunca los tapa)
  useEffect(() => {
    const instance = mapRef.current;
    if (!instance) return;
    if (orthoRef.current) {
      orthoRef.current.remove();
      orthoRef.current = null;
    }
    const capa = data?.imagery.find((c) => c.id === imageryId);
    if (!capa) return;
    orthoRef.current = L.tileLayer(capa.tile_template, {
      attribution: capa.attribution ?? undefined,
      opacity: imageryOpacity,
      minZoom: capa.min_zoom ?? undefined,
      maxZoom: capa.max_zoom ?? undefined,
    }).addTo(instance);
  }, [data, imageryId, imageryOpacity]);

  // Repintar la capa cuando cambia lo que se mira
  useEffect(() => {
    const group = layerRef.current;
    if (!group || !data || monitoring === null) return;
    group.clearLayers();

    if (layer === "trees") {
      for (const t of visibleTrees(data, monitoring, property)) {
        const state = stateAt(t, monitoring)!;
        L.circleMarker([t.lat, t.lon], {
          radius: 5,
          color: "#ffffff",
          weight: 1, // anillo blanco: separa puntos que se tocan
          fillColor: STATE_COLORS[state],
          fillOpacity: 0.95,
        })
          .on("click", () => setSelected(t))
          .bindTooltip(`${t.id} · ${STATE_LABELS[state]}`)
          .addTo(group);
      }
    } else {
      for (const p of visiblePlots(data, monitoring, property)) {
        const m = p.metrics[String(monitoring)];
        const forma =
          p.hull.length >= 3
            ? L.polygon(p.hull as L.LatLngExpression[], {
                color: "#ffffff",
                weight: 1,
                fillColor: survivalColor(m.survival),
                fillOpacity: 0.75,
              })
            : L.circleMarker([p.centroid.lat, p.centroid.lon], {
                radius: 8,
                color: "#ffffff",
                weight: 1,
                fillColor: survivalColor(m.survival),
                fillOpacity: 0.75,
              });
        forma
          .bindTooltip(
            `Parcela ${p.plot ?? p.key} · ${m.survival.toFixed(1)} % vivos de ${m.n}` +
              (p.low_sample ? " · muestra pequeña" : ""),
          )
          .addTo(group);
      }
    }
  }, [data, monitoring, property, layer]);

  function elegirOrtofoto(layerId: number | null) {
    setImageryId(layerId);
    const capa: ImageryLayer | undefined = data?.imagery.find((c) => c.id === layerId);
    if (capa) setImageryOpacity(capa.opacity);
  }

  const trees = useMemo(
    () => (data && monitoring !== null ? visibleTrees(data, monitoring, property) : []),
    [data, monitoring, property],
  );
  const leyenda = useMemo(
    () => (monitoring !== null ? stateCounts(trees, monitoring) : []),
    [trees, monitoring],
  );

  const volver = (
    <Link to={`/proyectos/${projectId}`}>{project.data?.name ?? "Volver al proyecto"}</Link>
  );

  if (map.loading && !data) return <p className="state">Ubicando los árboles…</p>;
  if (map.error) {
    return (
      <div className="state">
        <h2>No se pudo abrir el mapa</h2>
        <p className="muted">{map.error.message}</p>
        {volver}
      </div>
    );
  }
  if (data && data.trees.length === 0) {
    return (
      <div className="state">
        <h2>Todavía no hay árboles que ubicar</h2>
        <p className="muted">
          {data.without_coordinates > 0
            ? `El proyecto tiene ${data.without_coordinates} árboles, pero ninguno trae coordenadas en el archivo.`
            : "Cargue el Excel de campo del proyecto para ver su mapa."}
        </p>
        {volver}
      </div>
    );
  }

  const d = data!;
  return (
    <div className="page page-wide">
      <header className="page-head">
        <p className="muted">
          <Link to="/proyectos">Mis proyectos</Link> / {volver} / Mapa
        </p>
        <h1>Mapa del predio</h1>
        <p className="subtitle">
          {d.trees.length} árboles ubicados en {d.plots.length} parcelas
          {d.without_coordinates > 0 && (
            <span className="warn"> · {d.without_coordinates} sin coordenada en el archivo</span>
          )}
        </p>
      </header>

      <div className="map-controls">
        <div className="chip-row" role="group" aria-label="Monitoreo">
          {d.monitorings.map((n) => (
            <button
              key={n}
              type="button"
              className={`chip${n === monitoring ? " chip-on" : ""}`}
              aria-pressed={n === monitoring}
              onClick={() => setMonitoring(n)}
            >
              M{n}
            </button>
          ))}
        </div>
        {d.properties.length > 1 && (
          <div className="chip-row" role="group" aria-label="Predio">
            <button
              type="button"
              className={`chip${property === ALL_PROPERTIES ? " chip-on" : ""}`}
              aria-pressed={property === ALL_PROPERTIES}
              onClick={() => setProperty(ALL_PROPERTIES)}
            >
              Todos
            </button>
            {d.properties.map((p) => (
              <button
                key={p}
                type="button"
                className={`chip${property === p ? " chip-on" : ""}`}
                aria-pressed={property === p}
                onClick={() => setProperty(p)}
              >
                {p}
              </button>
            ))}
          </div>
        )}
        <div className="chip-row" role="group" aria-label="Capa">
          <button
            type="button"
            className={`chip${layer === "trees" ? " chip-on" : ""}`}
            aria-pressed={layer === "trees"}
            onClick={() => setLayer("trees")}
          >
            Árboles
          </button>
          <button
            type="button"
            className={`chip${layer === "plots" ? " chip-on" : ""}`}
            aria-pressed={layer === "plots"}
            onClick={() => setLayer("plots")}
          >
            Calor por parcela
          </button>
        </div>
      </div>

      <div className="map-layout">
        <div className="map-canvas" ref={container} role="application" aria-label="Mapa" />
        <div className="map-side">
          {layer === "trees" ? (
            <ul className="legend" aria-label="Leyenda de estados">
              {leyenda.map(([estado, n]) => (
                <li key={estado}>
                  <span
                    className="state-dot"
                    style={{ background: STATE_COLORS[estado] }}
                    aria-hidden="true"
                  />
                  {STATE_LABELS[estado]} <span className="muted">({n})</span>
                </li>
              ))}
            </ul>
          ) : (
            <ul className="legend" aria-label="Leyenda de supervivencia">
              {[0, 20, 40, 60, 80].map((desde) => (
                <li key={desde}>
                  <span
                    className="state-dot"
                    style={{ background: survivalColor(desde) }}
                    aria-hidden="true"
                  />
                  {desde}–{desde + 20} % vivos
                </li>
              ))}
            </ul>
          )}
          <ImageryPanel
            projectId={projectId}
            layers={d.imagery}
            selected={imageryId}
            opacity={imageryOpacity}
            onSelect={elegirOrtofoto}
            onOpacity={setImageryOpacity}
            onChanged={() => setRecarga((n) => n + 1)}
          />
          {selected ? (
            <TreeCard tree={selected} monitorings={d.monitorings} />
          ) : (
            <p className="muted">Pinche un árbol para ver su historial.</p>
          )}
        </div>
      </div>
    </div>
  );
}
