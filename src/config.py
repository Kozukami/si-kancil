# src/config.py
"""Central config for the Kancil pipeline.

LAYERS (never rank across layers):
  item           : garment / style
  material       : fabric (a fabric-interest proxy, NOT garment demand)
  item+material  : garment + fabric (parent = material item, if tracked)

DATA NOTES
  - trend_cotton.csv and trend_fleece.csv are SWAPPED on disk (contents vs name).
    Mapped crosswise below; do NOT also rename the files.
  - naver_denim.xlsx holds 청자켓 (denim JACKET), not 데님 (denim fabric): unused.
    denim material is therefore not tracked and denim_jacket has no parent.
  - Sep-2026: Naver covers 28/30 days for the six oldest items. Treated as a
    complete month (28-day mean is a fair level estimate) - known compromise.
  - GOOGLE_ANOMALY_MONTHS: Google spiked across many unrelated items while
    Naver was flat (Feb-2026: fleece x8.7, hoodie x7.4, polyester x3.9 ...).
    Re-downloaded on a separate day for three affected items (oversized_hoodie,
    polyester, cotton) and the spike PERSISTED across all three. Treated as a
    Google normalisation / sampling artifact and masked with a CAUSAL
    forward-fill. Do NOT switch this to Sep-2026: the September spike you may
    remember is in Naver DataLab, not in Google Trends.
  - KEYWORD TYPE MIX: some Google Trends files mix Topic entities (capitalised,
    e.g. "Cotton", "Polyester") with search terms (lowercase, e.g. "katun").
    Topics can dominate the 0-100 normalisation and compress search-term
    variation. Visual re-downloads showed the trends were similar, so the mix
    is treated as an acceptable approximation for this MVP and documented as
    a limitation rather than fixed.
"""
ITEMS = {
    # ---- item layer ----
    "cardigan":         {"layer": "item", "parent": None, "naver_file": "naver_cardigan.xlsx",         "gtrends_file": "trend_cardigan.csv"},
    "cargo_pants":      {"layer": "item", "parent": None, "naver_file": "naver_cargo_pants.xlsx",      "gtrends_file": "trend_cargo_pants.csv"},
    "knit_vest":        {"layer": "item", "parent": None, "naver_file": "naver_knit_vest.xlsx",        "gtrends_file": "trend_knit-vest.csv"},
    "oversized_blazer": {"layer": "item", "parent": None, "naver_file": "naver_oversized_blazer.xlsx", "gtrends_file": "trend_oversized_blazer.csv"},
    "oversized_hoodie": {"layer": "item", "parent": None, "naver_file": "naver_oversized_hoodie.xlsx", "gtrends_file": "trend_oversized_hoodie.csv"},
    "wide_leg_pants":   {"layer": "item", "parent": None, "naver_file": "naver_wide-leg_pants.xlsx",   "gtrends_file": "trend_wide-leg_pants.csv"},
    # ---- material layer ----
    "viscose":          {"layer": "material", "parent": None, "naver_file": "naver_viscose.xlsx",      "gtrends_file": "trend_viscose.csv"},
    "polyester":        {"layer": "material", "parent": None, "naver_file": "naver_polyester.xlsx",    "gtrends_file": "trend_polyester.csv"},
    "cotton":           {"layer": "material", "parent": None, "naver_file": "naver_cotton.xlsx",       "gtrends_file": "trend_fleece.csv"},  # SWAP
    "fleece":           {"layer": "material", "parent": None, "naver_file": "naver_fleece.xlsx",       "gtrends_file": "trend_cotton.csv"},  # SWAP
    # ---- item+material layer ----
    "cotton_shirt":     {"layer": "item+material", "parent": "cotton", "naver_file": "naver_cotton_shirt.xlsx", "gtrends_file": "trend_cotton_shirt.csv"},
    "denim_jacket":     {"layer": "item+material", "parent": None,     "naver_file": "naver_denim_jacket.xlsx", "gtrends_file": "trend_denim_jacket.csv"},
}
LAYERS = ("item", "material", "item+material")
EXPECTED_ITEMS = set(ITEMS)

# Manual Google keyword exclusions (audited).
EXCLUDE_KEYWORDS = {
    "cardigan":     ["Cardigan", "rajutan cardigan"],   # Topic entity / 100% zero
    "cotton_shirt": ["cotton clothes"],                 # single-month spike to 100 (median 0)
}
ZERO_DROP = 0.90               # drop keyword if >90% zeros
SPIKE_MEDIAN_ZERO_MAX = 50     # safety net: drop if median==0 AND max>=50

FREQ = "MS"
DATE_RANGE = ("2016-01-01", "2026-09-30")
PARTIAL_MONTHS = []
GOOGLE_ANOMALY_MONTHS = ["2026-02"]   # confirmed across 3 re-downloads

# ---- forecast policy (gate baseline is PRE-REGISTERED: persistence) ----
FORECAST_GATE_BASELINE = "persistence"
FORECAST_MIN_REL_IMPROVEMENT = 0.10   # mean MASE gain must be >=10% of baseline MASE
FORECAST_BOOTSTRAP_N = 2000
FORECAST_BOOTSTRAP_BLOCK = 3          # fold-level block bootstrap (autocorrelated folds)
FORECAST_CLIP = (0.0, 100.0)
SEED = 42