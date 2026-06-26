#!/usr/bin/env python3
"""TASK B/C — build a collision-free, corpus-text-grounded validated query set.

The original external_consultation_queries.json used bare control codes as
candidate labels. 13/30 collided across control systems (normalize_code maps
ECCN-2B001 and a SCOMET 2B001 to the same key) and many labels did not match
the eCFR text they pointed to (e.g. a lithium-battery-chemical query labeled
1C991 "Vaccines, immunotoxins").

This script keeps all 30 genuine consultation queries but replaces the labels
with a curated, source-pinned ground truth:

- Labels are stored as FULL eCFR codes (ECCN-XXXX), so matching is exact and
  collision-free (TASK C).
- A label is kept only when the eCFR entry's own text clearly describes the
  item category in the query (grounded, not guessed). Confidence is high when
  the text is an obvious description match, medium when a plausible category.
- Queries whose item has no clearly matching single eCFR entry are flagged
  excluded_from_metrics with a reason, instead of being given a fake label.

IMPORTANT: this is corpus-text-grounded CATEGORY labeling for a retrieval
target, NOT a legal export-control determination and NOT expert-validated.
Output: data/external_consultation_queries_validated.json
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SRC = DATA_DIR / "external_consultation_queries.json"
DST = DATA_DIR / "external_consultation_queries_validated.json"
CORPUS = DATA_DIR / "corpus" / "combined.json"

# id -> (labels[list of full eCFR codes], confidence, basis, exclusion_reason or None)
CURATION = {
    "ext-002": (["ECCN-3B001"], "high", "eCFR 3B001 = semiconductor manufacturing equipment; matches plasma etching equipment.", None),
    "ext-003": (["ECCN-2B001"], "high", "eCFR 2B001 = machine tools for cutting metals; matches 5-axis CNC machining center.", None),
    "ext-004": (["ECCN-7A002"], "high", "eCFR 7A002 = gyros / angular rate sensors; matches drone gyroscope module.", None),
    "ext-005": (["ECCN-5D002", "ECCN-5D991"], "high", "eCFR 5D002 = encryption software; matches cryptographic source code.", None),
    "ext-006": (["ECCN-1C002"], "medium", "eCFR 1C002 = metal alloys (incl. titanium aluminides); plausible for titanium alloy plate.", None),
    "ext-007": (["ECCN-6A001"], "high", "eCFR 6A001 = acoustic systems; matches underwater acoustic test equipment.", None),
    "ext-013": (["ECCN-2D001"], "medium", "eCFR 2D001 = software for 2B test/production equipment; plausible for vibration-test control software.", None),
    "ext-015": (["ECCN-3A002"], "medium", "eCFR 3A002 = general purpose electronic test/measurement equipment; plausible for >1GHz oscilloscope.", None),
    "ext-016": (["ECCN-1C002"], "medium", "eCFR 1C002 = metal alloy powder; plausible for 3D-printing metal powder.", None),
    "ext-017": (["ECCN-3A001"], "high", "eCFR 3A001 = electronic items (incl. MMICs at 3A001.b.2); matches GaAs MMIC radar components.", None),
    "ext-023": (["ECCN-5A002", "ECCN-5A991"], "high", "eCFR 5A002 = information security systems/components; matches encryption chips.", None),
    "ext-028": (["ECCN-6A001"], "high", "eCFR 6A001 = acoustic systems; matches torpedo sonar / acoustic signal processing.", None),
    "ext-029": (["ECCN-3B001"], "medium", "eCFR 3B001 = semiconductor manufacturing equipment; plausible for lithography positioning table.", None),
    # --- excluded: no clearly matching single eCFR entry ---
    "ext-001": ([], "none", "", "Lithium-ion battery cathode chemicals do not map to a clear single eCFR entry; original labels (1C350 toxic precursors, 1C991 vaccines) mismatch."),
    "ext-008": ([], "none", "", "MRI cryogenic cooling part: 3A001/3A002 are generic; no clear single-entry match."),
    "ext-009": ([], "none", "", "FPGA firmware for image processing: ambiguous between 3D001/5D002; no clear match."),
    "ext-010": ([], "none", "", "UAV fuel cell stack: 1A001/1A002 (fluorinated/composite) mismatch the item."),
    "ext-011": ([], "none", "", "Query intentionally generic ('electronic components'); no single ground-truth entry."),
    "ext-012": ([], "none", "", "Laser rangefinder: labels 6A001 (acoustic)/6A008 (radar) are wrong category; lasers fall under 6A005-series not in matched labels."),
    "ext-014": ([], "none", "", "High-pressure hydrogen tank: 1C005/1C006 (superconductors/fluids) mismatch the item."),
    "ext-018": ([], "none", "", "USV propulsion: 1A001/1A002 mismatch the item."),
    "ext-019": ([], "none", "", "Composite honeycomb tech data: 2C001 absent in eCFR, 2E001 link weak; no clear match."),
    "ext-020": ([], "none", "", "Medical detector module: 3A001 generic, 3A980 (voiceprint) wrong; no clear match."),
    "ext-021": ([], "none", "", "Liquid-hydrogen cryogenic pump: 2B002/2B003 (machine tools) mismatch the item."),
    "ext-022": ([], "none", "", "Radiation detector: 6A001 (acoustic)/6A002 (optical) wrong category."),
    "ext-024": ([], "none", "", "Turbo compressor: 2B001/2B002 (machine tools) mismatch the item."),
    "ext-025": ([], "none", "", "Multi-stage centrifugal pump: 2B001 (machine tools)/2D001 mismatch the item."),
    "ext-026": ([], "none", "", "Drone RF module 5GHz: 7A001/7A002 (accelerometers/gyros) wrong category; RF falls under 5A001-series."),
    "ext-027": ([], "none", "", "Semiconductor photoresist precursor: 1C350 (toxic precursors)/1C991 (vaccines) mismatch the item."),
    "ext-030": ([], "none", "", "EV battery cooling plate: 1C002 (alloys)/1C005 link weak; no clear single match."),
}


def main() -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    by_code = {e["code"]: e for e in corpus}
    payload = json.loads(SRC.read_text(encoding="utf-8"))

    kept = excluded = 0
    out_queries = []
    for q in payload["queries"]:
        qid = q["id"]
        if qid not in CURATION:
            raise KeyError(f"no curation entry for {qid}")
        labels, conf, basis, reason = CURATION[qid]
        # verify every kept label exists uniquely as an exact corpus code
        for lbl in labels:
            if lbl not in by_code:
                raise ValueError(f"{qid}: label {lbl} not an exact corpus code")
        excluded_flag = reason is not None
        if excluded_flag:
            excluded += 1
        else:
            kept += 1
        out_queries.append({
            "id": qid,
            "lang": q.get("lang"),
            "query": q.get("query", ""),
            "context": q.get("context"),
            "validated_labels": labels,            # exact full eCFR codes
            "label_confidence": conf,
            "label_basis_corpus_text": basis,
            "excluded_from_metrics": excluded_flag,
            "exclusion_reason": reason or "",
            "original_candidate_labels": q.get("candidate_labels", []),
        })

    out = {
        "meta": {
            "count": len(out_queries),
            "evaluated_count": kept,
            "excluded_count": excluded,
            "label_space": "eCFR full codes only (collision-free, exact match)",
            "label_nature": (
                "Corpus-text-grounded CATEGORY labels for a retrieval target. "
                "NOT a legal export-control determination and NOT expert-validated. "
                "Labels kept only when the eCFR entry text clearly describes the item category; "
                "otherwise the query is excluded_from_metrics with a reason."
            ),
            "built_by": "build_validated_queries.py",
        },
        "queries": out_queries,
    }
    DST.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total": len(out_queries), "evaluated": kept, "excluded": excluded},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
