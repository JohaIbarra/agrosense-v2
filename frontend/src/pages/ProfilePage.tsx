/**
 * Perfil del ingeniero: nombre, matrícula profesional y organización, que
 * firmarán los informes técnicos.
 */
import { useEffect, useState, type FormEvent } from "react";

import { getMe, updateMe } from "../api/projects";
import { useAsync } from "../hooks/useAsync";

export function ProfilePage() {
  const me = useAsync((signal) => getMe(signal), []);
  const [valores, setValores] = useState({ full_name: "", professional_license: "", organization: "" });
  const [estado, setEstado] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (me.data) {
      setValores({
        full_name: me.data.full_name ?? "",
        professional_license: me.data.professional_license ?? "",
        organization: me.data.organization ?? "",
      });
    }
  }, [me.data]);

  if (me.loading) return <p className="state">Cargando perfil…</p>;
  if (me.error) {
    return (
      <p className="state form-error" role="alert">
        {me.error.message}
      </p>
    );
  }

  async function guardar(e: FormEvent) {
    e.preventDefault();
    setEstado(null);
    setError(null);
    try {
      await updateMe(valores);
      setEstado("Perfil guardado.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const campo = (f: keyof typeof valores, titulo: string) => (
    <label className="field">
      <span>{titulo}</span>
      <input
        value={valores[f]}
        onChange={(e) => setValores((v) => ({ ...v, [f]: e.target.value }))}
      />
    </label>
  );

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <h1>Perfil</h1>
        <p className="subtitle">{me.data?.email}</p>
      </header>
      <form className="card project-form-single" onSubmit={guardar}>
        {campo("full_name", "Nombre completo")}
        {campo("professional_license", "Matrícula profesional")}
        {campo("organization", "Organización")}
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        {estado && <p className="form-ok">{estado}</p>}
        <div className="form-actions">
          <button type="submit" className="btn btn-primary">
            Guardar
          </button>
        </div>
      </form>
    </div>
  );
}
