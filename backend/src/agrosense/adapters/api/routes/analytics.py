"""Endpoints de analitica del slice 5.

Regla ADR-003: las routes parsean -> llaman application/ -> mapean respuesta.
Cero logica de negocio aqui: la interpretacion de un OR y el criterio de
significancia viven en `application/use_cases/read_analytics.py`.

Contratos (todos de solo lectura; la carga la hace `scripts/load_analytics.py`):

    GET /api/v1/analytics/species                  -> 200 list[SpeciesAnalyticsResponse]
    GET /api/v1/analytics/species/top-risk-stall   -> 200 list[...]
    GET /api/v1/analytics/species/top-protective   -> 200 list[...]
    GET /api/v1/analytics/species/{name}           -> 200 SpeciesAnalyticsResponse | 404
    GET /api/v1/analytics/plots                    -> 200 list[PlotAnalyticsResponse]
    GET /api/v1/analytics/variance-decomposition   -> 200 list[ModelVarianceResponse]

Orden de declaracion: las rutas fijas `top-risk-stall` y `top-protective` van
ANTES de `/{name}`. Al reves, FastAPI resolveria `/species/top-risk-stall`
contra el parametro y devolveria un 404 buscando la especie "top-risk-stall".
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agrosense.adapters.api.deps import get_current_engineer, get_session
from agrosense.adapters.api.errors import raise_for_value_error
from agrosense.adapters.api.schemas import (
    ModelVarianceResponse,
    PlotAnalyticsResponse,
    RiskResponse,
    SpeciesAnalyticsResponse,
    VarianceComponentResponse,
)
from agrosense.adapters.db.repository import AnalyticsRepository
from agrosense.application.dtos import (
    ModelVarianceDTO,
    PlotAnalyticsDTO,
    RiskDTO,
    SpeciesAnalyticsDTO,
)
from agrosense.application.use_cases.read_analytics import (
    get_species_analytics,
    list_plot_analytics,
    list_species_analytics,
    top_protective,
    top_risk_stall,
    variance_decomposition,
)

# E1: el referente tambien exige sesion (ADR-006). No hay dato sensible, pero
# toda la API es para ingenieros autenticados y la regla es una sola.
router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_engineer)],
)

SessionDep = Annotated[Session, Depends(get_session)]

# Techo del top-N: es un atajo de lectura para el dashboard, no un listado
# paginado. Quien quiera el ranking completo pide /species.
MAX_TOP = 30


def _repo(session: Session) -> AnalyticsRepository:
    return AnalyticsRepository(session)


# ── Mapeo DTO -> schema ────────────────────────────────────────────────────

def _to_risk(dto: RiskDTO) -> RiskResponse:
    return RiskResponse(
        odds_ratio=dto.odds_ratio,
        or_ci95=dto.or_ci95,
        ci95_log_odds=dto.ci95_log_odds,
        significant=dto.significant,
        interpretation=dto.interpretation,
    )


def _to_species(dto: SpeciesAnalyticsDTO) -> SpeciesAnalyticsResponse:
    return SpeciesAnalyticsResponse(
        species=dto.species,
        stall_risk=_to_risk(dto.stall_risk),
        mortality_risk=_to_risk(dto.mortality_risk),
        n_observations=dto.n_observations,
        n_trees=dto.n_trees,
        gremio=dto.gremio,
    )


def _to_plot(dto: PlotAnalyticsDTO) -> PlotAnalyticsResponse:
    return PlotAnalyticsResponse(
        plot_code=dto.plot_code,
        localidad=dto.localidad,
        stall_risk=_to_risk(dto.stall_risk),
        mortality_risk=_to_risk(dto.mortality_risk),
        n_trees=dto.n_trees,
    )


def _to_variance(dto: ModelVarianceDTO) -> ModelVarianceResponse:
    return ModelVarianceResponse(
        model=dto.model,
        components=[
            VarianceComponentResponse(
                grouping=c.grouping,
                variance=c.variance,
                sd=c.sd,
                icc=c.icc,
                n_levels=c.n_levels,
                n_observations=c.n_observations,
                n_events=c.n_events,
            )
            for c in dto.components
        ],
        species_to_plot_ratio=dto.species_to_plot_ratio,
        interpretation=dto.interpretation,
    )


# ── Ranking de especies ────────────────────────────────────────────────────

@router.get("/species", response_model=list[SpeciesAnalyticsResponse])
def list_species_endpoint(
    session: SessionDep,
    gremio: Annotated[str | None, Query(max_length=100)] = None,
    sort: Annotated[str, Query(pattern="^(stall_risk|mortality_risk|name|n_observations)$")]
    = "stall_risk",
) -> list[SpeciesAnalyticsResponse]:
    """Ranking completo de las 30 especies.

    `sort` es un vocabulario cerrado validado por el patron: asi un valor
    invalido se rechaza en el borde con 422 y nunca llega al caso de uso.
    """
    try:
        dtos = list_species_analytics(_repo(session), gremio=gremio, sort=sort)
    except ValueError as exc:
        raise_for_value_error(exc)
    return [_to_species(d) for d in dtos]


# ── Atajos del dashboard (ANTES de /{name}, ver docstring del modulo) ──────

@router.get("/species/top-risk-stall", response_model=list[SpeciesAnalyticsResponse])
def top_risk_stall_endpoint(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=MAX_TOP)] = 5,
) -> list[SpeciesAnalyticsResponse]:
    """Especies con mayor riesgo de estancamiento y IC concluyente.

    Solo devuelve especies significativas: un top-N sin ese filtro lo
    encabezarian las especies con 4 arboles y un IC enorme.
    """
    return [_to_species(d) for d in top_risk_stall(_repo(session), limit=limit)]


@router.get("/species/top-protective", response_model=list[SpeciesAnalyticsResponse])
def top_protective_endpoint(
    session: SessionDep,
    model: Annotated[str, Query(pattern="^(stall|mortality)$")] = "stall",
    limit: Annotated[int, Query(ge=1, le=MAX_TOP)] = 5,
) -> list[SpeciesAnalyticsResponse]:
    """Especies con efecto protector significativo (OR < 1, IC que no cruza 1)."""
    try:
        dtos = top_protective(_repo(session), model=model, limit=limit)
    except ValueError as exc:
        raise_for_value_error(exc)
    return [_to_species(d) for d in dtos]


@router.get("/species/{name}", response_model=SpeciesAnalyticsResponse)
def get_species_endpoint(name: str, session: SessionDep) -> SpeciesAnalyticsResponse:
    try:
        dto = get_species_analytics(_repo(session), name)
    except ValueError as exc:
        raise_for_value_error(exc)
    return _to_species(dto)


# ── Parcelas ───────────────────────────────────────────────────────────────

@router.get("/plots", response_model=list[PlotAnalyticsResponse])
def list_plots_endpoint(
    session: SessionDep,
    localidad: Annotated[str | None, Query(max_length=200)] = None,
) -> list[PlotAnalyticsResponse]:
    return [_to_plot(d) for d in list_plot_analytics(_repo(session), localidad=localidad)]


# ── Descomposicion de varianza ─────────────────────────────────────────────

@router.get("/variance-decomposition", response_model=list[ModelVarianceResponse])
def variance_decomposition_endpoint(session: SessionDep) -> list[ModelVarianceResponse]:
    """ICCs de ambos modelos mixtos con su lectura estrategica.

    Es el endpoint que evita el malentendido central del dashboard: los dos
    rankings se ven iguales, pero en estancamiento la especie pesa 2.7x mas
    que la parcela y en mortalidad pesan casi lo mismo.
    """
    if not (dtos := variance_decomposition(_repo(session))):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ANALYTICS_NOT_LOADED",
                "message": "La analitica no esta cargada. Ejecute "
                "scripts/load_analytics.py.",
            },
        )
    return [_to_variance(d) for d in dtos]
