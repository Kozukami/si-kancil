# src/clean.py
"""Causal cleaning. No look-ahead, no interpolation.

Input : <project_root>/data/processed/monthly_merged.parquet
Output: <project_root>/data/processed/monthly_clean.parquet

Cols  : item, layer, parent, date, naver_raw, google_raw, google_anomaly_masked,
        naver_roll3, google_roll3, naver_yoy, google_yoy,
        naver_yoy_z, google_yoy_z, is_partial

Design decisions:
  - YoY differencing (x - x.shift(12)) is causal and removes seasonality.
    NaN from diff are DROPPED, not interpolated. Analysis therefore starts 2017-01.
  - Expanding z-score (no look-ahead) is applied ONLY to YoY series.
  - Rolling mean (3 months, trailing) is for level display only; NOT for
    correlations, which would inflate apparent lead-lag.
  - PARTIAL_MONTHS is currently empty: Sep-2026 is treated as complete
    (28/30 days). is_partial exists so future data with known gaps can be
    filtered by downstream consumers.
"""
from pathlib import Path
import pandas as pd

from config import PARTIAL_MONTHS

ROOT = Path(__file__).resolve().parents[1]
IN_PATH = ROOT / "data" / "processed" / "monthly_merged.parquet"
OUT_PATH = ROOT / "data" / "processed" / "monthly_clean.parquet"

YOY = 12
ROLL = 3
Z_MIN_PERIODS = 12


def _expanding_z(s: pd.Series) -> pd.Series:
    mu = s.expanding(min_periods=Z_MIN_PERIODS).mean()
    sd = s.expanding(min_periods=Z_MIN_PERIODS).std()
    return (s - mu) / sd.replace(0, float("nan"))


def clean_item(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    expected = pd.date_range(df["date"].min(), df["date"].max(), freq="MS")
    assert len(df) == len(expected) and (df["date"].values == expected.values).all(), \
        f"{df['item'].iloc[0]}: gap or duplicate in monthly index"

    out = pd.DataFrame({
        "item": df["item"],
        "layer": df["layer"],
        "parent": df["parent"],
        "date": df["date"],
        "naver_raw": df["naver"],
        "google_raw": df["google"],
        "google_anomaly_masked": df["google_anomaly_masked"],
    })
    out["naver_roll3"] = out["naver_raw"].rolling(ROLL, min_periods=ROLL).mean()
    out["google_roll3"] = out["google_raw"].rolling(ROLL, min_periods=ROLL).mean()
    out["naver_yoy"] = out["naver_raw"] - out["naver_raw"].shift(YOY)
    out["google_yoy"] = out["google_raw"] - out["google_raw"].shift(YOY)
    out["naver_yoy_z"] = _expanding_z(out["naver_yoy"])
    out["google_yoy_z"] = _expanding_z(out["google_yoy"])
    out["is_partial"] = out["date"].dt.strftime("%Y-%m").isin(PARTIAL_MONTHS)
    return out


def main() -> None:
    df = pd.read_parquet(IN_PATH)
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
    clean = pd.concat([clean_item(g) for _, g in df.groupby("item", sort=True)], ignore_index=True)
    clean = clean.dropna(subset=["naver_yoy", "google_yoy"]).reset_index(drop=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(OUT_PATH, index=False)
    print(f"[OK] {OUT_PATH}")
    print(f"shape = {clean.shape}")
    print(clean.groupby("item").agg(
        n=("date", "size"),
        start=("date", "min"),
        end=("date", "max"),
        n_z=("naver_yoy_z", "count"),
        n_partial=("is_partial", "sum"),
    ).to_string())


if __name__ == "__main__":
    main()