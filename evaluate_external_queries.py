#!/usr/bin/env python3
"""Evaluate external consultation-style simulated queries against the BM25 baseline.

Reads and writes UTF-8 explicitly and compares retrieval output against
researcher-assigned candidate_labels using normalized control-code matching.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from run_experiments import BM25, build_doc_text

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "external_consultation_queries.json"
EVAL_JSON_PATH = OUT_DIR / "external_eval.json"
EVAL_MD_PATH = OUT_DIR / "external_eval.md"
AUDIT_JSON_PATH = OUT_DIR / "external_label_audit.json"
MODES = ["minimal_text", "minimal_no_code", "full_text"]


def normalize_code(code: str | None) -> str:
    if not code:
        return ""
    normalized = str(code).strip().upper()
    normalized = normalized.replace("ECCN-", "")
    normalized = normalized.replace("ECCN", "")
    normalized = re.sub(r"[^A-Z0-9]", "", normalized)
    return normalized


def select_query_text(query: dict[str, Any], use_query_en: bool) -> str:
    if use_query_en and query.get("query_en"):
        return query["query_en"]
    return query.get("query", "")


def rounded_scores(scores: list[float], digits: int = 4) -> list[float]:
    return [round(float(score), digits) for score in scores]


def build_corpus_lookup(corpus: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[dict[str, Any]]]]:
    """Map each normalized code to ALL corpus entries that share it.

    Normalization collapses namespace prefixes (e.g. ``ECCN-2B001`` -> ``2B001``),
    so a single normalized code can resolve to multiple distinct corpus entries
    from different control systems (a code collision). Returning a list instead
    of a single entry makes those collisions auditable rather than silently
    resolving to whichever entry happened to be indexed first.
    """
    codes = [entry["code"] for entry in corpus]
    lookup: dict[str, list[dict[str, Any]]] = {}
    for entry in corpus:
        lookup.setdefault(normalize_code(entry["code"]), []).append(entry)
    return codes, lookup


def label_audit_rows(
    query: dict[str, Any],
    corpus_lookup: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    labels = list(query.get("candidate_labels") or [])
    normalized = [normalize_code(label) for label in labels]
    audit = []
    all_exist = True
    any_collision = False
    for original, normalized_code in zip(labels, normalized):
        entries = corpus_lookup.get(normalized_code, [])
        exists = len(entries) > 0
        has_collision = len(entries) > 1
        all_exist = all_exist and exists
        any_collision = any_collision or has_collision
        audit.append(
            {
                "original": original,
                "normalized": normalized_code,
                "exists": exists,
                "corpus_match_count": len(entries),
                "has_code_collision": has_collision,
                "matched_corpus_codes": [entry.get("code") for entry in entries],
                "matched_sources": [entry.get("source") for entry in entries],
                "preview": (entries[0].get("text", "")[:160] if entries else None),
            }
        )
    return {
        "id": query["id"],
        "lang": query.get("lang"),
        "query": query.get("query", ""),
        "candidate_labels": labels,
        "candidate_labels_normalized": normalized,
        "all_candidate_labels_exist": all_exist,
        "any_candidate_label_collision": any_collision,
        "label_audit": audit,
        "source_system": query.get("source_system"),
        "label_confidence": query.get("label_confidence"),
        "label_basis": query.get("label_basis"),
    }


def failure_type_for_row(row: dict[str, Any]) -> str:
    if not row["all_candidate_labels_exist"]:
        return "candidate_label_missing_in_corpus"
    if row["lang"] == "ko" and row["zero_score"]:
        return "korean_query_no_match"
    if row["zero_score"]:
        return "zero_score_no_lexical_overlap"
    return "candidate_label_not_in_top10"


def evaluate_mode(
    corpus: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    mode: str,
    use_query_en: bool,
    codes: list[str],
    corpus_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    docs = [build_doc_text(entry, mode) for entry in corpus]
    index = BM25(docs)
    per_query: list[dict[str, Any]] = []

    for query in queries:
        query_text = select_query_text(query, use_query_en)
        scores = index.scores(query_text)
        ranked = np.argsort(-scores)
        top10_indices = ranked[:10]
        top10_codes = [codes[i] for i in top10_indices]
        top10_scores = [float(scores[i]) for i in top10_indices]
        top10_normalized = [normalize_code(code) for code in top10_codes]

        candidate_labels = list(query.get("candidate_labels") or [])
        candidate_labels_normalized = [
            normalize_code(label) for label in candidate_labels if normalize_code(label)
        ]
        hit_ranks = [
            top10_normalized.index(label) + 1
            for label in candidate_labels_normalized
            if label in top10_normalized
        ]

        audit_row = label_audit_rows(query, corpus_lookup)
        matched_candidates = [
            {
                "candidate_label": candidate_labels[idx],
                "candidate_label_normalized": normalized,
                "rank": top10_normalized.index(normalized) + 1,
                "matched_corpus_code": top10_codes[top10_normalized.index(normalized)],
                "score": round(top10_scores[top10_normalized.index(normalized)], 4),
            }
            for idx, normalized in enumerate(candidate_labels_normalized)
            if normalized in top10_normalized
        ]

        row = {
            "id": query["id"],
            "lang": query.get("lang"),
            "query": query.get("query", ""),
            "query_used": query_text,
            "used_query_en": bool(use_query_en and query.get("query_en")),
            "context": query.get("context"),
            "candidate_labels": candidate_labels,
            "candidate_labels_normalized": candidate_labels_normalized,
            "label_confidence": query.get("label_confidence"),
            "label_basis": query.get("label_basis"),
            "source_system": query.get("source_system"),
            "all_candidate_labels_exist": audit_row["all_candidate_labels_exist"],
            "any_candidate_label_collision": audit_row["any_candidate_label_collision"],
            "top10_codes": top10_codes,
            "top10_codes_normalized": top10_normalized,
            "top10_scores": rounded_scores(top10_scores),
            "matched_candidates": matched_candidates,
            "candidate_hit_ranks": hit_ranks,
            "hit@1": int(any(rank <= 1 for rank in hit_ranks)),
            "hit@5": int(any(rank <= 5 for rank in hit_ranks)),
            "hit@10": int(any(rank <= 10 for rank in hit_ranks)),
            "max_score": round(float(top10_scores[0]) if top10_scores else 0.0, 4),
            "zero_score": bool(top10_scores and float(top10_scores[0]) == 0.0),
        }
        row["failure_type"] = failure_type_for_row(row)
        per_query.append(row)

    total = len(per_query) or 1
    ko_rows = [row for row in per_query if row["lang"] == "ko"]
    en_rows = [row for row in per_query if row["lang"] == "en"]

    metrics = {
        "recall@1": round(sum(row["hit@1"] for row in per_query) / total, 4),
        "recall@5": round(sum(row["hit@5"] for row in per_query) / total, 4),
        "recall@10": round(sum(row["hit@10"] for row in per_query) / total, 4),
        "ko_recall@10": round(sum(row["hit@10"] for row in ko_rows) / (len(ko_rows) or 1), 4),
        "en_recall@10": round(sum(row["hit@10"] for row in en_rows) / (len(en_rows) or 1), 4),
        "ko_count": len(ko_rows),
        "en_count": len(en_rows),
        "zero_score_count": sum(int(row["zero_score"]) for row in per_query),
        "all_candidate_labels_exist_count": sum(
            int(row["all_candidate_labels_exist"]) for row in per_query
        ),
        "candidate_label_collision_count": sum(
            int(row["any_candidate_label_collision"]) for row in per_query
        ),
    }

    failure_breakdown = dict(Counter(row["failure_type"] for row in per_query))
    representative_failures = sorted(
        [row for row in per_query if not row["hit@10"]],
        key=lambda row: (
            row["zero_score"],
            -row["max_score"],
            row["id"],
        ),
    )[:5]

    return {
        "metrics": metrics,
        "failure_breakdown": failure_breakdown,
        "representative_failures": representative_failures,
        "per_query": per_query,
    }


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# 외부 모사 질의 평가 결과",
        "",
        "- 질의셋: `data/external_consultation_queries.json`",
        "- 평가 기준: researcher-assigned `candidate_labels`와 정규화된 코드 비교",
        f"- query field: {'query_en 우선 사용' if payload['meta']['use_query_en'] else '원문 query 사용'}",
        "- 파일 입출력: UTF-8",
        "",
        "> 주의: `candidate_labels`는 연구자가 예비로 부여한 후보값이며 검증된 정답이 아니다.",
        "> 따라서 R@10=0은 \"BM25의 현장 성능이 0\"이 아니라 \"불확실한 후보 라벨 기준으로",
        "> 어휘 매칭이 수렴하지 않는다\"로 해석해야 한다. 코드 정규화 충돌(`candidate_label_collision_count`)이",
        "> 있는 질의는 라벨이 의도와 다른 통제체계 항목을 가리킬 수 있다.",
        "",
        "## 요약표",
        "",
        "| 조건 | R@1 | R@5 | R@10 | 영어 R@10 | 한국어 R@10 | zero-score 수 | 라벨충돌 질의수 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        metrics = payload["results"][mode]["metrics"]
        lines.append(
            f"| {mode} | {metrics['recall@1']:.4f} | {metrics['recall@5']:.4f} | "
            f"{metrics['recall@10']:.4f} | {metrics['en_recall@10']:.4f} | "
            f"{metrics['ko_recall@10']:.4f} | {metrics['zero_score_count']} | "
            f"{metrics['candidate_label_collision_count']} |"
        )

    lines.extend(
        [
            "",
            "## failure type 분포",
            "",
        ]
    )
    for mode in MODES:
        lines.append(f"### {mode}")
        for failure_type, count in sorted(payload["results"][mode]["failure_breakdown"].items()):
            lines.append(f"- {failure_type}: {count}")
        lines.append("")

    lines.extend(
        [
            "## 대표 실패 사례 5개 (minimal_text 기준)",
            "",
        ]
    )
    for row in payload["results"]["minimal_text"]["representative_failures"]:
        lines.extend(
            [
                f"- **{row['id']}** [{row['lang']}] max_score={row['max_score']}, hit@10={row['hit@10']}, failure_type={row['failure_type']}",
                f"  - query: {row['query']}",
                f"  - candidate_labels: {row['candidate_labels']}",
                f"  - top10: {row['top10_codes'][:5]}",
                f"  - top5_scores: {row['top10_scores'][:5]}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--use-query-en",
        action="store_true",
        help="Use query_en when present; otherwise fall back to query.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    query_payload = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    queries = query_payload["queries"]
    codes, corpus_lookup = build_corpus_lookup(corpus)

    audits = [label_audit_rows(query, corpus_lookup) for query in queries]
    results = {
        mode: evaluate_mode(
            corpus=corpus,
            queries=queries,
            mode=mode,
            use_query_en=args.use_query_en,
            codes=codes,
            corpus_lookup=corpus_lookup,
        )
        for mode in MODES
    }

    payload = {
        "meta": {
            "description": "External consultation-style simulated query evaluation against BM25 baseline.",
            "corpus_size": len(corpus),
            "query_count": len(queries),
            "use_query_en": args.use_query_en,
            "note": "These are simulated queries, not real enterprise consultations. Labels are researcher-assigned candidate labels.",
        },
        "results": results,
    }
    audit_payload = {
        "meta": {
            "description": "Label audit for external consultation-style simulated queries.",
            "note": (
                "Existence check only. Semantic correctness of label-to-query mapping is not asserted here. "
                "When has_code_collision is true, the normalized code maps to multiple corpus entries from "
                "different control systems, so 'exists' does not guarantee the intended namespace was matched."
            ),
            "corpus_size": len(corpus),
            "query_count": len(queries),
        },
        "audit": audits,
    }

    EVAL_JSON_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    EVAL_MD_PATH.write_text(markdown_report(payload), encoding="utf-8")
    AUDIT_JSON_PATH.write_text(
        json.dumps(audit_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "meta": payload["meta"],
        "metrics": {mode: payload["results"][mode]["metrics"] for mode in MODES},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
