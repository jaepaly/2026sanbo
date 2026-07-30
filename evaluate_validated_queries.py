#!/usr/bin/env python3
"""TASK B/C/E — evaluate retrievers on the validated, collision-free query set.

Uses data/external_consultation_queries_validated.json, where labels are exact
full eCFR codes (no normalization, no collisions) and only the 13 queries with
a corpus-text-grounded label are scored (excluded_from_metrics queries are
reported but not counted).

Matching is exact code equality against corpus codes, so the collision problem
that affected the original evaluate_external_queries.py cannot occur here.

Retrievers: BM25, Dense (multilingual MiniLM), Hybrid (min-max alpha blend).

**대체 공지 (M9-B).** 이 스크립트의 n=13 산출물은 `experiment_validated_suite.py`
(n=71)로 대체되었다. 논문·문서 헤드라인에 `output/validated_eval.json`을 쓰지 마라.
n=13 수치는 감사 목적으로만 보존한다(`docs/statistics_n13_superseded.md`).
소표본에서 percentile bootstrap CI가 0을 포함하는 것은 이산 경계 인공물이므로
exact McNemar / Clopper-Pearson을 primary로 읽어야 한다(`docs/statistics.md` §5).

정정 (M14-D4): `np.argsort(-blended)` → `retrieval_core.rank_indices`, BM25 점수가
전부 0인 질의는 α=1.0에서 검색 실패로 집계, per-query `hit_vectors` 저장.

Outputs: output/validated_eval.json, output/validated_eval.md
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import retrieval_core as rc
from retrieval_core import BM25, index_text as build_doc_text

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "external_consultation_queries_validated.json"
JSON_PATH = OUT_DIR / "validated_eval.json"
MD_PATH = OUT_DIR / "validated_eval.md"

MODE = "minimal_text"
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ALPHAS = [1.0, 0.7, 0.5, 0.3, 0.0]


minmax = rc.minmax


def main() -> None:
    from sentence_transformers import SentenceTransformer

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    queries = payload["queries"]
    docs = [build_doc_text(e, MODE) for e in corpus]
    codes = [e["code"] for e in corpus]
    index = BM25(docs)

    model = SentenceTransformer(DENSE_MODEL)
    doc_emb = model.encode(docs, batch_size=64, normalize_embeddings=True,
                           show_progress_bar=False).astype(np.float32)

    scored = [q for q in queries if not q["excluded_from_metrics"]]
    q_emb = model.encode([q["query"] for q in scored], batch_size=64,
                         normalize_embeddings=True, show_progress_bar=False).astype(np.float32)

    rows = {a: [] for a in ALPHAS}
    per_query = []
    no_signal = 0
    for qi, q in enumerate(scored):
        labels = set(q["validated_labels"])
        raw_bm = index.scores(q["query"])
        signal = rc.has_signal(raw_bm)
        if not signal:
            no_signal += 1
        bm = minmax(raw_bm)
        dn = minmax(doc_emb @ q_emb[qi])
        q_rec = {"id": q["id"], "lang": q["lang"], "confidence": q["label_confidence"],
                 "labels": q["validated_labels"], "has_bm25_signal": bool(signal),
                 "by_alpha": {}}
        for a in ALPHAS:
            if a == 1.0 and not signal:
                top10: list[str] = []
            else:
                ranked = rc.rank_indices(rc.blend(bm, dn, a))
                top10 = [codes[i] for i in ranked[:10]]
            rank = next((r + 1 for r, c in enumerate(top10) if c in labels), None)
            hit = int(rank is not None)
            rows[a].append({"lang": q["lang"], "hit@10": hit, "rank": rank})
            q_rec["by_alpha"][f"alpha={a}"] = {"hit@10": hit, "rank": rank, "top3": top10[:3]}
        per_query.append(q_rec)

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
            "ko_n": len(ko), "en_n": len(en),
        }

    summary = {f"alpha={a}": summ(rows[a]) for a in ALPHAS}
    out = {
        "meta": {
            "mode": MODE, "dense_model": DENSE_MODEL, "alphas": ALPHAS,
            "evaluated_count": len(scored),
            "excluded_count": sum(q["excluded_from_metrics"] for q in queries),
            "matching": "exact full-code equality (collision-free)",
            "label_nature": payload["meta"]["label_nature"],
            "superseded_by": "output/validated_suite.json (n=71). n=13 결과는 감사 보존용이며 "
                             "헤드라인으로 인용하지 않는다. docs/statistics_n13_superseded.md 참조.",
            "bm25_no_signal_queries": no_signal,
        },
        "env": rc.env_meta({"seed": None, "deterministic": True}),
        "summary": summary,
        "hit_vectors": {f"alpha={a}": [r["hit@10"] for r in rows[a]] for a in ALPHAS},
        "langs": [q["lang"] for q in scored],
        "per_query": per_query,
    }
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# [SUPERSEDED] 검증 질의셋 평가 (TASK B/C/E, n=13)",
        "",
        "> ⚠ 이 산출물은 `output/validated_suite.json`(n=71)으로 대체되었다. 헤드라인으로",
        "> 인용하지 마라. 보존 사유와 before/after는 `docs/statistics_n13_superseded.md` 참조.",
        "> 소표본에서 percentile bootstrap CI가 0을 포함하는 것은 이산 경계 인공물이므로",
        "> exact McNemar / Clopper-Pearson을 primary로 읽어야 한다(`docs/statistics.md` §5).",
        "",
        f"- 질의셋: `{QUERIES_PATH.name}` (평가 {len(scored)}개 / 제외 {out['meta']['excluded_count']}개)",
        f"- 매칭: exact full eCFR code (충돌 없음) / 노출 {MODE} / Dense {DENSE_MODEL}",
        "- 라벨 성격: 코퍼스 텍스트 근거 카테고리 라벨. 법적 판정 아님, 전문가 검증 아님.",
        "",
        "| retriever | R@10 | 영어 R@10 | 한국어 R@10 |",
        "|---|---:|---:|---:|",
    ]
    for a in ALPHAS:
        r = summary[f"alpha={a}"]
        name = {1.0: "BM25 (1.0)", 0.0: "Dense (0.0)"}.get(a, f"hybrid ({a})")
        lines.append(f"| {name} | {r['recall@10']:.4f} | {r['en_recall@10']:.4f} | {r['ko_recall@10']:.4f} |")
    lines += [
        "",
        f"- 평가 표본: 영어 {summary['alpha=1.0']['en_n']}개 / 한국어 {summary['alpha=1.0']['ko_n']}개 (소표본 주의).",
        "",
        "## 해석",
        "- 충돌 없는 정확 매칭 + 코퍼스 텍스트 근거 라벨에서의 retriever별 성능.",
        "- BM25는 한국어에서 어휘 매칭 불가(코퍼스 100% 영어), 다국어 dense/hybrid의 cross-lingual 효과를 확인.",
        "- 표본이 13개(영/한 분할)로 작으므로 절대값보다 retriever 간 상대 경향으로 해석.",
        "",
    ]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
