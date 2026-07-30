#!/usr/bin/env python3
"""TASK E — retriever comparison under an honest evaluation.

The self-derived synthetic queries make BM25 look unbeatable: lexical overlap
with the answer document is artificially high, so dense retrieval appears weak
(dense-only R@10 ~0.16 in v4) and hybrid never beats BM25. This script re-runs
BM25 vs dense vs hybrid under two stress conditions that remove that artifact,
to reveal each retriever's real behavior:

1. Vocabulary gap: progressively remove the N highest-IDF tokens a query shares
   with its answer document (same mechanism as experiment_paraphrase_gap.py).
   As exact-term overlap disappears, dense (semantic) retrieval should overtake
   BM25 (lexical).
2. Language split: the corpus is 100% English but half the queries are Korean.
   BM25 cannot match Korean (zero lexical overlap); a multilingual dense model
   embeds both languages into one space and should rescue Korean recall.

Exposure mode fixed to minimal_text (the headline low-exposure condition).
Dense model: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (cached).

정정 (M14-D2 / M14-D4):

* **입력 비대칭 제거.** 이전 판은 ablation을 토큰 리스트에 적용한 뒤 BM25에는
  토큰 리스트를 그대로 주고, dense에는 `" ".join(tokens)`를 주었다. 즉 dense는
  구두점이 사라지고 전부 소문자화된 detokenize 문자열을 받았고 — 문장 임베더에
  가장 불리한 입력 — BM25는 자신에게 최적인 토큰 형태를 받았다. 두 검색기를
  비교하면서 입력 전처리를 다르게 준 것이므로 격차 자체가 인공물이었다.
  이제 **원문 질의에서 제거 대상 토큰만 word-boundary 단위로 삭제한 텍스트**를
  만들어 BM25(`index.scores(text)`)와 dense(`encode(text)`)에 **동일하게** 준다.
* **결정론적 랭킹.** `np.argsort(-blended)` → `retrieval_core.rank_indices`.
  ablation으로 어휘 교집합이 사라져 BM25 점수가 전부 0이 되는 질의는 α=1.0에서
  검색 실패로 기록한다(이전에는 코퍼스 앞머리 20행이 결과로 집계됐다).
* **per-query hit 벡터 저장.** `experiment_stats.py`가 반올림된 aggregate rate에서
  가짜 벡터를 재구성하지 않도록 `results.hit_vectors`를 남긴다.

Outputs:
- output/retriever_compare.json
- output/retriever_compare.md
"""

from __future__ import annotations

import json
import re
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
JSON_PATH = OUT_DIR / "retriever_compare.json"
MD_PATH = OUT_DIR / "retriever_compare.md"

MODE = "minimal_text"
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ABLATION_LEVELS = [0, 3, 5, 10]
ALPHAS = [1.0, 0.7, 0.5, 0.3, 0.0]  # 1.0 = pure BM25, 0.0 = pure dense


minmax = rc.minmax


def drop_tokens(q_tokens, doc_tokens, idf, n) -> set[str]:
    """제거할 토큰 집합: 정답문서와 공유하는 고-IDF 토큰 상위 N개."""
    if n <= 0:
        return set()
    shared = {t for t in q_tokens if t in doc_tokens}
    ranked = sorted(shared, key=lambda t: idf.get(t, 0.0), reverse=True)
    return set(ranked[:n])


def ablate_text(text: str, drop: set[str]) -> str:
    """원문에서 지정 토큰만 word-boundary 단위로 삭제한다.

    BM25와 dense가 **완전히 같은 문자열**을 받도록 하는 것이 핵심이다. 이전 판은
    dense에만 detokenize·소문자화된 `" ".join(tokens)`를 주어 비교를 왜곡했다.
    """
    if not drop:
        return text
    out = text
    for token in sorted(drop, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(token)}\b", " ", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip()


def recall_at(rank, k):
    return int(rank is not None and rank <= k)


def ndcg_at(rank, k):
    import math
    return 1.0 / math.log2(rank + 1) if rank and rank <= k else 0.0


def evaluate(corpus, queries):
    from sentence_transformers import SentenceTransformer

    docs = [build_doc_text(e, MODE) for e in corpus]
    codes = [e["code"] for e in corpus]
    code_to_idx = {c: i for i, c in enumerate(codes)}
    index = BM25(docs)
    doc_token_sets = [set(t) for t in index.tokens]

    print(f"[dense] loading {DENSE_MODEL} ...", flush=True)
    model = SentenceTransformer(DENSE_MODEL)
    print("[dense] encoding corpus ...", flush=True)
    doc_emb = model.encode(docs, batch_size=64, normalize_embeddings=True,
                           show_progress_bar=False).astype(np.float32)

    valid = [q for q in queries if q["answer_code"] in code_to_idx]

    # results[level][alpha] -> list of per-query (rank, lang)
    results: dict = {}
    diagnostics: dict = {}
    for level in ABLATION_LEVELS:
        results[level] = {a: [] for a in ALPHAS}
        # 두 검색기가 완전히 같은 문자열을 본다: 원문에서 제거 대상 토큰만
        # word-boundary 삭제한 텍스트를 BM25와 dense에 동일하게 준다.
        ablated_texts = []
        for q in valid:
            drop = drop_tokens(tokenize(q["query"]),
                               doc_token_sets[code_to_idx[q["answer_code"]]],
                               index.idf, level)
            ablated_texts.append(ablate_text(q["query"], drop))
        print(f"[dense] encoding {len(valid)} queries at ablation N={level} ...", flush=True)
        q_emb = model.encode(ablated_texts, batch_size=64,
                             normalize_embeddings=True, show_progress_bar=False).astype(np.float32)
        no_signal = 0
        for qi, q in enumerate(valid):
            ans = q["answer_code"]
            raw_bm = index.scores(ablated_texts[qi])
            signal = rc.has_signal(raw_bm)
            if not signal:
                no_signal += 1
            bm = minmax(raw_bm)
            dn = minmax(doc_emb @ q_emb[qi])
            for a in ALPHAS:
                if a == 1.0 and not signal:
                    # 어휘 교집합 0 → BM25 단독으로는 아무것도 검색하지 못한다
                    retrieved: list[str] = []
                else:
                    ranked = rc.rank_indices(rc.blend(bm, dn, a))
                    retrieved = [codes[i] for i in ranked[:20]]
                rank = retrieved.index(ans) + 1 if ans in retrieved else None
                results[level][a].append((rank, q.get("lang")))
        diagnostics[str(level)] = {"bm25_no_signal_queries": no_signal}

    def summarize(rows):
        total = len(rows) or 1
        ko = [r for r in rows if r[1] == "ko"]
        en = [r for r in rows if r[1] == "en"]
        hits10 = [recall_at(r[0], 10) for r in rows]
        return {
            "recall@1": round(sum(recall_at(r[0], 1) for r in rows) / total, 4),
            "recall@5": round(sum(recall_at(r[0], 5) for r in rows) / total, 4),
            "recall@10": round(sum(hits10) / total, 4),
            "recall@10_ci95": rc.rate_with_ci(hits10)["ci95"],
            "mrr": round(sum((1.0 / r[0]) if r[0] else 0.0 for r in rows) / total, 4),
            "ndcg@10": round(sum(ndcg_at(r[0], 10) for r in rows) / total, 4),
            "ko_recall@10": round(sum(recall_at(r[0], 10) for r in ko) / (len(ko) or 1), 4),
            "en_recall@10": round(sum(recall_at(r[0], 10) for r in en) / (len(en) or 1), 4),
        }

    summary = {
        str(level): {f"alpha={a}": summarize(results[level][a]) for a in ALPHAS}
        for level in ABLATION_LEVELS
    }
    # 실제 per-query hit 벡터 (가짜 재구성 방지)
    hit_vectors = {
        str(level): {f"alpha={a}": [recall_at(r[0], 10) for r in results[level][a]]
                     for a in ALPHAS}
        for level in ABLATION_LEVELS
    }
    return {"query_count": len(valid), "summary": summary,
            "hit_vectors": hit_vectors, "diagnostics": diagnostics,
            "langs": [q.get("lang") for q in valid]}


def md_report(payload):
    lines = [
        "# TASK E — Retriever 비교 (BM25 vs Dense vs Hybrid)",
        "",
        f"- 코퍼스: {payload['corpus_size']}개 / 평가 쿼리: {payload['query_count']}개",
        f"- 노출 조건: {MODE} (저노출 헤드라인) / Dense: {DENSE_MODEL}",
        "- alpha=1.0 순수 BM25, alpha=0.0 순수 Dense, 그 사이는 hybrid(min-max 후 가중합).",
        "- 어휘격차 N: 쿼리가 정답문서와 공유하는 고-IDF 토큰 N개를 **원문에서 word-boundary",
        "  삭제**. BM25와 dense가 동일한 문자열을 입력받는다(이전 판은 dense에만 detokenize·",
        "  소문자 문자열을 주어 비교가 왜곡됐다).",
        "- 랭킹은 동점을 코퍼스 인덱스 오름차순으로 깨며, BM25 점수가 전부 0인 질의는 α=1.0에서",
        "  검색 실패로 집계한다.",
        "",
        "## 어휘격차별 R@10 (alpha별)",
        "",
        "| 어휘격차 N | BM25(1.0) | hybrid(0.7) | hybrid(0.5) | hybrid(0.3) | Dense(0.0) |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for level in ABLATION_LEVELS:
        s = payload["results"]["summary"][str(level)]
        lines.append(
            f"| {level} | {s['alpha=1.0']['recall@10']:.4f} | {s['alpha=0.7']['recall@10']:.4f} | "
            f"{s['alpha=0.5']['recall@10']:.4f} | {s['alpha=0.3']['recall@10']:.4f} | "
            f"{s['alpha=0.0']['recall@10']:.4f} |"
        )
    lines += [
        "",
        "## 언어별 R@10 (N=0, 어휘격차 없음)",
        "",
        "| retriever | 전체 R@10 | 영어 R@10 | 한국어 R@10 |",
        "|---|---:|---:|---:|",
    ]
    s0 = payload["results"]["summary"]["0"]
    for a in ALPHAS:
        row = s0[f"alpha={a}"]
        name = {1.0: "BM25 (1.0)", 0.0: "Dense (0.0)"}.get(a, f"hybrid ({a})")
        lines.append(
            f"| {name} | {row['recall@10']:.4f} | {row['en_recall@10']:.4f} | {row['ko_recall@10']:.4f} |"
        )
    lines += [
        "",
        "## 해석 (실측 후 작성용 체크포인트)",
        "",
        "- 어휘격차 N이 커질수록 BM25 대비 Dense의 상대 R@10이 어떻게 변하는가 → 역전 여부.",
        "- 한국어 R@10: BM25 vs Dense 격차 → 다국어 dense의 cross-lingual 구제 효과.",
        "- hybrid가 두 극단보다 robust한 alpha 구간이 있는가.",
        "",
    ]
    return "\n".join(lines)


def main():
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))["test"]
    res = evaluate(corpus, queries)
    payload = {
        "experiment": "retriever_comparison_honest",
        "env": rc.env_meta({"seed": None, "deterministic": True}),
        "corpus_size": len(corpus),
        "query_count": res["query_count"],
        "mode": MODE,
        "dense_model": DENSE_MODEL,
        "ablation_levels": ABLATION_LEVELS,
        "alphas": ALPHAS,
        "results": res,
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(md_report(payload), encoding="utf-8")
    # compact print
    s = res["summary"]
    print(json.dumps({
        "ablation_recall@10": {
            lvl: {f"a={a}": s[lvl][f"alpha={a}"]["recall@10"] for a in ALPHAS}
            for lvl in s
        },
        "lang_split_N0": {
            f"a={a}": {"ko": s["0"][f"alpha={a}"]["ko_recall@10"],
                       "en": s["0"][f"alpha={a}"]["en_recall@10"]}
            for a in ALPHAS
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
