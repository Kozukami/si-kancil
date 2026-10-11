# src/check_json.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "data" / "processed" / "trend_radar.json"

with open(path, encoding="utf-8") as f:
    d = json.load(f)

print(f"schema_version : {d.get('schema_version')}")
print(f"generated_at   : {d.get('generated_at')}")
print(f"data_range     : {d.get('data_range')}")
print(f"items          : {len(d.get('items', []))}")
print(f"limitations    : {len(d.get('limitations', []))}")
print()
print(f"analysis_status:")
for k, v in d.get("analysis_status", {}).items():
    print(f"  {k}: {v}")
print()
print(f"{'item':20s} | {'pos':18s} | {'conf':7s} | {'kr':4s} | {'id':4s} | {'offset':>6s} | reliability")
print("-" * 110)
for i in d["items"]:
    pos = i["current_status"]["month_position"]
    conf = i["confidence"]["overall"]
    kr = i["seasonality"]["kr"]["peak_month"]
    idp = i["seasonality"]["id"]["peak_month"]
    po = i["phase_offset"]
    off = po["offset_months"] if po["offset_months"] is not None else "  —"
    rel = po["reliability"]
    print(f"{i['item']:20s} | {pos:18s} | {conf:7s} | {kr:4s} | {idp:4s} | {str(off):>6s} | {rel}")