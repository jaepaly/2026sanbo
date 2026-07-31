#!/usr/bin/env python3
"""Corpus v3: give the eCFR entries their List of Items Controlled bodies.

351 of the 637 eCFR entries in v2 are headings that point elsewhere for their
content -- `"... (see List of Items Controlled)."` -- so the technical parameters
a query would have to match are simply not in the corpus. 42 of the 71 validated
queries have a gold document that is nothing but such a heading, which caps
absolute recall regardless of the retriever. `fetch_ecfr.py --text-field full`
recovers those bodies from the source XML: heading-only drops 351 -> 47 and eCFR
text goes 117,539 -> 814,807 characters.

Only the eCFR third is rebuilt. Wassenaar and SCOMET come from PDF parsing and
the PDFs are not in the repository (third-party redistribution), so v2's parse of
them is carried over byte-for-byte -- which also keeps the change attributable to
one variable.

v2 is left untouched. v3 is a separate file registered in the version manifest,
because adopting it moves every number and that is the team's decision, not this
script's.

    python build_corpus_v3.py --check    # report, write nothing
    python build_corpus_v3.py            # write combined_v3.json + report

Adopt with `python adopt_corpus_v2.py` only after this has been reviewed; see
the manifest's regeneration chain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "data" / "corpus"
ACTIVE = CORPUS_DIR / "combined.json"
V2 = CORPUS_DIR / "combined_v2.json"
ECFR_FULL = CORPUS_DIR / "ecfr_supp1_full.json"
OUT = CORPUS_DIR / "combined_v3.json"
REPORT = CORPUS_DIR / "corpus_quality_report_v3.json"
MD = ROOT / "docs" / "corpus_v3_stub_recovery.md"
MANIFEST = CORPUS_DIR / "corpus_version_manifest.json"
QUERIES = ROOT / "data" / "validated_queries_expanded.json"

# `audit_label_quality.is_stub` asks whether the text contains the phrase
# "(see list of items control...)". That is a proxy for "the parameters are
# elsewhere", and it is the wrong question once the body has been recovered: the
# heading still carries the phrase, so a fully populated entry keeps counting as
# a stub. Both definitions are reported here so the difference is visible rather
# than hidden behind a metric that cannot move.
MARKER_RE = re.compile(r"\(\s*see\s+(?:the\s+)?list\s+of\s+items\s+cont(?:r)?ol", re.I)
SHORT_TEXT_CHARS = 150


def is_stub_marker(entry: dict) -> bool:
    """저장소 기존 정의: 본문에 '(see List of Items Controlled)' 문구가 있는가."""
    return bool(MARKER_RE.search(entry.get("text") or ""))


def is_stub_content(entry: dict) -> bool:
    """내용 기준: 기술 파라미터가 실제로 코퍼스 텍스트에 없는가.

    보강된 항목은 `items_controlled` 본문을 갖는다. 그 필드가 없는 v2 항목은
    문구와 길이로 판정한다(기존 동작과 동일).
    """
    items = (entry.get("items_controlled") or "").strip()
    if items:
        return False
    if entry.get("heading_only"):
        return True
    text = (entry.get("text") or "").strip()
    return bool(MARKER_RE.search(text)) or len(text) < SHORT_TEXT_CHARS


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def base_corpus() -> tuple[list[dict], str]:
    """v2 as the base, whichever file currently holds it."""
    if V2.exists():
        return json.loads(V2.read_text(encoding="utf-8")), V2.name
    return json.loads(ACTIVE.read_text(encoding="utf-8")), ACTIVE.name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if not ECFR_FULL.exists():
        print(f"오류: {ECFR_FULL.name} 이 없습니다. 먼저 실행하세요:\n"
              f"  python fetch_ecfr.py --text-field full "
              f"--save-xml data/raw/ecfr_supp1.xml --out {ECFR_FULL}")
        return 2

    base, base_name = base_corpus()
    full = {e["code"]: e for e in json.loads(ECFR_FULL.read_text(encoding="utf-8"))}

    kept, replaced, missing_in_full = [], 0, []
    before_stub_marker = after_stub_marker = 0
    before_stub_content = after_stub_content = 0
    before_chars = after_chars = 0

    for entry in base:
        if entry.get("source") != "ecfr_part774":
            kept.append(entry)
            continue
        old_text = entry.get("text", "")
        before_chars += len(old_text)
        before_stub_marker += int(is_stub_marker(entry))
        before_stub_content += int(is_stub_content(entry))
        new = full.get(entry["code"])
        if new is None:
            missing_in_full.append(entry["code"])
            after_chars += len(old_text)
            after_stub_marker += int(is_stub_marker(entry))
            after_stub_content += int(is_stub_content(entry))
            kept.append(entry)
            continue
        # v2가 들고 있던 메타(source_url, control_system, official_route,
        # review_flags 등)는 그대로 두고 본문만 교체한다.
        merged = dict(entry)
        merged["text"] = new["text"]
        merged["heading"] = new.get("heading", "")
        merged["items_controlled"] = new.get("items", "")
        merged["related_controls"] = new.get("related_controls", "")
        merged["related_definitions"] = new.get("related_definitions", "")
        merged["heading_only"] = bool(new.get("heading_only"))
        merged["text_completeness"] = (
            "heading_only" if is_stub_content(merged) else "full")
        flags = list(entry.get("parse_flags") or [])
        if "items_recovered_from_xml" not in flags:
            flags.append("items_recovered_from_xml")
        merged["parse_flags"] = flags
        after_chars += len(merged["text"])
        after_stub_marker += int(is_stub_marker(merged))
        after_stub_content += int(is_stub_content(merged))
        replaced += 1
        kept.append(merged)

    # v2에 없던 신규 eCFR 항목(638번째)은 추가하지 않는다. 코퍼스 크기를 바꾸면
    # 라벨공간·도달불가 지표가 함께 움직여 스텁 보강의 효과와 뒤섞이기 때문이다.
    only_in_full = sorted(set(full) - {e["code"] for e in base
                                       if e.get("source") == "ecfr_part774"})

    # 검증셋 정답이 스텁인 비율 (이 작업의 핵심 지표)
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    by_code_before = {e["code"]: e for e in base}
    by_code_after = {e["code"]: e for e in kept}

    def gold_all_stub(qs, by_code, fn):
        n = 0
        for q in qs:
            golds = [by_code.get(c) for c in q["validated_labels"]]
            golds = [g for g in golds if g]
            if golds and all(fn(g) for g in golds):
                n += 1
        return n

    gold_stub_before = gold_all_stub(queries, by_code_before, is_stub_marker)
    gold_stub_after = gold_all_stub(queries, by_code_after, is_stub_marker)
    gold_content_before = gold_all_stub(queries, by_code_before, is_stub_content)
    gold_content_after = gold_all_stub(queries, by_code_after, is_stub_content)

    # 색인 텍스트(minimal_text)가 실제로 달라진 항목 수 — 검색에 영향을 주는 것
    idx_changed = sum(
        1 for e in kept
        if e.get("source") == "ecfr_part774"
        and rc.index_text(by_code_before[e["code"]], "minimal_text")
        != rc.index_text(e, "minimal_text"))

    summary = {
        "base": base_name,
        "ecfr_source": ECFR_FULL.name,
        "entries_total": len(kept),
        "ecfr_entries_replaced": replaced,
        "ecfr_missing_in_full": missing_in_full,
        "ecfr_only_in_full_not_added": only_in_full,
        "ecfr_stub_marker_before": before_stub_marker,
        "ecfr_stub_marker_after": after_stub_marker,
        "ecfr_stub_content_before": before_stub_content,
        "ecfr_stub_content_after": after_stub_content,
        "ecfr_chars_before": before_chars,
        "ecfr_chars_after": after_chars,
        "gold_all_stub_marker_before": gold_stub_before,
        "gold_all_stub_marker_after": gold_stub_after,
        "gold_all_stub_content_before": gold_content_before,
        "gold_all_stub_content_after": gold_content_after,
        "n_queries": len(queries),
        "minimal_text_index_changed": idx_changed,
        "by_source": dict(Counter(e["source"] for e in kept)),
        "text_completeness": dict(Counter(e.get("text_completeness") for e in kept)),
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.check:
        print("\n--check 모드: 파일을 쓰지 않았습니다.")
        return 0

    OUT.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(json.dumps(
        {"version": "v3", "env": rc.env_meta(), "summary": summary,
         "sha256": {"combined_v3.json": sha256(OUT),
                    "ecfr_supp1_full.json": sha256(ECFR_FULL)},
         "note": "v2에서 eCFR 본문만 교체. Wassenaar/SCOMET 은 v2 파싱 결과 그대로."},
        ensure_ascii=False, indent=2), encoding="utf-8")

    MD.parent.mkdir(exist_ok=True)
    MD.write_text(render(summary, sha256(OUT)), encoding="utf-8")

    if MANIFEST.exists():
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        m["v3_available"] = {
            "path": OUT.name, "sha256": sha256(OUT), "total": len(kept),
            "note": "eCFR 표제 스텁 보강판. 채택 전 docs/corpus_v3_stub_recovery.md 검토 필요.",
        }
        MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nwrote {OUT.name}, {REPORT.name}, {MD.relative_to(ROOT)}")
    return 0


def render(s: dict, sha: str) -> str:
    def pct(a, b):
        return f"{100 * a / b:.1f}%" if b else "-"
    return "\n".join([
        "# 코퍼스 v3 — eCFR 표제 스텁 보강",
        "",
        f"기준 `{s['base']}` 의 eCFR {s['ecfr_entries_replaced']}건 본문을 "
        f"`{s['ecfr_source']}` 으로 교체. Wassenaar·SCOMET 은 손대지 않았다.",
        f"sha256 `{sha[:16]}...`",
        "",
        "## 무엇이 달라졌나",
        "",
        "| 지표 | v2 | v3 |",
        "|---|---:|---:|",
        f"| 스텁 — 문구 기준(기존 정의) | {s['ecfr_stub_marker_before']} "
        f"({pct(s['ecfr_stub_marker_before'], s['ecfr_entries_replaced'])}) | "
        f"{s['ecfr_stub_marker_after']} "
        f"({pct(s['ecfr_stub_marker_after'], s['ecfr_entries_replaced'])}) |",
        f"| **스텁 — 내용 기준(본문 유무)** | **{s['ecfr_stub_content_before']}** "
        f"({pct(s['ecfr_stub_content_before'], s['ecfr_entries_replaced'])}) | "
        f"**{s['ecfr_stub_content_after']}** "
        f"({pct(s['ecfr_stub_content_after'], s['ecfr_entries_replaced'])}) |",
        f"| eCFR 본문 문자수 | {s['ecfr_chars_before']:,} | {s['ecfr_chars_after']:,} |",
        f"| 정답이 전부 스텁인 질의 — 문구 기준 | {s['gold_all_stub_marker_before']}/{s['n_queries']} | "
        f"{s['gold_all_stub_marker_after']}/{s['n_queries']} |",
        f"| **정답이 전부 스텁인 질의 — 내용 기준** | "
        f"**{s['gold_all_stub_content_before']}/{s['n_queries']}** | "
        f"**{s['gold_all_stub_content_after']}/{s['n_queries']}** |",
        f"| 색인 텍스트(minimal_text)가 바뀐 eCFR 항목 | — | {s['minimal_text_index_changed']} |",
        f"| 전체 항목수 | {s['entries_total']} | {s['entries_total']} (불변) |",
        "",
        "항목수를 바꾸지 않은 이유: 원문에는 v2에 없던 eCFR 항목이 "
        f"{len(s['ecfr_only_in_full_not_added'])}건 더 있으나"
        f"({', '.join(s['ecfr_only_in_full_not_added']) or '없음'}) 추가하면 라벨공간과 "
        "도달불가 지표가 함께 움직여 스텁 보강의 효과와 뒤섞인다. 한 번에 한 변수만 바꾼다.",
        "",
        "## 두 정의를 함께 보고하는 이유",
        "",
        "`audit_label_quality.is_stub` 는 본문에 `(see List of Items Controlled)` **문구가**",
        "있는지를 본다. 본문을 복구해도 표제에 그 문구는 그대로 남으므로, 이 지표는 보강",
        "여부와 무관하게 거의 움직이지 않는다. 즉 **지표가 측정하려던 것(기술 파라미터가",
        "코퍼스에 없다)과 실제로 재는 것(문구가 있다)이 다르다.** 내용 기준은 `items_controlled`",
        "본문이 실제로 채워졌는지를 본다. v3 채택 시 `audit_label_quality.is_stub` 도 내용",
        "기준으로 바꿔야 하며, 그러지 않으면 `docs/label_audit.md` 의 스텁 지표가 개선을",
        "반영하지 못한다.",
        "",
        "## 주의",
        "",
        "- **채택 전이다.** `combined.json` 은 여전히 v2다. 채택하면 모든 수치가 움직인다.",
        "- `minimal_text` 색인은 첫 문장 260자 상한이므로, 표제가 짧아 두 번째 문장까지 "
        "끌어오던 항목에서만 색인이 바뀐다. 위 표의 '색인 텍스트가 바뀐 항목' 수가 "
        "검색에 실제로 영향을 줄 수 있는 상한이다.",
        "- `full_text` 색인·반환은 크게 달라진다(본문 6.9배).",
        "",
    ])


if __name__ == "__main__":
    raise SystemExit(main())
