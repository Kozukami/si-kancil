# Si Kancil — Trend Radar for Indonesian Fashion UMKM

**Live dashboard:** https://kozukami.github.io/si-kancil/kancil.html
**Live lookup endpoint:** https://kancil-lookup.kancil-kori.workers.dev

> *I pre-registered a validation gate. 1 of 12 signals passed. Widened to 48 tests, 0 survive multiple-comparison correction. I report both numbers in the same view. That is the product.*

---

## Bahasa Indonesia — ringkas

Si Kancil adalah dashboard analitik tren fesyen untuk UMKM Indonesia, dibangun dari Naver DataLab (Korea) dan Google Trends (Indonesia), rentang 2017–2026.

Saya **pra-registrasi gate validasi** sebelum melihat data: forecast 3 bulan harus mengalahkan baseline *persistence* (MASE gain > 0, block-bootstrap 95% CI > 0, gain ≥ 10%). Hasilnya saya tampilkan apa adanya:

| Metrik | Hasil |
|---|---|
| Forecast 3 bulan tervalidasi | **1 / 12** (cotton, gain +23.9%) |
| Setelah diperluas ke 48 tes & koreksi Benjamini-Hochberg | **0 / 48** |
| Lead-lag Korea → Indonesia lolos FDR | **0 / 12** |
| Lead-lag dengan peringatan placebo | **9 / 12** |

Platform berjalan sepenuhnya client-side pada satu file HTML — tidak ada server, tidak ada API key. IBM Bob via Langflow berfungsi sebagai lapisan percakapan yang **secara arsitektur tidak dapat mengarang angka**: setiap nilai harus melewati komponen Langflow deterministik.

---

## What this project is

A market radar for Indonesian fashion MSMEs. It fuses **Naver DataLab** (Korea, daily → monthly mean) and **Google Trends** (Indonesia, monthly) into a single dashboard that tracks **12 fashion items** across three layers:

| Layer | Items |
|---|---|
| item | cardigan, cargo_pants, knit_vest, oversized_blazer, oversized_hoodie, wide_leg_pants |
| material | viscose, polyester, cotton, fleece |
| item+material | cotton_shirt, denim_jacket |

Data range: **2017-01 → 2026-09**.

The dashboard answers one question: **"Of all the signals I see, which ones are actually worth acting on?"** — and it answers it by showing its own failures first.

---

## The honesty headline

The same four numbers appear on the dashboard hero and in every report:

- **1 of 12** items passed the pre-registered 3-month forecast gate
- **0 of 48** survive Benjamini-Hochberg correction when the gate is widened to 4 horizons
- **0 of 12** Korea → Indonesia lead-lag relationships survive FDR
- **9 of 12** lead-lag relationships trigger a placebo warning

I show all four simultaneously. Most trend products show only the first.

---

## The pre-registered gate

Before any data was seen, I fixed the criteria for calling a signal "validated":

> A candidate model must (a) beat a persistence baseline on mean MASE, (b) have a block-bootstrap 95% confidence interval above 0, and (c) achieve ≥ 10% relative improvement over persistence.

The gate is not adjusted after results are seen. This is the core discipline of the project. The pipeline holds the design to it — the dashboard reads `verdict: "validated"` or `verdict: "not_validated"` directly from `trend_radar.json` and refuses to display a forecast for any item that didn't pass.

**Note:** cotton is displayed in *amber*, labelled "passed initial test" — never as "verified". It passes the single-horizon gate, but fails BH correction when the gate is widened to 48 tests (raw p = 0.0015 → BH-adjusted p = 0.072).

---

## Results

### Validated 3-month forecasts — 1 of 12

| Item | Layer | Gain vs persistence | 95% CI | Fold win rate |
|---|---|---|---|---|
| **cotton** | material | **+23.9%** | [0.0329, 0.2195] | 74% |
| all other 11 items | — | not validated | — | — |

Cotton is a **fabric-interest proxy**, not a garment-demand forecast. The validated number is an index (0–100), not units sold.

### Multi-horizon extension (exploratory) — 0 of 48

The single-horizon gate (h=3) was extended to horizons {1, 3, 6, 12} with BH correction over all 48 tests:

- 2 tests pass the raw gate
- **0 survive BH**
- Strongest single signal: cotton at h=3 (raw p = 0.0015 → BH p = 0.072)

### Lead-lag Korea → Indonesia (exploratory) — 0 of 12

I tested whether Naver (Korea) leads Google (Indonesia) at any lag in [-6, +8] months. No pair survives FDR at α = 0.05. 9 of 12 trigger a placebo warning: an unrelated item correlates as strongly as the pair itself, indicating a shared trend/shock rather than a specific adoption lag.

**I do not claim Korea leads Indonesia.** The Korean data is context, not causation.

---

## IBM Langflow + IBM Bob integration

The conversational layer runs on **IBM Langflow** with a custom component (`src/langflow_component.py`) that:

1. Resolves Indonesian / English aliases — `"kardigan"` → `cardigan`, `"celana kulot"` → `wide_leg_pants`, `"jaket jeans"` → `denim_jacket`
2. Handles genuine ambiguity by **asking, not guessing** — `"cotton"` returns `"bisa merujuk ke: cotton, cotton_shirt. Mohon perjelas."`
3. Rejects untracked queries informatively — `"sepatu"` returns the list of 12 tracked items
4. Renders a structured report from `trend_radar.json` — including the item's last three `item_limitations`

**IBM Bob** is the conversational orchestrator. It calls `TrendRadarTool` from Langflow; it has **no direct access to the JSON**. Every number Bob speaks is traceable to a field in `trend_radar.json`. Architecturally, Bob cannot invent a number.

The dashboard also exposes this as a live HTTP endpoint (`kancil-lookup.kancil-kori.workers.dev`) with identical routing logic — Cloudflare Workers, no LLM in the loop, no API key, no quota risk.

---

## How to run it

### Frontend (the dashboard)

The dashboard is a single static file with the JSON inlined. **No build server, no API keys, no install.**

1. Open `kancil.html` in a browser. Done.

To rebuild it from the current `trend_radar.json`:

```bash
cd src
python build_frontend.py

```

Expected output:

```
[OK] ... | schema 4.4 | validated 1/12 | multi-horizon 0/48 | lag {'n': 12, 'fdr': 0, 'placebo': 9}
```

### Pipeline (from raw data to `trend_radar.json`)

```bash
cd src
bash run_all.sh
```

Key scripts in `src/`: `load_data.py`, `clean.py`, `seasonality.py`, `lifecycle.py`, `lebaran_effect.py`, `lag_analysis.py`, `forecast.py`, `forecast_multi_horizon.py`, `trend_radar.py`, `build_frontend.py`, `check_json_v2.py`.

---

## Repository structure

```
.
├── README.md
├── kancil.html
├── src/
│   ├── kancil_template.html
│   ├── build_frontend.py
│   ├── langflow_component.py
│   ├── trend_radar.py
│   ├── forecast.py
│   ├── forecast_multi_horizon.py
│   ├── lag_analysis.py
│   ├── check_json_v2.py
│   └── run_all.sh
└── data/processed/
    ├── trend_radar.json
    ├── forecast_skill_multi_horizon.csv
    └── lag_results.csv
```

---

## Known limitations

- Naver and Google keywords are not semantically equivalent across languages
- Search interest is not sales
- Phase offset may reflect shared year-end seasonality, not adoption lag
- Forecast values exist only for validated items (1 of 12)
- Forecast CIs are block-bootstrap based and approximate; fold autocorrelation is not fully corrected
- Feb-2026 Google anomaly masked with causal forward-fill (reconfirmed by re-downloading three affected items)
- Some Google Trends files mix Topic entities with search terms; documented as MVP approximation
- China is not tracked (Baidu Index requires a Chinese phone number)
- `denim_jacket` has no parent material because denim fabric is not tracked
- Sep-2026 covers 28/30 days for the six oldest Naver files; treated as complete
- Lag analysis is exploratory; p-values are not robust to method choice
- Multi-horizon backtest is exploratory; **0 of 48 tests survive BH correction**
- Findings specific to 2017–2026; not generalizable without validation

Full list in `data/processed/trend_radar.json` under `limitations`.

---

## Responsible AI

- **No hidden numbers.** Every figure in the UI is sourced from `trend_radar.json` or `lag_results.csv`
- **No cross-layer ranking.** The UI is structurally unable to compare item / material / item+material levels
- **No invented quantities.** Store Advisor never provides a quantity for material-layer signals, and never issues ORDER NOW for items with weak seasonality evidence
- **No LLM hallucination surface.** IBM Bob has no direct file access; every number must pass through the Langflow component
- **Two-sided results.** The dashboard hero shows 1/12 *and* 0/48 in the same view

---

## Author

**Solo submission — Kori, BINUS University**
Hacktiv8 × IBM Hackathon, 11 October 2026

The statistical pipeline, pre-registered validation gate, frontend, Cloudflare Workers endpoint, and IBM Langflow component were built by one person in the hackathon window.

## Acknowledgements

Naver DataLab (Korea), Google Trends (Indonesia), IBM Langflow, IBM Bob.
