/**
 * Iconos de trazo (24×24, currentColor) y la marca de Dendrova.
 *
 * Inline y sin librería: son una docena y una dependencia de iconos sería peso
 * sin uso. Todos son decorativos (aria-hidden): el texto del control los nombra.
 */
import type { ReactNode } from "react";

function Icon({ children, size = 18 }: { children: ReactNode; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const IconProjects = () => (
  <Icon>
    <path d="m12 3 9 5-9 5-9-5 9-5Z" />
    <path d="m3 13 9 5 9-5" />
  </Icon>
);

export const IconOverview = () => (
  <Icon>
    <rect x="3" y="3" width="7" height="9" rx="1.5" />
    <rect x="14" y="3" width="7" height="5" rx="1.5" />
    <rect x="14" y="12" width="7" height="9" rx="1.5" />
    <rect x="3" y="16" width="7" height="5" rx="1.5" />
  </Icon>
);

export const IconChart = () => (
  <Icon>
    <path d="M3 3v18h18" />
    <path d="M8 16v-5" />
    <path d="M13 16V8" />
    <path d="M18 16v-9" />
  </Icon>
);

export const IconMap = () => (
  <Icon>
    <path d="m9 4-6 2v14l6-2 6 2 6-2V4l-6 2-6-2Z" />
    <path d="M9 4v14" />
    <path d="M15 6v14" />
  </Icon>
);

export const IconLeaf = () => (
  <Icon>
    <path d="M5 20c8 0 14-6 14-16-8 0-14 5-14 13v3Z" />
    <path d="M5 20 13 11" />
  </Icon>
);

export const IconSpecies = () => (
  <Icon>
    <path d="M12 22V12" />
    <path d="M12 12c-4 0-7-3-7-7 4 0 7 3 7 7Z" />
    <path d="M12 15c3.5 0 6-2.5 6-6-3.5 0-6 2.5-6 6Z" />
  </Icon>
);

export const IconUser = () => (
  <Icon>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0 1 16 0" />
  </Icon>
);

export const IconLogout = () => (
  <Icon>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <path d="m16 17 5-5-5-5" />
    <path d="M21 12H9" />
  </Icon>
);

export const IconMenu = () => (
  <Icon size={20}>
    <path d="M4 6h16" />
    <path d="M4 12h16" />
    <path d="M4 18h16" />
  </Icon>
);

export const IconPlus = () => (
  <Icon size={16}>
    <path d="M12 5v14" />
    <path d="M5 12h14" />
  </Icon>
);

export const IconDownload = () => (
  <Icon size={16}>
    <path d="M12 3v12" />
    <path d="m7 10 5 5 5-5" />
    <path d="M5 21h14" />
  </Icon>
);

export const IconEdit = () => (
  <Icon size={16}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
  </Icon>
);

export const IconUpload = () => (
  <Icon size={20}>
    <path d="M12 15V3" />
    <path d="m7 8 5-5 5 5" />
    <path d="M5 21h14" />
  </Icon>
);

export const IconAlert = () => (
  <Icon>
    <path d="M12 9v4" />
    <path d="M12 17h.01" />
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
  </Icon>
);

export const IconTrend = () => (
  <Icon>
    <path d="M3 17h18" />
    <path d="m7 13 3-3 4 2 4-5" />
  </Icon>
);

export const IconCheck = () => (
  <Icon>
    <path d="m5 12 5 5L20 7" />
  </Icon>
);

/** Anillos de crecimiento con el centro desplazado, como un corte real del tronco. */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true" focusable="false">
      <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="2" />
      <circle cx="16.8" cy="15.4" r="9.5" stroke="currentColor" strokeWidth="1.6" opacity="0.85" />
      <circle cx="17.4" cy="15" r="5.4" stroke="currentColor" strokeWidth="1.4" opacity="0.7" />
      <circle cx="17.8" cy="14.7" r="1.8" fill="currentColor" />
    </svg>
  );
}
