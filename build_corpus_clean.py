#!/usr/bin/env python3
"""Build a cleaned, source-traceable export-control retrieval corpus.

This script intentionally avoids assigning legal conclusions such as
"industrial technology protection law applies".  All entries are official
control-list entries from public sources, and any Korean legal routing is
represented only as a conservative review hint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from build_corpus import (
    TERMINATOR_RE,
    classify_completeness,
    parse_scomet,
    parse_scomet_v2,
    parse_wassenaar,
    parse_wassenaar_v2,
)

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


# ===========================================================================
# v2 (M7 파싱 결함 교정) — combined_v2.json / corpus_quality_report_v2.json
# ---------------------------------------------------------------------------
# combined.json 은 절대 덮어쓰지 않는다. 코퍼스를 교체하면 논문의 모든 수치가
# 바뀌므로 교체 시점은 팀이 결정한다. 여기서는 v2를 별도 산출물로만 만들고
# before/after 대조 수치를 남긴다.
# ===========================================================================

# 코퍼스 빌드는 난수를 쓰지 않는다(완전 결정론적). 규약상 seed를 명시 기록한다.
CORPUS_BUILD_SEED = 20260730

V2_FIELD_ORDER = [
    "code",
    "text",
    "source",
    "page",
    "pages",
    "control_system",
    "source_name",
    "source_url",
    "official_route",
    "text_completeness",
    "parse_flags",
    "duplicate_occurrences",
    "review_flags",
]


def unterminated_ratio(entries: list[dict]) -> dict:
    """종결부호로 끝나지 않는 항목 수/비율. 페이지 경계 절단의 대리지표."""
    n = len(entries)
    bad = sum(1 for e in entries if not TERMINATOR_RE.search((e.get("text") or "").strip()))
    return {"n": n, "unterminated": bad, "ratio": round(bad / n, 4) if n else 0.0}


def by_source(entries: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        out[e.get("source", "?")].append(e)
    return out


def should_drop_v2(entry: dict) -> tuple[bool, str | None]:
    """v2 드롭 규칙.

    v1과 달리 스텁/표제는 **버리지 않고** ``text_completeness`` 로 표시한다.
    v1은 'invalid_code_format' 15건을 통째로 버렸는데, 그 본문은 실제로는
    앞 항목의 연속이어서 폐기가 아니라 재결합이 정답이었다(v2 파서가 처리).
    """
    code = (entry.get("code") or "").strip()
    source = entry.get("source", "")
    text = clean_text(entry.get("text", ""))
    if not code or not text:
        return True, "empty_code_or_text"
    if not source_valid_code(source, code):
        return True, "invalid_code_format"
    return False, None


def normalize_entry_v2(entry: dict) -> dict:
    source = entry["source"]
    meta = SOURCE_META[source]
    text = clean_text(entry.get("text", ""))
    code = entry["code"].strip()
    flags = sorted(set(entry.get("parse_flags", [])))
    if not TERMINATOR_RE.search(text) and "unterminated_text" not in flags:
        flags.append("unterminated_text")
    out = {
        "code": code,
        "text": text,
        "source": source,
        "page": entry.get("page"),
        "pages": entry.get("pages") or ([entry["page"]] if entry.get("page") else []),
        "control_system": meta["control_system"],
        "source_name": meta["source_name"],
        "source_url": meta["source_url"],
        "official_route": meta["official_route"],
        "text_completeness": entry.get("text_completeness") or classify_completeness(code, text),
        "parse_flags": sorted(flags),
        "duplicate_occurrences": int(entry.get("duplicate_occurrences", 0)),
        "review_flags": [],
    }
    out["review_flags"] = quality_flags(out)
    return {k: out[k] for k in V2_FIELD_ORDER}


def load_raw_entries_v2() -> list[dict]:
    wass = parse_wassenaar_v2(WASSENAAR_PDF)
    scomet = parse_scomet_v2(SCOMET_PDF)
    ecfr = json.loads(ECFR_JSON.read_text(encoding="utf-8"))
    for item in wass:
        item["source"] = "wassenaar_2025"
    for item in scomet:
        item["source"] = "india_scomet_2024"
    for item in ecfr:
        # eCFR은 PDF 파싱 산출물이 아니라 사전 구축 JSON이므로 페이지 경계 결함이 없다.
        item["source"] = "ecfr_part774"
        item.setdefault("page", None)
        item.setdefault("pages", [])
        item["parse_flags"] = ["prebuilt_json_source"]
        item["text_completeness"] = classify_completeness(item["code"], item.get("text", ""))
        item["duplicate_occurrences"] = 0
    return wass + scomet + ecfr


def main_v2() -> None:
    from retrieval_core import env_meta

    # --- before: 레거시 파서 결과(메모리 상에서만 재현, combined.json 은 손대지 않음) ---
    legacy_wass = parse_wassenaar(WASSENAAR_PDF)
    legacy_scomet = parse_scomet(SCOMET_PDF)
    ecfr = json.loads(ECFR_JSON.read_text(encoding="utf-8"))
    for item in legacy_wass:
        item["source"] = "wassenaar_2025"
    for item in legacy_scomet:
        item["source"] = "india_scomet_2024"
    for item in ecfr:
        item["source"] = "ecfr_part774"
    legacy_raw = legacy_wass + legacy_scomet + ecfr

    legacy_kept: list[dict] = []
    legacy_dropped: list[dict] = []
    for entry in [dict(e) for e in legacy_raw]:
        entry["text"] = clean_text(entry.get("text", ""))
        drop, reason = should_drop(entry)
        if drop:
            legacy_dropped.append({"source": entry.get("source"), "code": entry.get("code"), "reason": reason})
            continue
        legacy_kept.append(normalize_entry(entry))
    legacy_combined, _ = dedupe(legacy_kept)

    # 기존에 커밋된 combined.json 과 실제로 일치하는지 확인(재현성 검사)
    existing_path = CORPUS_DIR / "combined.json"
    existing_n = None
    if existing_path.exists():
        existing_n = len(json.loads(existing_path.read_text(encoding="utf-8")))

    # --- after: v2 ---
    raw_v2 = load_raw_entries_v2()
    kept: list[dict] = []
    dropped: list[dict] = []
    for entry in raw_v2:
        entry["text"] = clean_text(entry.get("text", ""))
        drop, reason = should_drop_v2(entry)
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
        kept.append(normalize_entry_v2(entry))

    combined, duplicates = dedupe(kept)
    combined = sorted(combined, key=lambda x: (x["source"], x["code"]))

    (CORPUS_DIR / "combined_v2.json").write_text(
        json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- before/after 대조 ---
    legacy_by_src = by_source(legacy_combined)
    v2_by_src = by_source(combined)
    all_sources = sorted(set(legacy_by_src) | set(v2_by_src))
    comparison = {}
    for src in all_sources:
        a, b = legacy_by_src.get(src, []), v2_by_src.get(src, [])
        a_codes = {x["code"] for x in a}
        b_codes = {x["code"] for x in b}
        a_len = {x["code"]: len(x["text"]) for x in a}
        b_len = {x["code"]: len(x["text"]) for x in b}
        shared = a_codes & b_codes
        comparison[src] = {
            "entries_before": len(a),
            "entries_after": len(b),
            "entries_delta": len(b) - len(a),
            "chars_before": sum(a_len.values()),
            "chars_after": sum(b_len.values()),
            "chars_delta": sum(b_len.values()) - sum(a_len.values()),
            "codes_only_before": sorted(a_codes - b_codes),
            "codes_only_after": sorted(b_codes - a_codes),
            "shared_codes": len(shared),
            "shared_text_grew": sum(1 for c in shared if b_len[c] > a_len[c]),
            "shared_text_shrank": sum(1 for c in shared if b_len[c] < a_len[c]),
            "shared_text_unchanged": sum(1 for c in shared if b_len[c] == a_len[c]),
            "unterminated_before": unterminated_ratio(a),
            "unterminated_after": unterminated_ratio(b),
        }

    # 결함별 실측 건수
    def count_flag(flag: str) -> int:
        return sum(1 for e in combined if flag in e["parse_flags"])

    footer_residue_re = re.compile(r"\d{2}-\d{2}-\d{4}\s*-\s*\d{1,3}\s*-")

    # Wassenaar 에서 사라진 코드를 원인별로 분해한다.
    # 부속서(Sensitive List / Very Sensitive List)는 170-180쪽에 있다.
    WASS_ANNEX_PAGES = range(170, 181)
    LEGACY_FAKE_CODES_IN_CORPUS = ["1.A.n", "2.A.n", "2.A.t", "3.A.n", "5.A.n"]
    legacy_wass_by_code = {e["code"]: e for e in legacy_by_src.get("wassenaar_2025", [])}
    v2_wass_codes = {e["code"] for e in v2_by_src.get("wassenaar_2025", [])}
    lost_codes = sorted(set(legacy_wass_by_code) - v2_wass_codes)
    lost_fake = [c for c in lost_codes if c in LEGACY_FAKE_CODES_IN_CORPUS]
    lost_annex = [
        c for c in lost_codes
        if c not in lost_fake and legacy_wass_by_code[c].get("page") in WASS_ANNEX_PAGES
    ]
    lost_other = [c for c in lost_codes if c not in lost_fake and c not in lost_annex]
    gained_codes = sorted(v2_wass_codes - set(legacy_wass_by_code))

    defect_metrics = {
        "defect_1_page_boundary_truncation": {
            "legacy_page_end_flushes": {"wassenaar_2025": 167, "india_scomet_2024": 251},
            "legacy_silently_discarded_lines": {"wassenaar_2025": 3544, "india_scomet_2024": 5093},
            "legacy_silently_discarded_chars": {"wassenaar_2025": 172620, "india_scomet_2024": 278443},
            "note": (
                "버려진 행에는 표지·목차·정의절 등 항목에 속하지 않는 행도 포함된다. "
                "실제 회복량은 comparison[*].chars_delta 로 판단하라."
            ),
            "v2_entries_flagged_page_continuation": count_flag("page_continuation"),
        },
        "defect_2_numbered_list_as_fake_entry": {
            "legacy_invalid_code_occurrences_in_pdf": 26,
            "legacy_invalid_codes_unique": 15,
            "legacy_invalid_codes": [
                "2.I.n", "3.I.n", "5.C.P", "2.I.s", "2.T.o", "3.A.2.d.4.A", "3.A.2.d.5.A",
                "3.A.2.d.6.A", "1.T.o", "1.I.t", "2.I.t", "2.C.W", "1.C.W", "4.C.W", "2.A.P",
            ],
            "legacy_disposition": "corpus_quality_report.json 이 invalid_code_format 15건으로 드롭 — 본문까지 폐기",
            "v2_disposition": (
                "WASS_ENTRY_V2_RE 가 코드 성분마다 '마침표+공백'을 요구해 번호목록을 애초에 "
                "항목으로 보지 않는다. 남는 예외는 repair_wassenaar_code() 가 처리한다."
            ),
            "v2_invalid_code_entries": sum(
                1 for e in combined if not source_valid_code(e["source"], e["code"])
            ),
            "v2_code_repaired": count_flag("code_repaired"),
            "v2_code_repaired_codes": [e["code"] for e in combined if "code_repaired" in e["parse_flags"]],
            "v2_recovered_real_entries": {
                code: len(next((e["text"] for e in combined if e["code"] == code), ""))
                for code in ("3.A.2.d.4", "3.A.2.d.5", "3.A.2.d.6")
            },
            "v2_recovered_note": (
                "v1이 3.A.2.d.4.A / .5.A / .6.A 라는 잘못된 코드로 만들었다가 invalid_code_format "
                "으로 통째로 버린 3개 항목이다. v2에서는 정상 코드로 복원됐다."
            ),
        },
        "defect_3_stub_and_footer_contamination": {
            "legacy_not_used_since_entries_wassenaar": 44,
            "legacy_reserved_entries_scomet": 16,
            "legacy_footer_residue_entries_wassenaar": 59,
            "legacy_footer_pattern_missed": "skip_tail=r'\\d+\\s*-\\s*\\d+\\s*-\\s*\\d+$' 는 '15-01-2026 - 95 -' 변형을 놓친다",
            "v2_stub_entries": sum(1 for e in combined if e["text_completeness"] == "stub"),
            "v2_heading_only_entries": sum(1 for e in combined if e["text_completeness"] == "heading_only"),
            "v2_full_entries": sum(1 for e in combined if e["text_completeness"] == "full"),
            "v2_footer_residue_entries": sum(1 for e in combined if footer_residue_re.search(e["text"])),
        },
        "defect_4_literal_dot_star": {
            "verdict": "정규식 잔재가 아니다 — 원문 각주 표식(*)이다",
            "evidence": [
                "wassenaar_2025.pdf p130 행 '2.d.*' (각주 표식)",
                "wassenaar_2025.pdf p157 행 '... see the Munitions List.*'",
                "두 페이지 모두 각주 본문 '* The Russian Federation and Ukraine view this list as a reference list ...' 를 포함",
            ],
            "legacy_entries_with_literal_dot_star": 2,
            "legacy_codes": ["6.A.5.f", "9.A"],
            "v2_entries_with_literal_dot_star": sum(1 for e in combined if ".*" in e["text"]),
            "v2_footnote_marker_stripped": count_flag("footnote_marker_stripped"),
        },
        "defect_5_scomet_table_row_split": {
            "note": (
                "SCOMET 원문은 좌측 코드 열이 하위 문단마다 반복되는 표다. v1은 매 행을 새 항목으로 "
                "만들고 중복 제거에서 하나만 남겨 하위 문단을 잃었다."
            ),
            "legacy_rows_with_lowercase_description": 380,
            "v2_entries_flagged_table_row_merged": count_flag("table_row_merged"),
        },
        "defect_6_annex_listing_as_primary_entry": {
            "note": (
                "Wassenaar 170-180쪽 Sensitive List / Very Sensitive List 는 본문 항목이 아니라 "
                "코드 나열 부속서다. v1은 여기서도 항목을 생성했다."
            ),
            "legacy_annex_only_codes": len(
                [
                    c
                    for c in (
                        {x["code"] for x in legacy_by_src.get("wassenaar_2025", [])}
                        - {x["code"] for x in v2_by_src.get("wassenaar_2025", [])}
                    )
                    if source_valid_code("wassenaar_2025", c)
                ]
            ),
            "v2_disposition": "DUAL-USE LIST 러닝 헤더가 있는 페이지에서만 항목을 생성",
        },
    }

    # v1 리포트가 기록한 SHA-256 과 현재 원본 파일의 SHA-256 이 일치하는지 대조.
    # (불일치는 곧 v1 코퍼스가 지금의 원본으로는 재현되지 않는다는 뜻이다.)
    legacy_report_path = CORPUS_DIR / "corpus_quality_report.json"
    sha_check: dict = {}
    if legacy_report_path.exists():
        legacy_report = json.loads(legacy_report_path.read_text(encoding="utf-8"))
        for name, path in (
            ("wassenaar_2025.pdf", WASSENAAR_PDF),
            ("india_scomet_2024_official.pdf", SCOMET_PDF),
            ("ecfr_supp1.json", ECFR_JSON),
        ):
            recorded = (legacy_report.get("source_files", {}).get(name) or {}).get("sha256")
            actual = sha256(path)
            sha_check[name] = {
                "recorded_in_v1_report": recorded,
                "actual_now": actual,
                "match": recorded == actual,
            }

    report = {
        "generated_by": "build_corpus_clean.py --v2",
        "schema_version": 2,
        "seed": CORPUS_BUILD_SEED,
        "deterministic": True,
        "env": env_meta({"corpus_build_seed": CORPUS_BUILD_SEED}),
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
        "source_sha256_vs_v1_report": sha_check,
        "outputs": {
            "combined_v2.json": {"entries": len(combined)},
            "combined.json": {
                "entries": existing_n,
                "status": "unchanged — v2 는 이 파일을 절대 덮어쓰지 않는다",
            },
        },
        "raw_count_by_source": dict(Counter(x.get("source") for x in raw_v2)),
        "kept_count_by_source": dict(Counter(x.get("source") for x in combined)),
        "dropped_count_by_reason": dict(Counter(x["reason"] for x in dropped)),
        "dropped_examples": dropped[:80],
        "duplicate_count": len(duplicates),
        "duplicate_examples": duplicates[:80],
        "before_after": {
            "total_entries_before": len(legacy_combined),
            "total_entries_after": len(combined),
            "total_chars_before": sum(len(x["text"]) for x in legacy_combined),
            "total_chars_after": sum(len(x["text"]) for x in combined),
            "legacy_dropped_count_by_reason": dict(Counter(x["reason"] for x in legacy_dropped)),
            "by_source": comparison,
        },
        "text_completeness_by_source": {
            src: dict(Counter(e["text_completeness"] for e in v2_by_src.get(src, [])))
            for src in all_sources
        },
        "parse_flag_counts": dict(
            Counter(f for e in combined for f in e["parse_flags"])
        ),
        "defect_metrics": defect_metrics,
        "notes": [
            "combined.json / corpus_quality_report.json 은 v1 그대로 보존한다. 교체 시점은 팀 결정 사항.",
            "source_sha256_vs_v1_report 를 확인하라. match=false 인 원본이 있으면 v1 코퍼스는 "
            "현재 원본으로 재현되지 않는다(확인 필요).",
            "text_completeness='stub' 항목은 검색 코퍼스에서 제외하고 쓰는 것을 권장한다 "
            "(예: [e for e in corpus if e['text_completeness'] != 'stub']).",
            "SCOMET 파서의 스킵 집합('Technical Note' 등)은 v1과 동일하게 유지했다. "
            "이 스킵이 본문 일부를 버리는지는 별도 검토 필요(확인 필요).",
            "Wassenaar MUNITIONS LIST(ML*) 항목은 v1/v2 모두 코퍼스에 포함되지 않는다. "
            "코드 문법이 dual-use 정규식과 다르기 때문이다(확인 필요: 포함 여부는 설계 결정).",
            "official_route 는 보수적 워크플로 힌트이며 법적 결론이 아니다.",
        ],
    }
    (CORPUS_DIR / "corpus_quality_report_v2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"[v2] raw={len(raw_v2)} kept={len(combined)} dropped={len(dropped)} duplicates={len(duplicates)}")
    print("[v2] kept_by_source:", dict(Counter(x.get("source") for x in combined)))
    print(f"[before] total={len(legacy_combined)}  [after] total={len(combined)}")
    for src, c in comparison.items():
        print(
            f"  {src}: {c['entries_before']}->{c['entries_after']} "
            f"chars {c['chars_before']}->{c['chars_after']} ({c['chars_delta']:+d}) "
            f"unterminated {c['unterminated_before']['ratio']}->{c['unterminated_after']['ratio']}"
        )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="통제목록 코퍼스 빌드")
    ap.add_argument(
        "--v2",
        action="store_true",
        help="M7 교정판(combined_v2.json + corpus_quality_report_v2.json) 생성. combined.json 은 건드리지 않는다.",
    )
    args = ap.parse_args()
    if args.v2:
        main_v2()
    else:
        main()
