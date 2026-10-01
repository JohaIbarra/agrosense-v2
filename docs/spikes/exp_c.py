"""Experimento C (exploratorio): ¿el gremio ecológico reemplaza a la especie?

Mismo split que E7: entrena en la ola 2 (M2→M3), evalúa en la ola 3 (M3→M4).
Se reporta PR-AUC, «veces mejor que el azar» (PR-AUC / prevalencia) e IC 90 %
por bootstrap de PARCELAS sobre el test (diferencia pareada vs modelo actual).
"""
from collections import defaultdict
from pathlib import Path

import numpy as np

from agrosense.adapters.ingester.excel_source import ExcelCampaignSource
from agrosense.ml.evaluation import pr_auc, species_rate_scores
from agrosense.ml.preprocessing import fit_preprocessor, transform
from agrosense.ml.stall_features import (
    CATEGORICAL_FEATURES, NUMERIC_FEATURES, _normalize_category, build_wave,
)
from agrosense.ml.train_stall import StallTrainConfig, fit_logistic

raw = Path("data/raw/anexo1.xlsx")
c = ExcelCampaignSource().read(raw.read_bytes(), raw.name)
guild = {t.tree_id: _normalize_category(t.guild) for t in c.trees}
cfg = StallTrainConfig()


def wave(t):
    rows = build_wave(c.trees, c.observations, t, labeled=True)
    for r in rows:
        r.features["guild"] = guild[r.tree_id]
    return rows


train, test = wave(2), wave(3)
y_te = np.array([int(r.label) for r in test])
plots_te = np.array([str(r.plot) for r in test])
prev = y_te.mean()
print(f"train {len(train)} ({sum(r.label for r in train)} pos) · test {len(test)} "
      f"({y_te.sum()} pos, prevalencia {prev:.3f})")
cnt = defaultdict(int)
for t in c.trees:
    cnt[guild[t.tree_id]] += 1
print("gremios:", dict(cnt))


def scores(num, cat):
    keep = tuple(num) + tuple(cat)
    f_tr = [{k: r.features[k] for k in keep} for r in train]
    f_te = [{k: r.features[k] for k in keep} for r in test]
    p = fit_preprocessor(f_tr, tuple(num), tuple(cat))
    m = fit_logistic(transform(p, f_tr), [int(r.label) for r in train], cfg)
    return np.array(m.predict_proba(np.asarray(transform(p, f_te)))[:, 1])


def rate_rule(key):
    return np.array(species_rate_scores([r.features[key] for r in train],
                                        [int(r.label) for r in train],
                                        [r.features[key] for r in test]))


SIZE = ("h_t", "copa_t", "esbeltez_t")
SITE_CAT = ("locality", "monitoring_unit", "fito_t")
NO_SP = tuple(x for x in CATEGORICAL_FEATURES if x != "species")
variants = {
    "A. actual (todo, con especie)": scores(NUMERIC_FEATURES, CATEGORICAL_FEATURES),
    "B. todo, especie→gremio": scores(NUMERIC_FEATURES, NO_SP + ("guild",)),
    "C. todo sin especie ni gremio": scores(NUMERIC_FEATURES, NO_SP),
    "D. especie + tamaño": scores(SIZE, ("species",)),
    "E. gremio + tamaño": scores(SIZE, ("guild",)),
    "F. solo tamaño": scores(SIZE, ()),
    "G. gremio + tamaño + historia (sin sitio)": scores(NUMERIC_FEATURES, ("guild",)),
    "H. regla: tasa por especie": rate_rule("species"),
    "I. regla: tasa por gremio": rate_rule("guild"),
}

rng = np.random.default_rng(42)
uplots = np.unique(plots_te)
idx_by_plot = {p: np.flatnonzero(plots_te == p) for p in uplots}
boots = []
for _ in range(1000):
    idx = np.concatenate([idx_by_plot[p] for p in rng.choice(uplots, len(uplots))])
    if y_te[idx].sum() == 0:
        continue
    boots.append(idx)
base = variants["A. actual (todo, con especie)"]
print(f"\n{'variante':<44}{'PR-AUC':>7}{'×azar':>7}   Δ vs A (IC90 bootstrap parcelas)")
for name, s in variants.items():
    ap = pr_auc(y_te.tolist(), s.tolist())
    d = [pr_auc(y_te[i].tolist(), s[i].tolist()) - pr_auc(y_te[i].tolist(), base[i].tolist())
         for i in boots]
    print(f"{name:<44}{ap:>7.3f}{ap/prev:>7.2f}   {np.mean(d):+.3f} "
          f"[{np.percentile(d,5):+.3f}, {np.percentile(d,95):+.3f}]")
