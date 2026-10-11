# src/build_frontend.py   run:  python build_frontend.py   -> writes kancil.html (single file, JSON inlined)
import csv, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
PROC = HERE.parent / "data" / "processed"
die = lambda m: sys.exit("[ERROR] " + m)

jp = PROC / "trend_radar.json"
if not jp.exists(): die(f"{jp} not found. Run trend_radar.py first.")
data = json.load(open(jp, encoding="utf-8"))

# --- guards: the page assumes schema 4.4 with the frontend blocks ---
for k in ("schema_version", "data_range", "items", "analysis_status", "multi_horizon", "data_quality", "limitations"):
    if k not in data: die(f"trend_radar.json missing '{k}'. Re-run trend_radar.py.")
if data["schema_version"] != "4.4": die(f"schema {data['schema_version']} != 4.4")
if not data["multi_horizon"].get("available"): die("multi_horizon not available: run forecast_multi_horizon.py, then trend_radar.py")
for i in data["items"]:
    for k in ("seasonal_profile", "momentum", "expected_rise", "seasonality", "forecast"):
        if k not in i: die(f"item '{i['item']}' missing '{k}'")
    if not all(h in i["expected_rise"] for h in ("+1", "+3", "+6")): die(f"{i['item']}: expected_rise horizons missing")

# --- consistency: numbers the page shows must agree with each other ---
n_val = sum(i["forecast"]["verdict"] == "validated" for i in data["items"])
if n_val != data["analysis_status"]["forecast_validated"]: die("validated count mismatch")
best = data["multi_horizon"].get("best_single_result")
if not best: die("multi_horizon has no best_single_result")

# --- exploratory lag results are not in the JSON: read from CSV ---
extra = {"lag": None}
p = PROC / "lag_results.csv"
if p.exists():
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    extra["lag"] = {"n": len(rows),
                    "fdr": sum(r["significant_fdr05"] == "True" for r in rows),
                    "placebo": sum(r["placebo_flag"].startswith("WARNING") for r in rows)}
else:
    print("[WARN] lag_results.csv not found: lag/placebo cells will show '-'")

tpl = (HERE / "kancil_template.html").read_text(encoding="utf-8")
blob = ("window.KANCIL=" + json.dumps(data, ensure_ascii=False) + ";window.KANCIL_EXTRA="
        + json.dumps(extra) + ";").replace("</", "<\\/")
out = HERE / "kancil.html"
out.write_text(tpl.replace("/*__DATA__*/", blob), encoding="utf-8")
print(f"[OK] {out} ({out.stat().st_size/1024:.0f} KB) | schema {data['schema_version']} | validated {n_val}/{len(data['items'])} "
      f"| multi-horizon {data['multi_horizon']['validated_after_bh']}/{data['multi_horizon']['n_tests']} | lag {extra['lag']}")
