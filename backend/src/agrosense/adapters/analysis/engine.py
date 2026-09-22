"""Motor del analisis exploratorio por monitoreo (E3).

Reproduce, desde los datos crudos, las 7 hojas que el ingeniero hacia a mano
en el Anexo 1 (Composicion, Alturas, Diametro de copa, Supervivencia, Estado
fito, Edades, DAP), con sus mismos cortes: predio x diseno floristico y
predio x cobertura, monitoreo k frente al k-1.

Por que pandas vive aqui y no en `domain/`: es agregacion, no regla. Las
DEFINICIONES (que es una plantula, que estados fitosanitarios existen, desde
cuantos arboles un % dice algo) estan en `domain/analysis_rules.py`.

Forma del resultado (contrato interno, ADR-008): un dict JSON-serializable
con `sections`; cada seccion trae `tables` TIPADAS (cada columna dice si es
texto, entero, decimal o porcentaje y con cuantos decimales se muestra) y
`charts` que REFERENCIAN una tabla por su id. Asi la pagina y el `.xlsx` se
construyen del mismo calculo y ninguno recalcula nada: solo presentan.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from datetime import date

import pandas as pd

from agrosense.domain.analysis_rules import (
    DEVELOPMENT_CLASSES,
    MIN_SAMPLE_FOR_PERCENT,
    PHYTOSANITARY_STATES,
    development_class,
    is_low_sample,
    normalize_phytosanitary,
)
from agrosense.domain.entities import Observation, StatusSemantic, Tree
from agrosense.domain.rules import MAX_CONTRACTION_M, STAGNATION_THRESHOLD_M, plot_key

# Cambiar CUALQUIER definicion o forma del resultado = nueva version. Los
# snapshots con otra version se recalculan al leerse (provenance, ADR-008).
ANALYSIS_VERSION = "2026-09-22-e4.1"

NO_PROPERTY = "Sin predio"
NO_DESIGN = "Sin diseño florístico"
NO_COVER = "Sin cobertura"

_DIMS = {
    "design": ("Diseño florístico", "diseño florístico", "diseno"),
    "cover": ("Cobertura vegetal asociada", "cobertura", "cobertura"),
}


# ── Construccion del marco largo ─────────────────────────────────────────────


def _mode(values: Iterable[str | None]) -> str | None:
    s = pd.Series([v for v in values if v], dtype="object")
    if s.empty:
        return None
    counts = s.value_counts()
    # Empate: el alfabeticamente primero, para que el resultado sea estable
    top = counts[counts == counts.max()].index
    return sorted(top)[0]


def build_frame(trees: Sequence[Tree], observations: Sequence[Observation]) -> pd.DataFrame:
    """Un renglon por (arbol, monitoreo) con las dimensiones del arbol."""
    tree_rows = [
        {
            "tree_id": t.tree_id,
            "species": t.species,
            "family": t.family,
            "guild": t.guild,
            "property": t.locality or NO_PROPERTY,
            "design": t.floristic_design or NO_DESIGN,
            "cover": t.associated_cover or NO_COVER,
            "plot": plot_key(t),
        }
        for t in trees
    ]
    obs_rows = [
        {
            "tree_id": o.tree_id,
            "monitoring": o.campaign,
            "height": o.height_m,
            "crown": o.crown_diameter_m,
            # Solo el DAP MEDIDO: 0 o blanco es «no alcanza el umbral», no una
            # medicion (StatusSemantic), y promediarlo hundiria la media.
            "dap": o.dap_cm if o.dap_status == StatusSemantic.MEDIDO else None,
            "alive": o.alive,
            "phyto": normalize_phytosanitary(o.phytosanitary),
        }
        for o in observations
    ]
    t = pd.DataFrame(
        tree_rows,
        columns=["tree_id", "species", "family", "guild", "property", "design", "cover", "plot"],
    )
    o = pd.DataFrame(
        obs_rows,
        columns=["tree_id", "monitoring", "height", "crown", "dap", "alive", "phyto"],
    )
    frame = o.merge(t, on="tree_id", how="inner")
    for col in ("height", "crown", "dap"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


def input_hash(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    dates: Mapping[int, date] | None = None,
) -> str:
    """Huella de los datos de entrada: ata un snapshot a lo que lo produjo.

    Las FECHAS entran en la huella desde E4: el crecimiento anualizado depende
    de ellas, asi que corregir la fecha de un monitoreo tiene que recalcular
    el analisis igual que corregir una altura.
    """
    payload = {
        "trees": sorted(t.model_dump_json() for t in trees),
        "observations": sorted(o.model_dump_json() for o in observations),
        "dates": {str(k): v.isoformat() for k, v in sorted((dates or {}).items())},
    }
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


# ── Utilidades de presentacion tipada ────────────────────────────────────────


def _clean(value):
    """Valor JSON-seguro: sin NaN ni tipos de numpy."""
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _col(key: str, label: str, kind: str, decimals: int | None = None, group: str | None = None):
    col = {"key": key, "label": label, "kind": kind}
    if decimals is not None:
        col["decimals"] = decimals
    if group is not None:
        col["group"] = group
    return col


def _text(key, label, group=None):
    return _col(key, label, "text", group=group)


def _int(key, label, group=None):
    return _col(key, label, "int", 0, group)


def _dec(key, label, decimals=2, group=None):
    return _col(key, label, "decimal", decimals, group)


def _pct(key, label, group=None):
    return _col(key, label, "percent", 1, group)


def _table(
    table_id: str,
    title: str,
    columns: list[dict],
    rows: list[dict],
    footer: list[dict] | None = None,
    prop: str | None = None,
    notes: list[str] | None = None,
) -> dict:
    return {
        "id": table_id,
        "title": title,
        "property": prop,
        "columns": columns,
        "rows": [{k: _clean(v) for k, v in r.items()} for r in rows],
        "footer": [{k: _clean(v) for k, v in r.items()} for r in (footer or [])],
        "notes": notes or [],
    }


def _chart(
    chart_id: str,
    title: str,
    table_id: str,
    x: str,
    series: list[str],
    *,
    stacked: bool = False,
    y_label: str = "",
    percent: bool = False,
    prop: str | None = None,
) -> dict:
    return {
        "id": chart_id,
        "title": title,
        "table": table_id,
        "kind": "bar",
        "x": x,
        "series": series,
        "stacked": stacked,
        "percent": percent,
        "y_label": y_label,
        "property": prop,
    }


def _slug(text: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    return "-".join(p for p in out.split("-") if p)


def _pct_of(part: float, total: float) -> float | None:
    return None if not total else 100.0 * part / total


def _mean(series: pd.Series) -> float | None:
    s = series.dropna()
    return None if s.empty else float(s.mean())


def _low_flag(n: int) -> dict:
    return {"_flags": ["low_sample"]} if is_low_sample(n) else {}


# ── Contexto del analisis ────────────────────────────────────────────────────


class _Ctx:
    def __init__(
        self, frame: pd.DataFrame, number: int, dates: Mapping[int, date] | None = None
    ):
        self.frame = frame
        self.k = number
        self.dates: dict[int, date] = dict(dates or {})
        previos = sorted(m for m in frame["monitoring"].unique() if m < number)
        self.prev: int | None = int(previos[-1]) if previos else None
        self.monitorings = sorted(int(m) for m in frame["monitoring"].unique() if m <= number)
        self.properties = sorted(frame["property"].unique())
        # Familia y gremio son atributos de la ESPECIE; si el archivo trae
        # valores distintos para la misma especie se toma el mas frecuente.
        self.family = {s: _mode(g["family"]) for s, g in frame.groupby("species")}
        self.guild = {s: _mode(g["guild"]) for s, g in frame.groupby("species")}

    def at(self, number: int | None, prop: str | None = None) -> pd.DataFrame:
        if number is None:
            return self.frame.iloc[0:0]
        df = self.frame[self.frame["monitoring"] == number]
        if prop is not None:
            df = df[df["property"] == prop]
        return df

    def alive_at(self, number: int | None, prop: str | None = None) -> pd.DataFrame:
        df = self.at(number, prop)
        return df[df["alive"] == True]  # noqa: E712 — columna de objetos (None posible)

    def dim_values(self, dim: str, prop: str) -> list[str]:
        df = self.frame[self.frame["property"] == prop]
        return sorted(df[dim].unique())

    def m(self, number: int | None) -> str:
        return f"M{number}"

    @property
    def interval_years(self) -> float | None:
        """Anos entre el monitoreo anterior y el actual, si ambos tienen fecha.

        Sin fechas devuelve None y el analisis NO anualiza: un crecimiento de
        30 cm en seis meses y otro en dos anos no son el mismo dato, y
        presentarlos juntos como "crecimiento" ya es una comparacion honesta;
        inventar el denominador no lo seria.
        """
        if self.prev is None:
            return None
        a, b = self.dates.get(self.prev), self.dates.get(self.k)
        if a is None or b is None:
            return None
        dias = (b - a).days
        return dias / 365.25 if dias > 0 else None

    def pairs(self, prop: str | None = None) -> pd.DataFrame:
        """Un renglon por arbol censado en Mk-1 Y en Mk, con ambas medidas.

        Es la base de todo el intervalo: quien murio, quien crecio y quien no.
        """
        if self.prev is None:
            return pd.DataFrame(
                columns=["tree_id", "species", "property", "plot", "h_prev", "h_cur",
                         "alive_prev", "alive_cur", "phyto_prev", "phyto_cur", "growth"]
            )
        prev = self.at(self.prev, prop)[
            ["tree_id", "species", "property", "plot", "height", "alive", "phyto"]
        ].rename(columns={"height": "h_prev", "alive": "alive_prev", "phyto": "phyto_prev"})
        cur = self.at(self.k, prop)[["tree_id", "height", "alive", "phyto"]].rename(
            columns={"height": "h_cur", "alive": "alive_cur", "phyto": "phyto_cur"}
        )
        par = prev.merge(cur, on="tree_id", how="inner")
        # Solo cuenta el intervalo de quien estaba VIVO al empezar: un arbol
        # ya muerto en Mk-1 no puede volver a morir ni crecer.
        par = par[par["alive_prev"] == True]  # noqa: E712
        par["growth"] = par["h_cur"] - par["h_prev"]
        par.loc[par["alive_cur"] != True, "growth"] = None  # noqa: E712
        return par


# ── 1. Composicion ───────────────────────────────────────────────────────────


def _composition(ctx: _Ctx) -> dict:
    tables, charts = [], []
    k = ctx.k
    vivos = ctx.alive_at(k)

    for prop in ctx.properties:
        vp = vivos[vivos["property"] == prop]
        for dim, (dim_label, dim_lower, _) in _DIMS.items():
            valores = ctx.dim_values(dim, prop)
            cols = [
                _text("species", "Especie"),
                _text("family", "Familia"),
                _text("guild", "Gremio"),
            ]
            cols += [_int(f"c{i}", v) for i, v in enumerate(valores)]
            cols.append(_int("total", "Total"))
            conteo = vp.groupby(["species", dim]).size()
            rows = []
            for sp in sorted(vp["species"].unique()):
                row = {"species": sp, "family": ctx.family.get(sp), "guild": ctx.guild.get(sp)}
                for i, v in enumerate(valores):
                    row[f"c{i}"] = int(conteo.get((sp, v), 0))
                row["total"] = sum(row[f"c{i}"] for i in range(len(valores)))
                rows.append(row)
            footer = {"species": "Total", "total": len(vp)}
            for i, v in enumerate(valores):
                footer[f"c{i}"] = int((vp[dim] == v).sum())
            tid = f"composicion-{_slug(prop)}-{dim}"
            tables.append(
                _table(
                    tid,
                    f"Composición por {dim_lower} — {prop} ({ctx.m(k)})",
                    cols,
                    rows,
                    [footer],
                    prop,
                    ["Individuos vivos en el monitoreo, por especie."],
                )
            )
            if dim == "design":
                charts.append(
                    _chart(
                        f"{tid}-chart",
                        f"Individuos vivos por especie y {dim_lower} — {prop}",
                        tid,
                        "species",
                        [f"c{i}" for i in range(len(valores))],
                        stacked=True,
                        y_label="Individuos",
                        prop=prop,
                    )
                )

    # Por gremio y por familia, todo el proyecto (hoja «Composición» H1)
    props = ctx.properties
    for attr, label, lookup in (("guild", "Gremio", ctx.guild), ("family", "Familia", ctx.family)):
        vivos_attr = vivos.assign(_attr=vivos["species"].map(lookup).fillna("Sin dato"))
        cols = [_text("value", label), _int("species_n", "Especies")]
        cols += [_int(f"p{i}", p) for i, p in enumerate(props)]
        cols += [_int("total", "Total"), _pct("pct", "% del total")]
        rows = []
        for value, g in sorted(vivos_attr.groupby("_attr"), key=lambda x: str(x[0])):
            row = {"value": value, "species_n": int(g["species"].nunique())}
            for i, p in enumerate(props):
                row[f"p{i}"] = int((g["property"] == p).sum())
            row["total"] = len(g)
            row["pct"] = _pct_of(len(g), len(vivos))
            rows.append(row)
        footer = {
            "value": "Total",
            "species_n": int(vivos["species"].nunique()),
            "total": len(vivos),
            "pct": 100.0 if len(vivos) else None,
        }
        for i, p in enumerate(props):
            footer[f"p{i}"] = int((vivos["property"] == p).sum())
        tid = f"composicion-{attr}"
        tables.append(
            _table(
                tid,
                f"Composición por {label.lower()} — proyecto ({ctx.m(k)})",
                cols,
                rows,
                [footer],
            )
        )
        if attr == "guild":
            charts.append(
                _chart(
                    f"{tid}-chart",
                    "Individuos vivos por gremio ecológico",
                    tid,
                    "value",
                    [f"p{i}" for i in range(len(props))],
                    stacked=True,
                    y_label="Individuos",
                )
            )

    return {
        "id": "composicion",
        "title": "Composición",
        "description": (
            f"Individuos vivos en {ctx.m(k)} por especie, diseño florístico, cobertura, "
            "gremio ecológico y familia."
        ),
        "tables": tables,
        "charts": charts,
    }


# ── 2 y 3. Alturas y diametro de copa (misma forma) ──────────────────────────


def _measure_section(
    ctx: _Ctx, var: str, section_id: str, title: str, noun: str, unit: str, decimals: int
) -> dict:
    tables, charts = [], []
    k, prev = ctx.k, ctx.prev
    mk, mp = ctx.m(k), ctx.m(prev)
    notes_base = [
        f"Media de {noun} ({unit}) de los individuos vivos medidos en cada monitoreo.",
    ]
    if prev is not None:
        notes_base.append(
            f"Crecimiento = media {mk} − media {mp} de cada celda; CP = promedio de los "
            "crecimientos de la especie (definición del Anexo 1)."
        )

    for prop in ctx.properties:
        vk = ctx.alive_at(k, prop)
        vp = ctx.alive_at(prev, prop)
        vk_var, vp_var = vk.dropna(subset=[var]), vp.dropna(subset=[var])
        especies = sorted(set(vk_var["species"]) | set(vp_var["species"]))
        if not especies:
            continue

        # a) Por especie (resumen del predio, como «Alturas promedio - Predio …»)
        cols = [_text("species", "Especie"), _int("n", f"n {mk}")]
        if prev is not None:
            cols.append(_dec("prev", f"Media {mp}", decimals))
        cols.append(_dec("cur", f"Media {mk}", decimals))
        if prev is not None:
            cols.append(_dec("growth", "Crecimiento", decimals))
        cols += [
            _dec("sd", f"Desv. est. {mk}", decimals),
            _dec("min", f"Mín. {mk}", decimals),
            _dec("max", f"Máx. {mk}", decimals),
        ]
        rows = []
        for sp in especies:
            sk = vk_var.loc[vk_var["species"] == sp, var]
            sp_prev = vp_var.loc[vp_var["species"] == sp, var]
            row = {
                "species": sp,
                "n": int(sk.size),
                "cur": _mean(sk),
                "sd": float(sk.std()) if sk.size > 1 else None,
                "min": float(sk.min()) if sk.size else None,
                "max": float(sk.max()) if sk.size else None,
            }
            if prev is not None:
                row["prev"] = _mean(sp_prev)
                row["growth"] = (
                    row["cur"] - row["prev"]
                    if row["cur"] is not None and row["prev"] is not None
                    else None
                )
            rows.append(row)
        footer = {
            "species": "Total del predio",
            "n": int(vk_var[var].size),
            "cur": _mean(vk_var[var]),
            "sd": float(vk_var[var].std()) if vk_var[var].size > 1 else None,
            "min": float(vk_var[var].min()) if vk_var[var].size else None,
            "max": float(vk_var[var].max()) if vk_var[var].size else None,
        }
        if prev is not None:
            footer["prev"] = _mean(vp_var[var])
            footer["growth"] = (
                footer["cur"] - footer["prev"]
                if footer["cur"] is not None and footer["prev"] is not None
                else None
            )
        tid = f"{section_id}-{_slug(prop)}-especie"
        tables.append(
            _table(tid, f"{title} por especie — {prop}", cols, rows, [footer], prop, notes_base)
        )
        charts.append(
            _chart(
                f"{tid}-chart",
                f"{title} media por especie — {prop}",
                tid,
                "species",
                (["prev"] if prev is not None else []) + ["cur"],
                y_label=unit,
                prop=prop,
            )
        )

        # b) Por especie x diseno / cobertura
        for dim, (dim_label, dim_lower, _) in _DIMS.items():
            valores = ctx.dim_values(dim, prop)
            cols = [_text("species", "Especie")]
            for i, v in enumerate(valores):
                if prev is not None:
                    cols.append(_dec(f"c{i}_prev", mp, decimals, group=v))
                cols.append(_dec(f"c{i}_cur", mk, decimals, group=v))
            if prev is not None:
                cols.append(_dec("cp", "CP (crecimiento promedio)", decimals))
            mean_k = vk_var.groupby(["species", dim])[var].mean()
            mean_p = vp_var.groupby(["species", dim])[var].mean()
            rows = []
            growth_by_col: dict[int, list[float]] = {i: [] for i in range(len(valores))}
            for sp in especies:
                row = {"species": sp}
                crec = []
                for i, v in enumerate(valores):
                    cur = mean_k.get((sp, v))
                    row[f"c{i}_cur"] = cur
                    if prev is not None:
                        pre = mean_p.get((sp, v))
                        row[f"c{i}_prev"] = pre
                        if (
                            cur is not None
                            and pre is not None
                            and not (pd.isna(cur) or pd.isna(pre))
                        ):
                            crec.append(cur - pre)
                            growth_by_col[i].append(cur - pre)
                if prev is not None:
                    row["cp"] = sum(crec) / len(crec) if crec else None
                if any(row.get(f"c{i}_cur") is not None for i in range(len(valores))) or (
                    prev is not None
                    and any(row.get(f"c{i}_prev") is not None for i in range(len(valores)))
                ):
                    rows.append(row)
            footer_rows = []
            media = {"species": "Media general"}
            for i, v in enumerate(valores):
                media[f"c{i}_cur"] = _mean(vk_var.loc[vk_var[dim] == v, var])
                if prev is not None:
                    media[f"c{i}_prev"] = _mean(vp_var.loc[vp_var[dim] == v, var])
            footer_rows.append(media)
            if prev is not None:
                crec_row = {"species": f"Crecimiento promedio por {dim_lower}"}
                for i in range(len(valores)):
                    g = growth_by_col[i]
                    crec_row[f"c{i}_cur"] = sum(g) / len(g) if g else None
                cps = [r["cp"] for r in rows if r.get("cp") is not None]
                crec_row["cp"] = sum(cps) / len(cps) if cps else None
                footer_rows.append(crec_row)
            tid = f"{section_id}-{_slug(prop)}-{dim}"
            tables.append(
                _table(
                    tid,
                    f"{title} por especie y {dim_lower} — {prop}",
                    cols,
                    rows,
                    footer_rows,
                    prop,
                    notes_base,
                )
            )

    # c) Resumen del proyecto: predio x cobertura / diseno en Mk
    vk_all = ctx.alive_at(k).dropna(subset=[var])
    vp_all = ctx.alive_at(prev).dropna(subset=[var])
    for dim, (dim_label, dim_lower, _) in _DIMS.items():
        valores = sorted(ctx.frame[dim].unique())
        cols = [_text("property", "Predio")] + [
            _dec(f"c{i}", v, decimals) for i, v in enumerate(valores)
        ]
        if prev is not None:
            cols.append(_dec("total_prev", f"Total {mp}", decimals))
        cols.append(_dec("total", f"Total {mk}", decimals))
        rows = []
        for prop in ctx.properties:
            g = vk_all[vk_all["property"] == prop]
            row = {"property": prop, "total": _mean(g[var])}
            for i, v in enumerate(valores):
                row[f"c{i}"] = _mean(g.loc[g[dim] == v, var])
            if prev is not None:
                row["total_prev"] = _mean(vp_all.loc[vp_all["property"] == prop, var])
            rows.append(row)
        footer = {"property": "Total general", "total": _mean(vk_all[var])}
        for i, v in enumerate(valores):
            footer[f"c{i}"] = _mean(vk_all.loc[vk_all[dim] == v, var])
        if prev is not None:
            footer["total_prev"] = _mean(vp_all[var])
        tables.append(
            _table(
                f"{section_id}-proyecto-{dim}",
                f"{title} media por predio y {dim_lower} — proyecto ({mk})",
                cols,
                rows,
                [footer],
            )
        )

    return {
        "id": section_id,
        "title": title,
        "description": (
            f"{title} media por especie, diseño florístico y cobertura, "
            + (f"{mp} frente a {mk}." if prev is not None else f"en {mk}.")
        ),
        "tables": tables,
        "charts": charts,
    }


# ── 4. Supervivencia ─────────────────────────────────────────────────────────


def _status_counts(df: pd.DataFrame) -> tuple[int, int]:
    vivos = int((df["alive"] == True).sum())  # noqa: E712
    muertos = int((df["alive"] == False).sum())  # noqa: E712
    return vivos, muertos


def _survival(ctx: _Ctx) -> dict:
    tables, charts = [], []
    k, prev = ctx.k, ctx.prev
    mk, mp = ctx.m(k), ctx.m(prev)
    nota_n = (
        f"Filas marcadas: menos de {MIN_SAMPLE_FOR_PERCENT} árboles; el porcentaje "
        "es poco robusto."
    )
    for prop in ctx.properties:
        ak = ctx.at(k, prop)
        ap = ctx.at(prev, prop)
        if ak.empty:
            continue
        vivos_p, muertos_p = _status_counts(ak)

        # a) Por diseno y especie (tabla «TDS» del Anexo)
        cols = [
            _text("design", "Diseño florístico"),
            _text("species", "Especie"),
            _int("alive", "Vivos"),
            _int("dead", "Muertos"),
            _int("total", "Total"),
            _pct("pct", "% supervivencia"),
        ]
        rows = []
        for (d, sp), g in sorted(ak.groupby(["design", "species"]), key=lambda x: x[0]):
            v, m = _status_counts(g)
            if v + m == 0:
                continue
            rows.append(
                {
                    "design": d,
                    "species": sp,
                    "alive": v,
                    "dead": m,
                    "total": v + m,
                    "pct": _pct_of(v, v + m),
                    **_low_flag(v + m),
                }
            )
        tid = f"supervivencia-{_slug(prop)}-especie"
        tables.append(
            _table(
                tid,
                f"Supervivencia por diseño y especie — {prop} ({mk})",
                cols,
                rows,
                [
                    {
                        "design": "Total del predio",
                        "alive": vivos_p,
                        "dead": muertos_p,
                        "total": vivos_p + muertos_p,
                        "pct": _pct_of(vivos_p, vivos_p + muertos_p),
                    }
                ],
                prop,
                ["Supervivencia = vivos / (vivos + muertos) con estado registrado.", nota_n],
            )
        )

        # b) Por diseno / cobertura, con el monitoreo anterior
        for dim, (dim_label, dim_lower, _) in _DIMS.items():
            cols = [_text("value", dim_label), _int("total", f"Árboles {mk}")]
            if prev is not None:
                cols += [_int("alive_prev", f"Vivos {mp}"), _pct("pct_prev", f"% {mp}")]
            cols += [
                _int("alive", f"Vivos {mk}"),
                _int("dead", f"Muertos {mk}"),
                _pct("pct", f"% {mk}"),
                _pct("pct_property", "% del predio"),
            ]
            rows = []
            for v in ctx.dim_values(dim, prop):
                gv, gm = _status_counts(ak[ak[dim] == v])
                row = {
                    "value": v,
                    "total": gv + gm,
                    "alive": gv,
                    "dead": gm,
                    "pct": _pct_of(gv, gv + gm),
                    "pct_property": _pct_of(gv + gm, vivos_p + muertos_p),
                    **_low_flag(gv + gm),
                }
                if prev is not None:
                    pv, pm = _status_counts(ap[ap[dim] == v])
                    row["alive_prev"] = pv
                    row["pct_prev"] = _pct_of(pv, pv + pm)
                rows.append(row)
            footer = {
                "value": "Total del predio",
                "total": vivos_p + muertos_p,
                "alive": vivos_p,
                "dead": muertos_p,
                "pct": _pct_of(vivos_p, vivos_p + muertos_p),
                "pct_property": 100.0,
            }
            if prev is not None:
                pv, pm = _status_counts(ap)
                footer["alive_prev"] = pv
                footer["pct_prev"] = _pct_of(pv, pv + pm)
            tid = f"supervivencia-{_slug(prop)}-{dim}"
            tables.append(
                _table(tid, f"Supervivencia por {dim_lower} — {prop}", cols, rows, [footer], prop)
            )
            if dim == "design":
                charts.append(
                    _chart(
                        f"{tid}-chart",
                        f"Supervivencia por diseño florístico — {prop}",
                        tid,
                        "value",
                        (["pct_prev"] if prev is not None else []) + ["pct"],
                        percent=True,
                        y_label="% supervivencia",
                        prop=prop,
                    )
                )

    # c) Evolucion por predio, M1..Mk
    cols = [_text("property", "Predio"), _int("total", f"Árboles {mk}")]
    cols += [_pct(f"m{n}", f"% M{n}") for n in ctx.monitorings]
    rows = []
    for prop in ctx.properties:
        row = {"property": prop}
        v, m = _status_counts(ctx.at(k, prop))
        row["total"] = v + m
        for n in ctx.monitorings:
            vv, mm = _status_counts(ctx.at(n, prop))
            row[f"m{n}"] = _pct_of(vv, vv + mm)
        rows.append(row)
    footer = {"property": "Proyecto"}
    v, m = _status_counts(ctx.at(k))
    footer["total"] = v + m
    for n in ctx.monitorings:
        vv, mm = _status_counts(ctx.at(n))
        footer[f"m{n}"] = _pct_of(vv, vv + mm)
    tables.append(
        _table(
            "supervivencia-proyecto", "Supervivencia por predio y monitoreo", cols, rows, [footer]
        )
    )
    charts.append(
        _chart(
            "supervivencia-proyecto-chart",
            "Evolución de la supervivencia por predio",
            "supervivencia-proyecto",
            "property",
            [f"m{n}" for n in ctx.monitorings],
            percent=True,
            y_label="% supervivencia",
        )
    )
    return {
        "id": "supervivencia",
        "title": "Supervivencia",
        "description": (
            "Porcentaje de individuos vivos por especie, diseño florístico, cobertura "
            f"y predio en {mk}."
        ),
        "tables": tables,
        "charts": charts,
    }


# ── 5. Estado fitosanitario ──────────────────────────────────────────────────

_PHYTO_KEYS = {"Bueno": "good", "Regular": "fair", "Malo": "poor"}


def _phyto_counts(df: pd.DataFrame) -> dict:
    vivos = df[df["alive"] == True]  # noqa: E712
    out = {_PHYTO_KEYS[s]: int((vivos["phyto"] == s).sum()) for s in PHYTOSANITARY_STATES}
    out["total"] = sum(out.values())
    out["missing"] = int(vivos["phyto"].isna().sum())
    for s in PHYTOSANITARY_STATES:
        out[f"pct_{_PHYTO_KEYS[s]}"] = _pct_of(out[_PHYTO_KEYS[s]], out["total"])
    return out


def _phyto_cols() -> list[dict]:
    cols = [_int(_PHYTO_KEYS[s], s) for s in PHYTOSANITARY_STATES]
    cols.append(_int("total", "Total evaluados"))
    cols += [_pct(f"pct_{_PHYTO_KEYS[s]}", f"% {s}") for s in PHYTOSANITARY_STATES]
    cols.append(_int("missing", "Vivos sin registro"))
    return cols


def _phytosanitary(ctx: _Ctx) -> dict:
    tables, charts = [], []
    k = ctx.k
    mk = ctx.m(k)
    pct_series = [f"pct_{_PHYTO_KEYS[s]}" for s in PHYTOSANITARY_STATES]
    for prop in ctx.properties:
        ak = ctx.at(k, prop)
        if ak.empty:
            continue
        total_p = _phyto_counts(ak)

        # a) Por diseno y especie, con % por especie, por diseno y por predio
        cols = [_text("design", "Diseño florístico"), _text("species", "Especie")] + _phyto_cols()
        cols += [_pct("pct_design", "% del diseño"), _pct("pct_property", "% del predio")]
        rows = []
        for d, gd in sorted(ak.groupby("design"), key=lambda x: x[0]):
            total_d = _phyto_counts(gd)["total"]
            for sp, g in sorted(gd.groupby("species"), key=lambda x: x[0]):
                c = _phyto_counts(g)
                if c["total"] == 0 and c["missing"] == 0:
                    continue
                rows.append(
                    {
                        "design": d,
                        "species": sp,
                        **c,
                        "pct_design": _pct_of(c["total"], total_d),
                        "pct_property": _pct_of(c["total"], total_p["total"]),
                        **_low_flag(c["total"]),
                    }
                )
        tid = f"estado-{_slug(prop)}-especie"
        tables.append(
            _table(
                tid,
                f"Estado fitosanitario por diseño y especie — {prop} ({mk})",
                cols,
                rows,
                [
                    {
                        "design": "Total del predio",
                        **total_p,
                        "pct_design": None,
                        "pct_property": 100.0,
                    }
                ],
                prop,
                ["Solo individuos vivos con estado registrado."],
            )
        )

        # b) Por diseno / cobertura
        for dim, (dim_label, dim_lower, _) in _DIMS.items():
            cols = [_text("value", dim_label)] + _phyto_cols()
            rows = []
            for v in ctx.dim_values(dim, prop):
                c = _phyto_counts(ak[ak[dim] == v])
                rows.append({"value": v, **c, **_low_flag(c["total"])})
            tid = f"estado-{_slug(prop)}-{dim}"
            tables.append(
                _table(
                    tid,
                    f"Estado fitosanitario por {dim_lower} — {prop} ({mk})",
                    cols,
                    rows,
                    [{"value": "Total del predio", **total_p}],
                    prop,
                )
            )
            if dim == "design":
                charts.append(
                    _chart(
                        f"{tid}-chart",
                        f"Estado fitosanitario por diseño florístico — {prop}",
                        tid,
                        "value",
                        pct_series,
                        stacked=True,
                        percent=True,
                        y_label="% de individuos",
                        prop=prop,
                    )
                )

    # c) Estado global por predio (Mk) y evolucion del % Bueno
    cols = [_text("property", "Predio")] + _phyto_cols()
    rows = [{"property": p, **_phyto_counts(ctx.at(k, p))} for p in ctx.properties]
    tables.append(
        _table(
            "estado-global",
            f"Estado fitosanitario global por predio ({mk})",
            cols,
            rows,
            [{"property": "Proyecto", **_phyto_counts(ctx.at(k))}],
        )
    )
    charts.append(
        _chart(
            "estado-global-chart",
            "Estado fitosanitario por predio",
            "estado-global",
            "property",
            pct_series,
            stacked=True,
            percent=True,
            y_label="% de individuos",
        )
    )
    cols = [_text("property", "Predio")] + [_pct(f"m{n}", f"% Bueno M{n}") for n in ctx.monitorings]
    rows = []
    for p in ctx.properties:
        row = {"property": p}
        for n in ctx.monitorings:
            row[f"m{n}"] = _phyto_counts(ctx.at(n, p))["pct_good"]
        rows.append(row)
    footer = {"property": "Proyecto"}
    for n in ctx.monitorings:
        footer[f"m{n}"] = _phyto_counts(ctx.at(n))["pct_good"]
    tables.append(
        _table(
            "estado-evolucion", "Evolución del % en buen estado por predio", cols, rows, [footer]
        )
    )
    return {
        "id": "estado_fitosanitario",
        "title": "Estado fitosanitario",
        "description": (
            f"Bueno / Regular / Malo de los individuos vivos en {mk}, por especie, "
            "diseño, cobertura y predio."
        ),
        "tables": tables,
        "charts": charts,
    }


# ── 6. Edades (categoria de desarrollo) ──────────────────────────────────────


def _with_class(df: pd.DataFrame) -> pd.DataFrame:
    vivos = df[df["alive"] == True]  # noqa: E712
    return vivos.assign(
        dev=vivos["height"].map(lambda h: development_class(None if pd.isna(h) else h))
    )


def _development(ctx: _Ctx) -> dict:
    tables, charts = [], []
    k, prev = ctx.k, ctx.prev
    mk, mp = ctx.m(k), ctx.m(prev)
    clases = [c.name for c in DEVELOPMENT_CLASSES]
    rangos = "; ".join(
        f"{c.name}: {'> 6' if c.upper_m is None else '≤ ' + format(c.upper_m, 'g')} m"
        for c in DEVELOPMENT_CLASSES
    )
    for prop in ctx.properties:
        ck = _with_class(ctx.at(k, prop))
        cp = _with_class(ctx.at(prev, prop))
        if ck.empty and cp.empty:
            continue
        for dim, (dim_label, dim_lower, _) in _DIMS.items():
            cols = [_text("value", dim_label)]
            for j, c in enumerate(clases):
                if prev is not None:
                    cols.append(_int(f"k{j}_prev", mp, group=c))
                cols.append(_int(f"k{j}_cur", mk, group=c))
            if prev is not None:
                cols.append(_int("total_prev", f"Total {mp}"))
            cols.append(_int("total", f"Total {mk}"))
            rows = []
            for v in ctx.dim_values(dim, prop):
                gk, gp = ck[ck[dim] == v], cp[cp[dim] == v]
                row = {"value": v, "total": int(gk["dev"].notna().sum())}
                for j, c in enumerate(clases):
                    row[f"k{j}_cur"] = int((gk["dev"] == c).sum())
                    if prev is not None:
                        row[f"k{j}_prev"] = int((gp["dev"] == c).sum())
                if prev is not None:
                    row["total_prev"] = int(gp["dev"].notna().sum())
                rows.append(row)
            footer = {"value": "Total del predio", "total": int(ck["dev"].notna().sum())}
            for j, c in enumerate(clases):
                footer[f"k{j}_cur"] = int((ck["dev"] == c).sum())
                if prev is not None:
                    footer[f"k{j}_prev"] = int((cp["dev"] == c).sum())
            if prev is not None:
                footer["total_prev"] = int(cp["dev"].notna().sum())
            tid = f"edades-{_slug(prop)}-{dim}"
            tables.append(
                _table(
                    tid,
                    f"Categoría de desarrollo por {dim_lower} — {prop}",
                    cols,
                    rows,
                    [footer],
                    prop,
                    [f"Individuos vivos por rango de altura total ({rangos})."],
                )
            )
            if dim == "design":
                charts.append(
                    _chart(
                        f"{tid}-chart",
                        f"Categoría de desarrollo por diseño florístico — {prop} ({mk})",
                        tid,
                        "value",
                        [f"k{j}_cur" for j in range(len(clases))],
                        stacked=True,
                        y_label="Individuos",
                        prop=prop,
                    )
                )

    # Individuos por categoria y monitoreo, todo el proyecto (M1..Mk)
    cols = [_text("category", "Categoría")] + [_int(f"m{n}", f"M{n}") for n in ctx.monitorings]
    rows = []
    muertos = {"category": "Muertos"}
    for n in ctx.monitorings:
        muertos[f"m{n}"] = _status_counts(ctx.at(n))[1]
    rows.append(muertos)
    por_monitoreo = {n: _with_class(ctx.at(n)) for n in ctx.monitorings}
    for c in clases:
        row = {"category": c}
        for n in ctx.monitorings:
            row[f"m{n}"] = int((por_monitoreo[n]["dev"] == c).sum())
        rows.append(row)
    sin = {"category": "Vivos sin altura"}
    for n in ctx.monitorings:
        sin[f"m{n}"] = int(por_monitoreo[n]["dev"].isna().sum())
    rows.append(sin)
    tables.append(
        _table(
            "edades-proyecto",
            "Individuos por categoría de desarrollo y monitoreo — proyecto",
            cols,
            rows,
            notes=[
                f"Rangos: {rangos}. El Anexo 1 nombra subadulto y adulto sin rango: se agrupan en "
                "«Mayor de 6 m»."
            ],
        )
    )
    charts.append(
        _chart(
            "edades-proyecto-chart",
            "Individuos por categoría de desarrollo",
            "edades-proyecto",
            "category",
            [f"m{n}" for n in ctx.monitorings],
            y_label="Individuos",
        )
    )
    return {
        "id": "edades",
        "title": "Edades (categoría de desarrollo)",
        "description": "Clasificación por rango de altura total, "
        + (f"{mp} frente a {mk}." if prev is not None else f"en {mk}."),
        "tables": tables,
        "charts": charts,
    }


# ── 7. DAP ───────────────────────────────────────────────────────────────────


def _dap(ctx: _Ctx) -> dict:
    descripcion = (
        "Diámetro a la altura del pecho (cm) de los individuos que superan el umbral de medición; "
        "los que no lo alcanzan no entran en la media."
    )
    medidos = pd.concat([ctx.alive_at(ctx.k), ctx.alive_at(ctx.prev)])["dap"].notna().any()
    if not medidos:
        return {
            "id": "dap",
            "title": "DAP",
            "description": descripcion,
            "tables": [],
            "charts": [],
            "notes": ["Ningún individuo supera el umbral de DAP en los monitoreos analizados."],
        }
    section = _measure_section(ctx, "dap", "dap", "DAP", "DAP", "cm", 2)
    section["description"] = descripcion
    return section


# ── Entrada publica ──────────────────────────────────────────────────────────


# ── 8. Comparacion entre monitoreos (E4) ─────────────────────────────────────

_PHYTO_TO = (*PHYTOSANITARY_STATES, "Muerto", "Sin dato")


def _to_key(destino: str) -> str:
    """Clave de columna para un estado de llegada (`Sin dato` -> to_sin_dato)."""
    return "to_" + _slug(destino).replace("-", "_")


def _interval_stats(par: pd.DataFrame, years: float | None) -> dict:
    """Las cifras del intervalo para un grupo de arboles ya emparejados."""
    vivos_antes = len(par)
    muertos = int((par["alive_cur"] != True).sum())  # noqa: E712
    medidos = par.dropna(subset=["growth"])
    crecimiento = _mean(medidos["growth"])
    fila = {
        "alive_prev": vivos_antes,
        "deaths": muertos,
        "mortality": _pct_of(muertos, vivos_antes),
        "measured": int(len(medidos)),
        "stagnant": int((medidos["growth"] <= STAGNATION_THRESHOLD_M).sum()),
        "contractions": int((medidos["growth"] < -MAX_CONTRACTION_M).sum()),
        "growth": crecimiento,
    }
    fila["stagnant_pct"] = _pct_of(fila["stagnant"], fila["measured"])
    if years:
        fila["growth_year"] = None if crecimiento is None else crecimiento / years
    return fila


def _interval_cols(years: float | None, first: dict) -> list[dict]:
    cols = [
        first,
        _int("alive_prev", "Vivos al inicio"),
        _int("deaths", "Muertos"),
        _pct("mortality", "Mortalidad"),
        _int("measured", "Medidos en ambos"),
        _int("stagnant", "Estancados"),
        _pct("stagnant_pct", "% estancados"),
        _int("contractions", "Contracciones"),
        _dec("growth", "Crecimiento medio (m)", 3),
    ]
    if years:
        cols.append(_dec("growth_year", "Crecimiento (m/año)", 3))
    return cols


def _comparison(ctx: _Ctx) -> dict:
    """Que cambio entre Mk-1 y Mk: la vision central del producto (E4)."""
    k, prev = ctx.k, ctx.prev
    mk, mp = ctx.m(k), ctx.m(prev)
    if prev is None:
        return {
            "id": "comparacion",
            "title": "Comparación entre monitoreos",
            "description": "Qué cambió entre un monitoreo y el siguiente.",
            "notes": [
                "Este es el primer monitoreo del proyecto: no hay intervalo que "
                "comparar todavía. La comparación aparece a partir del segundo."
            ],
            "tables": [],
            "charts": [],
        }

    years = ctx.interval_years
    par = ctx.pairs()
    notes = [
        f"Solo entran los árboles vivos en {mp} y censados también en {mk}: "
        "quien ya estaba muerto no puede morir ni crecer otra vez.",
        f"Estancado = creció {STAGNATION_THRESHOLD_M * 100:.0f} cm o menos; "
        f"contracción = perdió más de {MAX_CONTRACTION_M * 100:.0f} cm de altura.",
    ]
    if years:
        notes.append(
            f"El intervalo mide {years:.2f} años, así que el crecimiento también "
            "se presenta anualizado (m/año)."
        )
    else:
        notes.append(
            "Sin la fecha de uno de los dos monitoreos no se puede anualizar el "
            "crecimiento: registre las fechas para comparar intervalos de "
            "distinta duración."
        )

    tables, charts = [], []

    # a) Resumen por predio, con el proyecto entero en el pie
    filas = []
    for prop in ctx.properties:
        sub = par[par["property"] == prop]
        if sub.empty:
            continue
        filas.append({"property": prop, **_interval_stats(sub, years), **_low_flag(len(sub))})
    total = {"property": "Proyecto", **_interval_stats(par, years)}
    resumen = _table(
        "comparacion-resumen",
        f"Qué pasó entre {mp} y {mk}, por predio",
        _interval_cols(years, _text("property", "Predio")),
        filas,
        footer=[total],
        notes=notes,
    )
    tables.append(resumen)
    charts.append(
        _chart(
            "comparacion-mortalidad-predio",
            f"Mortalidad y estancamiento del intervalo {mp} → {mk}",
            resumen["id"],
            "property",
            ["mortality", "stagnant_pct"],
            y_label="%",
            percent=True,
        )
    )

    # b) Por especie, dentro de cada predio (donde se decide que replantar)
    for prop in ctx.properties:
        sub = par[par["property"] == prop]
        if sub.empty:
            continue
        filas_sp = []
        for sp in sorted(sub["species"].unique()):
            g = sub[sub["species"] == sp]
            filas_sp.append({"species": sp, **_interval_stats(g, years), **_low_flag(len(g))})
        tabla = _table(
            f"comparacion-especie-{_slug(prop)}",
            f"Intervalo {mp} → {mk} por especie — {prop}",
            _interval_cols(years, _text("species", "Especie")),
            filas_sp,
            prop=prop,
            notes=[f"{len(sub)} árboles vivos en {mp}."],
        )
        tables.append(tabla)
        charts.append(
            _chart(
                f"comparacion-crecimiento-{_slug(prop)}",
                f"Crecimiento medio por especie — {prop}",
                tabla["id"],
                "species",
                ["growth"],
                y_label="m",
                prop=prop,
            )
        )

    # c) Por parcela: si el problema es del sitio y no de la especie
    filas_plot = []
    for plot in sorted(x for x in par["plot"].dropna().unique()):
        g = par[par["plot"] == plot]
        filas_plot.append({"plot": plot, **_interval_stats(g, years), **_low_flag(len(g))})
    if filas_plot:
        tables.append(
            _table(
                "comparacion-parcela",
                f"Intervalo {mp} → {mk} por parcela",
                _interval_cols(years, _text("plot", "Parcela")),
                filas_plot,
                notes=[
                    "La parcela es la unidad de muestreo del archivo "
                    "(«Código de unidad muestreo»)."
                ],
            )
        )

    # d) Transicion fitosanitaria: de que estado a cual
    transicion = []
    for antes in PHYTOSANITARY_STATES:
        sub = par[par["phyto_prev"] == antes]
        fila = {"from": antes, "total": int(len(sub))}
        vivos = sub[sub["alive_cur"] == True]  # noqa: E712
        for destino in _PHYTO_TO:
            if destino == "Muerto":
                n = int((sub["alive_cur"] != True).sum())  # noqa: E712
            elif destino == "Sin dato":
                n = int(vivos["phyto_cur"].isna().sum())
            else:
                n = int((vivos["phyto_cur"] == destino).sum())
            fila[_to_key(destino)] = n
        transicion.append(fila)
    if any(f["total"] for f in transicion):
        tabla_estado = _table(
            "comparacion-estado",
            f"Cambio de estado fitosanitario {mp} → {mk}",
            [
                _text("from", f"Estado en {mp}"),
                _int("total", f"Árboles en {mp}"),
                *[_int(_to_key(d), d, group=f"Estado en {mk}") for d in _PHYTO_TO],
            ],
            transicion,
            notes=[
                "Cada fila reparte los árboles que estaban en ese estado según "
                f"cómo llegaron a {mk}. La diagonal es «siguió igual»."
            ],
        )
        tables.append(tabla_estado)
        charts.append(
            _chart(
                "comparacion-estado-chart",
                f"A dónde fue cada estado de {mp}",
                tabla_estado["id"],
                "from",
                [_to_key(d) for d in _PHYTO_TO],
                stacked=True,
                y_label="árboles",
            )
        )

    return {
        "id": "comparacion",
        "title": f"Comparación {mp} → {mk}",
        "description": (
            f"Qué le pasó a cada árbol entre {mp} y {mk}: quién murió, quién creció "
            "y quién se quedó igual."
        ),
        "notes": [],
        "tables": tables,
        "charts": charts,
    }


def _summary(ctx: _Ctx) -> list[dict]:
    ak = ctx.at(ctx.k)
    vivos, muertos = _status_counts(ak)
    vk = ctx.alive_at(ctx.k)
    return [
        {
            "key": "trees",
            "label": f"Árboles registrados en {ctx.m(ctx.k)}",
            "kind": "int",
            "value": len(ak),
        },
        {"key": "alive", "label": "Vivos", "kind": "int", "value": vivos},
        {"key": "dead", "label": "Muertos", "kind": "int", "value": muertos},
        {
            "key": "survival",
            "label": "Supervivencia",
            "kind": "percent",
            "decimals": 1,
            "value": _clean(_pct_of(vivos, vivos + muertos)),
        },
        {
            "key": "species",
            "label": "Especies vivas",
            "kind": "int",
            "value": int(vk["species"].nunique()),
        },
        {"key": "properties", "label": "Predios", "kind": "int", "value": len(ctx.properties)},
        {
            "key": "height",
            "label": "Altura media",
            "kind": "decimal",
            "decimals": 2,
            "unit": "m",
            "value": _clean(_mean(vk["height"])),
        },
        *_interval_summary(ctx),
    ]


def _interval_summary(ctx: _Ctx) -> list[dict]:
    """Las dos cifras del intervalo que encabezan la comparacion (E4).

    Solo aparecen cuando hay intervalo: en el primer monitoreo no existen, y
    un cero seria una afirmacion falsa (nadie murio porque nada ha pasado).
    """
    if ctx.prev is None:
        return []
    par = ctx.pairs()
    if par.empty:
        return []
    stats = _interval_stats(par, ctx.interval_years)
    intervalo = f"{ctx.m(ctx.prev)} → {ctx.m(ctx.k)}"
    resumen = [
        {
            "key": "interval_mortality",
            "label": f"Mortalidad {intervalo}",
            "kind": "percent",
            "decimals": 1,
            "value": _clean(stats["mortality"]),
        },
        {
            "key": "interval_growth",
            "label": f"Crecimiento medio {intervalo}",
            "kind": "decimal",
            "decimals": 3,
            "unit": "m",
            "value": _clean(stats["growth"]),
        },
    ]
    if "growth_year" in stats:
        resumen.append(
            {
                "key": "interval_growth_year",
                "label": "Crecimiento anualizado",
                "kind": "decimal",
                "decimals": 3,
                "unit": "m/año",
                "value": _clean(stats["growth_year"]),
            }
        )
    return resumen


def analyze_monitoring(
    trees: Sequence[Tree],
    observations: Sequence[Observation],
    number: int,
    dates: Mapping[int, date] | None = None,
) -> dict:
    """Las 7 hojas del Anexo 1 para el monitoreo `number`, frente al anterior.

    Raises:
        ValueError: si el proyecto no tiene observaciones en ese monitoreo.
    """
    frame = build_frame(trees, observations)
    if frame.empty or number not in set(frame["monitoring"].unique()):
        raise ValueError(f"El monitoreo M{number} no tiene observaciones.")
    ctx = _Ctx(frame, number, dates)
    return {
        "analysis_version": ANALYSIS_VERSION,
        "monitoring": number,
        "previous": ctx.prev,
        "monitorings": ctx.monitorings,
        "properties": ctx.properties,
        "summary": _summary(ctx),
        "sections": [
            _composition(ctx),
            _measure_section(ctx, "height", "alturas", "Altura", "altura total", "m", 2),
            _measure_section(ctx, "crown", "copa", "Diámetro de copa", "diámetro de copa", "m", 2),
            _survival(ctx),
            _phytosanitary(ctx),
            _development(ctx),
            _dap(ctx),
            _comparison(ctx),
        ],
    }


class ExploratoryAnalysisEngine:
    """El motor tal como lo consumen los casos de uso (inyectado por parametro)."""

    version = ANALYSIS_VERSION

    def fingerprint(
        self,
        trees: Sequence[Tree],
        observations: Sequence[Observation],
        dates: Mapping[int, date] | None = None,
    ) -> str:
        return input_hash(trees, observations, dates)

    def analyze(
        self,
        trees: Sequence[Tree],
        observations: Sequence[Observation],
        number: int,
        dates: Mapping[int, date] | None = None,
    ) -> dict:
        return analyze_monitoring(trees, observations, number, dates)
