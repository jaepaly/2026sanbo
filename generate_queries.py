#!/usr/bin/env python3
"""Generate no-code-leakage retrieval queries.

The previous experiment used an A-scenario where the control code was already
present in the query.  That is useful for "known-code lookup" but invalid for
claiming candidate discovery.  This generator builds product/technology
description queries and rejects any query that contains the answer code or a
control-code-shaped token.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "queries.json"
REPORT_PATH = DATA_DIR / "query_quality_report.json"

RANDOM_SEED = 42
MAX_PER_SOURCE = 260
MIN_DESCRIPTION_CHARS = 80

CONTROL_CODE_RE = re.compile(
    r"\b(?:ECCN-)?[0-9][A-EY][0-9]{3}[A-Za-z]?(?:\.[A-Za-z0-9]+)*\b"
    r"|\b[0-9]\.[A-E](?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?\b",
    re.I,
)

TEMPLATES_EN = [
    "Find likely export-control candidates for this technical description: {desc}",
    "Which control-list entry is most relevant to this product or technology description? {desc}",
    "Screen this item description for potentially applicable strategic-goods controls: {desc}",
    "Identify candidate control-list provisions for the following specification: {desc}",
    "A compliance officer needs candidate controls for this description: {desc}",
]

TEMPLATES_KO = [
    "다음 기술 설명과 가장 관련 있는 통제목록 후보를 찾아줘: {desc}",
    "아래 품목 설명을 바탕으로 가능한 전략물자 통제번호 후보를 검색해줘: {desc}",
    "수출통제 사전 검토를 위해 다음 사양과 유사한 통제목록 항목을 찾아줘: {desc}",
    "다음 영문 기술 설명에 대응하는 후보 통제 항목을 제시해줘: {desc}",
    "컴플라이언스 담당자가 아래 설명으로 후보 통제 항목을 찾고 있다: {desc}",
]


def strip_control_codes(text: str) -> str:
    text = CONTROL_CODE_RE.sub(" ", text or "")
    text = re.sub(r"\b(?:ECCN|SCOMET|Wassenaar)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" ;,.-")
    return text


def compact_description(text: str, max_chars: int = 360) -> str:
    text = strip_control_codes(text)
    text = re.sub(r"\([^)]*(?:see|controlled by|specified in)[^)]*\)", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last = max(cut.rfind("."), cut.rfind(";"), cut.rfind(","))
    if last > 160:
        return cut[:last].strip(" ;,.") + "."
    return cut.strip(" ;,.") + "..."


def has_code_leak(query: str, answer_code: str) -> bool:
    variants = {
        answer_code,
        answer_code.replace("ECCN-", ""),
        answer_code.replace(".", " "),
        answer_code.replace("-", " "),
    }
    lower_query = query.lower()
    if any(v and v.lower() in lower_query for v in variants):
        return True
    return CONTROL_CODE_RE.search(query) is not None


def build_queries(corpus: list[dict]) -> tuple[list[dict], list[dict]]:
    rng = random.Random(RANDOM_SEED)
    by_source: dict[str, list[dict]] = defaultdict(list)
    rejects: list[dict] = []

    for entry in corpus:
        desc = compact_description(entry.get("text", ""))
        if len(desc) < MIN_DESCRIPTION_CHARS:
            rejects.append(
                {
                    "code": entry.get("code"),
                    "source": entry.get("source"),
                    "reason": "description_too_short_after_code_removal",
                    "description": desc[:160],
                }
            )
            continue
        by_source[entry["source"]].append({**entry, "description_for_query": desc})

    selected: list[dict] = []
    for source, items in sorted(by_source.items()):
        rng.shuffle(items)
        selected.extend(items[:MAX_PER_SOURCE])

    rng.shuffle(selected)

    queries: list[dict] = []
    for idx, entry in enumerate(selected):
        lang = "ko" if idx % 2 else "en"
        tpl = rng.choice(TEMPLATES_KO if lang == "ko" else TEMPLATES_EN)
        desc = entry["description_for_query"]
        query = tpl.format(desc=desc)
        if has_code_leak(query, entry["code"]):
            rejects.append(
                {
                    "code": entry.get("code"),
                    "source": entry.get("source"),
                    "reason": "code_leak_detected",
                    "query": query[:240],
                }
            )
            continue
        queries.append(
            {
                "id": f"q{len(queries):04d}",
                "query": query,
                "answer_code": entry["code"],
                "source": entry.get("source"),
                "control_system": entry.get("control_system"),
                "lang": lang,
                "query_type": "description_without_control_code",
            }
        )

    rng.shuffle(queries)
    return queries, rejects


def split_queries(queries: list[dict]) -> dict:
    n = len(queries)
    train_n = int(n * 0.10)
    val_n = int(n * 0.10)
    return {
        "train": queries[:train_n],
        "val": queries[train_n : train_n + val_n],
        "test": queries[train_n + val_n :],
        "total": n,
        "generation_notes": {
            "scenario": "candidate retrieval from product/technology description; answer code is not included in the query",
            "random_seed": RANDOM_SEED,
            "max_per_source": MAX_PER_SOURCE,
            "leakage_policy": "reject answer-code variants and generic control-code-shaped tokens",
        },
    }


def main() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries, rejects = build_queries(corpus)
    payload = split_queries(queries)
    QUERIES_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "generated_by": "generate_queries.py",
        "total_queries": len(queries),
        "split_sizes": {k: len(payload[k]) for k in ["train", "val", "test"]},
        "source_distribution": dict(Counter(q["source"] for q in queries)),
        "language_distribution": dict(Counter(q["lang"] for q in queries)),
        "reject_count_by_reason": dict(Counter(r["reason"] for r in rejects)),
        "reject_examples": rejects[:80],
        "leak_check_passed": all(not has_code_leak(q["query"], q["answer_code"]) for q in queries),
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
