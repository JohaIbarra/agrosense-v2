"""Experimento A (exploratorio, no productivo): ¿más datos o más variables?"""
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from agrosense.adapters.ingester.excel_source import ExcelCampaignSource
from agrosense.ml.evaluation import pr_auc, species_rate_scores
from agrosense.ml.preprocessing import fit_preprocessor, transform
from agrosense.ml.stall_features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, build_wave
from agrosense.ml.train_stall import StallTrainConfig, fit_logistic

raw = Path("data/raw/anexo1.xlsx")
c = ExcelCampaignSource().read(raw.read_bytes(), raw.name)
cfg = StallTrainConfig()
train = build_wave(c.trees, c.observations, 2, labeled=True)
test = build_wave(c.trees, c.observations, 3, labeled=True)
y_te = [int(r.label) for r in test]
print(f"train {len(train)} ({sum(r.label for r in train)} pos) · test {len(test)} ({sum(y_te)} pos)")


def fit_score(rows, num=NUMERIC_FEATURES, cat=CATEGORICAL_FEATURES, algo="logreg"):
    keep = set(num) | set(cat)
    f_tr = [{k: v for k, v in r.features.items() if k in keep} for r in rows]
    f_te = [{k: v for k, v in r.features.items() if k in keep} for r in test]
    p = fit_preprocessor(f_tr, tuple(num), tuple(cat))
    X, Xt = transform(p, f_tr), transform(p, f_te)
    y = [int(r.label) for r in rows]
    if algo == "logreg":
        m = fit_logistic(X, y, cfg)
    else:
        m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                           random_state=42, class_weight="balanced")
        m.fit(np.asarray(X), np.asarray(y))
    return pr_auc(y_te, m.predict_proba(np.asarray(Xt))[:, 1].tolist())


# 1) Curva de aprendizaje: submuestreo por PARCELA (simula tener menos parcelas)
by_plot = defaultdict(list)
for r in train:
    by_plot[r.plot].append(r)
plots = sorted(by_plot, key=str)
rng = np.random.default_rng(42)
print("\n1) Curva de aprendizaje (entrena M2→M3 con una fracción de parcelas, evalúa M3→M4)")
for frac in (0.25, 0.5, 0.75, 1.0):
    vals = []
    for _ in range(1 if frac == 1.0 else 30):
        chosen = rng.choice(len(plots), size=max(2, round(frac * len(plots))), replace=False)
        rows = [r for i in chosen for r in by_plot[plots[i]]]
        if len({r.label for r in rows}) < 2:
            continue
        vals.append(fit_score(rows))
    print(f"   {int(frac*100):>3} % parcelas (~{int(frac*len(train))} árboles): PR-AUC "
          f"media {np.mean(vals):.3f} (p10 {np.percentile(vals,10):.3f} – p90 {np.percentile(vals,90):.3f})")

# 2) ¿De dónde sale la señal? (grupos de variables)
print("\n2) Grupos de variables (logística, mismo split)")
sp = species_rate_scores([r.features["species"] for r in train], [int(r.label) for r in train],
                         [r.features["species"] for r in test])
print(f"   solo tasa por especie (regla)      {pr_auc(y_te, sp):.3f}")
groups = {
    "solo especie": ((), ("species",)),
    "solo tamaño (altura, copa, esbeltez)": (("h_t", "copa_t", "esbeltez_t"), ()),
    "solo historia (crecimiento previo)": (("dh_lag", "dcopa_lag", "estanco_lag", "h_prev"), ()),
    "sitio (predio, unidad)": ((), ("locality", "monitoring_unit")),
    "todo menos especie": (NUMERIC_FEATURES, tuple(x for x in CATEGORICAL_FEATURES if x != "species")),
    "todo (modelo actual)": (NUMERIC_FEATURES, CATEGORICAL_FEATURES),
}
for name, (num, cat) in groups.items():
    print(f"   {name:<37}{fit_score(train, num, cat):.3f}")

# 3) ¿Es el algoritmo el límite?
print("\n3) Algoritmo (mismas variables)")
print(f"   regresión logística                 {fit_score(train):.3f}")
print(f"   gradient boosting (árboles)         {fit_score(train, algo='gbm'):.3f}")

# 4) Resolución de la medición de altura
hs = [o.height_m for o in c.observations if o.height_m]
cm = Counter(round(h * 100) % 5 == 0 for h in hs)
print(f"\n4) Alturas múltiplos de 5 cm: {100*cm[True]/len(hs):.1f} % de {len(hs)} mediciones")
dh = [r.features["dh_lag"] for r in test if r.features["dh_lag"] is not None]
print(f"   crecimiento M2→M3 (4 meses): mediana {100*np.median(dh):.1f} cm; "
      f"{100*np.mean([d <= 0 for d in dh]):.0f} % ≤ 0; {100*np.mean([0 < d <= 0.05 for d in dh]):.0f} % entre 0 y 5 cm")
by_sp = defaultdict(list)
for r in train + test:
    by_sp[r.features["species"]].append(int(r.label))
top = sorted(((np.mean(v), len(v), s) for s, v in by_sp.items() if len(v) >= 25), reverse=True)
print("   tasa de estancamiento por especie (n≥25):")
for rate, n, s in top[:4] + [("…", "", "")] + top[-3:] if len(top) > 7 else top:
    print(f"     {s:<30}{rate if isinstance(rate, str) else f'{100*rate:.0f} %'} {n}")
