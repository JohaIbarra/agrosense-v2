"""Experimento E (exploratorio): ¿el modelo GENERAL de mortalidad transfiere entre proyectos?

Validación dejando un proyecto fuera (LOPO) con 3 proyectos: Anexo 1 (referencia),
Werden 2018 y Werden 2020 (Costa Rica, CC0, Zenodo 4956588 / 4968196).
Solo variables que existen en los tres: percentil de altura en la ola (h_pct) y
«no creció en el intervalo previo» (estanco_lag, igualdad en mm como E7).
Etiqueta: vivo y medido en t → muerto en t+1. Métrica: PR-AUC y × azar por intervalo.
Uso (desde backend/): python ../docs/spikes/exp_e.py DIR_CON_w18.csv_Y_w20.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score as ap

from agrosense.adapters.ingester.excel_source import ExcelCampaignSource

d = Path(sys.argv[1])
w18 = pd.read_csv(d / "w18.csv")
W18 = [1, 4, 8, 10, 11, 12, 13]  # censos con altura
w18 = w18[w18.surveyNumber.isin(W18)].assign(
    tree=lambda x: x.seedlingID, k=lambda x: x.surveyNumber.map({s: i for i, s in enumerate(W18)}),
    h=lambda x: x.height_cm / 100, alive=lambda x: x.survival == 1)
w20 = pd.read_csv(d / "w20.csv").assign(
    tree=lambda x: x.seedlingID, k=lambda x: x.surveyNumber - 1, h=lambda x: x.height / 100,
    alive=lambda x: x.survival == 1)
raw = Path("data/raw/anexo1.xlsx")
c = ExcelCampaignSource().read(raw.read_bytes(), raw.name)
ref = pd.DataFrame([{"tree": o.tree_id, "k": o.campaign - 1, "alive": o.alive, "h": o.height_m}
                    for o in c.observations])
PROJECTS = {"Anexo 1": ref, "Werden 2018": w18, "Werden 2020": w20}
FEATS = ["h_pct", "estanco_lag"]


def intervals(df):
    by_k = {k: g.drop_duplicates("tree").set_index("tree") for k, g in df.groupby("k")}
    out = []
    for k in sorted(by_k)[:-1]:
        a, b = by_k[k], by_k.get(k + 1)
        a = a[(a.alive == True) & a.h.notna()].copy()  # noqa: E712
        a = a[a.index.isin(b.index)]
        nxt = b.loc[a.index]
        ok = nxt.alive.notna()
        a, y = a[ok], (nxt.alive[ok] == False).astype(int)  # noqa: E712
        a["h_pct"] = a.h.rank(pct=True)
        prev = by_k.get(k - 1)
        hp = prev.h.reindex(a.index) if prev is not None else pd.Series(np.nan, index=a.index)
        a["estanco_lag"] = np.where(hp.isna(), np.nan, (np.round(a.h * 1000) <= np.round(hp * 1000)))
        a["k"], a["y"] = k, y.values
        out.append(a.reset_index()[["tree", "k", "y"] + FEATS])
    return pd.concat(out, ignore_index=True)


data = {n: intervals(df) for n, df in PROJECTS.items()}


def prep(df, med):
    X = df[FEATS].copy()
    X["lag_missing"] = X.estanco_lag.isna().astype(float)
    X["estanco_lag"] = X.estanco_lag.fillna(med)
    return X.values


for feats_name, cols in (("h_pct", [0]), ("h_pct + estanco_lag", [0, 1, 2])):
    print(f"\n=== Modelo general con {feats_name}")
    for held in PROJECTS:
        tr = pd.concat([v for n, v in data.items() if n != held])
        te = data[held]
        med = tr.estanco_lag.median()
        m = LogisticRegression(C=1.0, max_iter=2000).fit(prep(tr, med)[:, cols], tr.y)
        s = m.predict_proba(prep(te, med)[:, cols])[:, 1]
        cells = []
        for k, g in te.assign(s=s).groupby("k"):
            if g.y.nunique() == 2:
                cells.append(f"t{k}: {ap(g.y, g.s) / g.y.mean():.1f}×(prev {g.y.mean():.2f})")
        print(f"  fuera {held:<12} coef {np.round(m.coef_[0], 2)}  " + " · ".join(cells))
