"""Experimento B (exploratorio): «creció menos de lo esperado para su especie y tamaño, por mes».

Referencia de crecimiento esperado ajustada SOLO con el intervalo de entrenamiento
(M2→M3). Umbral de «bajo lo esperado» = percentil 20 de los residuos de ese mismo
intervalo. Se entrena en t=2 y se evalúa en t=3, como el modelo actual.
"""
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression

from agrosense.adapters.ingester.excel_source import ExcelCampaignSource
from agrosense.domain.stall_rules import stall_label
from agrosense.ml.evaluation import pr_auc
from agrosense.ml.preprocessing import fit_preprocessor, transform
from agrosense.ml.stall_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, build_wave
from agrosense.ml.train_stall import StallTrainConfig, fit_logistic

MONTHS = 4.0  # intervalo entre monitoreos en el proyecto de referencia
raw = Path("data/raw/anexo1.xlsx")
c = ExcelCampaignSource().read(raw.read_bytes(), raw.name)
obs = {(o.tree_id, o.campaign): o for o in c.observations}
species = {t.tree_id: (t.species or "?").strip().casefold() for t in c.trees}
cfg = StallTrainConfig()


def interval(t):
    """(tree_id, altura_t, crecimiento cm/mes) para árboles vivos y medidos en t y t+1."""
    out = []
    for (tid, camp), o in obs.items():
        if camp != t:
            continue
        nxt = obs.get((tid, t + 1))
        if stall_label(o, nxt) is None:
            continue
        out.append((tid, o.height_m, 100 * (nxt.height_m - o.height_m) / MONTHS))
    return out


ref_rows = interval(2)
sp_levels = sorted({species[t] for t, _, _ in ref_rows})


def design(rows):
    X = []
    for tid, h, _ in rows:
        one = [1.0 if species[tid] == s else 0.0 for s in sp_levels]
        X.append(one + [np.log(max(h, 0.05))])
    return np.asarray(X)


ref = LinearRegression().fit(design(ref_rows), [g for _, _, g in ref_rows])


def residuals(t):
    rows = interval(t)
    return {tid: g - e for (tid, _, g), e in zip(rows, ref.predict(design(rows)))}


res = {t: residuals(t) for t in (1, 2, 3)}
threshold = np.percentile(list(res[2].values()), 20)
print(f"Crecimiento esperado: especie + log(altura), ajustado en M2→M3 (n={len(ref_rows)}); "
      f"R² = {ref.score(design(ref_rows), [g for _, _, g in ref_rows]):.2f}")
print(f"'Bajo lo esperado' = residuo < {threshold:.2f} cm/mes (percentil 20 del entrenamiento)")

# Diagnóstico clave: ¿el bajo rendimiento de un árbol se repite de un intervalo al siguiente?
print("\n1) Repetibilidad del residuo del mismo árbol (Spearman)")
for a, b in ((1, 2), (2, 3), (1, 3)):
    common = sorted(set(res[a]) & set(res[b]))
    rho, _ = spearmanr([res[a][x] for x in common], [res[b][x] for x in common])
    print(f"   intervalo {a}→{a+1} vs {b}→{b+1}: rho = {rho:+.2f} (n={len(common)})")
raw_g = {t: {tid: g for tid, _, g in interval(t)} for t in (1, 2, 3)}
common = sorted(set(raw_g[2]) & set(raw_g[3]))
rho, _ = spearmanr([raw_g[2][x] for x in common], [raw_g[3][x] for x in common])
print(f"   (crecimiento bruto 2→3 vs 3→4: rho = {rho:+.2f})")


# 2) Modelo predictivo con la nueva etiqueta
def rows_for(t):
    wave = {r.tree_id: r for r in build_wave(c.trees, c.observations, t, labeled=True)}
    X, y = [], []
    for tid, r in wave.items():
        if tid not in res[t]:
            continue
        f = dict(r.features)
        f["res_prev"] = res.get(t - 1, {}).get(tid)
        X.append(f)
        y.append(int(res[t][tid] < threshold))
    return X, y


Xtr, ytr = rows_for(2)
Xte, yte = rows_for(3)
print(f"\n2) Predecir 'bajo lo esperado' en M3→M4 · train {len(ytr)} ({sum(ytr)} pos) · "
      f"test {len(yte)} ({sum(yte)} pos, prevalencia {np.mean(yte):.3f})")


def score(num, cat):
    p = fit_preprocessor([{k: f[k] for k in num + cat} for f in Xtr], num, cat)
    m = fit_logistic(transform(p, [{k: f[k] for k in num + cat} for f in Xtr]), ytr, cfg)
    return pr_auc(yte, m.predict_proba(np.asarray(
        transform(p, [{k: f[k] for k in num + cat} for f in Xte])))[:, 1].tolist())


num_all = NUMERIC_FEATURES + ("res_prev",)
for name, num, cat in [
    ("solo residuo previo (persistencia)", ("res_prev",), ()),
    ("solo tamaño", ("h_t", "copa_t", "esbeltez_t"), ()),
    ("todas las variables actuales", NUMERIC_FEATURES, CATEGORICAL_FEATURES),
    ("todas + residuo previo", num_all, CATEGORICAL_FEATURES),
]:
    print(f"   {name:<37}{score(tuple(num), tuple(cat)):.3f}")

# 3) Por especie: ¿la nueva etiqueta ya no depende de la especie?
rate = defaultdict(list)
for f, y in zip(Xtr + Xte, ytr + yte):
    rate[f["species"]].append(y)
big = sorted((np.mean(v), s, len(v)) for s, v in rate.items() if len(v) >= 25)
print("\n3) Tasa de 'bajo lo esperado' por especie (n≥25): "
      f"mín {100*big[0][0]:.0f} % ({big[0][1]}) · máx {100*big[-1][0]:.0f} % ({big[-1][1]})")
