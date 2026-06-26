#!/usr/bin/env python3
"""TASK A — quantify how much the synthetic R@k depends on self-derivation.

The synthetic queries (generate_queries.py) are built from each corpus entry's
own text, so a query and its answer document are near-duplicates (mean Jaccard
~0.49 against the minimal_text document). High R@10 on that set therefore
reflects self-retrieval, not candidate discovery.

This experiment makes the dependency measurable WITHOUT any external model, in
keeping with the BM25 transparency stance. For each test query it removes the
N most discriminative (highest-IDF) tokens that the query SHARES with its
answer document, simulating a user who describes the item in generic terms
instead of quoting the control list's rare vocabulary. R@k is then recomputed
at increasing N. A steep drop shows the headline number is driven by exact
rare-term overlap.

Outputs:
- output/paraphrase_gap.json
- output/paraphrase_gap.md
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import numpy as np

from run_experiments import BM25, build_doc_text, tokenize

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "queries.json"
JSON_PATH = OUT_DIR / "paraphrase_gap.json"
MD_PATH = OUT_DIR / "paraphrase_gap.md"

MODES = ["minimal_text", "full_text"]
ABLATION_LEVELS = [0, 1, 2, 3, 5, 10]


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def ablate_query(
    query_tokens: list[str],
    doc_tokens: set[str],
    idf: dict[str, float],
    n_remove: int,
) -> list[str]:
    """Drop the N highest-IDF tokens the query shares with the answer document."""
    if n_remove <= 0:
        return query_tokens
    shared = {t for t in query_tokens if t in doc_tokens}
    ranked = sorted(shared, key=lambda t: idf.get(t, 0.0), reverse=True)
    to_remove = set(ranked[:n_remove])
    return [t for t in query_tokens if t not in to_remove]


def score_tokens(index: BM25, q_tokens: list[str]) -> np.ndarray:
    out = np.zeros(index.N, dtype=float)
    for idx, doc_tokens in enumerate(index.tokens):
        tf: dict[str, int] = {}
        for token in doc_tokens:
            tf[token] = tf.get(token, 0) + 1
        dl = len(doc_tokens)
        score = 0.0
        for token in q_tokens:
            if token not in index.idf:
                continue
            freq = tf.get(token, 0)
            denom = freq + index.k1 * (1 - index.b + index.b * dl / index.avgdl)
            if denom:
                score += index.idf[token] * freq * (index.k1 + 1) / denom
        out[idx] = score
    return out


def evaluate_mode(corpus: list[dict], queries: list[dict], mode: str) -> dict:
    docs = [build_doc_text(entry, mode) for entry in corpus]
    codes = [entry["code"] for entry in corpus]
    code_to_idx = {c: i for i, c in enumerate(codes)}
    index = BM25(docs)
    doc_token_sets = [set(t) for t in index.tokens]

    rows_by_level: dict[int, list[dict]] = {n: [] for n in ABLATION_LEVELS}

    for query in queries:
        answer = query["answer_code"]
        ans_idx = code_to_idx.get(answer)
        if ans_idx is None:
            continue
        ans_doc_tokens = doc_token_sets[ans_idx]
        q_tokens_full = tokenize(query["query"])

        for n in ABLATION_LEVELS:
            q_tokens = ablate_query(q_tokens_full, ans_doc_tokens, index.idf, n)
            scores = score_tokens(index, q_tokens)
            ranked = np.argsort(-scores)
            retrieved = [codes[i] for i in ranked[:20]]
            rank = retrieved.index(answer) + 1 if answer in retrieved else None
            rows_by_level[n].append(
                {
                    "id": query["id"],
                    "rank": rank,
                    "recall@1": int(rank is not None and rank <= 1),
                    "recall@5": int(rank is not None and rank <= 5),
                    "recall@10": int(rank is not None and rank <= 10),
                    "jaccard_vs_answer": round(jaccard(q_tokens, list(ans_doc_tokens)), 4),
                    "removed": len(q_tokens_full) - len(q_tokens),
                }
            )

    summary = []
    for n in ABLATION_LEVELS:
        rows = rows_by_level[n]
        total = len(rows) or 1
        summary.append(
            {
                "n_removed_high_idf_shared_terms": n,
                "recall@1": round(sum(r["recall@1"] for r in rows) / total, 4),
                "recall@5": round(sum(r["recall@5"] for r in rows) / total, 4),
                "recall@10": round(sum(r["recall@10"] for r in rows) / total, 4),
                "mean_jaccard_vs_answer": round(
                    st.mean(r["jaccard_vs_answer"] for r in rows), 4
                ),
                "mean_terms_removed": round(st.mean(r["removed"] for r in rows), 2),
            }
        )
    return {"summary": summary, "query_count": len(rows_by_level[0])}


def markdown_report(payload: dict) -> str:
    lines = [
        "# TASK A — 자기참조(self-retrieval) 의존성 검증",
        "",
        "합성 쿼리는 정답 항목 본문에서 파생되어 정답 문서와 near-duplicate다.",
        "아래는 쿼리가 정답 문서와 공유하는 **고-IDF(희소·변별) 토큰을 N개 제거**했을 때",
        "Recall이 어떻게 무너지는지를 보여준다. N=0이 기존 헤드라인 설정이다.",
        "",
        f"- 코퍼스: {payload['corpus_size']}개 / 테스트 쿼리: {payload['query_count']}개",
        "- 외부 모델 미사용(결정론적). 쿼리에서 공유 고-IDF 토큰만 제거.",
        "",
    ]
    for mode in MODES:
        lines += [
            f"## 조건: {mode}",
            "",
            "| 제거 고-IDF 공유토큰 수 | R@1 | R@5 | R@10 | 평균 Jaccard(정답문서) | 평균 제거토큰수 |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
        for s in payload["results"][mode]["summary"]:
            lines.append(
                f"| {s['n_removed_high_idf_shared_terms']} | {s['recall@1']:.4f} | "
                f"{s['recall@5']:.4f} | {s['recall@10']:.4f} | "
                f"{s['mean_jaccard_vs_answer']:.4f} | {s['mean_terms_removed']:.2f} |"
            )
        lines.append("")
    lines += [
        "## 해석",
        "",
        "- N=0(기존 설정)의 높은 R@10은 정답 문서와의 정확한 희소어 중첩에 의존한다.",
        "- 변별 토큰을 소수만 제거해도 R@10이 급락하면, 합성 절대수치는 후보 발견 능력이",
        "  아니라 자기참조 재검색에 가깝다는 직접 증거다.",
        "- 따라서 논문은 합성 절대수치 대신 (1) 노출량-성능 frontier의 형태와",
        "  (2) 어휘 격차에 따른 성능 민감도를 주력 근거로 삼아야 한다.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))["test"]
    results = {mode: evaluate_mode(corpus, queries, mode) for mode in MODES}
    payload = {
        "experiment": "self_retrieval_dependency_vocab_gap",
        "corpus_size": len(corpus),
        "query_count": results[MODES[0]]["query_count"],
        "ablation_levels": ABLATION_LEVELS,
        "method": (
            "Remove the N highest-IDF tokens shared between each query and its "
            "answer document, then recompute BM25 ranking. No external model."
        ),
        "results": results,
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps(
        {mode: results[mode]["summary"] for mode in MODES},
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
