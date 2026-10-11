# src/check_cardigan.py
"""Sanity check: is 'Cardigan' (uppercase) a search term or a Topic entity?"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "data" / "raw" / "gtrends" / "trend_cardigan.csv"

df = pd.read_csv(path)
df.columns = ["date"] + list(df.columns[1:])
df["date"] = pd.to_datetime(df["date"])
df = df.set_index("date")

print("=== DESCRIPTION ===")
print(df.describe().round(2).to_string())

print("\n=== CORRELATION BETWEEN KEYWORDS ===")
print(df.corr().round(3).to_string())

print("\n=== FIRST / LAST ROWS ===")
print(df.head(6).to_string())
print("...")
print(df.tail(6).to_string())

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 5))
    for col in df.columns:
        ax.plot(df.index, df[col], label=col, linewidth=1.5)
    ax.set_title("Cardigan keyword curves (Google Trends ID, monthly)")
    ax.set_ylabel("Interest (0-100)")
    ax.legend()
    ax.grid(alpha=0.3)
    out = ROOT / "data" / "processed" / "cardigan_curve.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    print(f"\n[OK] plot saved -> {out}")
except ImportError:
    print("\n[skip plot] matplotlib not installed")