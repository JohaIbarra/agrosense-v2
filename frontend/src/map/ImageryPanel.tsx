/**
 * Ortofoto del proyecto (E6b): elegir cuál se ve, con qué opacidad, y
 * registrar una nueva pegando su dirección de teselas.
 *
 * AgroSense no guarda la imagen, guarda dónde está (ADR-009). Por eso el
 * formulario pide una plantilla XYZ y no un archivo.
 */
import { useState } from "react";

import { addImageryLayer, removeImageryLayer } from "../api/map";
import type { ImageryLayer } from "../api/types";

interface Props {
  projectId: number;
  layers: ImageryLayer[];
  selected: number | null;
  opacity: number;
  onSelect: (layerId: number | null) => void;
  onOpacity: (value: number) => void;
  onChanged: () => void;
}

export function ImageryPanel({
  projectId,
  layers,
  selected,
  opacity,
  onSelect,
  onOpacity,
  onChanged,
}: Props) {
  const [abierto, setAbierto] = useState(false);
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("");
  const [attribution, setAttribution] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function guardar(event: React.FormEvent) {
    event.preventDefault();
    setGuardando(true);
    setError(null);
    try {
      const capa = await addImageryLayer(projectId, {
        name,
        tile_template: template,
        attribution: attribution || null,
      });
      setName("");
      setTemplate("");
      setAttribution("");
      setAbierto(false);
      onSelect(capa.id);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setGuardando(false);
    }
  }

  async function quitar(layer: ImageryLayer) {
    setError(null);
    try {
      await removeImageryLayer(projectId, layer.id);
      if (selected === layer.id) onSelect(null);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="imagery-panel" aria-labelledby="ortofoto-titulo">
      <h2 id="ortofoto-titulo">Ortofoto</h2>

      <ul className="imagery-list">
        <li>
          <label>
            <input
              type="radio"
              name="ortofoto"
              checked={selected === null}
              onChange={() => onSelect(null)}
            />
            Solo satélite
          </label>
        </li>
        {layers.map((capa) => (
          <li key={capa.id}>
            <label>
              <input
                type="radio"
                name="ortofoto"
                checked={selected === capa.id}
                onChange={() => onSelect(capa.id)}
              />
              {capa.name}
            </label>
            <button
              type="button"
              className="link-btn"
              onClick={() => quitar(capa)}
              aria-label={`Quitar ${capa.name}`}
            >
              Quitar
            </button>
          </li>
        ))}
      </ul>

      {selected !== null && (
        <label className="opacity-control">
          Opacidad
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={opacity}
            onChange={(e) => onOpacity(Number(e.target.value))}
          />
          <span className="muted">{Math.round(opacity * 100)} %</span>
        </label>
      )}

      {abierto ? (
        <form className="imagery-form" onSubmit={guardar}>
          <label>
            Nombre
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label>
            Dirección de las teselas
            <input
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
              placeholder="https://…/{z}/{x}/{y}.png"
              required
            />
          </label>
          <label>
            Créditos de la imagen
            <input
              value={attribution}
              onChange={(e) => setAttribution(e.target.value)}
              placeholder="Autor, fuente y licencia"
            />
          </label>
          <p className="muted small">
            La imagen se queda donde está: AgroSense solo guarda su dirección, y la carga
            su navegador. Debe empezar por <code>https://</code> e incluir{" "}
            <code>{"{z}/{x}/{y}"}</code>.
          </p>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={guardando}>
              {guardando ? "Guardando…" : "Añadir ortofoto"}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setAbierto(false)}>
              Cancelar
            </button>
          </div>
        </form>
      ) : (
        <>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button type="button" className="link-btn" onClick={() => setAbierto(true)}>
            Añadir ortofoto…
          </button>
        </>
      )}
    </section>
  );
}
