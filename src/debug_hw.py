# src/debug_hw.py
"""Debug why Holt-Winters fails on our data."""
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_parquet(ROOT / "data" / "processed" / "monthly_merged.parquet")
df["date"] = pd.to_datetime(df["date"])
df = df[df["date"].dt.strftime("%Y-%m") != "2026-09"]

for item, g in df.groupby("item"):
    g = g.sort_values("date").set_index("date")
    s = g["google"].dropna()
    n = len(s)
    zeros = int((s == 0).sum())

    try:
        m = ExponentialSmoothing(
            s,
            trend="add",
            seasonal="add",
            seasonal_periods=12,
            initialization_method="estimated",
        ).fit()
        print(f"{item:20s} n={n:3d} zeros={zeros:2d}  OK")
    except Exception as e:
        print(f"{item:20s} n={n:3d} zeros={zeros:2d}  FAIL — {type(e).__name__}: {e}")

    # Also test WITHOUT explicit initialization_method
    try:
        m2 = ExponentialSmoothing(
            s, trend="add", seasonal="add", seasonal_periods=12
        ).fit()
        print(f"{'':20s} (default init) OK")
    except Exception as e:
        print(f"{'':20s} (default init) FAIL — {type(e).__name__}: {e}")