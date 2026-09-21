"""Casos de uso de lectura de la analitica del slice 5.

Traducen las filas de `species_analytics` / `plot_analytics` /
`variance_components` a DTOs con la interpretacion ya resuelta.

Por que la interpretacion vive aqui y no en la route: decidir que significa
un OR de 4.94 cuyo IC no cruza 1 — y sobre todo, decidir que un IC que SI
cruza 1 no se presenta como hallazgo — es una regla de negocio. Si viviera en
el adapter, el frontend acabaria reimplementandola (AGENTS.md: "business
rules must not be duplicated in the frontend").

El repositorio entra por parametro sin interfaz, como decidio ADR-003: solo
se le piden atributos por nombre, asi que sirve el ORM o cualquier doble.
"""
from __future__ import annotations

import math
from typing import Protocol

from agrosense.application.dtos import (
    ModelVarianceDTO,
    PlotAnalyticsDTO,
    RiskDTO,
    SpeciesAnalyticsDTO,
    VarianceComponentDTO,
)
from agrosense.application.errors import AppError

# Nombres de modelo del contrato (coinciden con la columna `model`).
MODEL_STALL = "stall"
MODEL_MORTALITY = "mortality"

# Etiquetas de los dos desenlaces, para armar las frases.
_VERBO = {MODEL_STALL: "se estanca", MODEL_MORTALITY: "muere"}


class AnalyticsReader(Protocol):
    """Lo que estos casos de uso necesitan de la persistencia."""

    def list_species(self, gremio: str | None = None) -> list: ...
    def get_species(self, name: str) -> object | None: ...
    def list_plots(self, localidad: str | None = None) -> list: ...
    def list_variance(self) -> list: ...


# ── Interpretacion ─────────────────────────────────────────────────────────

def interpret(
    odds_ratio: float | None,
    or_lo: float | None,
    or_hi: float | None,
    significant: bool | None,
    model: str,
) -> str:
    """Frase para el ingeniero de campo a partir del OR y su IC.

    Tres casos, y el orden importa:

      1. Sin estimacion: se dice, no se inventa un "sin efecto".
      2. IC que cruza 1: NO es un hallazgo. Se enuncia como indistinguible del
         promedio aunque el OR puntual se vea alto — es el error que convierte
         un ranking en supersticion.
      3. IC que no cruza 1: se reporta la magnitud y la direccion.
    """
    verbo = _VERBO.get(model, "responde")

    if odds_ratio is None:
        return "Sin estimacion disponible para este modelo."

    if not significant:
        rango = (
            f" (IC 95% del OR [{or_lo:.2f}, {or_hi:.2f}], cruza 1)"
            if or_lo is not None and or_hi is not None
            else ""
        )
        return f"Sin efecto significativo distinguible del promedio{rango}."

    rango = (
        f", IC 95% del OR [{or_lo:.2f}, {or_hi:.2f}] no cruza 1"
        if or_lo is not None and or_hi is not None
        else ""
    )
    if odds_ratio >= 1:
        return f"{verbo.capitalize()} ~{odds_ratio:.1f}x mas de lo esperado{rango}."
    # Un OR de 0.35 se lee mejor como "2.8x menos" que como "0.35x mas".
    return (
        f"{verbo.capitalize()} ~{1 / odds_ratio:.1f}x menos de lo esperado "
        f"(efecto protector){rango}."
    )


def _risk(
    or_value: float | None,
    or_lo: float | None,
    or_hi: float | None,
    lo_log: float | None,
    hi_log: float | None,
    significant: bool | None,
    model: str,
) -> RiskDTO:
    return RiskDTO(
        odds_ratio=or_value,
        or_ci95=(or_lo, or_hi) if or_lo is not None and or_hi is not None else None,
        ci95_log_odds=(
            (lo_log, hi_log) if lo_log is not None and hi_log is not None else None
        ),
        significant=significant,
        interpretation=interpret(or_value, or_lo, or_hi, significant, model),
    )


def _log_ci(effect: float | None, se: float | None) -> tuple[float | None, float | None]:
    """Reconstruye el IC en log-odds a partir de efecto y error estandar.

    No se persiste porque es derivable y porque lo que la UI dibuja es el OR;
    se recalcula aqui para que la respuesta pueda cotejarse contra el CSV del
    modelo mixto sin abrir la base de datos.
    """
    if effect is None or se is None:
        return None, None
    return effect - 1.96 * se, effect + 1.96 * se


def _species_dto(row) -> SpeciesAnalyticsDTO:
    lo_s, hi_s = _log_ci(row.effect_stall, row.se_stall)
    lo_m, hi_m = _log_ci(row.effect_mort, row.se_mort)
    return SpeciesAnalyticsDTO(
        species=row.species_name,
        stall_risk=_risk(
            row.or_stall, row.or_stall_lo, row.or_stall_hi,
            lo_s, hi_s, row.sig_stall, MODEL_STALL,
        ),
        mortality_risk=_risk(
            row.or_mort, row.or_mort_lo, row.or_mort_hi,
            lo_m, hi_m, row.sig_mort, MODEL_MORTALITY,
        ),
        n_observations=row.n_observations,
        n_trees=row.n_trees,
        gremio=row.gremio,
    )


def _plot_dto(row) -> PlotAnalyticsDTO:
    lo_s, hi_s = _log_ci(row.effect_stall, row.se_stall)
    lo_m, hi_m = _log_ci(row.effect_mort, row.se_mort)
    return PlotAnalyticsDTO(
        plot_code=row.plot_code,
        localidad=row.localidad,
        # Las parcelas no llevan `sig_*` persistido (solo 3 de 42 y 1 de 45
        # resultaron significativas): se deriva del IC reconstruido, con la
        # misma regla que las especies.
        stall_risk=_risk(
            row.or_stall, _exp(lo_s), _exp(hi_s), lo_s, hi_s,
            _sig(lo_s, hi_s), MODEL_STALL,
        ),
        mortality_risk=_risk(
            row.or_mort, _exp(lo_m), _exp(hi_m), lo_m, hi_m,
            _sig(lo_m, hi_m), MODEL_MORTALITY,
        ),
        n_trees=row.n_trees,
    )


def _exp(value: float | None) -> float | None:
    return None if value is None else math.exp(value)


def _sig(lo: float | None, hi: float | None) -> bool | None:
    if lo is None or hi is None:
        return None
    return bool(lo > 0 or hi < 0)


# ── Ordenamientos del ranking ──────────────────────────────────────────────

SORT_FIELDS = {
    "stall_risk": lambda d: (d.stall_risk.odds_ratio is None, -(d.stall_risk.odds_ratio or 0)),
    "mortality_risk": lambda d: (
        d.mortality_risk.odds_ratio is None, -(d.mortality_risk.odds_ratio or 0)
    ),
    "name": lambda d: (False, d.species),
    "n_observations": lambda d: (d.n_observations is None, -(d.n_observations or 0)),
}


def list_species_analytics(
    repo: AnalyticsReader,
    gremio: str | None = None,
    sort: str = "stall_risk",
) -> list[SpeciesAnalyticsDTO]:
    """Ranking completo de especies, opcionalmente filtrado por gremio."""
    if sort not in SORT_FIELDS:
        raise AppError(
            "INVALID_SORT",
            f"Orden '{sort}' no reconocido. Use uno de: "
            f"{', '.join(sorted(SORT_FIELDS))}.",
        )
    dtos = [_species_dto(r) for r in repo.list_species(gremio=gremio)]
    return sorted(dtos, key=SORT_FIELDS[sort])


def get_species_analytics(repo: AnalyticsReader, name: str) -> SpeciesAnalyticsDTO:
    row = repo.get_species(name)
    if row is None:
        raise AppError(
            "SPECIES_NOT_FOUND",
            f"No hay analitica para la especie '{name}'.",
        )
    return _species_dto(row)


def top_risk_stall(repo: AnalyticsReader, limit: int = 5) -> list[SpeciesAnalyticsDTO]:
    """Especies que MAS se estancan, solo entre las que tienen IC concluyente.

    Filtrar por significancia no es un detalle cosmetico: sin el filtro, el
    top-5 lo encabezarian especies con 4 observaciones y un IC enorme, y el
    vivero plantaria en funcion de ruido.
    """
    dtos = [
        d for d in list_species_analytics(repo, sort="stall_risk")
        if d.stall_risk.significant and (d.stall_risk.odds_ratio or 0) > 1
    ]
    return dtos[:limit]


def top_protective(
    repo: AnalyticsReader, model: str = MODEL_STALL, limit: int = 5
) -> list[SpeciesAnalyticsDTO]:
    """Especies con efecto protector significativo (OR < 1 con IC concluyente)."""
    if model not in (MODEL_STALL, MODEL_MORTALITY):
        raise AppError(
            "INVALID_MODEL",
            f"Modelo '{model}' no reconocido. Use '{MODEL_STALL}' o "
            f"'{MODEL_MORTALITY}'.",
        )
    dtos = list_species_analytics(repo, sort="name")

    def risk(d: SpeciesAnalyticsDTO):
        return d.stall_risk if model == MODEL_STALL else d.mortality_risk

    protectoras = [
        d for d in dtos
        if risk(d).significant and (risk(d).odds_ratio or 1) < 1
    ]
    # Mas protector = OR mas bajo.
    protectoras.sort(key=lambda d: risk(d).odds_ratio or 1)
    return protectoras[:limit]


def list_plot_analytics(
    repo: AnalyticsReader, localidad: str | None = None
) -> list[PlotAnalyticsDTO]:
    return [_plot_dto(r) for r in repo.list_plots(localidad=localidad)]


def variance_decomposition(repo: AnalyticsReader) -> list[ModelVarianceDTO]:
    """ICCs de ambos modelos con la lectura estrategica ya hecha.

    Es el endpoint que sostiene el resto del dashboard: sin el, los dos
    rankings parecen decir lo mismo cuando en realidad implican estrategias
    opuestas.
    """
    por_modelo: dict[str, list[VarianceComponentDTO]] = {}
    for r in repo.list_variance():
        por_modelo.setdefault(r.model, []).append(
            VarianceComponentDTO(
                model=r.model,
                grouping=r.grouping,
                variance=r.variance,
                sd=r.sd,
                icc=r.icc,
                n_levels=r.n_levels,
                n_observations=r.n_observations,
                n_events=r.n_events,
            )
        )

    out: list[ModelVarianceDTO] = []
    for model in sorted(por_modelo):
        comps = sorted(por_modelo[model], key=lambda c: c.grouping)
        especie = next((c for c in comps if c.grouping == "especie"), None)
        parcela = next((c for c in comps if c.grouping == "parcela"), None)
        ratio = (
            especie.variance / parcela.variance
            if especie and parcela and parcela.variance
            else None
        )
        out.append(
            ModelVarianceDTO(
                model=model,
                components=comps,
                species_to_plot_ratio=ratio,
                interpretation=_variance_reading(model, ratio),
            )
        )
    return out


def _variance_reading(model: str, ratio: float | None) -> str:
    """La conclusion operativa de la razon de varianzas.

    El corte en 1.5 no es magico: separa "un nivel domina claramente" de
    "los dos pesan parecido". Con 2.7 (estancamiento) y 1.1 (mortalidad),
    los dos modelos reales caen holgadamente a cada lado.
    """
    if ratio is None:
        return "Descomposicion incompleta: falta alguno de los dos niveles."
    desenlace = "el estancamiento" if model == MODEL_STALL else "la mortalidad"
    if ratio >= 1.5:
        return (
            f"La especie explica {ratio:.1f}x mas varianza que la parcela: "
            f"{desenlace} es sobre todo un problema de QUE se planta. "
            f"La palanca principal es la seleccion de especies."
        )
    if ratio <= 1 / 1.5:
        return (
            f"La parcela explica {1 / ratio:.1f}x mas varianza que la especie: "
            f"{desenlace} es sobre todo un problema de DONDE se planta. "
            f"La palanca principal es la condicion del sitio."
        )
    return (
        f"Especie y parcela pesan de forma similar ({ratio:.1f}x): "
        f"{desenlace} depende tanto de que se planta como de las condiciones "
        f"del sitio. Actuar solo sobre la seleccion de especies deja fuera "
        f"la mitad del problema."
    )
