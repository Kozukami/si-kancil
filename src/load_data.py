# src/load_data.py
"""Naver (xlsx, daily) + Google Trends (csv, monthly) -> long monthly.

Outputs (data/processed/):
  - monthly_merged.parquet   (item, layer, parent, date, naver, google, google_anomaly_masked)
  - naver_weekly.parquet     (item, date, naver)   [raw artifact only]
  - qc_report.csv            (per-keyword zero-share + median + max + kept/drop reason)

QC rules (in order):
  1. EXCLUDE_KEYWORDS  (manual, audited)
  2. ZERO_DROP         (>90% zeros)
  3. SPIKE_MEDIAN_ZERO_MAX  (median==0 AND max>=threshold) — general safety net
  Anomaly months: GOOGLE_ANOMALY_MONTHS replaced with a CAUSAL forward-fill.
"""
import warnings
from pathlib import Path
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

from config import (
    ITEMS, ZERO_DROP, FREQ, DATE_RANGE, EXCLUDE_KEYWORDS,
    SPIKE_MEDIAN_ZERO_MAX, GOOGLE_ANOMALY_MONTHS,
)

ROOT = Path(__file__).resolve().parents[1]
IN_NAVER = ROOT / "data" / "raw" / "naver"
IN_GTRENDS = ROOT / "data" / "raw" / "gtrends"
OUT_DIR = ROOT / "data" / "processed"


def load_naver(path: Path, item: str):
    """Naver DataLab (통검): rows 0-5 metadata, row 6 header, daily data."""
    df = pd.read_excel(path, skiprows=6).iloc[:, :2]
    df.columns = ["date", "naver"]
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["naver"] = pd.to_numeric(df["naver"], errors="coerce")
    s = df.dropna().set_index("date")["naver"]
    m = s.resample(FREQ).mean().rename("naver").reset_index()
    m["item"] = item
    w = s.resample("W-MON").mean().rename("naver").reset_index()
    w["item"] = item
    return m, w


def load_google(path: Path, item: str):
    """Google Trends CSV, header row 0. Applies manual / zero / spike keyword rules."""
    df = pd.read_csv(path)
    df = df.rename(columns={df.columns[0]: "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    excluded = set(EXCLUDE_KEYWORDS.get(item, []))
    if excluded:
        print(f"[info] {item}: excluding manual keywords = {sorted(excluded)}")

    all_kws = [c for c in df.columns if c != "date"]
    for c in all_kws:
        df[c] = pd.to_numeric(
            df[c].astype(str).str.replace("<1", "0", regex=False),
            errors="coerce",
        )

    zero = {c: float((df[c] == 0).mean()) for c in all_kws}
    median = {c: float(df[c].median()) for c in all_kws}
    max_ = {c: float(df[c].max()) for c in all_kws}

    kept = [c for c in all_kws if c not in excluded and zero[c] <= ZERO_DROP]
    spike = {c for c in kept if median[c] == 0 and max_[c] >= SPIKE_MEDIAN_ZERO_MAX}
    if spike:
        print(f"[info] {item}: spike-dropped = {sorted(spike)}")
    kept = [c for c in kept if c not in spike]

    def reason(c):
        if c in excluded:   return "excluded_manual"
        if c in spike:      return "spike_median_zero"
        if c not in kept:   return "zero_ratio"
        return "kept"

    qc = pd.DataFrame({
        "item": item,
        "keyword": all_kws,
        "pct_zero": [round(zero[c], 3) for c in all_kws],
        "median":   [median[c] for c in all_kws],
        "max":      [max_[c] for c in all_kws],
        "kept":     [(c in kept) for c in all_kws],
        "reason":   [reason(c) for c in all_kws],
    })

    if not kept:
        print(f"[WARN] {item}: all keywords dropped. Item excluded.")
        empty = pd.DataFrame({"date": df["date"], "google": float("nan")})
        empty["item"] = item
        return empty.dropna(), qc

    merged = df[kept].mean(axis=1)
    qc_merged = pd.DataFrame([{
        "item": item, "keyword": "__merged__",
        "pct_zero": round(float((merged == 0).mean()), 3),
        "median":   float(merged.median()),
        "max":      float(merged.max()),
        "kept": True, "reason": "kept",
    }])

    out = pd.DataFrame({"date": df["date"], "google": merged})
    out["item"] = item
    return out.dropna(), pd.concat([qc, qc_merged], ignore_index=True)


def mask_google_anomalies(m: pd.DataFrame) -> pd.DataFrame:
    """Replace known Google artifact months by a CAUSAL forward-fill (no look-ahead).

    Naver is flat/down in the same month; the Google spike is a normalisation
    or sampling artifact, not signal. ffill uses only prior months.
    """
    m = m.sort_values(["item", "date"]).copy()
    bad = m["date"].dt.strftime("%Y-%m").isin(GOOGLE_ANOMALY_MONTHS)
    m["google_anomaly_masked"] = bad
    if bad.any():
        m.loc[bad, "google"] = np.nan
        m["google"] = m.groupby("item")["google"].ffill()
        if m["google"].isna().any():
            print("[warn] NaN left after ffill (anomaly at series start?) -> bfill")
            m["google"] = m.groupby("item")["google"].bfill()
        print(f"[info] masked {int(bad.sum())} google rows in {GOOGLE_ANOMALY_MONTHS} (ffill)")
    return m


def build(naver_dir: Path, google_dir: Path):
    nv_m, nv_w, gg, qcs = [], [], [], []
    for item, cfg in ITEMS.items():
        m, w = load_naver(naver_dir / cfg["naver_file"], item)
        nv_m.append(m); nv_w.append(w)
        g, qc = load_google(google_dir / cfg["gtrends_file"], item)
        gg.append(g); qcs.append(qc)

    m = pd.concat(nv_m).merge(pd.concat(gg), on=["item", "date"], how="inner")
    m = m[(m["date"] >= DATE_RANGE[0]) & (m["date"] <= DATE_RANGE[1])]
    m = mask_google_anomalies(m)

    layer_map = {i: c["layer"] for i, c in ITEMS.items()}
    parent_map = {i: c.get("parent") for i, c in ITEMS.items()}
    m["layer"] = m["item"].map(layer_map)
    m["parent"] = m["item"].map(parent_map)

    m = m[["item", "layer", "parent", "date",
           "naver", "google", "google_anomaly_masked"]] \
        .sort_values(["layer", "item", "date"]).reset_index(drop=True)

    expected = len(pd.date_range(DATE_RANGE[0], DATE_RANGE[1], freq=FREQ))
    counts = m.groupby("item").size()
    bad = counts[counts != expected]
    if len(bad):
        print(f"[WARN] rows != {expected}:"); print(bad.to_string())

    missing = set(ITEMS.keys()) - set(m["item"].unique())
    if missing:
        print(f"[WARN] items missing: {sorted(missing)}")

    return m, pd.concat(nv_w, ignore_index=True), pd.concat(qcs, ignore_index=True)


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    m, w, qc = build(IN_NAVER, IN_GTRENDS)
    qc.to_csv(OUT_DIR / "qc_report.csv", index=False)
    m.to_parquet(OUT_DIR / "monthly_merged.parquet", index=False)
    w.to_parquet(OUT_DIR / "naver_weekly.parquet", index=False)
    print("\n" + qc.to_string(index=False))
    print(f"\n[OK] monthly_merged shape = {m.shape}")
    print(f"[OK] naver_weekly shape   = {w.shape}")
    print("\nrows per item (monthly):")
    print(m.groupby(["layer", "item"]).size().to_string())