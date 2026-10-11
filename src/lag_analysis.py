# src/lag_analysis.py
"""Does Naver (KR) lead Google (ID)? EXPLORATORY ONLY - not used in trend_radar.json.

Every statistic (best lag, r, p, placebo) is computed on ONE common window per
item: the most recent k points (k = largest multiple of BLOCK_SIZE <= n).
p-values come from a block permutation of google_yoy; results are method-sensitive
(a circular shift gives different p-values), so treat them as hypotheses.

PLACEBO CHECK: Naver_yoy of item X is correlated (at X's best lag) against the
Google_yoy of every OTHER item. If some unrelated item correlates nearly as
strongly (>= PLACEBO_RATIO x observed), the observed link is not specific to
the pair. This points to a SHARED trend or shock across items (e.g. a common
Google/Naver level shift), NOT to seasonality: YoY differencing already
removes calendar seasonality. Flagged items must not be read as evidence
that Korea leads Indonesia.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests
from config import SEED

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "processed" / "monthly_clean.parquet"
OUT_PATH = ROOT / "data" / "processed" / "lag_results.csv"
R_MATRIX_PATH = ROOT / "data" / "processed" / "lag_r_matrix.csv"
LAGS = list(range(-6, 9))
N_PERM, BLOCK_SIZE, MIN_OVERLAP, PLACEBO_RATIO = 1000, 12, 60, 0.8


def _r(a, b, lag):
    n = len(a)
    if lag > 0:   x, y = a[: n - lag], b[lag:]
    elif lag < 0: x, y = a[-lag:], b[: n + lag]
    else:         x, y = a, b
    if len(x) < MIN_OVERLAP or np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def best_lag(a, b):
    best_l, best_r = None, 0.0
    for L in LAGS:
        r = _r(a, b, L)
        if not np.isnan(r) and abs(r) > abs(best_r):
            best_l, best_r = L, r
    return best_l, best_r


def max_abs_r(a, b):
    rs = [abs(r) for r in (_r(a, b, L) for L in LAGS) if not np.isnan(r)]
    return max(rs) if rs else np.nan


def block_p(a, b, rng):
    obs = max_abs_r(a, b)
    if np.isnan(obs):
        return np.nan
    blocks = [b[i:i + BLOCK_SIZE] for i in range(0, len(b), BLOCK_SIZE)]
    null = np.empty(N_PERM)
    for i in range(N_PERM):
        rng.shuffle(blocks)
        null[i] = max_abs_r(a, np.concatenate(blocks))
    return float((1 + (null >= obs).sum()) / (1 + N_PERM))


def main():
    df = pd.read_parquet(IN_PATH)
    df = df[~df["is_partial"]].copy()
    df["date"] = pd.to_datetime(df["date"])

    W = {}
    for it, g in df.groupby("item"):
        g = g.sort_values("date")
        n = len(g)
        k = (n // BLOCK_SIZE) * BLOCK_SIZE
        if k >= MIN_OVERLAP:
            W[it] = (g["naver_yoy"].to_numpy()[-k:],
                     g["google_yoy"].to_numpy()[-k:],
                     g["layer"].iloc[0], g["parent"].iloc[0], n)

    rng = np.random.default_rng(SEED)
    rows = []
    for it, (a, b, layer, parent, n) in W.items():
        bl, br = best_lag(a, b)
        direction = ("none" if bl is None
                     else "naver_leads" if bl > 0
                     else "google_leads" if bl < 0
                     else "contemporaneous")
        rows.append({
            "item": it, "layer": layer, "parent": parent,
            "n_points_full": n, "n_points_used": len(a),
            "best_lag": bl, "best_r": round(br, 4),
            "max_abs_r": round(max_abs_r(a, b), 4),
            "direction": direction,
            "p_perm": block_p(a, b, rng),
        })
    res = pd.DataFrame(rows)
    ok = res["p_perm"].notna()
    res["p_adj"] = np.nan
    if ok.any():
        res.loc[ok, "p_adj"] = multipletests(res.loc[ok, "p_perm"], method="fdr_bh")[1]
    res["significant_fdr05"] = res["p_adj"] < 0.05
    res["exploratory_only"] = True

    # Placebo: skip items whose best_lag is None (guard against a latent crash)
    pl = []
    for it, (a, _, *_rest) in W.items():
        bl_series = res.loc[res["item"] == it, "best_lag"]
        bl_val = bl_series.iloc[0] if not bl_series.empty else None
        if bl_val is None or pd.isna(bl_val):
            pl.append((it, np.nan))
            continue
        bl = int(bl_val)
        pl.append((it, max(abs(_r(a, W[j][1], bl)) for j in W if j != it)))
    res = res.merge(pd.DataFrame(pl, columns=["item", "max_abs_placebo_r"]), on="item")
    res["placebo_flag"] = np.where(
        res["max_abs_placebo_r"].notna()
        & (res["max_abs_placebo_r"] >= PLACEBO_RATIO * res["max_abs_r"]),
        "WARNING: unrelated item correlates as strongly (shared trend/shock, not seasonality)", "ok")

    res.to_csv(OUT_PATH, index=False)
    mat = [{"item": it, "layer": v[2],
            **{f"lag_{L:+d}": round(_r(v[0], v[1], L), 4) for L in LAGS}}
           for it, v in W.items()]
    pd.DataFrame(mat).to_csv(R_MATRIX_PATH, index=False)
    pd.set_option("display.width", 220)
    print(res.to_string(index=False))
    print("\nEXPLORATORY ONLY - not used in trend_radar.json")


if __name__ == "__main__":
    main()