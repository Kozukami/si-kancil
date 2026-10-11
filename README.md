# Si Kancil — Trend Radar for Indonesian Fashion UMKM

**Live dashboard:** https://kozukami.github.io/si-kancil/kancil.html
**Live lookup endpoint:** https://kancil-lookup.kancil-kori.workers.dev

> *We pre-registered a validation gate. 1 of 12 signals passed. Widened to 48 tests, 0 survive multiple-comparison correction. We report both numbers in the same view. That is the product.*

---

## Bahasa Indonesia — ringkas

Si Kancil adalah dashboard analitik tren fesyen untuk UMKM Indonesia, dibangun dari Naver DataLab (Korea) dan Google Trends (Indonesia), rentang 2017–2026.

Kami **pra-registrasi gate validasi** sebelum melihat data: forecast 3 bulan harus mengalahkan baseline *persistence* (MASE gain > 0, block-bootstrap 95% CI > 0, gain ≥ 10%). Hasilnya kami tampilkan apa adanya:

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

- **1 of 12** items passed our pre-registered 3-month forecast gate
- **0 of 48** survive Benjamini-Hochberg correction when the gate is widened to 4 horizons
- **0 of 12** Korea → Indonesia lead-lag relationships survive FDR
- **9 of 12** lead-lag relationships trigger a placebo warning

We show all four simultaneously. Most trend products show only the first.

---

## The pre-registered gate

Before any data was seen, we fixed the criteria for calling a signal "validated":

> A candidate model must (a) beat a persistence baseline on mean MASE, (b) have a block-bootstrap 95% confidence interval above 0, and (c) achieve ≥ 10% relative improvement over persistence.

The gate is not adjusted after results are seen. This is the core discipline of the project. The pipeline holds us to it — the dashboard reads `verdict: "validated"` or `verdict: "not_validated"` directly from `trend_radar.json` and refuses to display a forecast for any item that didn't pass.

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

We tested whether Naver (Korea) leads Google (Indonesia) at any lag in [-6, +8] months. No pair survives FDR at α = 0.05. 9 of 12 trigger a placebo warning: an unrelated item correlates as strongly as the pair itself, indicating a shared trend/shock rather than a specific adoption lag.

**We do not claim Korea leads Indonesia.** The Korean data is context, not causation.

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