#!/usr/bin/env python3
"""TASK E (external) — BM25 vs Dense vs Hybrid on the genuine consultation set.

The synthetic benchmark cannot fairly compare retrievers: queries are derived
from each answer document (BM25 inflated) and the "Korean" synthetic queries
actually carry English description bodies, so BM25 scores them like English.
The external consultation set is the only genuinely paraphrased, genuinely
Korean test we have, and BM25 scored R@10=0 there (14/30 zero-score, all KO
queries unmatched because the corpus is 100% English).

This script re-runs that set with a multilingual dense retriever, which embeds
Korean queries and English corpus into one space, to measure whether dense
recovers the cross-lingual matches BM25 structurally cannot make.

Caveat: candidate_labels are researcher estimates (13/30 have code collisions),
so absolute R@10 is noisy. The fair signal is the BM25-vs-dense DELTA on the
same labels, plus the Korean zero-recall recovery.

정정 (M14-D4): `np.argsort(-blended)` → `retrieval_core.rank_indices`(동점을 코퍼스
인덱스 오름차순으로 결정론적 처리), BM25 점수가 전부 0인 질의는 α=1.0에서 검색
실패로 집계, per-query `hit_vectors` 저장(experiment_stats.py가 반올림된 rate에서
가짜 벡터를 재구성하지 않도록).

Outputs: output/external_retriever.json, output/external_retriever.md
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import retrieval_core as rc
from retrieval_core import BM25, index_text as build_doc_text, tokenize
from evaluate_external_queries import normalize_code

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "external_consultation_queries.json"
JSON_PATH = OUT_DIR / "external_retriever.json"
MD_PATH = OUT_DIR / "external_retriever.md"

MODE = "minimal_text"
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ALPHAS = [1.0, 0.7, 0.5, 0.3, 0.0]  # 1.0 = pure BM25, 0.0 = pure dense


minmax = rc.minmax


def evaluate():
    from sentence_transformers import SentenceTransformer

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))["queries"]
    docs = [build_doc_text(e, MODE) for e in corpus]
    codes = [e["code"] for e in corpus]
    norm_codes = [normalize_code(c) for c in codes]
    index = BM25(docs)

    model = SentenceTransformer(DENSE_MODEL)
    doc_emb = model.encode(docs, batch_size=64, normalize_embeddings=True,
                           show_progress_bar=False).astype(np.float32)
    q_emb = model.encode([q["query"] for q in queries], batch_size=64,
                         normalize_embeddings=True, show_progress_bar=False).astype(np.float32)

    rows = {a: [] for a in ALPHAS}
    no_signal = 0
    for qi, q in enumerate(queries):
        labels = [normalize_code(c) for c in (q.get("candidate_labels") or []) if normalize_code(c)]
        raw_bm = index.scores(q["query"])
        signal = rc.has_signal(raw_bm)
        if not signal:
            no_signal += 1
        bm = minmax(raw_bm)
        dn = minmax(doc_emb @ q_emb[qi])
        for a in ALPHAS:
            if a == 1.0 and not signal:
                top10: list[str] = []
            else:
                ranked = rc.rank_indices(rc.blend(bm, dn, a))
                top10 = [norm_codes[i] for i in ranked[:10]]
            hit = any(lbl in top10 for lbl in labels)
            rows[a].append({"lang": q.get("lang"), "hit@10": int(hit)})

    def summ(rs):
        total = len(rs) or 1
        ko = [r for r in rs if r["lang"] == "ko"]
        en = [r for r in rs if r["lang"] == "en"]
        hits = [r["hit@10"] for r in rs]
        return {
            "recall@10": round(sum(hits) / total, 4),
            "recall@10_ci95": rc.rate_with_ci(hits)["ci95"],
            "ko_recall@10": round(sum(r["hit@10"] for r in ko) / (len(ko) or 1), 4),
            "en_recall@10": round(sum(r["hit@10"] for r in en) / (len(en) or 1), 4),
        }

    summary = {f"alpha={a}": summ(rows[a]) for a in ALPHAS}
    # 실제 per-query hit 벡터 (가짜 재구성 방지)
    hit_vectors = {f"alpha={a}": [r["hit@10"] for r in rows[a]] for a in ALPHAS}
    return {"corpus_size": len(corpus), "query_count": len(queries),
            "summary": summary, "hit_vectors": hit_vectors,
            "langs": [q.get("lang") for q in queries],
            "diagnostics": {"bm25_no_signal_queries": no_signal}}


def md_report(p):
    lines = [
        "# TASK E (외부셋) — BM25 vs Dense vs Hybrid",
        "",
        f"- 코퍼스 {p['corpus_size']} / 외부 상담셋 {p['query_count']}개 / 노출 {MODE}",
        f"- Dense: {DENSE_MODEL} (다국어, 영어 코퍼스 + 한국어 질의 cross-lingual)",
        "- 기준: 연구자 예비 `candidate_labels`(노이즈 있음, 13/30 코드충돌). 절대값보다 BM25 대비 변화에 주목.",
        "",
        "| retriever | 전체 R@10 | 영어 R@10 | 한국어 R@10 |",
        "|---|---:|---:|---:|",
    ]
    for a in ALPHAS:
        r = p["summary"][f"alpha={a}"]
        name = {1.0: "BM25 (1.0)", 0.0: "Dense (0.0)"}.get(a, f"hybrid ({a})")
        lines.append(f"| {name} | {r['recall@10']:.4f} | {r['en_recall@10']:.4f} | {r['ko_recall@10']:.4f} |")
    lines += [
        "",
        "## 해석",
        "",
        "- BM25(α=1.0)는 한국어 질의에서 어휘 매칭이 불가능하다(코퍼스 100% 영어).",
        "- 다국어 Dense(α=0.0)가 한국어 R@10을 BM25 대비 회복시키는지가 핵심 지표.",
        "- candidate_labels 노이즈 때문에 절대 R@10은 낮을 수 있으나, BM25→Dense 상대 변화는",
        "  cross-lingual 검색 필요성의 정량 근거가 된다.",
        "",
    ]
    return "\n".join(lines)


def main():
    res = evaluate()
    payload = {"experiment": "external_retriever_comparison", "mode": MODE,
               "env": rc.env_meta({"seed": None, "deterministic": True}),
               "dense_model": DENSE_MODEL, "alphas": ALPHAS, **res}
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(md_report(payload), encoding="utf-8")
    print(json.dumps(res["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
