# src/seasonality.py
"""Monthly seasonal profile + Kruskal-Wallis on year-normalised values.
BH-adjusted over all items x 2 sources. trend_radar uses the ADJUSTED p-values."""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import kruskal
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "processed" / "monthly_clean.parquet"
OUT = ROOT / "data" / "processed" / "seasonality.csv"
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]


def add_year_norm(df, col):
    df = df.copy()
    df["year"], df["month"] = df["date"].dt.year, df["date"].dt.month
    df["norm"] = df[col] / df.groupby(["item", "year"])[col].transform("mean").replace(0, np.nan)
    return df


def monthly_profile(df):
    p = df.groupby(["item", "month"])["norm"].mean().unstack("month")
    p.columns = [MONTHS[c - 1] for c in p.columns]
    return p


def kruskal_seasonality(df_norm, item):
    g = df_norm[df_norm["item"] == item]
    groups = [g.loc[g["month"] == m, "norm"].dropna().to_numpy() for m in range(1, 13)]
    groups = [x for x in groups if len(x) >= 2]
    if len(groups) < 4:
        return np.nan, np.nan
    try:
        s, p = kruskal(*groups)
        return float(s), float(p)
    except Exception:
        return np.nan, np.nan


def main():
    df = pd.read_parquet(CLEAN)
    df = df[~df["is_partial"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    kr, idd = add_year_norm(df, "naver_raw"), add_year_norm(df, "google_raw")
    kp, ip = monthly_profile(kr), monthly_profile(idd)
    items = sorted(df["item"].unique())

    raw = [(src, it, kruskal_seasonality(d, it)[1]) for it in items for src, d in (("kr", kr), ("id", idd))]
    vals = np.array([p for *_, p in raw], float)
    ok = ~np.isnan(vals)
    adj = np.full(len(vals), np.nan)
    if ok.any():
        adj[ok] = multipletests(vals[ok], method="fdr_bh")[1]
    P = {(s, i): (vals[k], adj[k]) for k, (s, i, _) in enumerate(raw)}

    def r4(x): return None if np.isnan(x) else round(float(x), 4)

    rows = []
    for it in items:
        g0 = df[df["item"] == it].iloc[0]
        row = {"item": it, "layer": g0["layer"], "parent": g0["parent"]}
        for src, prof in (("kr", kp), ("id", ip)):
            pr = prof.loc[it]
            row.update({
                f"{src}_peak_month": pr.idxmax(),
                f"{src}_peak_idx": round(float(pr.max()), 2),
                f"{src}_trough_month": pr.idxmin(),
                f"{src}_amplitude": round(float(pr.max() - pr.min()), 2),
                f"{src}_kruskal_p": r4(P[(src, it)][0]),
                f"{src}_kruskal_p_adj": r4(P[(src, it)][1]),
            })
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(out.to_string(index=False))
    print(f"\n[OK] -> {OUT}")


if __name__ == "__main__":
    main()