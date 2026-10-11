# src/lebaran_effect.py
"""Indonesia: does shopping surge around Eid al-Fitr?
Eid moves ~11 days earlier each year; we assign each obs to the nearest Eid
within a [-6, +3] month window and normalise within each Eid cycle.
Wilcoxon signed-rank: pre-Eid vs post-Eid months, paired per year.
One test per item (12 tests) -> Benjamini-Hochberg adjusted (wilcoxon_p_adj).
trend_radar uses the ADJUSTED p-value; raw p is kept for transparency only.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "processed" / "monthly_clean.parquet"
OUT = ROOT / "data" / "processed" / "lebaran_effect.csv"

EID_DATES = {
    2015: "2015-07-17",
    2016: "2016-07-06", 2017: "2017-06-25", 2018: "2018-06-15",
    2019: "2019-06-05", 2020: "2020-05-24", 2021: "2021-05-13",
    2022: "2022-05-02", 2023: "2023-04-22", 2024: "2024-04-10",
    2025: "2025-03-31", 2026: "2026-03-20", 2027: "2027-03-09",
}


def assign_eid(df, eids):
    df = df.copy()
    df["eid"] = pd.NaT
    df["months_from_eid"] = np.nan
    for eid in eids:
        delta = (df["date"].dt.year - eid.year) * 12 + (df["date"].dt.month - eid.month)
        mask = (delta >= -6) & (delta <= 3) & df["eid"].isna()
        df.loc[mask, "eid"] = eid
        df.loc[mask, "months_from_eid"] = delta[mask]
    return df.dropna(subset=["eid", "months_from_eid"])


def main():
    df = pd.read_parquet(CLEAN)
    df = df[~df["is_partial"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    eids = pd.to_datetime(list(EID_DATES.values()))
    df = assign_eid(df, eids)
    df["months_from_eid"] = df["months_from_eid"].astype(int)

    cycle_mean = df.groupby(["item", "eid"])["google_raw"].transform("mean")
    df["norm"] = df["google_raw"] / cycle_mean.replace(0, np.nan)
    profile = df.groupby(["item", "months_from_eid"])["norm"].mean().unstack("months_from_eid")

    rows = []
    for item, g in df.groupby("item"):
        pre = g[g["months_from_eid"] < 0].groupby("eid")["norm"].mean()
        post = g[g["months_from_eid"] >= 0].groupby("eid")["norm"].mean()
        paired = pd.concat([pre, post], axis=1, keys=["pre", "post"]).dropna()
        p_val = None
        if len(paired) >= 5:
            try:
                _, p_val = wilcoxon(paired["pre"], paired["post"])
                p_val = round(float(p_val), 4)
            except Exception:
                p_val = None
        ip = profile.loc[item].dropna()
        rows.append({
            "item": item, "layer": g["layer"].iloc[0],
            "peak_offset_month": int(ip.idxmax()),
            "peak_idx": round(float(ip.max()), 2),
            "pre_eid_avg": round(float(pre.mean()), 2) if not pre.empty else None,
            "post_eid_avg": round(float(post.mean()), 2) if not post.empty else None,
            "n_eid_cycles": int(paired.shape[0]),
            "wilcoxon_p": p_val,
        })
    summary = pd.DataFrame(rows)
    summary["wilcoxon_p_adj"] = np.nan
    ok = summary["wilcoxon_p"].notna()
    if ok.any():
        summary.loc[ok, "wilcoxon_p_adj"] = np.round(
            multipletests(summary.loc[ok, "wilcoxon_p"], method="fdr_bh")[1], 4)
    print(summary.to_string(index=False))
    summary.to_csv(OUT, index=False)
    print(f"\n[OK] -> {OUT}")


if __name__ == "__main__":
    main()