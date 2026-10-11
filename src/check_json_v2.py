# src/check_json_v2.py
"""Structural + consistency checks on trend_radar.json."""
import json, sys
from pathlib import Path
from config import EXPECTED_ITEMS, LAYERS, ITEMS, GOOGLE_ANOMALY_MONTHS
from trend_radar import SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
d = json.load(open(ROOT / "data" / "processed" / "trend_radar.json", encoding="utf-8"))

errs = []
def chk(cond, msg):
    if not cond:
        errs.append(msg)

chk(d.get("schema_version") == SCHEMA_VERSION,
    f"schema {d.get('schema_version')} != {SCHEMA_VERSION}")

got = {i["item"] for i in d["items"]}
chk(got == EXPECTED_ITEMS,
    f"items mismatch: missing={sorted(EXPECTED_ITEMS - got)} "
    f"extra={sorted(got - EXPECTED_ITEMS)}")

print(f"schema {d['schema_version']} | {len(d['items'])} items | "
      f"{len(d['limitations'])} limitations | range {d['data_range']}")

# pitch_summary and data_quality presence
chk("pitch_summary" in d, "missing pitch_summary block")
chk("data_quality" in d, "missing data_quality block")
if "data_quality" in d:
    chk(set(d["data_quality"].get("google_anomaly_months_masked", []))
        == set(GOOGLE_ANOMALY_MONTHS),
        "data_quality.google_anomaly_months_masked mismatch")

print(f"{'item':18s}{'layer':15s}{'KR seas':14s}{'ID seas':14s}"
      f"{'phase':8s}{'forecast':14s}conf")

validated_count = 0
for i in d["items"]:
    chk(i["layer"] == ITEMS[i["item"]]["layer"] and i["layer"] in LAYERS,
        f"{i['item']}: bad layer")
    fc = i["forecast"]
    chk(fc["available"] == (fc["verdict"] == "validated"),
        f"{i['item']}: available/verdict mismatch")
    if fc["available"]:
        validated_count += 1
        chk(len(fc["next_3_months"]) == 3,
            f"{i['item']}: need 3 forecast months")
        chk(all(0 <= m["value"] <= 100 for m in fc["next_3_months"]),
            f"{i['item']}: forecast outside 0-100")
        chk(fc["skill"]["delta_ci_95"][0] > 0,
            f"{i['item']}: validated but CI low <= 0")
        chk(fc["skill"].get("beats_persistence") is True,
            f"{i['item']}: validated but beats_persistence is not True")
    else:
        chk("next_3_months" not in fc,
            f"{i['item']}: values leaked for non-validated item")
    if i["layer"] == "material":
        chk("siapkan stok" not in i["business_action"].lower(),
            f"{i['item']}: SKU-stock wording on material layer")
    po = i["phase_offset"]["offset_months"]
    print(f"{i['item']:18s}{i['layer']:15s}"
          f"{i['seasonality']['kr']['interpretation']:14s}"
          f"{i['seasonality']['id']['interpretation']:14s}"
          f"{('-' if po is None else f'{po:+d}'):8s}"
          f"{fc['verdict']:14s}{i['confidence']['overall']}")

st = d["analysis_status"]
chk(st["forecast_validated"] == validated_count,
    "analysis_status.forecast_validated mismatch")
if "pitch_summary" in d:
    chk(d["pitch_summary"]["n_items"] == len(d["items"]),
        "pitch_summary.n_items mismatch")

print("\n" + ("OK: no inconsistencies." if not errs
              else "PROBLEMS:\n  - " + "\n  - ".join(errs)))
sys.exit(1 if errs else 0)