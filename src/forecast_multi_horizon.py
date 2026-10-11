# src/forecast_multi_horizon.py  (EXTENSION - exploratory)
"""Same pre-registered gate as forecast.py, evaluated separately at horizons 1, 3, 6, 12.
Origins every 3 months (expanding window); 12-step forecasts are made once per origin and sliced to h.
Windows overlap more as h grows -> block bootstrap block = ceil(h/3) origins (min 3).
48 tests (12 items x 4 horizons) -> BH adjustment on one-sided bootstrap p-values."""
import warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from statsmodels.stats.multitest import multipletests
import forecast as F
from config import FORECAST_MIN_REL_IMPROVEMENT, FORECAST_BOOTSTRAP_N, SEED

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
HORIZONS = [1, 3, 6, 12]
MODELS = ["persistence", "seasonal_naive", "holt_winters", "xgboost"]

def preds(model, tr, H=12):
    if model == "persistence": return F.persistence(tr.values, H)
    if model == "seasonal_naive": return F.seasonal_naive(tr.values, H)
    if model == "holt_winters": return F.holt_winters(tr, H)
    return F.xgb_recursive_delta(tr, H)

def boot(d, block, rng):
    n = len(d); k = int(np.ceil(n / block)); m = np.empty(FORECAST_BOOTSTRAP_N)
    for i in range(FORECAST_BOOTSTRAP_N):
        idx = np.concatenate([(s + np.arange(block)) % n for s in rng.integers(0, n, k)])[:n]
        m[i] = d[idx].mean()
    return np.percentile(m, 2.5), np.percentile(m, 97.5), float((m <= 0).mean())

def main():
    df = pd.read_parquet(PROC / "monthly_merged.parquet"); df["date"] = pd.to_datetime(df["date"])
    rng = np.random.default_rng(SEED); rows = []
    for item, g in df.groupby("item"):
        s = g.sort_values("date").set_index("date")["google"].dropna().asfreq("MS"); n = len(s)
        origins = list(range(max(36, int(n * .55)), n, 3))
        E = {h: {m: [] for m in MODELS} for h in HORIZONS}
        for ts in origins:
            tr = s.iloc[:ts]; P = {m: preds(m, tr) for m in MODELS}
            for h in HORIZONS:
                if ts + h > n: continue
                te = s.iloc[ts:ts + h].values
                for m in MODELS:
                    E[h][m].append(F.mase(te, P[m][:h], tr.values) if P[m] is not None else np.nan)
        for h in HORIZONS:
            A = {m: np.array(v, float) for m, v in E[h].items()}
            mean = {m: np.nanmean(a) for m, a in A.items()}
            w = min(F.CANDIDATES, key=lambda m: mean[m])
            d = A["persistence"] - A[w]; d = d[np.isfinite(d)]
            lo, hi, p = boot(d, max(3, int(np.ceil(h / 3))), rng)
            rel = d.mean() / mean["persistence"]
            rows.append({"item": item, "horizon": h, "n_origins": len(d), "best_candidate": w,
                         "persistence_mase": round(mean["persistence"], 3), "seasonal_naive_mase": round(mean["seasonal_naive"], 3),
                         "candidate_mase": round(mean[w], 3), "rel_gain": round(rel, 3), "ci_low": round(lo, 3),
                         "ci_high": round(hi, 3), "p_one_sided": round(p, 4),
                         "gate_pass": bool(d.mean() > 0 and lo > 0 and rel >= FORECAST_MIN_REL_IMPROVEMENT)})
    r = pd.DataFrame(rows)
    r["p_adj_bh"] = multipletests(r["p_one_sided"], method="fdr_bh")[1].round(4)
    r["validated"] = r["gate_pass"] & (r["p_adj_bh"] < 0.05)
    r.to_csv(PROC / "forecast_skill_multi_horizon.csv", index=False)
    print(r.pivot(index="item", columns="horizon", values="rel_gain").round(2).to_string())
    print("\ngate_pass (CI>0 & >=10%):"); print(r.pivot(index="item", columns="horizon", values="gate_pass").to_string())
    print("\nvalidated after BH over 48 tests:", r[r.validated][["item", "horizon", "rel_gain", "ci_low", "p_adj_bh"]].to_string(index=False) if r.validated.any() else "NONE")
    print("\nbest persistence-vs-seasonal-naive by horizon (mean MASE across items):")
    print(r.groupby("horizon")[["persistence_mase", "seasonal_naive_mase", "candidate_mase"]].mean().round(3).to_string())
main()
