#!/usr/bin/env python3
"""Run the corrected no-code-leakage retrieval experiment."""

from __future__ import annotations

import json
import math
import random
import re
from collections import Counter
from pathlib import Path
from statistics import mean

import numpy as np

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "queries.json"
ALPHA = 0.05
PERMUTATIONS = 2000
RANDOM_SEED = 123

CONTROL_CODE_RE = re.compile(
    r"\b(?:ECCN-)?[0-9][A-EY][0-9]{3}[A-Za-z]?(?:\.[A-Za-z0-9]+)*\b"
    r"|\b[0-9]\.[A-E](?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?\b",
    re.I,
)


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z0-9가-힣]+", text or "")]


def first_sentence(text: str, max_chars: int = 260) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    parts = re.split(r"(?<=[.;])\s+", text)
    candidate = parts[0] if parts else text
    if len(candidate) < 80 and len(parts) > 1:
        candidate = " ".join(parts[:2])
    return candidate[:max_chars].strip()


def route_text(entry: dict) -> str:
    flags = ", ".join(entry.get("review_flags", [])) or "none"
    return f"{entry.get('control_system')} | {entry.get('official_route')} | flags={flags}"


def build_doc_text(entry: dict, mode: str) -> str:
    code = entry.get("code", "")
    text = entry.get("text", "")
    if mode == "full_text":
        return f"{code} {text}"
    if mode == "minimal_text":
        return f"{code} {first_sentence(text)}"
    if mode == "minimal_no_code":
        return first_sentence(text)
    if mode == "route_only":
        return route_text(entry)
    raise ValueError(f"unknown mode: {mode}")


def exposure_for_entry(entry: dict, mode: str) -> int:
    if mode == "full_text":
        return len(entry.get("text", ""))
    if mode == "minimal_text":
        return len(first_sentence(entry.get("text", "")))
    if mode == "minimal_no_code":
        return len(first_sentence(entry.get("text", "")))
    if mode == "route_only":
        return len(route_text(entry))
    return 0


class BM25:
    def __init__(self, corpus_texts: list[str]):
        self.tokens = [tokenize(t) for t in corpus_texts]
        self.N = len(self.tokens)
        self.avgdl = mean(len(t) for t in self.tokens) or 1.0
        self.k1 = 1.2
        self.b = 0.75
        df: dict[str, int] = {}
        for toks in self.tokens:
            for token in set(toks):
                df[token] = df.get(token, 0) + 1
        self.idf = {
            token: math.log((self.N - freq + 0.5) / (freq + 0.5) + 1)
            for token, freq in df.items()
        }

    def scores(self, query: str) -> np.ndarray:
        q_tokens = tokenize(query)
        out = np.zeros(self.N, dtype=float)
        for idx, doc_tokens in enumerate(self.tokens):
            tf: dict[str, int] = {}
            for token in doc_tokens:
                tf[token] = tf.get(token, 0) + 1
            dl = len(doc_tokens)
            score = 0.0
            for token in q_tokens:
                if token not in self.idf:
                    continue
                freq = tf.get(token, 0)
                denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                if denom:
                    score += self.idf[token] * freq * (self.k1 + 1) / denom
            out[idx] = score
        return out


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


def evaluate_mode(corpus: list[dict], queries: list[dict], mode: str) -> dict:
    docs = [build_doc_text(entry, mode) for entry in corpus]
    codes = [entry["code"] for entry in corpus]
    index = BM25(docs)

    per_query: list[dict] = []
    for query in queries:
        scores = index.scores(query["query"])
        ranked = np.argsort(-scores)
        retrieved_codes = [codes[i] for i in ranked[:100]]
        answer = query["answer_code"]
        rank = retrieved_codes.index(answer) + 1 if answer in retrieved_codes else None
        per_query.append(
            {
                "id": query["id"],
                "answer_code": answer,
                "rank_top100": rank,
                "recall@1": int(rank is not None and rank <= 1),
                "recall@5": int(rank is not None and rank <= 5),
                "recall@10": int(rank is not None and rank <= 10),
                "recall@20": int(rank is not None and rank <= 20),
                "mrr": 1.0 / rank if rank else 0.0,
                "ndcg@10": 1.0 / math.log2(rank + 1) if rank and rank <= 10 else 0.0,
                "exposure@10": sum(exposure_for_entry(corpus[i], mode) for i in ranked[:10]),
                "top10": retrieved_codes[:10],
            }
        )

    return {
        "metrics": {
            "recall@1": round(mean(x["recall@1"] for x in per_query), 4),
            "recall@5": round(mean(x["recall@5"] for x in per_query), 4),
            "recall@10": round(mean(x["recall@10"] for x in per_query), 4),
            "recall@20": round(mean(x["recall@20"] for x in per_query), 4),
            "mrr": round(mean(x["mrr"] for x in per_query), 4),
            "ndcg@10": round(mean(x["ndcg@10"] for x in per_query), 4),
            "exposure@10": round(mean(x["exposure@10"] for x in per_query), 2),
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
        f"- 소스 분포: {payload['source_distribution']}",
        "",
        "## 핵심 결과",
        "",
        "| 조건 | R@1 | R@5 | R@10 | R@20 | MRR | nDCG@10 | 평균 노출량@10 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, row in metrics.items():
        lines.append(
            f"| {mode} | {row['recall@1']:.4f} | {row['recall@5']:.4f} | "
            f"{row['recall@10']:.4f} | {row['recall@20']:.4f} | {row['mrr']:.4f} | "
            f"{row['ndcg@10']:.4f} | {row['exposure@10']:.0f} |"
        )
    lines += [
        f"| random_baseline | - | - | {payload['random_baseline']['recall@10']:.4f} | - | - | - | - |",
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
        "- `route_only`는 법제 안내 정보만 반환하는 극단적 저노출 조건이므로 후보검색 성능이 낮은 것이 정상이다.",
    ]
    return "\n".join(lines)


def main() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    query_payload = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    queries = query_payload["test"]

    leaks = [q for q in queries if has_code_leak(q["query"], q["answer_code"])]
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
        "route_only_vs_full_text": paired_permutation(
            [x["recall@10"] for x in results["route_only"]["per_query"]],
            [x["recall@10"] for x in results["full_text"]["per_query"]],
        ),
    }

    payload = {
        "experiment": "no_code_leakage_bm25_retrieval",
        "corpus_size": len(corpus),
        "query_total": query_payload.get("total"),
        "test_query_count": len(queries),
        "source_distribution": dict(Counter(q["source"] for q in queries)),
        "language_distribution": dict(Counter(q["lang"] for q in queries)),
        "leak_check_passed": not leaks,
        "leak_examples": leaks[:20],
        "metrics": metrics,
        "statistical_tests": tests,
        "random_baseline": random_baseline(corpus, queries),
        "sample_errors": {
            mode: [
                x
                for x in results[mode]["per_query"]
                if not x["recall@10"]
            ][:20]
            for mode in modes
        },
        "notes": [
            "All queries are generated without answer-code strings.",
            "BM25 is used as a transparent baseline; dense or rerank models must be added only after this baseline is stable.",
            "Metrics are candidate-retrieval metrics, not legal classification accuracy.",
        ],
    }
    (OUT_DIR / "experiment_logs.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "report.md").write_text(markdown_report(payload), encoding="utf-8")
    print(json.dumps({"metrics": metrics, "leak_check_passed": not leaks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
