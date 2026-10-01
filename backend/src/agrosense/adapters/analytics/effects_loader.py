"""Lee los efectos de los modelos mixtos ya ajustados y los deja listos para
persistir (slice 5).

Fuente de verdad (AGENTS.md, data provenance): los CSV de
`backend/data/processed/`, producidos por los `lme4::glmer` binomiales sobre
`backend/data/raw/anexo1.xlsx`. **Aqui no se re-estima nada**: este modulo
traduce, no modela. Si un numero de la API no cuadra con el informe, el que
manda es el CSV.

Todos los CSV son **UTF-8**. Verificado byte a byte el 2026-09-21, no asumido:
el panel trae la secuencia de dos bytes C3 B3 para la 'o' acentuada de
"Rehabilitacion vegetal", que es UTF-8; en cp1252 seria el byte suelto F3.
El encoding se declara explicito igualmente porque estos archivos los exporta
R en Windows y el default de `read_csv` depende del locale de quien ejecute el
script: leerlos como cp1252 NO falla, solo guarda mojibake en la base de datos.

Los `efectos_aleatorios*.csv` mezclan los dos niveles de agrupamiento en una
sola tabla (columna `grupo`: especie | parcela), asi que SIEMPRE hay que
filtrar antes de escribir.

Escala: `efecto`, `se`, `lo` y `hi` estan en **log-odds**; `lo`/`hi` son
`efecto +- 1.96*se`. El OR es `exp(efecto)` y el IC del OR es `exp(lo)`,
`exp(hi)`. La significancia es "el IC en log-odds no cruza 0", que es lo mismo
que "el IC del OR no cruza 1".
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pandas as pd

# Encodings de cada familia de archivos (ver docstring del modulo).
EFFECTS_ENCODING = "utf-8"
PANEL_ENCODING = "utf-8"

# z de un IC del 95 % normal — el mismo que uso R para generar `lo`/`hi`.
Z_95 = 1.96


# ── Nombres ────────────────────────────────────────────────────────────────

def normalize_level(raw: object) -> str:
    """Normaliza un nombre de especie o codigo de parcela.

    Existe por un caso real, no por prolijidad: en los tres CSV la especie
    aparece como `'Inga punctata\\xa0'`, con un espacio duro (NBSP) pegado al
    final que viene del Excel original. Sin normalizar:

      - la PK de `reference_species_effects` acepta `'Inga punctata\\xa0'` y
        `'Inga punctata'` como dos taxones distintos;
      - el join con el panel no casa, asi que esa especie se queda sin gremio
        ni conteos;
      - y `GET /analytics/species/Inga punctata` devuelve 404 justo para la
        UNICA especie con efecto significativo en mortalidad (OR 0.35).

    Normaliza a NFC, convierte cualquier espacio Unicode (NBSP incluido) en
    espacio normal, colapsa repeticiones y recorta los extremos.
    """
    s = unicodedata.normalize("NFC", str(raw))
    s = "".join(" " if ch.isspace() else ch for ch in s)
    return " ".join(s.split())


# ── Filas listas para persistir ────────────────────────────────────────────

@dataclass(frozen=True)
class SpeciesRow:
    species_name: str
    effect_stall: float | None
    se_stall: float | None
    or_stall: float | None
    or_stall_lo: float | None
    or_stall_hi: float | None
    sig_stall: bool | None
    effect_mort: float | None
    se_mort: float | None
    or_mort: float | None
    or_mort_lo: float | None
    or_mort_hi: float | None
    sig_mort: bool | None
    n_observations: int | None
    n_trees: int | None
    gremio: str | None


@dataclass(frozen=True)
class PlotRow:
    plot_code: str
    localidad: str | None
    effect_stall: float | None
    se_stall: float | None
    or_stall: float | None
    effect_mort: float | None
    se_mort: float | None
    or_mort: float | None
    n_trees: int | None


@dataclass(frozen=True)
class VarianceRow:
    model: str  # stall | mortality
    grouping: str  # especie | parcela
    variance: float
    sd: float
    icc: float
    n_levels: int | None
    n_observations: int | None
    n_events: int | None


@dataclass(frozen=True)
class AnalyticsBundle:
    """Todo lo que una corrida del loader produce, ya normalizado."""

    species: list[SpeciesRow]
    plots: list[PlotRow]
    variance: list[VarianceRow]


# ── Conversiones ───────────────────────────────────────────────────────────

def _f(value: object) -> float | None:
    """float o None, tratando NaN como ausente (pandas los mete por el merge)."""
    if value is None:
        return None
    try:
        out = float(cast("float", value))
    except (TypeError, ValueError):
        return None
    return None if math.isnan(out) else out


def _i(value: object) -> int | None:
    out = _f(value)
    return None if out is None else int(out)


def odds_ratio(effect: float | None) -> float | None:
    return None if effect is None else math.exp(effect)


def is_significant(lo: float | None, hi: float | None) -> bool | None:
    """True si el IC 95% en log-odds NO cruza 0.

    `lo > 0` = el efecto es positivo con confianza (mas riesgo);
    `hi < 0` = negativo con confianza (protector). Cualquier IC que contenga
    el 0 es "no distinguible del promedio".
    """
    if lo is None or hi is None:
        return None
    return bool(lo > 0 or hi < 0)


# ── Lectura de los CSV ─────────────────────────────────────────────────────

def read_effects(path: Path, grupo: str) -> pd.DataFrame:
    """Lee un `efectos_aleatorios*.csv` y se queda con un nivel de agrupamiento.

    El CSV mezcla especies y parcelas en la misma tabla; sin el filtro por
    `grupo`, los codigos de parcela acabarian en `reference_species_effects`.
    """
    df = pd.read_csv(path, encoding=EFFECTS_ENCODING)
    faltan = {"nivel", "efecto", "se", "grupo", "lo", "hi"} - set(df.columns)
    if faltan:
        raise ValueError(f"{path.name}: faltan columnas {sorted(faltan)}")
    df = df[df["grupo"] == grupo].copy()
    df["nivel"] = df["nivel"].map(normalize_level)
    return df


def _panel_species_meta(panel: pd.DataFrame) -> pd.DataFrame:
    """gremio, observaciones y arboles unicos por especie, desde el panel."""
    panel = panel.copy()
    panel["especie"] = panel["especie"].map(normalize_level)
    meta = panel.groupby("especie").agg(
        n_observations=("especie", "size"),
        n_trees=("arbol", "nunique"),
        gremio=("gremio", lambda s: s.dropna().iloc[0] if s.notna().any() else None),
    )
    return meta


def _panel_plot_meta(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["parcela"] = panel["parcela"].map(normalize_level)
    return panel.groupby("parcela").agg(
        n_trees=("arbol", "nunique"),
        localidad=("localidad", lambda s: s.dropna().iloc[0] if s.notna().any() else None),
    )


def read_panel(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding=PANEL_ENCODING)


# ── Armado ─────────────────────────────────────────────────────────────────

def build_species_rows(
    stall: pd.DataFrame, mort: pd.DataFrame, panel_stall: pd.DataFrame
) -> list[SpeciesRow]:
    """Combina los efectos de ambos modelos por especie.

    El merge es OUTER a proposito: hoy las 30 especies coinciden en los dos
    modelos, pero una especie que solo aparezca en uno debe entrar igual con
    el otro lado en NULL, no desaparecer del ranking.
    """
    merged = stall.merge(mort, on="nivel", how="outer", suffixes=("_stall", "_mort"))
    meta = _panel_species_meta(panel_stall)

    rows: list[SpeciesRow] = []
    for _, r in merged.iterrows():
        nombre = normalize_level(r["nivel"])
        e_s, se_s = _f(r.get("efecto_stall")), _f(r.get("se_stall"))
        lo_s, hi_s = _f(r.get("lo_stall")), _f(r.get("hi_stall"))
        e_m, se_m = _f(r.get("efecto_mort")), _f(r.get("se_mort"))
        lo_m, hi_m = _f(r.get("lo_mort")), _f(r.get("hi_mort"))

        m = meta.loc[nombre] if nombre in meta.index else None
        # `n` del CSV de efectos es el respaldo si la especie no esta en el panel.
        n_obs = _i(m["n_observations"]) if m is not None else _i(r.get("n_stall"))
        rows.append(
            SpeciesRow(
                species_name=nombre,
                effect_stall=e_s,
                se_stall=se_s,
                or_stall=odds_ratio(e_s),
                or_stall_lo=odds_ratio(lo_s),
                or_stall_hi=odds_ratio(hi_s),
                sig_stall=is_significant(lo_s, hi_s),
                effect_mort=e_m,
                se_mort=se_m,
                or_mort=odds_ratio(e_m),
                or_mort_lo=odds_ratio(lo_m),
                or_mort_hi=odds_ratio(hi_m),
                sig_mort=is_significant(lo_m, hi_m),
                n_observations=n_obs,
                n_trees=_i(m["n_trees"]) if m is not None else None,
                gremio=(m["gremio"] if m is not None else None),
            )
        )
    return sorted(rows, key=lambda x: x.species_name)


def build_plot_rows(
    stall: pd.DataFrame, mort: pd.DataFrame, panel_stall: pd.DataFrame,
    panel_mort: pd.DataFrame,
) -> list[PlotRow]:
    """Combina los efectos por parcela de ambos modelos.

    Aqui el OUTER no es hipotetico: el panel de mortalidad tiene 45 parcelas y
    el de estancamiento 42, asi que 3 parcelas existen solo del lado de
    mortalidad y tienen `effect_stall` en NULL.
    """
    merged = stall.merge(mort, on="nivel", how="outer", suffixes=("_stall", "_mort"))
    meta_s = _panel_plot_meta(panel_stall)
    meta_m = _panel_plot_meta(panel_mort)

    rows: list[PlotRow] = []
    for _, r in merged.iterrows():
        code = normalize_level(r["nivel"])
        e_s = _f(r.get("efecto_stall"))
        e_m = _f(r.get("efecto_mort"))

        # El panel de mortalidad cubre mas parcelas; se usa como respaldo.
        m = meta_s.loc[code] if code in meta_s.index else (
            meta_m.loc[code] if code in meta_m.index else None
        )
        rows.append(
            PlotRow(
                plot_code=code,
                localidad=(m["localidad"] if m is not None else None),
                effect_stall=e_s,
                se_stall=_f(r.get("se_stall")),
                or_stall=odds_ratio(e_s),
                effect_mort=e_m,
                se_mort=_f(r.get("se_mort")),
                or_mort=odds_ratio(e_m),
                n_trees=_i(m["n_trees"]) if m is not None else None,
            )
        )
    return sorted(rows, key=lambda x: x.plot_code)


def build_variance_rows(
    var_stall: pd.DataFrame,
    var_mort: pd.DataFrame,
    effects_stall: pd.DataFrame,
    effects_mort: pd.DataFrame,
    panel_stall: pd.DataFrame,
    panel_mort: pd.DataFrame,
) -> list[VarianceRow]:
    """Descomposicion de varianza de los dos modelos, con su contexto.

    `n_levels` sale de contar los efectos de ese nivel, y `n_observations` /
    `n_events` de los paneles: sin ellos, un ICC de 0.19 no dice si descansa
    sobre 310 eventos o sobre 12.
    """
    fuentes = (
        ("stall", var_stall, effects_stall, panel_stall),
        ("mortality", var_mort, effects_mort, panel_mort),
    )
    rows: list[VarianceRow] = []
    for modelo, var_df, eff_df, panel in fuentes:
        n_obs = int(len(panel))
        n_events = int(panel["y"].sum())
        for _, r in var_df.iterrows():
            grouping = normalize_level(r["grp"])
            rows.append(
                VarianceRow(
                    model=modelo,
                    grouping=grouping,
                    variance=float(r["vcov"]),
                    sd=float(r["sdcor"]),
                    icc=float(r["ICC"]),
                    n_levels=int((eff_df["grupo"] == grouping).sum()),
                    n_observations=n_obs,
                    n_events=n_events,
                )
            )
    return rows


def build_bundle(processed_dir: Path) -> AnalyticsBundle:
    """Lee `data/processed/` completo y devuelve las filas listas para escribir."""
    processed_dir = Path(processed_dir)

    def _need(name: str) -> Path:
        path = processed_dir / name
        if not path.exists():
            raise FileNotFoundError(
                f"Falta {path}. Los CSV de los modelos mixtos son la fuente de "
                f"verdad del slice 5; genera o copia data/processed/ antes de cargar."
            )
        return path

    eff_stall_all = pd.read_csv(_need("efectos_aleatorios.csv"), encoding=EFFECTS_ENCODING)
    eff_mort_all = pd.read_csv(
        _need("efectos_aleatorios_mortalidad.csv"), encoding=EFFECTS_ENCODING
    )
    panel_stall = read_panel(_need("panel_estancamiento.csv"))
    panel_mort = read_panel(_need("panel_mortalidad.csv"))
    var_stall = pd.read_csv(_need("componentes_varianza.csv"), encoding=EFFECTS_ENCODING)
    var_mort = pd.read_csv(
        _need("componentes_varianza_mortalidad.csv"), encoding=EFFECTS_ENCODING
    )

    def _nivel(df: pd.DataFrame, grupo: str) -> pd.DataFrame:
        out = df[df["grupo"] == grupo].copy()
        out["nivel"] = out["nivel"].map(normalize_level)
        return out

    return AnalyticsBundle(
        species=build_species_rows(
            _nivel(eff_stall_all, "especie"), _nivel(eff_mort_all, "especie"), panel_stall
        ),
        plots=build_plot_rows(
            _nivel(eff_stall_all, "parcela"),
            _nivel(eff_mort_all, "parcela"),
            panel_stall,
            panel_mort,
        ),
        variance=build_variance_rows(
            var_stall, var_mort, eff_stall_all, eff_mort_all, panel_stall, panel_mort
        ),
    )
