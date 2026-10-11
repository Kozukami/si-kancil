# src/test_persistence.py
import pandas as pd, numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_parquet(ROOT / "data" / "processed" / "monthly_merged.parquet")
df["date"] = pd.to_datetime(df["date"])
df = df[df["date"].dt.strftime("%Y-%m") != "2026-09"]

for item, g in df.groupby("item"):
    g = g.sort_values("date").set_index("date")
    s = g["google"].dropna().values
    n = len(s)
    h = 3
    
    # Persistence: y[t+3] = y[t]
    err_persist = [abs(s[t+h] - s[t]) for t in range(n-h-20, n-h)]
    # Seasonal naive: y[t+3] = y[t-9]  
    err_naive = [abs(s[t+h] - s[t+h-12]) for t in range(n-h-20, n-h)]
    
    print(f"{item:20s} | persist MAE: {np.mean(err_persist):.4f} | naive MAE: {np.mean(err_naive):.4f} | naive/persist ratio: {np.mean(err_naive)/np.mean(err_persist):.3f}")