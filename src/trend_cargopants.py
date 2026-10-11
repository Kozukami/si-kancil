# src/check_cargo_trend.py
import pandas as pd
import numpy as np
from scipy.stats import pearsonr
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_parquet(ROOT / "data/processed/monthly_clean.parquet")
df = df[(df["item"] == "cargo_pants") & (~df["is_partial"])].sort_values("date")

a_yoy = df["naver_yoy"].to_numpy()
b_yoy = df["google_yoy"].to_numpy()
a_d1 = np.diff(df["naver_raw"].to_numpy())
b_d1 = np.diff(df["google_raw"].to_numpy())

print(f"{'lag':>5} {'r_YoY':>10} {'r_diff1':>10}")
for L in range(0, 9):
    r_yoy, _ = pearsonr(a_yoy[:-L] if L > 0 else a_yoy,
                        b_yoy[L:] if L > 0 else b_yoy)
    r_d1, _ = pearsonr(a_d1[:-L] if L > 0 else a_d1,
                       b_d1[L:] if L > 0 else b_d1)
    print(f"{L:>5} {r_yoy:>10.3f} {r_d1:>10.3f}")