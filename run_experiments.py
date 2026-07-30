#!/usr/bin/env python3
"""BM25 baseline on the synthetic no-code-leakage query set.

Retrieval primitives now live in `retrieval_core`; this module keeps its public
names (`BM25`, `build_doc_text`, `tokenize`, `first_sentence`, `has_code_leak`,
`CONTROL_CODE_RE`) so the other experiment scripts import unchanged.

Three audit fixes are applied here:

* **Deterministic ranking.** `np.argsort(-scores)` handed back the sort
  implementation's tie order, which mattered enormously for `route_only` (only
  19 distinct documents exist under that mode, so almost every rank is a tie).
  Ranking now breaks ties by ascending corpus index, and a query whose score
  vector is entirely zero is recorded as a retrieval failure rather than being
  silently awarded the first k rows of the corpus.
* **Honest exposure accounting.** Exposure is derived from the text actually
  returned, so `minimal_text` and `minimal_no_code` no longer report identical
  disclosure. The previous value is emitted alongside as `exposure@10_legacy`
  so the change is auditable rather than invisible.
* **Independent leak detection.** The leak checker previously reused the exact
  regex that had generated the queries, making it structurally incapable of
  finding a leak. A second, broader pattern set now audits the same queries.

BM25 scoring math is unchanged, so R@k on `full_text` / `minimal_text` /
`minimal_no_code` reproduce the published values.
"""

from __future__ import annotations

import json
import math
import random
import re
from collections import Counter
from pathlib import Path
from statistics import mean

import numpy as np

from retrieval_core import (  # noqa: F401  (re-exported for other scripts)
    BM25,
    CONTROL_CODE_RE,
    exposure_chars,
    first_sentence,
    has_signal,
    index_text,
    legacy_exposure_chars,
    rank_indices,
    rate_with_ci,
    retrieve,
    route_text,
    tokenize,
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "queries.json"
ALPHA = 0.05
PERMUTATIONS = 2000
RANDOM_SEED = 123

# A leak audit must not reuse the generator's own pattern, or it can never fail.
# These catch shapes the primary regex misses: ML-numbers, "Category 3", spaced
# or hyphen-split codes, and Wassenaar-style dotted codes with letter suffixes.
INDEPENDENT_LEAK_PATTERNS = [
    re.compile(r"\bML\s?\d{1,2}\b", re.I),
    re.compile(r"\bcategory\s+[0-9]\b", re.I),
    re.compile(r"\b[0-9]\s?[A-EY]\s?[0-9]{3}\b", re.I),
    re.compile(r"\b[0-9]-[A-EY]-[0-9]{3}\b", re.I),
    re.compile(r"\b[0-9]\.[A-E]\.[0-9]{1,2}\b", re.I),
    re.compile(r"\becc?n\b", re.I),
]


def build_doc_text(entry: dict, mode: str) -> str:
    """Backwards-compatible alias for `retrieval_core.index_text`."""
    return index_text(entry, mode)


def exposure_for_entry(entry: dict, mode: str) -> int:
    """Backwards-compatible alias for the *fixed* exposure definition."""
    return exposure_chars(entry, mode)


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


def independent_leak_hits(query: str) -> list[str]:
    """Leak audit using patterns the query generator never applied."""
    return [p.pattern for p in INDEPENDENT_LEAK_PATTERNS if p.search(query or "")]


def evaluate_mode(corpus: list[dict], queries: list[dict], mode: str) -> dict:
    docs = [index_text(entry, mode) for entry in corpus]
    codes = [entry["code"] for entry in corpus]
    index = BM25(docs)

    per_query: list[dict] = []
    for query in queries:
        scores = index.scores(query["query"])
        signal = has_signal(scores)
        ranked = rank_indices(scores)
        # A query with no lexical overlap at all retrieves nothing; the old code
        # handed it corpus rows 0..k-1 and scored them as if they were results.
        retrieved_idx = list(ranked[:100]) if signal else []
        retrieved_codes = [codes[i] for i in retrieved_idx]
        answer = query["answer_code"]
        rank = retrieved_codes.index(answer) + 1 if answer in retrieved_codes else None
        top10_idx = retrieved_idx[:10]
        per_query.append(
            {
                "id": query["id"],
                "answer_code": answer,
                "has_signal": bool(signal),
                "vocab_overlap": index.vocabulary_overlap(query["query"]),
                "rank_top100": rank,
                "recall@1": int(rank is not None and rank <= 1),
                "recall@5": int(rank is not None and rank <= 5),
                "recall@10": int(rank is not None and rank <= 10),
                "recall@20": int(rank is not None and rank <= 20),
                "mrr": 1.0 / rank if rank else 0.0,
                "ndcg@10": 1.0 / math.log2(rank + 1) if rank and rank <= 10 else 0.0,
                "exposure@10": sum(exposure_chars(corpus[i], mode) for i in top10_idx),
                "exposure@10_legacy": sum(legacy_exposure_chars(corpus[i], mode) for i in top10_idx),
                "top10": retrieved_codes[:10],
            }
        )

    hits10 = [x["recall@10"] for x in per_query]
    return {
        "metrics": {
            "recall@1": round(mean(x["recall@1"] for x in per_query), 4),
            "recall@5": round(mean(x["recall@5"] for x in per_query), 4),
            "recall@10": round(mean(hits10), 4),
            "recall@20": round(mean(x["recall@20"] for x in per_query), 4),
            "mrr": round(mean(x["mrr"] for x in per_query), 4),
            "ndcg@10": round(mean(x["ndcg@10"] for x in per_query), 4),
            "exposure@10": round(mean(x["exposure@10"] for x in per_query), 2),
            "exposure@10_legacy": round(mean(x["exposure@10_legacy"] for x in per_query), 2),
            "recall@10_ci95": rate_with_ci(hits10)["ci95"],
            "no_signal_queries": sum(1 for x in per_query if not x["has_signal"]),
            "distinct_index_texts": len(set(docs)),
        },
        # per-query hit vectors are persisted so downstream statistics never has
        # to reconstruct them from a rounded aggregate rate
        "hit_vectors": {
            "recall@1": [x["recall@1"] for x in per_query],
            "recall@10": hits10,
        },
        "per_query": per_query,
    }


def paired_permutation(a: list[int], b: list[int]) -> dict:
    rng = random.Random(RANDOM_SEED)
    diffs = [x - y for x, y in zip(a, b)]
    observed = mean(diffs)
    extreme = 0
    for _ in range(PERMUTATIONS):
        sample = [d if rng.random() < 0.5 else -d for d in diffs]
        if abs(mean(sample)) >= abs(observed):
            extreme += 1
    return {
        "mean_diff": round(observed, 6),
        "p_value": round((extreme + 1) / (PERMUTATIONS + 1), 6),
        "significant_at_0.05": (extreme + 1) / (PERMUTATIONS + 1) < ALPHA,
    }


def random_baseline(corpus: list[dict], queries: list[dict]) -> dict:
    rng = random.Random(RANDOM_SEED)
    codes = [entry["code"] for entry in corpus]
    hits = []
    for query in queries:
        top10 = rng.sample(codes, min(10, len(codes)))
        hits.append(int(query["answer_code"] in top10))
    return {"recall@10": round(mean(hits), 4)}


def markdown_report(payload: dict) -> str:
    metrics = payload["metrics"]
    lines = [
        "# 전략물자 AI 사전 트리아지 — 정정 실험 결과",
        "",
        "이 보고서는 정답 통제번호가 쿼리에 포함되지 않는 설명형 쿼리만 사용한다.",
        "",
        "## 데이터",
        "",
        f"- 코퍼스: {payload['corpus_size']}개 정화 항목",
        f"- 테스트 쿼리: {payload['test_query_count']}개",
        f"- 코드 누출 검증: {'통과' if payload['leak_check_passed'] else '실패'}",
        f"- 독립 누출 감사(생성기와 다른 정규식): {payload['independent_leak_count']}건",
        f"- 소스 분포: {payload['source_distribution']}",
        "",
        "## 핵심 결과",
        "",
        "| 조건 | R@1 | R@5 | R@10 | R@10 95% CI | R@20 | MRR | nDCG@10 | 노출량@10 | 색인 고유문서 |",
        "|---|---:|---:|---:|---|---:|---:|---:|---:|---:|",
    ]
    for mode, row in metrics.items():
        ci = row["recall@10_ci95"]
        lines.append(
            f"| {mode} | {row['recall@1']:.4f} | {row['recall@5']:.4f} | "
            f"{row['recall@10']:.4f} | [{ci[0]:.3f}, {ci[1]:.3f}] | {row['recall@20']:.4f} | "
            f"{row['mrr']:.4f} | {row['ndcg@10']:.4f} | {row['exposure@10']:.0f} | "
            f"{row['distinct_index_texts']} |"
        )
    lines += [
        f"| random_baseline | - | - | {payload['random_baseline']['recall@10']:.4f} | - | - | - | - | - | - |",
        "",
        "> 노출량@10은 실제 반환 문자열 기준이다. 정정 전 정의는 `minimal_text`와",
        "> `minimal_no_code`에 동일한 값을 부여했으므로 두 조건을 구분하지 못했다.",
        "> 비교용 이전 값은 JSON의 `exposure@10_legacy`에 남겨 두었다.",
        "",
        "## 통계 검정",
        "",
        "| 비교 | R@10 평균차 | p-value | 유의 |",
        "|---|---:|---:|---:|",
    ]
    for name, result in payload["statistical_tests"].items():
        lines.append(
            f"| {name} | {result['mean_diff']:.6f} | {result['p_value']:.6f} | "
            f"{'예' if result['significant_at_0.05'] else '아니오'} |"
        )
    lines += [
        "",
        "## 해석 주의",
        "",
        "- 이 실험은 법적 판정, 수출허가 여부 판단, 전문판정 대체가 아니다.",
        "- 쿼리는 공개 통제목록 설명문에서 파생한 합성 쿼리이므로 실제 기업 질의 대표성은 제한된다.",
        "- 성능 수치는 후보검색 성능이며, 전략물자 해당/비해당 판정 정확도가 아니다.",
        "- `route_only`는 고유 색인 문서가 소수(표의 '색인 고유문서' 열)에 불과한 퇴화 조건이므로",
        "  순위 대부분이 동점이다. 랜덤 기준선과 구별되지 않는 sanity check로만 읽어야 하며,",
        "  이 조건의 소수 4자리 수치와 permutation p값에 해석을 부여해서는 안 된다.",
    ]
    return "\n".join(lines)


def main() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    query_payload = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    queries = query_payload["test"]

    leaks = [q for q in queries if has_code_leak(q["query"], q["answer_code"])]
    independent = [
        {"id": q["id"], "query": q["query"], "patterns": independent_leak_hits(q["query"])}
        for q in queries
        if independent_leak_hits(q["query"])
    ]
    modes = ["full_text", "minimal_text", "minimal_no_code", "route_only"]
    results = {mode: evaluate_mode(corpus, queries, mode) for mode in modes}
    metrics = {mode: results[mode]["metrics"] for mode in modes}

    tests = {
        "minimal_text_vs_full_text": paired_permutation(
            [x["recall@10"] for x in results["minimal_text"]["per_query"]],
            [x["recall@10"] for x in results["full_text"]["per_query"]],
        ),
        "minimal_no_code_vs_full_text": paired_permutation(
            [x["recall@10"] for x in results["minimal_no_code"]["per_query"]],
            [x["recall@10"] for x in results["full_text"]["per_query"]],
        ),
    }

    from retrieval_core import env_meta

    payload = {
        "experiment": "no_code_leakage_bm25_retrieval",
        "env": env_meta({"seed": RANDOM_SEED, "permutations": PERMUTATIONS}),
        "corpus_size": len(corpus),
        "query_total": query_payload.get("total"),
        "test_query_count": len(queries),
        "source_distribution": dict(Counter(q["source"] for q in queries)),
        "language_distribution": dict(Counter(q["lang"] for q in queries)),
        "leak_check_passed": not leaks,
        "leak_examples": leaks[:20],
        "independent_leak_count": len(independent),
        "independent_leak_examples": independent[:20],
        "metrics": metrics,
        "hit_vectors": {mode: results[mode]["hit_vectors"] for mode in modes},
        "statistical_tests": tests,
        "random_baseline": random_baseline(corpus, queries),
        "sample_errors": {
            mode: [x for x in results[mode]["per_query"] if not x["recall@10"]][:20]
            for mode in modes
        },
        "notes": [
            "All queries are generated without answer-code strings.",
            "Ranking breaks ties by ascending corpus index; a query with no lexical "
            "overlap is recorded as a retrieval failure, not as k arbitrary rows.",
            "exposure@10 counts the characters actually returned; exposure@10_legacy "
            "is the previous definition, which could not distinguish minimal_text "
            "from minimal_no_code.",
            "route_only is a degenerate index (see distinct_index_texts) and is "
            "reported only as a sanity check against the random baseline.",
            "Metrics are candidate-retrieval metrics, not legal classification accuracy.",
        ],
    }
    (OUT_DIR / "experiment_logs.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps({"metrics": metrics, "leak_check_passed": not leaks,
                      "independent_leak_count": len(independent)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
