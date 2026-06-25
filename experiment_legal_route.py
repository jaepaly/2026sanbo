#!/usr/bin/env python3
"""Summarize conservative legal/workflow routing hints.

This is not a classifier accuracy experiment.  The repository deliberately no
longer reports "legal routing accuracy" because the prior labels were
heuristic labels, not official legal determinations.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"

ROUTE_DESCRIPTIONS = {
    "strategic_goods_review": "전략물자/기술 통제목록 후보 검토 및 YesTrade 자가·전문판정 안내",
    "foreign_control_list_reference": "외국 공개 통제목록 참고자료. 한국 법적 판정에는 직접 사용하지 않고 국내 고시·YesTrade 확인 필요",
}


def summarize(corpus: list[dict]) -> dict:
    route_counter = Counter(entry.get("official_route", "unknown") for entry in corpus)
    source_counter = Counter(entry.get("source", "unknown") for entry in corpus)
    flag_counter = Counter(flag for entry in corpus for flag in entry.get("review_flags", []))
    nct_candidates = [
        {
            "code": entry["code"],
            "source": entry["source"],
            "text_preview": entry["text"][:220],
        }
        for entry in corpus
        if "possible_national_core_technology_review" in entry.get("review_flags", [])
    ][:50]

    return {
        "disclaimer": (
            "These are conservative workflow hints for research. They are not legal "
            "classifications, export permits, self-classification results, or expert determinations."
        ),
        "route_counts": dict(route_counter),
        "route_descriptions": ROUTE_DESCRIPTIONS,
        "source_counts": dict(source_counter),
        "review_flag_counts": dict(flag_counter),
        "possible_national_core_technology_examples": nct_candidates,
        "recommended_output_policy": [
            "Do not output 'not controlled' or 'safe to export'.",
            "Return candidate control entries, missing information, and official next steps.",
            "For Korean compliance, direct users to YesTrade self/expert classification and catch-all review.",
            "If national core technology keywords appear, add a secondary 산업기술보호법/국가핵심기술 검토 flag without claiming applicability.",
        ],
        "official_reference_links": {
            "YesTrade system guidance": "https://www.yestrade.go.kr/system-guidance",
            "YesTrade self-classification limitations": "https://www.yestrade.go.kr/judgements/self/intro",
            "Strategic Items Export/Import Notice": "https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000270104&chrClsCd=010201",
            "National Core Technology program": "https://kaits.or.kr/web/content.do?menu_cd=000067",
        },
    }


def main() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    result = summarize(corpus)
    out = OUT_DIR / "routing_summary.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
