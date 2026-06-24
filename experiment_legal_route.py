#!/usr/bin/env python3
"""
Evaluate legal_route classifier WITHOUT using pre-existing law_type labels.
Pure keyword + code-prefix rules only.
"""
import json, re
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

corpus = json.loads((DATA_DIR / "corpus" / "combined.json").read_text(encoding="utf-8"))

def classify_pure_rules(entry):
    """Classify using ONLY code prefix and keyword matching."""
    text = entry.get("text", "").lower()
    code = entry.get("code", "").upper()
    
    # ECCN prefix rules (US eCFR)
    if code.startswith("ECCN-"):
        base = code.replace("ECCN-", "")[:2]
        # 0A-E: military/strategic -> trade law
        if base.startswith("0") and base[1] in "ABCDE":
            return "대외무역법"
        # 1C/2B/3A/5A/6A/7A/8A/9A: advanced tech -> tech protection
        if base in ["1C", "2B", "3A", "5A", "6A", "7A", "8A", "9A"]:
            return "산업기술보호법"
        # 1A/2A/3A/4A/5A/6A: depends
        if base in ["1A", "2A", "3A", "4A", "5A", "6A"]:
            if any(kw in text for kw in ["semiconductor", "microprocessor", "integrated circuit", "encryption", "cryptographic"]):
                return "산업기술보호법"
            return "대외무역법"
        # Default for ECCN
        if base.startswith("1") or base.startswith("2"):
            return "산업기술보호법"
        return "대외무역법"
    
    # Wassenaar code patterns
    # 0A-E: military -> trade law
    if re.match(r'^0[ABCDE]', code):
        return "대외무역법"
    # 1.A -> military
    if code.startswith("1.A"):
        return "대외무역법"
    # 1.B -> missile
    if code.startswith("1.B"):
        return "대외무역법"
    # 2.B -> materials processing -> tech
    if code.startswith("2.B"):
        return "산업기술보호법"
    # 3.A -> electronics -> tech
    if code.startswith("3.A"):
        return "산업기술보호법"
    # 4.A -> sensors -> tech (sometimes military)
    if code.startswith("4.A"):
        if "missile" in text or "military" in text:
            return "대외무역법"
        return "산업기술보호법"
    # 5.A -> telecommunications -> tech
    if code.startswith("5.A"):
        return "산업기술보호법"
    # 6.A -> instruments -> tech
    if code.startswith("6.A"):
        return "산업기술보호법"
    # 7.A -> aerospace -> trade
    if code.startswith("7.A"):
        return "대외무역법"
    # 8.A -> marine -> trade
    if code.startswith("8.A"):
        return "대외무역법"
    # 9.A -> general -> tech
    if code.startswith("9.A"):
        return "산업기술보호법"
    
    # SCOMET patterns
    if code.startswith("SCOMET-MIL") or code.startswith("SCOMET-ML"):
        return "대외무역법"
    if code.startswith("SCOMET-NUM"):
        return "산업기술보호법"
    
    # Text keyword fallback
    military_kws = ["firearm", "ammunition", "weapon", "military", "tank", "aircraft",
                    "missile", "naval", "artillery", "munitions", "armored"]
    tech_kws = ["semiconductor", "microprocessor", "encryption", "cryptographic",
                "integrated circuit", "chip", "wafer", "sensor", "laser", "radar"]
    
    mil_score = sum(1 for kw in military_kws if kw in text)
    tech_score = sum(1 for kw in tech_kws if kw in text)
    
    if mil_score > tech_score:
        return "대외무역법"
    elif tech_score > mil_score:
        return "산업기술보호법"
    else:
        return "대외무역법"  # default

correct = 0
total = 0
confusion = {"TP": 0, "TN": 0, "FP": 0, "FN": 0}

for entry in corpus:
    true_label = entry.get("law_type", "")
    if not true_label:
        continue
    
    pred = classify_pure_rules(entry)
    
    true_is_trade = "대외" in true_label
    pred_is_trade = pred == "대외무역법"
    
    total += 1
    if pred_is_trade == true_is_trade:
        correct += 1
        if true_is_trade:
            confusion["TP"] += 1
        else:
            confusion["TN"] += 1
    else:
        if true_is_trade:
            confusion["FN"] += 1
        else:
            confusion["FP"] += 1

accuracy = correct / total if total > 0 else 0
print(f"Pure-rule legal_route accuracy: {accuracy:.4f}")
print(f"Total evaluated: {total}")
print(f"Confusion: {confusion}")

# Dump misclassified examples
fp_examples = []
fn_examples = []
for entry in corpus:
    true_label = entry.get("law_type", "")
    if not true_label:
        continue
    pred = classify_pure_rules(entry)
    true_is_trade = "대외" in true_label
    pred_is_trade = pred == "대외무역법"
    if pred_is_trade != true_is_trade:
        ex = {"code": entry["code"], "source": entry["source"], "pred": pred, "true": true_label}
        if pred_is_trade and not true_is_trade:
            fp_examples.append(ex)
        else:
            fn_examples.append(ex)

print(f"\nFalse positives (pred trade, true tech): {len(fp_examples)}")
for ex in fp_examples[:5]:
    print(f'  {ex["code"]} ({ex["source"]}): pred={ex["pred"]}, true={ex["true"]}')
print(f"\nFalse negatives (pred tech, true trade): {len(fn_examples)}")
for ex in fn_examples[:5]:
    print(f'  {ex["code"]} ({ex["source"]}): pred={ex["pred"]}, true={ex["true"]}')

results = {
    "accuracy": round(accuracy, 4),
    "total": total,
    "confusion": confusion,
    "fp_examples": fp_examples[:20],
    "fn_examples": fn_examples[:20],
}
(OUT_DIR / "legal_route_pure_rules.json").write_text(
    json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
)
