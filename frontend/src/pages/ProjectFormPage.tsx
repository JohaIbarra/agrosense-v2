/**
 * Crear (/proyectos/nuevo) o editar (/proyectos/:id/editar) un proyecto.
 */
import { useNavigate, useParams } from "react-router-dom";

import { createProject, getCatalogs, getProject, updateProject } from "../api/projects";
import { ProjectForm } from "../components/ProjectForm";
import { useAsync } from "../hooks/useAsync";

export function ProjectFormPage() {
  const { id } = useParams();
  const editando = id !== undefined;
  const navigate = useNavigate();

  const catalogs = useAsync((signal) => getCatalogs(signal), []);
  const project = useAsync(
    (signal) => (editando ? getProject(Number(id), signal) : Promise.resolve(undefined)),
    [id],
  );

  if (catalogs.loading || project.loading) return <p className="state">Cargando…</p>;
  const error = catalogs.error ?? project.error;
  if (error) {
    return (
      <p className="state form-error" role="alert">
        {error.message}
      </p>
    );
  }

  return (
    <div className="page page-narrow">
      <header className="page-head">
        <h1>{editando ? "Editar proyecto" : "Nuevo proyecto"}</h1>
        {!editando && (
          <p className="subtitle">
            Solo el nombre es obligatorio. Los demás datos puede completarlos cuando quiera.
          </p>
        )}
      </header>
      <ProjectForm
        catalogs={catalogs.data!}
        project={project.data ?? undefined}
        submitLabel={editando ? "Guardar cambios" : "Crear proyecto"}
        onSubmit={async (input) => {
          const saved = editando
            ? await updateProject(Number(id), input)
            : await createProject(input);
          navigate(`/proyectos/${saved.id}`);
        }}
      />
    </div>
  );
}
