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

정정 (M14-D4):
* 랭킹이 `np.argsort(-scores)`였다. 토큰을 제거하다 보면 점수 벡터가 전부 0이 되는
  질의가 생기는데(어휘 교집합 소멸), 그때 "top-20"은 사실 코퍼스 배열 앞머리
  20행이었고 정답이 우연히 그 안에 있으면 적중으로 집계됐다. 이제
  `retrieval_core.rank_indices`로 동점을 코퍼스 인덱스 오름차순으로 깨고,
  전점수 0 질의는 **검색 실패**로 기록한다. 이전(허용적) 정의도
  `recall@10_legacy_zero_permissive`로 함께 남겨 before/after 비교가 가능하다.
* per-query hit 벡터를 `hit_vectors`로 저장한다. 이전에는 집계값만 저장되어
  `experiment_stats.py`가 반올림된 rate에서 가짜 벡터를 재구성했다.

Outputs:
- output/paraphrase_gap.json
- output/paraphrase_gap.md
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import numpy as np

import retrieval_core as rc
from retrieval_core import BM25, index_text as build_doc_text, tokenize

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
    """참조 구현 (느림). BM25 수식은 retrieval_core.BM25.scores와 동일하다."""
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


class FastTokenScorer:
    """토큰 리스트에 대한 BM25 점수의 벡터화 구현.

    수식은 `score_tokens`(=`retrieval_core.BM25.scores`)와 **동일**하다. 다만 문서별
    tf 딕셔너리를 매 호출마다 새로 만들지 않고 역색인을 한 번만 만든다. 6개
    ablation 수준 × 2개 노출 모드 × 624개 질의 = 7,488회 스코어링을 순수 파이썬
    이중 루프로 돌리면 10분 이상 걸린다.

    수식이 정말 같은지 `self_check()`로 런타임에 검증하고, 어긋나면 예외를 던진다
    (조용히 다른 수를 만들지 않는다).
    """

    def __init__(self, index: BM25):
        self.index = index
        self.k1, self.b = index.k1, index.b
        dl = np.array([len(t) for t in index.tokens], dtype=float)
        # 분모의 문서 의존 항: k1 * (1 - b + b * dl / avgdl)
        self.denom_base = self.k1 * (1 - self.b + self.b * dl / index.avgdl)
        # token -> (문서 인덱스 배열, 해당 문서에서의 tf 배열)
        self.postings: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        acc: dict[str, dict[int, int]] = {}
        for di, tf in enumerate(index._tf):
            for token, freq in tf.items():
                acc.setdefault(token, {})[di] = freq
        for token, m in acc.items():
            docs = np.fromiter(m.keys(), dtype=np.int64, count=len(m))
            freqs = np.fromiter(m.values(), dtype=float, count=len(m))
            self.postings[token] = (docs, freqs)

    def scores(self, q_tokens: list[str]) -> np.ndarray:
        out = np.zeros(self.index.N, dtype=float)
        counts: dict[str, int] = {}
        for token in q_tokens:
            if token in self.index.idf:
                counts[token] = counts.get(token, 0) + 1
        for token, mult in counts.items():
            docs, freqs = self.postings[token]
            contrib = (self.index.idf[token] * freqs * (self.k1 + 1)
                       / (freqs + self.denom_base[docs]))
            np.add.at(out, docs, mult * contrib)
        return out

    def self_check(self, token_lists: list[list[str]], tol: float = 1e-9) -> float:
        worst = 0.0
        for toks in token_lists:
            diff = float(np.abs(self.scores(toks) - score_tokens(self.index, toks)).max())
            worst = max(worst, diff)
        if worst > tol:
            raise AssertionError(
                f"FastTokenScorer가 참조 구현과 다르다 (max|diff|={worst:.3g} > {tol})"
            )
        return worst


def evaluate_mode(corpus: list[dict], queries: list[dict], mode: str) -> dict:
    docs = [build_doc_text(entry, mode) for entry in corpus]
    codes = [entry["code"] for entry in corpus]
    code_to_idx = {c: i for i, c in enumerate(codes)}
    index = BM25(docs)
    doc_token_sets = [set(t) for t in index.tokens]
    scorer = FastTokenScorer(index)
    # 수식 동일성 런타임 검증 (어긋나면 예외로 중단한다)
    probe = [tokenize(q["query"]) for q in queries[:8]]
    max_diff = scorer.self_check(probe)
    print(f"[{mode}] FastTokenScorer self-check max|diff| = {max_diff:.3g}", flush=True)

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
            scores = scorer.scores(q_tokens)
            signal = rc.has_signal(scores)
            ranked = rc.rank_indices(scores)
            # 전점수 0이면 top-k를 만들 수 없다 (검색 실패). 이전 코드는 코퍼스
            # 앞머리 20행을 결과로 집계했다.
            retrieved = [codes[i] for i in ranked[:20]] if signal else []
            rank = retrieved.index(answer) + 1 if answer in retrieved else None
            # 정정 전(허용적) 정의: 무신호 질의에도 코퍼스 순서로 20행을 부여
            legacy_retrieved = [codes[i] for i in ranked[:20]]
            legacy_rank = (legacy_retrieved.index(answer) + 1
                           if answer in legacy_retrieved else None)
            rows_by_level[n].append(
                {
                    "id": query["id"],
                    "rank": rank,
                    "has_signal": bool(signal),
                    "recall@1": int(rank is not None and rank <= 1),
                    "recall@5": int(rank is not None and rank <= 5),
                    "recall@10": int(rank is not None and rank <= 10),
                    "recall@10_legacy_zero_permissive": int(
                        legacy_rank is not None and legacy_rank <= 10),
                    "jaccard_vs_answer": round(jaccard(q_tokens, list(ans_doc_tokens)), 4),
                    "removed": len(q_tokens_full) - len(q_tokens),
                }
            )

    summary = []
    hit_vectors: dict[str, dict[str, list[int]]] = {}
    for n in ABLATION_LEVELS:
        rows = rows_by_level[n]
        total = len(rows) or 1
        hits10 = [r["recall@10"] for r in rows]
        summary.append(
            {
                "n_removed_high_idf_shared_terms": n,
                "recall@1": round(sum(r["recall@1"] for r in rows) / total, 4),
                "recall@5": round(sum(r["recall@5"] for r in rows) / total, 4),
                "recall@10": round(sum(hits10) / total, 4),
                "recall@10_legacy_zero_permissive": round(
                    sum(r["recall@10_legacy_zero_permissive"] for r in rows) / total, 4),
                "recall@10_ci95": rc.rate_with_ci(hits10)["ci95"],
                "no_signal_queries": sum(1 for r in rows if not r["has_signal"]),
                "mean_jaccard_vs_answer": round(
                    st.mean(r["jaccard_vs_answer"] for r in rows), 4
                ),
                "mean_terms_removed": round(st.mean(r["removed"] for r in rows), 2),
            }
        )
        # experiment_stats.py가 가짜 벡터를 재구성하지 않도록 실제 벡터를 저장
        hit_vectors[str(n)] = {
            "recall@1": [r["recall@1"] for r in rows],
            "recall@10": hits10,
            "recall@10_legacy_zero_permissive": [
                r["recall@10_legacy_zero_permissive"] for r in rows],
        }
    return {"summary": summary, "hit_vectors": hit_vectors,
            "query_count": len(rows_by_level[0])}


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
            "| 제거 고-IDF 공유토큰 수 | R@1 | R@5 | R@10 | R@10 95% CI | 무신호 질의 | "
            "R@10(정정 전 정의) | 평균 Jaccard(정답문서) | 평균 제거토큰수 |",
            "|---:|---:|---:|---:|---|---:|---:|---:|---:|",
        ]
        for s in payload["results"][mode]["summary"]:
            ci = s["recall@10_ci95"]
            lines.append(
                f"| {s['n_removed_high_idf_shared_terms']} | {s['recall@1']:.4f} | "
                f"{s['recall@5']:.4f} | {s['recall@10']:.4f} | "
                f"[{ci[0]:.3f}, {ci[1]:.3f}] | {s['no_signal_queries']} | "
                f"{s['recall@10_legacy_zero_permissive']:.4f} | "
                f"{s['mean_jaccard_vs_answer']:.4f} | {s['mean_terms_removed']:.2f} |"
            )
        lines.append("")
    lines += [
        "> `R@10(정정 전 정의)` 열은 전점수 0 질의에도 코퍼스 앞머리 20행을 결과로 부여한",
        "> 이전 정의다. 두 열이 같으면 해당 조건에서는 무신호 질의가 결과에 영향을 주지 않았다는 뜻이다.",
        "",
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
        "env": rc.env_meta({"seed": None, "deterministic": True}),
        "corpus_size": len(corpus),
        "query_count": results[MODES[0]]["query_count"],
        "ablation_levels": ABLATION_LEVELS,
        "method": (
            "Remove the N highest-IDF tokens shared between each query and its "
            "answer document, then recompute BM25 ranking. No external model. "
            "Ranking breaks ties by ascending corpus index; an all-zero score "
            "vector is a retrieval failure (see recall@10_legacy_zero_permissive "
            "for the previous, permissive definition)."
        ),
        "results": results,
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps(
        {mode: [{k: s[k] for k in ("n_removed_high_idf_shared_terms", "recall@10",
                                   "recall@10_legacy_zero_permissive", "no_signal_queries")}
                for s in results[mode]["summary"]] for mode in MODES},
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
