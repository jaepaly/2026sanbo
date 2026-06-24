#!/usr/bin/env python3
"""Build combined corpus with legal routing labels."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = DATA_DIR / "corpus"

wass = json.loads((DATA_DIR / "corpus" / "wassenaar.json").read_text(encoding="utf-8"))
scomet = json.loads((DATA_DIR / "corpus" / "india_scomet.json").read_text(encoding="utf-8"))
ecfr = json.loads((DATA_DIR / "corpus" / "ecfr_supp1.json").read_text(encoding="utf-8"))

def classify_legal_route(entry):
    code = (entry.get("code") or "").upper()
    text = (entry.get("text") or "").upper()
    if any(k in code for k in ["0A", "0B", "0C", "0D", "0E"]) or \
       any(k in text for k in ["FIREARM", "AMMUNITION", "SHOTGUN", "RIFLE", "PISTOL", "MILITARY"]):
        return "대외무역법"
    if any(k in code for k in ["1C", "2B", "3A", "5A", "6A"]) or \
       any(k in text for k in ["SEMICONDUCTOR", "ADVANCED LOGIC", "ECRYPTION", "UNDERWATER", "AIRCRAFT", "UAV"]):
        return "산업기술보호법"
    return "대외무역법"

for item in wass:
    item["law_type"] = classify_legal_route(item)
for item in scomet:
    item["law_type"] = classify_legal_route(item)
for item in ecfr:
    item["law_type"] = classify_legal_route(item)

combined = wass + scomet + ecfr
out_path = OUT_DIR / "combined.json"
out_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Corpus size: {len(combined)} entries (Wassenaar={len(wass)}, SCOMET={len(scomet)}, eCFR={len(ecfr)})")
from collections import Counter
c = Counter(it["law_type"] for it in combined)
print(f"Law distribution: {dict(c)}")
