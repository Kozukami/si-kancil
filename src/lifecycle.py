# src/lifecycle.py
"""Lifecycle metrics per item: half-life (AR1, upper bound), surge duration, volatility."""
from pathlib import Path
import numpy as np
import pandas as pd
from statsmodels.tsa.ar_model import AutoReg

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "processed" / "monthly_clean.parquet"
OUT = ROOT / "data" / "processed" / "lifecycle.csv"


def half_life_yoy_upper_bound(series: pd.Series) -> float:
    """AR(1) half-life on YoY series. OVERESTIMATE (YoY overlaps 11/12 months)."""
    s = series.dropna().to_numpy()
    if len(s) < 12 or np.std(s) == 0:
        return np.nan
    try:
        res = AutoReg(s, lags=1, trend="c").fit()
        phi = res.params[1]
        if 0 < phi < 1:
            return float(-np.log(2) / np.log(phi))
        return np.nan
    except Exception:
        return np.nan


def surge_duration(z_series: pd.Series, threshold: float = 1.0) -> float:
    z = z_series.dropna()
    if z.empty:
        return 0.0
    high = (z >= threshold).astype(int)
    groups = (high != high.shift()).cumsum()
    runs = high.groupby(groups).sum()
    runs = runs[runs > 0]
    return float(runs.mean()) if not runs.empty else 0.0


def safe_cv(series: pd.Series) -> float:
    mu = float(series.mean())
    if mu <= 0 or np.isnan(mu):
        return np.nan
    return float(series.std() / mu)


def main():
    df = pd.read_parquet(CLEAN)
    df = df[~df["is_partial"]].copy()
    rows = []
    for item, g in df.groupby("item"):
        g = g.sort_values("date")
        kr_hl = half_life_yoy_upper_bound(g["naver_yoy"])
        kr_surge = surge_duration(g["naver_yoy_z"])
        kr_cv = safe_cv(g["naver_raw"])
        id_hl = half_life_yoy_upper_bound(g["google_yoy"])
        id_surge = surge_duration(g["google_yoy_z"])
        id_cv = safe_cv(g["google_raw"])
        rows.append({
            "item": item, "layer": g["layer"].iloc[0], "parent": g["parent"].iloc[0],
            "kr_half_life_yoy_months_upper_bound": round(kr_hl, 2) if pd.notna(kr_hl) else None,
            "kr_surge_dur_months": round(kr_surge, 1),
            "kr_volatility_cv": round(kr_cv, 2) if pd.notna(kr_cv) else None,
            "id_half_life_yoy_months_upper_bound": round(id_hl, 2) if pd.notna(id_hl) else None,
            "id_surge_dur_months": round(id_surge, 1),
            "id_volatility_cv": round(id_cv, 2) if pd.notna(id_cv) else None,
        })
    res = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.to_csv(OUT, index=False)
    print(res.to_string(index=False))
    print(f"\n[OK] -> {OUT}")


if __name__ == "__main__":
    main()