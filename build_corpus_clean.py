#!/usr/bin/env python3
"""Build a cleaned, source-traceable export-control retrieval corpus.

This script intentionally avoids assigning legal conclusions such as
"industrial technology protection law applies".  All entries are official
control-list entries from public sources, and any Korean legal routing is
represented only as a conservative review hint.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from build_corpus import parse_scomet, parse_wassenaar

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"
CORPUS_DIR.mkdir(parents=True, exist_ok=True)

WASSENAAR_PDF = DATA_DIR / "wassenaar_2025.pdf"
SCOMET_PDF = DATA_DIR / "india_scomet_2024_official.pdf"
ECFR_JSON = CORPUS_DIR / "ecfr_supp1.json"

SOURCE_META = {
    "wassenaar_2025": {
        "source_name": "Wassenaar Arrangement List of Dual-Use Goods and Technologies and Munitions List 2025 Corr.",
        "source_url": "https://www.wassenaar.org/app/uploads/2025/12/List-of-Dual-Use-Goods-and-Technologies-and-ML-2025.pdf",
        "control_system": "wassenaar_dual_use",
        "official_route": "strategic_goods_review",
    },
    "india_scomet_2024": {
        "source_name": "DGFT Updated and Revised SCOMET List 2024, as notified on 2024-09-02",
        "source_url": "https://content.dgft.gov.in/Website/UPDATED%20SCOMET%20List%202024%20as%20on%2002.09.2024.pdf",
        "control_system": "india_scomet",
        "official_route": "foreign_control_list_reference",
    },
    "ecfr_part774": {
        "source_name": "eCFR 15 CFR Part 774 Supplement No. 1 — Commerce Control List",
        "source_url": "https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-774/appendix-Supplement%20No.%201%20to%20Part%20774",
        "control_system": "us_ear_ccl",
        "official_route": "foreign_control_list_reference",
    },
}

CODE_PATTERNS = {
    "wassenaar_2025": re.compile(r"^[0-9]\.[A-E](?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?$"),
    "india_scomet_2024": re.compile(r"^[0-9][A-Z][0-9]{3}[a-z]?$"),
    "ecfr_part774": re.compile(r"^ECCN-[0-9][A-EY][0-9]{3}[A-Za-z]?(?:\.[A-Za-z0-9]+)*$"),
}

CONTROL_CODE_RE = re.compile(
    r"\b(?:ECCN-)?[0-9][A-EY][0-9]{3}[A-Za-z]?(?:\.[A-Za-z0-9]+)*\b"
    r"|\b[0-9]\.[A-E](?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?\b",
    re.I,
)

DROP_TEXT_RE = re.compile(
    r"^\s*(?:\[?reserved\]?|not used since|software$|technology$|materials(?:\s*-\s*none)?$|systems, equipment and components$)\s*$",
    re.I,
)

FRAGMENT_START_RE = re.compile(r"^\s*(?:or|and|&)\b", re.I)

POSSIBLE_NCT_KEYWORDS = [
    "semiconductor",
    "integrated circuit",
    "microprocessor",
    "wafer",
    "display",
    "battery",
    "secondary cell",
    "electric vehicle",
    "shipbuilding",
    "robot",
    "hydrogen",
    "aerospace",
    "biotechnology",
    "nuclear",
]


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text


def source_valid_code(source: str, code: str) -> bool:
    pat = CODE_PATTERNS.get(source)
    return bool(pat and pat.match(code or ""))


def quality_flags(entry: dict) -> list[str]:
    text = entry.get("text", "")
    flags: list[str] = []
    if len(text) < 40:
        flags.append("short_text")
    if FRAGMENT_START_RE.match(text):
        flags.append("possible_fragment")
    if CONTROL_CODE_RE.search(text):
        flags.append("contains_cross_reference")
    lower = text.lower()
    if any(k in lower for k in POSSIBLE_NCT_KEYWORDS):
        flags.append("possible_national_core_technology_review")
    return flags


def should_drop(entry: dict) -> tuple[bool, str | None]:
    code = entry.get("code", "")
    source = entry.get("source", "")
    text = clean_text(entry.get("text", ""))
    if not code or not text:
        return True, "empty_code_or_text"
    if not source_valid_code(source, code):
        return True, "invalid_code_format"
    if DROP_TEXT_RE.match(text):
        return True, "non_control_or_reserved_heading"
    if FRAGMENT_START_RE.match(text) and len(text) < 80:
        return True, "short_fragment"
    return False, None


def normalize_entry(entry: dict) -> dict:
    source = entry["source"]
    meta = SOURCE_META[source]
    text = clean_text(entry.get("text", ""))
    out = {
        "code": entry["code"].strip(),
        "text": text,
        "source": source,
        "page": entry.get("page"),
        "control_system": meta["control_system"],
        "source_name": meta["source_name"],
        "source_url": meta["source_url"],
        "official_route": meta["official_route"],
        "review_flags": [],
    }
    out["review_flags"] = quality_flags(out)
    return out


def load_raw_entries() -> list[dict]:
    wass = parse_wassenaar(WASSENAAR_PDF)
    scomet = parse_scomet(SCOMET_PDF)
    ecfr = json.loads(ECFR_JSON.read_text(encoding="utf-8"))
    for item in wass:
        item["source"] = "wassenaar_2025"
    for item in scomet:
        item["source"] = "india_scomet_2024"
    for item in ecfr:
        item["source"] = "ecfr_part774"
    return wass + scomet + ecfr


def dedupe(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for entry in entries:
        by_key[(entry["source"], entry["code"])].append(entry)

    deduped: list[dict] = []
    duplicates: list[dict] = []
    for key, group in sorted(by_key.items()):
        group = sorted(group, key=lambda x: len(x.get("text", "")), reverse=True)
        deduped.append(group[0])
        for dropped in group[1:]:
            duplicates.append(
                {
                    "source": key[0],
                    "code": key[1],
                    "kept_text_len": len(group[0].get("text", "")),
                    "dropped_text_len": len(dropped.get("text", "")),
                }
            )
    return deduped, duplicates


def main() -> None:
    raw = load_raw_entries()
    kept: list[dict] = []
    dropped: list[dict] = []

    for entry in raw:
        entry["text"] = clean_text(entry.get("text", ""))
        drop, reason = should_drop(entry)
        if drop:
            dropped.append(
                {
                    "source": entry.get("source"),
                    "code": entry.get("code"),
                    "reason": reason,
                    "text_preview": entry.get("text", "")[:160],
                }
            )
            continue
        kept.append(normalize_entry(entry))

    combined, duplicates = dedupe(kept)
    combined = sorted(combined, key=lambda x: (x["source"], x["code"]))

    (CORPUS_DIR / "combined.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (CORPUS_DIR / "corpus_quality_report.json").write_text(
        json.dumps(
            {
                "generated_by": "build_corpus_clean.py",
                "source_files": {
                    "wassenaar_2025.pdf": {
                        "path": str(WASSENAAR_PDF.relative_to(ROOT)),
                        "sha256": sha256(WASSENAAR_PDF),
                    },
                    "india_scomet_2024_official.pdf": {
                        "path": str(SCOMET_PDF.relative_to(ROOT)),
                        "sha256": sha256(SCOMET_PDF),
                    },
                    "ecfr_supp1.json": {
                        "path": str(ECFR_JSON.relative_to(ROOT)),
                        "sha256": sha256(ECFR_JSON),
                    },
                },
                "raw_count_by_source": dict(Counter(x.get("source") for x in raw)),
                "kept_count_by_source": dict(Counter(x.get("source") for x in combined)),
                "dropped_count_by_reason": dict(Counter(x["reason"] for x in dropped)),
                "dropped_examples": dropped[:80],
                "duplicate_count": len(duplicates),
                "duplicate_examples": duplicates[:80],
                "notes": [
                    "law_type was intentionally removed because it was a heuristic label, not an official legal determination.",
                    "official_route is a conservative workflow hint only; it is not a legal conclusion.",
                    "possible_national_core_technology_review is keyword-based and must be treated as a secondary review flag.",
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"raw={len(raw)} kept={len(combined)} dropped={len(dropped)} duplicates={len(duplicates)}")
    print("kept_by_source:", dict(Counter(x.get("source") for x in combined)))


if __name__ == "__main__":
    main()
