/**
 * Formulario de proyecto, para crear y para editar (campos de la decisión D7).
 *
 * Al crear solo se piden los datos mínimos: el ingeniero viene a cargar su
 * Excel, no a llenar una ficha. El resto (responsable, intervención, marco)
 * queda plegado en la edición.
 *
 * No valida reglas de negocio: los vocabularios vienen del backend
 * (GET /api/v1/catalogs) y las reglas (fechas coherentes, cantidades
 * positivas) las aplica el dominio; su mensaje se muestra tal cual.
 */
import { useState, type FormEvent } from "react";

import type { Catalogs, Project, ProjectInput } from "../api/types";
import { label } from "../labels";

type Values = Record<string, string>;

const TEXT_FIELDS = [
  "name", "contract_code", "objective", "executing_org", "contracting_entity",
  "department", "municipality", "locality", "intervention_type", "legal_framework",
  "environmental_authority", "status", "establishment_date", "start_date", "end_date",
] as const;
const NUMBER_FIELDS = ["area_ha", "planting_density", "coordinate_srid"] as const;
const INTEGER_FIELDS = ["planted_individuals"] as const;

function initialValues(project?: Project): Values {
  const v: Values = {};
  for (const f of [...TEXT_FIELDS, ...NUMBER_FIELDS, ...INTEGER_FIELDS]) {
    const raw = project?.[f as keyof Project];
    v[f] = raw === null || raw === undefined ? "" : String(raw);
  }
  return v;
}

/**
 * Convierte el formulario al cuerpo de la API.
 * - Crear: los campos vacíos no se envían.
 * - Editar: solo se envía lo que cambió; un campo vaciado se envía como null.
 */
export function toInput(values: Values, original?: Project): ProjectInput {
  const out: Record<string, string | number | null> = {};
  const all = [...TEXT_FIELDS, ...NUMBER_FIELDS, ...INTEGER_FIELDS] as readonly string[];
  for (const f of all) {
    const texto = (values[f] ?? "").trim();
    let valor: string | number | null = texto === "" ? null : texto;
    if (valor !== null && (NUMBER_FIELDS as readonly string[]).includes(f)) valor = Number(valor);
    if (valor !== null && (INTEGER_FIELDS as readonly string[]).includes(f)) {
      valor = Number.parseInt(String(valor), 10);
    }
    if (original) {
      const antes = original[f as keyof Project] ?? null;
      if (antes === valor) continue;
      out[f] = valor;
    } else if (valor !== null) {
      out[f] = valor;
    }
  }
  return out as ProjectInput;
}

interface Props {
  catalogs: Catalogs;
  project?: Project;
  submitLabel: string;
  onSubmit: (input: ProjectInput) => Promise<void>;
}

export function ProjectForm({ catalogs, project, submitLabel, onSubmit }: Props) {
  const [values, setValues] = useState<Values>(() => initialValues(project));
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const set = (f: string) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [f]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await onSubmit(toInput(values, project));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  const text = (f: string, titulo: string, extra: object = {}) => (
    <label className="field">
      <span>{titulo}</span>
      <input value={values[f]} onChange={set(f)} {...extra} />
    </label>
  );
  const select = (f: string, titulo: string, opciones: string[]) => (
    <label className="field">
      <span>{titulo}</span>
      <select value={values[f]} onChange={set(f)}>
        <option value="">—</option>
        {opciones.map((o) => (
          <option key={o} value={o}>
            {label(o)}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <form className="project-form" onSubmit={submit}>
      <fieldset className="card">
        <legend>Proyecto</legend>
        {text("name", "Nombre del proyecto *", { required: true, maxLength: 200 })}
        {text("contract_code", "Código de contrato", { maxLength: 100 })}
        {text("department", "Departamento", { maxLength: 100 })}
        {text("municipality", "Municipio", { maxLength: 100 })}
      </fieldset>

      {project && (
        <details className="card opcionales">
          <summary>Datos adicionales del proyecto (opcional)</summary>
          <div className="opcionales-cuerpo">
          <fieldset className="card card-flat">
            <legend>Responsable</legend>
            <p className="muted field-wide">
              El ingeniero a cargo es usted: el proyecto queda asociado a su cuenta.
            </p>
            {text("executing_org", "Empresa u organización ejecutora", { maxLength: 200 })}
            {text("contracting_entity", "Entidad contratante", { maxLength: 200 })}
          </fieldset>

          <fieldset className="card card-flat">
            <legend>Ubicación</legend>
            {text("locality", "Vereda o referencia", { maxLength: 200 })}
            <label className="field field-wide">
              <span>Objetivo de la intervención</span>
              <textarea rows={3} value={values.objective} onChange={set("objective")} />
            </label>
            <p className="muted field-wide">
              Los predios y parcelas se registran solos al cargar el Excel de monitoreo.
            </p>
          </fieldset>

          <fieldset className="card card-flat">
            <legend>Intervención</legend>
            {select("intervention_type", "Tipo de intervención", catalogs.intervention_types)}
            {text("area_ha", "Área (ha)", { type: "number", step: "any", min: 0 })}
            {text("planted_individuals", "Individuos plantados", { type: "number", step: 1, min: 0 })}
            {text("planting_density", "Densidad (ind/ha)", { type: "number", step: "any", min: 0 })}
            {text("establishment_date", "Fecha de siembra", { type: "date" })}
            {text("start_date", "Inicio del proyecto", { type: "date" })}
            {text("end_date", "Fin del proyecto", { type: "date" })}
          </fieldset>

          <fieldset className="card card-flat">
            <legend>Marco</legend>
            {select("legal_framework", "Marco legal / obligación", catalogs.legal_frameworks)}
            {text("environmental_authority", "Autoridad ambiental", { maxLength: 200 })}
            {select("status", "Estado", catalogs.project_statuses)}
            {text("coordinate_srid", "Sistema de coordenadas (EPSG)", {
              type: "number",
              step: 1,
              placeholder: String(catalogs.default_srid),
            })}
          </fieldset>
          </div>
        </details>
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={enviando}>
          {enviando ? "Guardando…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
