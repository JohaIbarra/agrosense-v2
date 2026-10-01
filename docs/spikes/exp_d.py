"""Experimento D (exploratorio): ¿desde cuántos monitoreos conviene el modelo PROPIO del proyecto?

Proyecto: Werden et al. 2018 (Costa Rica, bosque seco, CC0, Zenodo 4956588). La altura solo
se mide en los censos 1, 4, 8, 10, 11, 12, 13 (los demás son solo supervivencia), así que
esos 7 son los «monitoreos». En el monitoreo k se predice el intervalo k→k+1:
  * modelo propio: logística entrenada con TODOS los intervalos ya cerrados del proyecto (≤ k).
  * modelo general: entrenado solo con el proyecto de referencia (Anexo 1) y aplicado sin
    reentrenar. Única variable transferible: percentil de altura dentro de la ola.
Objetivos: estancamiento (altura t+1 ≤ altura t, vivos en ambos) y muerte (vivo en t, muerto en t+1).
Uso: python exp_d.py RUTA_w18.csv  (desde backend/)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score as ap
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

WAVES = [1, 4, 8, 10, 11, 12, 13]

# ---- Werden 2018 → formato largo común: tree, k, date, h, diam, alive, species, treatment, block
w = pd.read_csv(sys.argv[1])
w = w[w.surveyNumber.isin(WAVES)].assign(
    k=lambda d: d.surveyNumber.map({s: i for i, s in enumerate(WAVES)}),
    date=lambda d: pd.to_datetime(d.dateMeasured, format="%d-%b-%y"),
    h=lambda d: d.height_cm, diam=lambda d: d.diamBot_mm, alive=lambda d: d.survival == 1,
    species=lambda d: d.spCode, tree=lambda d: d.seedlingID,
)[["tree", "k", "date", "h", "diam", "alive", "species", "treatment", "block"]]

# ---- Anexo 1 al mismo formato (sin diámetro de base; solo se usa el percentil de altura)
raw = Path("data/raw/anexo1.xlsx")
c = ExcelCampaignSource().read(raw.read_bytes(), raw.name)
ref = pd.DataFrame([{"tree": o.tree_id, "k": o.campaign - 1, "alive": o.alive,
                     "h": None if o.height_m is None else 100 * o.height_m} for o in c.observations])


def intervals(df, target):
    """Filas (features en k, etiqueta en k+1) para todos los intervalos del proyecto."""
    out = []
    by_k = {k: g.set_index("tree") for k, g in df.groupby("k")}
    for k in sorted(by_k)[:-1]:
        a, b = by_k[k], by_k.get(k + 1)
        if b is None:
            continue
        a = a[(a.alive == True) & a.h.notna()].copy()  # noqa: E712 (alive puede ser None)
        a = a[a.index.isin(b.index)]
        nxt = b.loc[a.index]
        if target == "muerte":
            ok = nxt.alive.notna()
            y = (nxt.alive == False)  # noqa: E712
        else:
            ok = (nxt.alive == True) & nxt.h.notna()  # noqa: E712
            y = nxt.h <= a.h
        a, y = a[ok], y[ok].astype(int)
        a["h_pct"] = a.h.rank(pct=True)
        prev = by_k.get(k - 1)
        a["dh_lag"] = (a.h - prev.h.reindex(a.index)) if prev is not None else np.nan
        a["k"], a["y"] = k, y.values
        out.append(a.reset_index())
    return pd.concat(out, ignore_index=True)


def logit(num, cat):
    pre = ColumnTransformer([("n", StandardScaler(), num)]
                            + ([("c", OneHotEncoder(handle_unknown="ignore"), cat)] if cat else []))
    return make_pipeline(pre, LogisticRegression(C=1.0, max_iter=2000))


def fit_pred(tr, te, num, cat):
    tr = tr.copy()
    te = te.copy()
    for col in num:  # dh_lag no existe en la 1.ª ola: imputar con la mediana de ENTRENAMIENTO
        med = tr[col].median() if tr[col].notna().any() else 0.0
        tr[col], te[col] = tr[col].fillna(med), te[col].fillna(med)
    if tr.y.nunique() < 2:
        return None
    return logit(num, cat).fit(tr[num + cat], tr.y).predict_proba(te[num + cat])[:, 1]


SIZE = ["h", "diam", "esbeltez"]
VARIANTS = {
    "propio: tamaño": (SIZE, []),
    "propio: tamaño+especie+tratamiento": (SIZE, ["species", "treatment"]),
    "propio: + historia (dh_lag)": (SIZE + ["dh_lag"], ["species", "treatment"]),
}

dates = w.groupby("k").date.median()
for target in ("estancamiento", "muerte"):
    W = intervals(w, target)
    W["esbeltez"] = W.h / W.diam.where(W.diam > 0)
    W["esbeltez"] = W.esbeltez.fillna(W.esbeltez.median())
    W["diam"] = W.diam.fillna(W.diam.median())
    R = intervals(ref, target)
    general = logit(["h_pct"], []).fit(R[["h_pct"]], R.y)
    sign = "más pequeño ⇒ más riesgo" if general[-1].coef_[0][0] < 0 else "más grande ⇒ más riesgo"
    print(f"\n=== {target.upper()} · modelo general (Anexo 1, n={len(R)}): {sign}")
    print(f"{'k→k+1':<8}{'meses':>6}{'n':>6}{'pos':>5}{'prev':>6}  "
          + "".join(f"{s:>16}" for s in ["general", "tamaño", "+esp+trat", "+historia"]))
    for k in range(1, len(WAVES) - 1):
        te, tr = W[W.k == k], W[W.k < k]
        if te.y.nunique() < 2:
            continue
        prev = te.y.mean()
        cells = [ap(te.y, general.predict_proba(te[["h_pct"]])[:, 1])]
        for num, cat in VARIANTS.values():
            p = fit_pred(tr, te, num, cat)
            cells.append(np.nan if p is None else ap(te.y, p))
        months = (dates[k + 1] - dates[k]).days / 30.4
        print(f"{WAVES[k]:>2}→{WAVES[k+1]:<5}{months:>6.1f}{len(te):>6}{te.y.sum():>5}{prev:>6.2f}  "
              + "".join(f"{v:>9.3f} ({v/prev:3.1f}×)" for v in cells))
