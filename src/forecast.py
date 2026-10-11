# src/forecast.py
"""Forecast benchmark, rolling-origin CV (horizon 3, expanding window, non-overlapping folds).

Models : persistence (PRE-REGISTERED gate baseline), seasonal_naive (secondary reference),
         holt_winters, xgboost (recursive on deltas). Candidate outputs clipped to [0, 100].
Gate   : the better model candidate (by mean MASE) is compared with PERSISTENCE only,
         fold by fold.
         validated  <=> mean gain > 0
                        AND block-bootstrap 95% CI lower bound > 0
                        AND mean gain >= FORECAST_MIN_REL_IMPROVEMENT x baseline MASE.
         Otherwise  : not_validated (no forecast values emitted).
         Folds are autocorrelated -> CI is approximate (block bootstrap, not a formal test).

Reads  : monthly_merged.parquet (full 129-month series; Feb-2026 already masked).
Writes : forecast_backtest.csv (per item x model),
         forecast_skill.csv (per item; skill summary + verdict),
         forecast_next3.csv (validated items only).
"""
import warnings
warnings.filterwarnings("ignore")
import logging
logging.getLogger("statsmodels").setLevel(logging.ERROR)
from pathlib import Path
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import xgboost as xgb
from config import (PARTIAL_MONTHS, FORECAST_CLIP, FORECAST_MIN_REL_IMPROVEMENT,
                    FORECAST_BOOTSTRAP_N, FORECAST_BOOTSTRAP_BLOCK,
                    FORECAST_GATE_BASELINE, SEED)

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
HORIZON, SEASONALITY, MIN_TRAIN, TRAIN_FRACTION = 3, 12, 36, 0.55
MODELS = ["persistence", "seasonal_naive", "holt_winters", "xgboost"]
CANDIDATES = ["holt_winters", "xgboost"]


def mase(y_true, y_pred, y_train, m=SEASONALITY):
    if len(y_train) <= m:
        return np.nan
    scale = float(np.mean(np.abs(y_train[m:] - y_train[:-m])))
    if scale == 0 or np.isnan(scale):
        return np.nan
    return float(np.mean(np.abs(y_true - y_pred))) / scale


def seasonal_naive(v, h, m=SEASONALITY):
    T = len(v)
    return np.array([v[T + i - m] for i in range(h)], float)


def persistence(v, h):
    return np.full(h, v[-1], float)


def holt_winters(series, h):
    try:
        f = ExponentialSmoothing(series, trend="add", seasonal="add",
                                 seasonal_periods=SEASONALITY,
                                 initialization_method="estimated").fit()
        return np.clip(f.forecast(h).values.astype(float), *FORECAST_CLIP)
    except Exception as e:
        print(f"  [HW fail] {type(e).__name__}: {e}")
        return None


def xgb_recursive_delta(series, h, max_lag=3):
    df = pd.DataFrame({"y": series.values}, index=series.index)
    df["delta"] = df["y"].diff()
    for k in range(1, max_lag + 1):
        df[f"d_lag_{k}"] = df["delta"].shift(k)
    df["sin_m"] = np.sin(2 * np.pi * df.index.month / 12)
    df["cos_m"] = np.cos(2 * np.pi * df.index.month / 12)
    df = df.dropna()
    if len(df) < 24:
        return None
    feats = [f"d_lag_{k}" for k in range(1, max_lag + 1)] + ["sin_m", "cos_m"]
    model = xgb.XGBRegressor(n_estimators=50, max_depth=3, learning_rate=0.05,
                             random_state=SEED, verbosity=0)
    model.fit(df[feats].values, df["delta"].values)
    hist = list(series.values)
    deltas = [hist[i] - hist[i - 1] for i in range(1, len(hist))]
    last_m, out = series.index[-1].month, []
    for i in range(h):
        nm = (last_m + i) % 12 + 1
        X = np.array([[deltas[-1], deltas[-2], deltas[-3],
                       np.sin(2 * np.pi * nm / 12), np.cos(2 * np.pi * nm / 12)]])
        d = float(model.predict(X)[0])
        out.append(hist[-1] + d); hist.append(out[-1]); deltas.append(d)
    return np.clip(np.array(out), *FORECAST_CLIP)


def predict(model, series, h=HORIZON):
    v = series.values
    return {
        "persistence":    lambda: persistence(v, h),
        "seasonal_naive": lambda: seasonal_naive(v, h),
        "holt_winters":   lambda: holt_winters(series, h),
        "xgboost":        lambda: xgb_recursive_delta(series, h),
    }[model]()


def fold_mases(series):
    n = len(series)
    starts = range(max(MIN_TRAIN, int(n * TRAIN_FRACTION)), n - HORIZON + 1, HORIZON)
    res = {m: [] for m in MODELS}
    for ts in starts:
        tr, te = series.iloc[:ts], series.iloc[ts:ts + HORIZON]
        if len(te) < HORIZON:
            continue
        for m in MODELS:
            p = predict(m, tr)
            res[m].append(mase(te.values, p, tr.values)
                          if p is not None and len(p) == HORIZON else np.nan)
    return {m: np.array(v, float) for m, v in res.items()}


def block_bootstrap_ci(d, n_boot=FORECAST_BOOTSTRAP_N,
                       block=FORECAST_BOOTSTRAP_BLOCK, seed=SEED):
    rng = np.random.default_rng(seed)
    n = len(d)
    k = int(np.ceil(n / block))
    means = np.empty(n_boot)
    for i in range(n_boot):
        starts = rng.integers(0, n, k)
        idx = np.concatenate([(s + np.arange(block)) % n for s in starts])[:n]
        means[i] = d[idx].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def label_months(last):
    t = pd.Timestamp(last + "-01")
    return [(t + pd.DateOffset(months=k)).strftime("%Y-%m") for k in (1, 2, 3)]


def main():
    df = pd.read_parquet(PROC / "monthly_merged.parquet")
    df["date"] = pd.to_datetime(df["date"])
    df = df[~df["date"].dt.strftime("%Y-%m").isin(PARTIAL_MONTHS)] \
        .sort_values(["item", "date"])

    bt, skill, fc = [], [], []
    for item, g in df.groupby("item"):
        series = g.set_index("date")["google"].dropna().asfreq("MS")
        layer, parent = g["layer"].iloc[0], g["parent"].iloc[0]
        if len(series) < MIN_TRAIN + HORIZON:
            print(f"[skip] {item}: {len(series)} points")
            continue

        F = fold_mases(series)
        mean = {m: float(np.nanmean(a)) for m, a in F.items()}
        best_candidate = min(CANDIDATES, key=lambda m: mean[m])

        ok = np.isfinite(F[FORECAST_GATE_BASELINE]) & np.isfinite(F[best_candidate])
        d = (F[FORECAST_GATE_BASELINE] - F[best_candidate])[ok]
        lo, hi = block_bootstrap_ci(d)
        md = float(d.mean())
        wr = float((d > 0).mean())
        rel = md / mean[FORECAST_GATE_BASELINE] if mean[FORECAST_GATE_BASELINE] > 0 else np.nan
        validated = bool(md > 0 and lo > 0 and rel >= FORECAST_MIN_REL_IMPROVEMENT)
        verdict = "validated" if validated else "not_validated"
        beats_persistence = bool(mean[best_candidate] < mean[FORECAST_GATE_BASELINE])

        for m in MODELS:
            bt.append({
                "item": item, "layer": layer, "parent": parent, "model": m,
                "mase_mean": round(mean[m], 4),
                "n_folds": int(np.isfinite(F[m]).sum()),
                "is_gate_baseline": m == FORECAST_GATE_BASELINE,
                "is_candidate": m in CANDIDATES,
            })

        skill.append({
            "item": item, "layer": layer, "parent": parent,
            "best_candidate": best_candidate,
            "best_candidate_mase": round(mean[best_candidate], 4),
            "persistence_mase": round(mean[FORECAST_GATE_BASELINE], 4),
            "seasonal_naive_mase": round(mean["seasonal_naive"], 4),
            "beats_persistence": beats_persistence,
            "beats_seasonal_naive": bool(mean[best_candidate] < mean["seasonal_naive"]),
            "delta_mean": round(md, 4),
            "rel_improvement": round(rel, 3),
            "delta_ci_low": round(lo, 4),
            "delta_ci_high": round(hi, 4),
            "win_rate": round(wr, 3),
            "n_folds": int(ok.sum()),
            "verdict": verdict,
        })

        if validated:
            pred = predict(best_candidate, series)
            for mth, v in zip(label_months(series.index[-1].strftime("%Y-%m")), pred):
                fc.append({"item": item, "month": mth,
                           "value": round(float(v), 2),
                           "method": best_candidate, "verdict": verdict})

        print(f"[{item:17s}] best={best_candidate:12s} "
              f"pers={mean[FORECAST_GATE_BASELINE]:.3f} "
              f"best={mean[best_candidate]:.3f} gain={rel:+.1%} "
              f"CI=[{lo:+.3f},{hi:+.3f}] win={wr:.2f} -> {verdict}")

    pd.DataFrame(bt).to_csv(PROC / "forecast_backtest.csv", index=False)
    sk = pd.DataFrame(skill)
    sk.to_csv(PROC / "forecast_skill.csv", index=False)
    f = pd.DataFrame(fc, columns=["item", "month", "value", "method", "verdict"])
    f.to_csv(PROC / "forecast_next3.csv", index=False)
    print(f"\n[OK] validated items: "
          f"{int((sk.verdict == 'validated').sum())}/{len(sk)} "
          f"(forecast values only for those)")


if __name__ == "__main__":
    main()