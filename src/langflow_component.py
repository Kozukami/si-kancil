# src/langflow_component.py
"""Langflow custom component: reads trend_radar.json and exposes one item to IBM Bob.
Alias resolution never guesses: ambiguous queries return candidates; unknown ones say so."""
import json, os
from pathlib import Path

ALIASES = {
    "cardigan": "cardigan", "kardigan": "cardigan", "rajut cardigan": "cardigan",
    "cargo": "cargo_pants", "celana cargo": "cargo_pants", "cargo pants": "cargo_pants",
    "knit vest": "knit_vest", "rompi rajut": "knit_vest", "vest rajut": "knit_vest",
    "oversized blazer": "oversized_blazer", "blazer oversize": "oversized_blazer",
    "blazer": "oversized_blazer",
    "oversized hoodie": "oversized_hoodie", "hoodie oversize": "oversized_hoodie",
    "hoodie": "oversized_hoodie",
    "wide leg pants": "wide_leg_pants", "celana kulot": "wide_leg_pants",
    "kulot": "wide_leg_pants",
    "viscose": "viscose", "rayon": "viscose", "bahan viscose": "viscose",
    "polyester": "polyester", "poliester": "polyester", "bahan poliester": "polyester",
    "cotton": "cotton", "katun": "cotton", "kain katun": "cotton", "bahan katun": "cotton",
    "fleece": "fleece", "polar fleece": "fleece", "kain fleece": "fleece",
    "cotton shirt": "cotton_shirt", "kemeja katun": "cotton_shirt",
    "kemeja cotton": "cotton_shirt",
    "denim jacket": "denim_jacket", "jaket denim": "denim_jacket",
    "jaket jeans": "denim_jacket", "jean jacket": "denim_jacket",
}
AMBIGUOUS_EXACT = {"cotton": ["cotton", "cotton_shirt"],
                   "katun": ["cotton", "cotton_shirt"]}


def normalize_item(raw):
    """-> (canonical|None, kind, candidates).
    kinds: exact, substring_unique, ambiguous, too_short,
           material_not_tracked, not_found, empty."""
    if not raw or not raw.strip():
        return None, "empty", []
    key = raw.strip().lower()
    if len(key) < 3:
        return None, "too_short", []
    if key == "denim":
        return None, "material_not_tracked", ["denim_jacket"]
    if key in AMBIGUOUS_EXACT:
        return None, "ambiguous", AMBIGUOUS_EXACT[key]
    if key in ALIASES:
        return ALIASES[key], "exact", [ALIASES[key]]
    hits = sorted({c for a, c in ALIASES.items() if key in a or a in key})
    if len(hits) == 1:
        return hits[0], "substring_unique", hits
    if len(hits) > 1:
        return None, "ambiguous", hits
    return None, "not_found", []


def render_report(item_data):
    cs, fc = item_data["current_status"], item_data["forecast"]
    L = [f"**{item_data['item']}** (layer: {item_data['layer']}, "
         f"parent: {item_data.get('parent') or '—'})",
         f"Posisi bulan (per {cs['as_of_month']}): {cs['month_position']}",
         f"Puncak musiman KR: {cs['kr_peak_month']}",
         f"Puncak musiman ID: {cs['id_peak_month'] or 'tidak dapat diandalkan'}"]
    if fc.get("available"):
        L.append(f"Forecast (tervalidasi vs persistence): {fc['method_display']}")
        L += [f"  - {m['month']}: {m['value']}" for m in fc["next_3_months"]]
    else:
        L.append("Forecast: tidak tersedia. Model tidak terbukti mengalahkan "
                 "baseline persistence di backtest.")
    L += [f"Rekomendasi: {item_data['business_action']}",
          f"Confidence: {item_data['confidence']['overall']} "
          f"({item_data['confidence']['rationale']})",
          "Catatan: keputusan akhir ada di pemilik toko. "
          "Sumber: Naver DataLab (KR) + Google Trends (ID).",
          "Jangan membandingkan skor lintas layer (item / material / item+material).",
          "Batasan data:"]
    L += [f"  - {x}" for x in item_data.get("item_limitations", [])[-3:]]
    return "\n".join(L)


try:
    from langflow.custom import Component
    from langflow.io import MessageTextInput, Output
    from langflow.schema.message import Message

    def _msg(text):
        try:
            return Message(text=text)
        except TypeError:
            return Message(value=text)

    class TrendRadarTool(Component):
        display_name = "Kancil Trend Radar"
        description = ("Look up a fashion item/material: seasonality, validated "
                       "forecast, business action. Never rank across layers.")
        icon = "trending-up"
        inputs = [MessageTextInput(
            name="item_query", display_name="Item or material",
            info="e.g. blazer, katun, jaket denim, viscose")]
        outputs = [Output(display_name="Trend Report", name="report",
                          method="build_report")]

        def build_report(self):
            path = os.environ.get(
                "KANCIL_TREND_RADAR",
                str(Path(__file__).resolve().parents[1]
                    / "data" / "processed" / "trend_radar.json"))
            data = json.load(open(path, encoding="utf-8"))
            key, kind, cands = normalize_item(self.item_query or "")
            if kind in ("empty", "too_short"):
                return _msg("Kata kunci terlalu pendek. Mohon ketik lebih spesifik.")
            if kind == "material_not_tracked":
                return _msg("Bahan 'denim' belum dilacak. Terdekat: denim_jacket. "
                            "Mau lihat jaket denim?")
            if kind == "ambiguous":
                return _msg(f"'{self.item_query}' bisa merujuk ke: "
                            f"{', '.join(cands)}. Mohon perjelas.")
            if kind == "not_found":
                return _msg(f"'{self.item_query}' tidak dilacak. Tersedia: "
                            f"{sorted(i['item'] for i in data['items'])}")
            item = next((i for i in data["items"] if i["item"] == key), None)
            return _msg(render_report(item) if item
                        else f"Data untuk '{key}' tidak ditemukan.")
except ImportError:
    pass