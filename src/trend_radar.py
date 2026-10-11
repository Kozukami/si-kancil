# src/trend_radar.py
"""Build trend_radar.json for Langflow / IBM Bob. Schema 4.4.

Principles:
  - Never rank across layers.
  - Forecast values only for items whose backtest skill is validated against
    the PRE-REGISTERED persistence baseline (see forecast.py).
  - Seasonality labels use BH-adjusted p-values.
  - Every limitation shown to Bob is hedged and tied to the actual keywords.

Adds (schema 4.4):
  - pitch_summary         : one-glance numbers for the pitch deck.
  - data_quality          : auditable record of masks, exclusions, anomalies.
  - seasonal_profile      : 12-element year-normalised monthly means per source.
  - momentum              : YoY z-score at latest month per source.
  - expected_rise         : seasonal delta now -> +1/+3/+6/+12, with agreement badge.
  - multi_horizon         : exploratory 1/3/6/12-month backtest summary.

Schema changelog:
  4.3 -> 4.4 : lebaran wilcoxon_p renamed to wilcoxon_p_raw, wilcoxon_p_adj added;
               seasonal_profile, momentum, expected_rise, multi_horizon added.
"""
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from config import ITEMS, LAYERS, FORECAST_MIN_REL_IMPROVEMENT, GOOGLE_ANOMALY_MONTHS, EXCLUDE_KEYWORDS

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
SCHEMA_VERSION = "4.4"
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
METHOD_DISPLAY = {
    "holt_winters": "Holt-Winters (trend + seasonal, clipped 0-100)",
    "xgboost":      "XGBoost (recursive delta, clipped 0-100)",
}

ITEM_KEYWORD_LIMITATIONS = {
    "cardigan":         "LOW-RESOLUTION SIGNAL: the Google series has median ~2 and only ~13 distinct levels (the Topic keyword 'Cardigan' was excluded, which compressed the remaining search-term variation). Small absolute changes look large; treat seasonality and forecasts for this item with extra caution.",
    "oversized_blazer": "Google side effectively measures generic 'blazer wanita'/'Women's Blazer'; the literal 'oversized blazer' term was dropped (>90% zeros). Category-level demand, not the 'oversized' style.",
    "oversized_hoodie": "Google side is dominated by 'hoodie wanita' (generic hoodie); 'oversized hoodie' has very low volume. Category-level demand, not the 'oversized' style.",
    "cotton":           "Naver 코튼 and Google katun / kain katun / Cotton / bahan katun probably capture fabric-interest searches more than garment demand. Read as a fabric-interest proxy.",
    "polyester":        "Naver 폴리에스터 and Google poliester / Polyester may capture material-information searches more than consumer garment demand. Read as a fabric-interest proxy.",
    "viscose":          "Naver 비스코스 and Google viscose / Viscose / kain viscose / bahan viscose are fabric-interest proxies; interpret with caution.",
    "fleece":           "Naver keyword 기모 means brushed/fleece-lined (winter garments in general), not 'polar fleece' fabric; semantic gap to the Google side is larger than for other materials.",
    "cotton_shirt":     "Google side reflects 'kemeja katun'-type category demand; 'cotton clothes' was excluded (one-month spike to 100, median 0).",
    "denim_jacket":     "No parent material (denim fabric is not tracked). Google side spans 'jaket denim', 'jaket jeans', 'denim jacket', 'Jean jacket': jacket-level, not fabric-level.",
}
GENERIC_LIMITATIONS = [
    "Naver and Google keywords are not semantically equivalent across languages.",
    "Search interest is not sales.",
]
MATERIAL_NOTE = ("Material-layer signal: a leading indicator for product categories "
                 "using this fabric, not a direct SKU stocking signal.")


# ---------------------------------------------------------------------------
# Classification helpers (unchanged)
# ---------------------------------------------------------------------------
def classify_seasonality(p_adj, amp):
    if p_adj is None or pd.isna(p_adj): return "insufficient_data"
    if p_adj < 0.01 and amp > 1.0:      return "strong"
    if p_adj < 0.05 and amp > 0.3:      return "moderate"
    if p_adj < 0.05:                    return "weak"
    return "not_significant"


def phase_reliability(id_p_adj, id_amp):
    if id_p_adj is None or pd.isna(id_p_adj): return False, "insufficient_data"
    if id_p_adj >= 0.05: return False, "id_not_significant"
    if id_amp < 0.20:    return False, "amplitude_too_small"
    if id_amp < 0.30:    return True, "marginal_low_magnitude"
    return True, "valid"


def month_num(n): return MONTHS.index(n) + 1


def phase_offset(kr, idp):
    d = (month_num(idp) - month_num(kr)) % 12
    if d > 6: d -= 12
    return d, ("synchronized" if d == 0 else "id_lags_kr" if d > 0 else "id_leads_kr")


def lifecycle_position(kr_peak, now_month, p_adj, amp):
    if p_adj is None or pd.isna(p_adj) or p_adj >= 0.05 or amp < 0.3:
        return "unclear"
    off = (now_month - month_num(kr_peak)) % 12
    return ("in-season" if off == 0
            else "approaching-peak" if off in (10, 11)
            else "post-season" if off in (1, 2)
            else "off-season")


def business_action(layer, kr_interp, kr_peak, id_peak, offset, direction,
                    reliable, reason):
    hedge = (" Catatan: sinyal musiman Indonesia relatif kecil, offset kurang andal."
             if reliable and reason == "marginal_low_magnitude" else "")
    if layer == "material":
        if kr_interp in ("strong", "moderate"):
            return (f"Minat bahan ini memuncak di {kr_peak} (Korea) sebagai indikator awal "
                    f"untuk kategori produk yang memakai bahan ini; bukan sinyal langsung "
                    f"untuk stok SKU.{hedge}")
        return ("Sinyal musiman bahan ini lemah; hanya referensi sekunder untuk kategori "
                "produk, bukan sinyal stok SKU.")
    if reliable and direction == "id_lags_kr":
        return (f"Puncak musiman Korea ({kr_peak}) → Indonesia ({id_peak}), "
                f"offset {offset:+d} bulan. Pertimbangkan menyiapkan stok 1–2 bulan "
                f"sebelum puncak Indonesia.{hedge}")
    if reliable and direction == "synchronized":
        return (f"Puncak musiman Korea dan Indonesia bersamaan ({kr_peak}). "
                f"Pertimbangkan menyiapkan stok 1–2 bulan sebelumnya.{hedge}")
    if reliable and direction == "id_leads_kr":
        return (f"Puncak Indonesia ({id_peak}) mendahului Korea ({kr_peak}); bukan "
                f"kepemimpinan pasar Korea. Pola ini mungkin dipengaruhi musim akhir "
                f"tahun. Gunakan kalender Korea hanya sebagai referensi.{hedge}")
    if kr_interp == "strong":
        return (f"Musiman Korea kuat ({kr_peak}); musiman Indonesia tidak cukup andal "
                f"untuk offset. Verifikasi dengan penjualan lokal.")
    if kr_interp in ("moderate", "weak"):
        return ("Pola musiman lemah. Referensi sekunder, bukan dasar tunggal "
                "keputusan stok.")
    return ("Bukti musiman tidak cukup kuat. Jangan putuskan stok hanya "
            "berdasarkan kategori ini.")


# ---------------------------------------------------------------------------
# NEW: frontend data blocks
# ---------------------------------------------------------------------------
def compute_seasonal_profile(clean: pd.DataFrame) -> dict:
    """Year-normalised monthly mean per item per source.

    Returns {item: {'kr': [12 floats or None], 'id': [12 floats or None]}}
    Index is Jan..Dec. None where data is missing.
    """
    df = clean.copy()
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    for col in ("naver_raw", "google_raw"):
        df[f"{col}_norm"] = (
            df[col] / df.groupby(["item", "year"])[col].transform("mean").replace(0, np.nan)
        )
    out = {}
    for item, g in df.groupby("item"):
        prof = {}
        for src, col in (("kr", "naver_raw_norm"), ("id", "google_raw_norm")):
            monthly = g.groupby("month")[col].mean()
            arr = []
            for m in range(1, 13):
                v = monthly.get(m, np.nan)
                arr.append(None if pd.isna(v) else round(float(v), 4))
            prof[src] = arr
        out[item] = prof
    return out


def compute_momentum(clean: pd.DataFrame) -> dict:
    """YoY z-score at the latest month per item per source.

    Returns {item: {'kr': float|None, 'id': float|None}}.
    """
    last = clean.sort_values("date").groupby("item").tail(1).set_index("item")
    out = {}
    for item in last.index:
        row = last.loc[item]
        kr = row["naver_yoy_z"]
        idv = row["google_yoy_z"]
        out[item] = {
            "kr": None if pd.isna(kr) else round(float(kr), 3),
            "id": None if pd.isna(idv) else round(float(idv), 3),
        }
    return out


def momentum_interpretation(z):
    if z is None or (isinstance(z, float) and np.isnan(z)):
        return "no_data"
    if z >= 1.0:   return "rising"
    if z <= -1.0:  return "falling"
    return "flat"


def _add_months(year: int, month: int, offset: int):
    m = month - 1 + offset
    return year + m // 12, m % 12 + 1


def target_months_from(latest: pd.Timestamp) -> dict:
    """Return {'+1': (y, m), '+3': (y, m), '+6': (y, m), '+12': (y, m)}."""
    return {f"+{h}": _add_months(latest.year, latest.month, h) for h in (1, 3, 6, 12)}


def agreement_badge(kr_delta, id_delta, threshold: float = 0.05) -> str:
    """Do both sources point the same way?"""
    if kr_delta is None or id_delta is None:
        return "insufficient_data"
    same_sign = (kr_delta > 0) == (id_delta > 0)
    both_meaningful = abs(kr_delta) >= threshold and abs(id_delta) >= threshold
    if not same_sign:
        return "conflict"      # opposite signs
    if not both_meaningful:
        return "weak"          # same sign but small
    return "agree"             # same sign, both meaningful


def compute_expected_rise(profile: dict, target_months: dict,
                          now_month_idx: int) -> dict:
    """Seasonal delta (target - now) per source, per horizon, with agreement badge."""
    out = {}
    for label, (_y, tmonth) in target_months.items():
        tidx = tmonth - 1
        kr_now, id_now = profile["kr"][now_month_idx], profile["id"][now_month_idx]
        kr_tgt, id_tgt = profile["kr"][tidx], profile["id"][tidx]
        kr_delta = (None if (kr_now is None or kr_tgt is None)
                    else round(kr_tgt - kr_now, 3))
        id_delta = (None if (id_now is None or id_tgt is None)
                    else round(id_tgt - id_now, 3))
        out[label] = {
            "kr_delta": kr_delta,
            "id_delta": id_delta,
            "agreement": agreement_badge(kr_delta, id_delta),
        }
    return out


def compute_multi_horizon() -> dict:
    """Read forecast_skill_multi_horizon.csv and summarise."""
    path = PROC / "forecast_skill_multi_horizon.csv"
    if not path.exists():
        return {"available": False,
                "note": "forecast_skill_multi_horizon.csv not found. "
                        "Run forecast_multi_horizon.py first."}
    df = pd.read_csv(path)

    per_item = {}
    for item, g in df.groupby("item"):
        per_item[item] = {str(int(r["horizon"])): bool(r["gate_pass"])
                          for _, r in g.iterrows()}

    passed = df[df["gate_pass"]]
    best = None
    if not passed.empty:
        best_row = passed.sort_values("p_adj_bh").iloc[0]
        best = {
            "item": str(best_row["item"]),
            "horizon": int(best_row["horizon"]),
            "rel_gain": float(best_row["rel_gain"]),
            "ci_low": float(best_row["ci_low"]),
            "p_raw": float(best_row["p_one_sided"]),
            "p_adj_bh": float(best_row["p_adj_bh"]),
            "note": ("Strongest single signal across 48 tests; does not survive "
                     "Benjamini-Hochberg correction.")
        }

    horizons = sorted(int(h) for h in df["horizon"].unique().tolist())
    n_tests = int(len(df))
    n_gate_pass = int(df["gate_pass"].sum())
    n_validated = int(df["validated"].sum())

    return {
        "available": True,
        "horizons": horizons,
        "n_tests": n_tests,
        "n_gate_pass": n_gate_pass,
        "validated_after_bh": n_validated,
        "best_single_result": best,
        "per_item_gate_pass": per_item,
        "headline": (
            f"Extended from 12 pre-registered tests (horizon 3 only) to "
            f"{n_tests} tests across horizons {horizons}. "
            f"{n_gate_pass} test(s) pass the raw gate; "
            f"{n_validated} survive BH correction. "
            f"We report {n_validated} of {n_tests} validated."
        ),
        "methodology_note": (
            "Origins every 3 months (expanding window); 12-step forecasts sliced to h. "
            "Block bootstrap block = ceil(h/3) origins (min 3). One-sided bootstrap p, "
            "then BH across all 48 tests. Exploratory only — not part of the "
            "pre-registered single-horizon gate."
        ),
    }


# ---------------------------------------------------------------------------
# Per-item forecast block (unchanged)
# ---------------------------------------------------------------------------
def forecast_block(item, skill, fc):
    if item not in skill.index:
        return {"available": False, "verdict": "no_backtest",
                "note": "No backtest for this item."}
    s = skill.loc[item]
    summary = {
        "best_candidate": s["best_candidate"],
        "persistence_mase": float(s["persistence_mase"]),
        "best_candidate_mase": float(s["best_candidate_mase"]),
        "seasonal_naive_mase": float(s["seasonal_naive_mase"]),
        "beats_persistence": bool(s["beats_persistence"]),
        "beats_seasonal_naive": bool(s["beats_seasonal_naive"]),
        "rel_improvement_vs_persistence": float(s["rel_improvement"]),
        "delta_ci_95": [float(s["delta_ci_low"]), float(s["delta_ci_high"])],
        "fold_win_rate": float(s["win_rate"]),
        "n_folds": int(s["n_folds"]),
    }
    rows = fc[fc["item"] == item]
    if s["verdict"] != "validated" or rows.empty:
        return {
            "available": False,
            "verdict": "not_validated",
            "skill": summary,
            "note": ("Best model candidate did not beat the pre-registered "
                     "persistence baseline convincingly in backtest; no forecast "
                     "values reported."),
        }
    return {
        "available": True,
        "verdict": "validated",
        "method": s["best_candidate"],
        "method_display": METHOD_DISPLAY.get(s["best_candidate"], s["best_candidate"]),
        "next_3_months": [{"month": r["month"], "value": float(r["value"])}
                          for _, r in rows.iterrows()],
        "skill": summary,
        "disclaimer": (f"Validated = beats persistence with block-bootstrap 95% CI > 0 "
                       f"and >= {FORECAST_MIN_REL_IMPROVEMENT:.0%} MASE improvement. "
                       f"Index values (0-100), not units sold; CI is approximate "
                       f"(autocorrelated folds)."),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    lifecycle = pd.read_csv(PROC / "lifecycle.csv").set_index("item")
    seas = pd.read_csv(PROC / "seasonality.csv").set_index("item")
    leb = pd.read_csv(PROC / "lebaran_effect.csv").set_index("item")
    skill = pd.read_csv(PROC / "forecast_skill.csv").set_index("item")
    fc = pd.read_csv(PROC / "forecast_next3.csv")
    clean = pd.read_parquet(PROC / "monthly_clean.parquet")
    clean = clean[~clean["is_partial"]].copy()
    clean["date"] = pd.to_datetime(clean["date"])
    start, latest = clean["date"].min(), clean["date"].max()

    # --- NEW: precompute frontend data blocks once ---
    profiles = compute_seasonal_profile(clean)
    momenta = compute_momentum(clean)
    target_months = target_months_from(latest)
    now_month_idx = latest.month - 1  # 0-indexed for MONTHS list

    items = []
    for item in seas.index:
        s, lc, lb = seas.loc[item], lifecycle.loc[item], leb.loc[item]
        cfg = ITEMS[item]
        layer, parent = cfg["layer"], cfg.get("parent")
        kr_i = classify_seasonality(s["kr_kruskal_p_adj"], s["kr_amplitude"])
        id_i = classify_seasonality(s["id_kruskal_p_adj"], s["id_amplitude"])
        off, direc = phase_offset(s["kr_peak_month"], s["id_peak_month"])
        rel, why = phase_reliability(s["id_kruskal_p_adj"], s["id_amplitude"])
        if kr_i == "strong" and rel and why == "valid":
            conf, rat = "high", "Strong KR seasonality; reliable ID seasonality."
        elif kr_i in ("strong", "moderate"):
            conf, rat = "medium", f"KR {kr_i}; ID {id_i}; {why}."
        else:
            conf, rat = "low", "Weak or no seasonality."

        phase = ({"offset_months": off, "direction": direc, "reliability": why,
                  "disclaimer": ("Phase offset may reflect shared year-end seasonality, "
                                 "not adoption lag. Not causal.")} if rel else
                 {"offset_months": None, "direction": "unvalidated", "reliability": why,
                  "disclaimer": (f"Not reported: {why}. ID seasonality not reliable "
                                 f"enough to define a peak.")})

        p, pk = lb["wilcoxon_p"], int(lb["peak_offset_month"])
        p_adj = lb["wilcoxon_p_adj"]
        lb_i = ("insufficient_data" if pd.isna(p_adj)
                else "significant_near_eid" if p_adj < 0.05 and abs(pk) <= 2
                else "significant_but_confounded" if p_adj < 0.05
                else "not_significant")

        fb = forecast_block(item, skill, fc)
        lims = list(GENERIC_LIMITATIONS)
        if item in ITEM_KEYWORD_LIMITATIONS:
            lims.append(ITEM_KEYWORD_LIMITATIONS[item])
        if layer == "material":
            lims.append(MATERIAL_NOTE)
        if parent:
            lims.append(f"Related to material '{parent}'; do not rank against "
                        f"material-layer items.")

        # --- NEW blocks ---
        prof = profiles.get(item, {"kr": [None] * 12, "id": [None] * 12})
        mom = momenta.get(item, {"kr": None, "id": None})
        exp_rise = compute_expected_rise(prof, target_months, now_month_idx)

        items.append({
            "item": item, "layer": layer, "parent": parent,
            "current_status": {
                "as_of_month": latest.strftime("%Y-%m"),
                "month_position": lifecycle_position(
                    s["kr_peak_month"], latest.month,
                    s["kr_kruskal_p_adj"], s["kr_amplitude"]),
                "kr_peak_month": s["kr_peak_month"],
                "id_peak_month": s["id_peak_month"] if rel else None,
            },
            "seasonality": {
                src: {
                    "peak_month": s[f"{src}_peak_month"],
                    "peak_idx": float(s[f"{src}_peak_idx"]),
                    "trough_month": s[f"{src}_trough_month"],
                    "amplitude": float(s[f"{src}_amplitude"]),
                    "kruskal_p":     None if pd.isna(s[f"{src}_kruskal_p"])
                                     else float(s[f"{src}_kruskal_p"]),
                    "kruskal_p_adj": None if pd.isna(s[f"{src}_kruskal_p_adj"])
                                     else float(s[f"{src}_kruskal_p_adj"]),
                    "interpretation": kr_i if src == "kr" else id_i,
                    **({"peak_month_usable": bool(rel)} if src == "id" else {}),
                } for src in ("kr", "id")
            },
            "seasonal_profile": prof,               # NEW
            "momentum": {                            # NEW
                "kr_z": mom["kr"],
                "id_z": mom["id"],
                "kr_interpretation": momentum_interpretation(mom["kr"]),
                "id_interpretation": momentum_interpretation(mom["id"]),
                "as_of_month": latest.strftime("%Y-%m"),
                "note": ("YoY z-score vs the item's own history. Each item is "
                         "normalised against itself; do NOT rank raw levels across "
                         "items."),
            },
            "expected_rise": exp_rise,               # NEW
            "phase_offset": phase,
            "forecast": fb,
            "lifecycle": {
                "kr_surge_dur_months": float(lc["kr_surge_dur_months"]),
                "id_surge_dur_months": float(lc["id_surge_dur_months"]),
                "kr_volatility_cv": None if pd.isna(lc["kr_volatility_cv"])
                                    else float(lc["kr_volatility_cv"]),
                "id_volatility_cv": None if pd.isna(lc["id_volatility_cv"])
                                    else float(lc["id_volatility_cv"]),
                "half_life_note": "Half-life is an UPPER BOUND (YoY AR1 bias); "
                                  "not a headline metric.",
            },
            "lebaran_effect": {
                "peak_offset_month": pk,
                "wilcoxon_p_raw": None if pd.isna(p) else float(p),
                "wilcoxon_p_adj": None if pd.isna(p_adj) else float(p_adj),
                "interpretation": lb_i,
            },
            "confidence": {"overall": conf, "rationale": rat},
            "business_action": business_action(
                layer, kr_i, s["kr_peak_month"], s["id_peak_month"],
                off, direc, rel, why),
            "item_limitations": lims,
        })

    # --- NEW: multi-horizon summary ---
    multi_h = compute_multi_horizon()

    validated_items = [i["item"] for i in items if i["forecast"]["verdict"] == "validated"]
    validated = len(validated_items)
    phase_reported = sum(1 for i in items if i["phase_offset"]["offset_months"] is not None)
    strong_kr = [i["item"] for i in items
                 if i["seasonality"]["kr"]["interpretation"] == "strong"]

    out = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_range": [start.strftime("%Y-%m"), latest.strftime("%Y-%m")],
        "data_sources": {
            "origin": "Naver DataLab (Korea, daily -> monthly mean)",
            "destination": "Google Trends (Indonesia, monthly)",
        },
        "ranking_rule": ("Never rank across layers. Compare only within: "
                         "item vs item, material vs material, "
                         "item+material vs item+material."),
        "methodology": {
            "seasonality_test": ("Kruskal-Wallis on year-normalised monthly values, "
                                 "Benjamini-Hochberg adjusted over items x 2 sources."),
            "phase_offset": ("peak_month_id - peak_month_kr (mod 12); reported only "
                             "if adjusted ID p < 0.05 and amplitude >= 0.20."),
            "lebaran_test": ("Wilcoxon signed-rank, paired per Eid cycle "
                             "(-6..+3 months); BH-adjusted over 12 items. "
                             "Interpretation uses the adjusted p-value."),
            "forecast_method": (f"Rolling-origin CV, horizon 3, expanding window. "
                                f"Gate baseline pre-registered = persistence. "
                                f"Candidates: Holt-Winters, XGBoost (clipped 0-100). "
                                f"Validated only if mean MASE gain > 0, block-bootstrap "
                                f"95% CI > 0, and gain >= "
                                f"{FORECAST_MIN_REL_IMPROVEMENT:.0%} of baseline MASE."),
            "lag_analysis": ("EXPLORATORY ONLY, not used in this JSON; "
                             "no item survived FDR."),
            "multi_horizon": ("EXPLORATORY extension of the single-horizon gate to "
                              "1/3/6/12 months. 48 tests, BH-corrected. "
                              "Not part of the pre-registered gate."),
        },
        "pitch_summary": {
            "validated_forecast_items": validated_items,
            "strong_kr_seasonality_items": strong_kr,
            "phase_offset_items": phase_reported,
            "n_items": len(items),
            "multi_horizon_tests": multi_h.get("n_tests"),
            "multi_horizon_validated": multi_h.get("validated_after_bh"),
            "headline": (f"{validated} of {len(items)} items pass the pre-registered "
                         f"3-month forecast gate; {phase_reported} items have a "
                         f"reliable KR-to-ID phase offset. Extended to "
                         f"{multi_h.get('n_tests', '?')} tests across 4 horizons, "
                         f"{multi_h.get('validated_after_bh', '?')} survive BH."),
        },
        "data_quality": {
            "google_anomaly_months_masked": list(GOOGLE_ANOMALY_MONTHS),
            "mask_method": "causal forward-fill (prior month)",
            "anomaly_reconfirmed_by_redownload": [
                "oversized_hoodie", "polyester", "cotton"
            ],
            "keyword_type_mix": (
                "Some Google Trends files mix Topic entities (capitalised, e.g. "
                "'Cotton', 'Polyester') with search terms (lowercase, e.g. "
                "'katun'). Topics can dominate the 0-100 normalisation and "
                "compress search-term variation. Re-downloads on a separate day "
                "showed the trends were similar, so the mix is treated as an "
                "acceptable approximation for this MVP and documented as a "
                "limitation rather than fixed."
            ),
            "manual_keyword_exclusions": {k: list(v) for k, v in EXCLUDE_KEYWORDS.items()},
            "naver_denim_removed": True,
            "cotton_fleece_swap": True,
            "sep_2026_naver_days": 28,
            "sep_2026_treated_as": "complete",
        },
        "analysis_status": {
            "items_analyzed": len(items),
            "by_layer": {l: sum(1 for i in items if i["layer"] == l) for l in LAYERS},
            "forecast_validated": validated,
            "forecast_not_validated": len(items) - validated,
            "phase_offset_reported": phase_reported,
            "multi_horizon_tests": multi_h.get("n_tests"),
            "multi_horizon_validated": multi_h.get("validated_after_bh"),
        },
        "multi_horizon": multi_h,                    # NEW top-level block
        "items": items,
        "limitations": [
            "Naver and Google keywords are not semantically equivalent.",
            "Search interest is not sales.",
            "Phase offset may reflect shared year-end seasonality, not adoption lag.",
            f"Forecast values exist only for validated items ({validated} of "
            f"{len(items)}); the rest are reported as not validated, by design.",
            "Forecast confidence intervals are block-bootstrap based and approximate; "
            "fold autocorrelation is not fully corrected.",
            f"Google anomaly month(s) {GOOGLE_ANOMALY_MONTHS} were masked "
            f"(causal forward-fill): Google spiked across unrelated items while "
            f"Naver was flat. Reconfirmed by re-downloading three affected items.",
            "Some Google Trends files mix Topic entities (capitalised) with search "
            "terms (lowercase) in one comparison. Topics can dominate the 0-100 "
            "normalisation and compress search-term variation. Visual re-downloads "
            "showed similar trends; treated as an MVP approximation.",
            "China is not tracked (Baidu Index requires a Chinese phone number).",
            "denim_jacket has no parent material because denim fabric is not tracked.",
            "Sep-2026 covers 28/30 days for the six oldest Naver files; treated "
            "as complete.",
            "Lag analysis is exploratory; p-values are not robust to method choice.",
            "Multi-horizon backtest is exploratory; not part of the pre-registered "
            "single-horizon gate. 0 of 48 tests survive BH correction.",
            "Findings specific to 2017-2026; not generalizable without validation.",
        ],
    }

    path = PROC / "trend_radar.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] -> {path}")
    print(f"items={len(items)} by_layer={out['analysis_status']['by_layer']} "
          f"validated_forecasts={validated} "
          f"multi_horizon_validated={multi_h.get('validated_after_bh')}")


if __name__ == "__main__":
    main()