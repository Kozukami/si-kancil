# src/check_all_topics.py
"""Audit all Google Trends keywords:
   - Topic-entity candidates (single English word, huge scale)
   - Zero-inflated (>=90% zeros)
   - Spike-inflated (median==0 AND max>=50)
   - Manual exclusions from config
"""
from pathlib import Path
import pandas as pd

from config import EXCLUDE_KEYWORDS, ZERO_DROP, SPIKE_MEDIAN_ZERO_MAX

ROOT = Path(__file__).resolve().parents[1]
GTRENDS = ROOT / "data" / "raw" / "gtrends"

print(f"{'item':<20} {'keyword':<25} {'min':>6} {'max':>6} {'median':>7} "
      f"{'mean':>7} {'zero%':>7}  flag")
print("-" * 110)

for f in sorted(GTRENDS.glob("trend_*.csv")):
    item = f.stem.replace("trend_", "")
    df = pd.read_csv(f)
    df.columns = ["date"] + list(df.columns[1:])
    excluded = set(EXCLUDE_KEYWORDS.get(item, []))
    for col in df.columns[1:]:
        s = pd.to_numeric(df[col].astype(str).str.replace("<1", "0", regex=False),
                          errors="coerce")
        zero_pct = float((s == 0).mean())
        mn, mx, median, mean = float(s.min()), float(s.max()), float(s.median()), float(s.mean())
        flags = []
        if col in excluded:
            flags.append("excluded_manual")
        if zero_pct > ZERO_DROP:
            flags.append(f"drop (>={ZERO_DROP:.0%} zero)")
        if median == 0 and mx >= SPIKE_MEDIAN_ZERO_MAX:
            flags.append(f"drop (median==0, max>={SPIKE_MEDIAN_ZERO_MAX})")
        if mn > 15 and zero_pct == 0 and mean > 30 and col not in excluded:
            flags.append("TOPIC candidate?")
        print(f"{item:<20} {col:<25} {mn:>6.1f} {mx:>6.1f} {median:>7.1f} "
              f"{mean:>7.2f} {zero_pct:>6.1%}  {' | '.join(flags)}")
