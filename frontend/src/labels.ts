/**
 * Etiquetas legibles de los vocabularios del dominio.
 *
 * Solo PRESENTACION: los valores validos los decide el backend
 * (GET /api/v1/catalogs). Un valor nuevo que el backend añada sin etiqueta
 * aqui se muestra tal cual en vez de desaparecer del formulario.
 */
const LABELS: Record<string, string> = {
  // tipo de intervención
  rehabilitacion: "Rehabilitación",
  restauracion_activa: "Restauración activa",
  restauracion_pasiva: "Restauración pasiva",
  enriquecimiento: "Enriquecimiento",
  reforestacion: "Reforestación",
  agroforestal: "Sistema agroforestal",
  // marco legal
  compensacion_ambiental: "Compensación ambiental",
  inversion_1_por_ciento: "Inversión forzosa del 1 %",
  plan_de_manejo: "Plan de manejo",
  voluntario: "Voluntario",
  // estado
  activo: "Activo",
  cerrado: "Cerrado",
  otro: "Otro",
};

export function label(value: string | null | undefined): string {
  if (!value) return "—";
  return LABELS[value] ?? value;
}
