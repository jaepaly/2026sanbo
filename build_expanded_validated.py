#!/usr/bin/env python3
"""TASK I — merge the validated set with the TASK G slices and re-evaluate.

Combines:
  - the original validated set's evaluable queries (excluded_from_metrics=False)
  - every data/validated_queries_slice_*.json (TASK G reverse-generated queries)

into one collision-free set with exact full-eCFR-code labels, then evaluates
BM25 / Dense / Hybrid (min-max alpha blend) and computes paired bootstrap 95%
CIs for the headline comparisons (hybrid α=0.5 vs BM25, Dense vs BM25). The
point of the larger n is to see whether the hybrid>BM25 / Korean-recovery
effects, whose CIs included 0 at n=13, become statistically separable.

**대체 공지 (M9-B).** 평가 부분은 `experiment_validated_suite.py`(n=71, 3모델,
색인×반환 2차원 노출표, TOST, Holm)로 대체되었다. 이 스크립트의 존속 이유는
`data/validated_queries_expanded.json` **병합**이다. 평가 결과
(`output/validated_expanded_eval.json`)를 헤드라인으로 인용하지 마라.

정정 (M14-D4): `np.argsort(-...)` → `retrieval_core.rank_indices`, BM25 점수가 전부
0인 질의는 α=1.0에서 검색 실패로 집계, per-query `hit_vectors` 저장, primary 검정을
exact McNemar로 변경(percentile bootstrap은 보조).

Outputs:
  data/validated_queries_expanded.json
  output/validated_expanded_eval.json
  output/validated_expanded_eval.md
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np

import retrieval_core as rc
from retrieval_core import BM25, index_text as build_doc_text

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
BASE_PATH = DATA_DIR / "external_consultation_queries_validated.json"
SLICE_GLOB = str(DATA_DIR / "validated_queries_slice_*.json")
MERGED_PATH = DATA_DIR / "validated_queries_expanded.json"
EVAL_JSON = OUT_DIR / "validated_expanded_eval.json"
EVAL_MD = OUT_DIR / "validated_expanded_eval.md"

MODE = "minimal_text"
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ALPHAS = [1.0, 0.7, 0.5, 0.3, 0.0]
BOOTSTRAP_ITERS = 20000
SEED = 20260626


minmax = rc.minmax


def merge_queries() -> list[dict]:
    merged: list[dict] = []
    seen_codes: set[str] = set()

    base = json.loads(BASE_PATH.read_text(encoding="utf-8"))
    for q in base["queries"]:
        if q.get("excluded_from_metrics"):
            continue
        merged.append({
            "id": q["id"], "lang": q["lang"], "query": q["query"],
            "validated_labels": q["validated_labels"], "origin": "validated_base",
        })
        seen_codes.update(q["validated_labels"])

    for path in sorted(glob.glob(SLICE_GLOB)):
        name = Path(path).stem.replace("validated_queries_slice_", "")
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for q in payload["queries"]:
            dup = [c for c in q["validated_labels"] if c in seen_codes]
            if dup:  # automatic dedup across slices / base
                continue
            merged.append({
                "id": q["id"], "lang": q["lang"], "query": q["query"],
                "validated_labels": q["validated_labels"], "origin": f"slice_{name}",
            })
            seen_codes.update(q["validated_labels"])
    return merged


def main() -> None:
    from sentence_transformers import SentenceTransformer

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    docs = [build_doc_text(e, MODE) for e in corpus]
    codes = [e["code"] for e in corpus]
    index = BM25(docs)

    queries = merge_queries()
    MERGED_PATH.write_text(json.dumps(
        {"meta": {"evaluated_count": len(queries),
                  "label_nature": "corpus-text-grounded category labels (exact eCFR codes); not legal/expert determinations",
                  "sources": "validated base (evaluable) + TASK G slices"},
         "queries": queries}, ensure_ascii=False, indent=2), encoding="utf-8")

    model = SentenceTransformer(DENSE_MODEL)
    doc_emb = model.encode(docs, batch_size=64, normalize_embeddings=True,
                           show_progress_bar=False).astype(np.float32)
    q_emb = model.encode([q["query"] for q in queries], batch_size=64,
                         normalize_embeddings=True, show_progress_bar=False).astype(np.float32)

    hits = {a: [] for a in ALPHAS}   # per-query hit@10
    langs = [q["lang"] for q in queries]
    no_signal = 0
    for qi, q in enumerate(queries):
        labels = set(q["validated_labels"])
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
                top10 = [codes[i] for i in ranked[:10]]
            hits[a].append(int(any(c in labels for c in top10)))

    def rate(vec, mask=None):
        v = [h for h, lg in zip(vec, langs) if (mask is None or lg == mask)]
        return round(sum(v) / len(v), 4) if v else 0.0

    summary = {}
    for a in ALPHAS:
        summary[f"alpha={a}"] = {
            "recall@10": rate(hits[a]),
            "recall@10_ci95": rc.rate_with_ci(hits[a])["ci95"],
            "en_recall@10": rate(hits[a], "en"),
            "ko_recall@10": rate(hits[a], "ko"),
        }

    bm25 = hits[1.0]
    comparisons = {}
    for a, name in [(0.5, "hybrid_0.5_vs_bm25"), (0.0, "dense_vs_bm25"), (0.7, "hybrid_0.7_vs_bm25")]:
        diffs = [t - b for t, b in zip(hits[a], bm25)]
        boot = rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERS, seed=SEED)
        mc = rc.exact_mcnemar(hits[a], bm25)
        comparisons[name] = {
            "mean_diff": boot["mean"],
            "diff_95_ci": boot["ci"],
            "exact_mcnemar": mc,
            "primary_test": "exact_mcnemar",
            "wins": mc["wins"], "losses": mc["losses"], "ties": mc["ties"],
        }

    n_en = langs.count("en"); n_ko = langs.count("ko")
    out = {
        "meta": {"mode": MODE, "dense_model": DENSE_MODEL, "n": len(queries),
                 "n_en": n_en, "n_ko": n_ko, "bootstrap_iters": BOOTSTRAP_ITERS, "seed": SEED,
                 "bm25_no_signal_queries": no_signal,
                 "superseded_by": "output/validated_suite.json (experiment_validated_suite.py). "
                                  "이 파일의 평가 결과는 헤드라인으로 인용하지 않는다.",
                 "label_nature": "corpus-text-grounded category labels; not legal/expert determinations"},
        "env": rc.env_meta({"seed": SEED}),
        "summary": summary, "comparisons": comparisons,
        "hit_vectors": {f"alpha={a}": hits[a] for a in ALPHAS}, "langs": langs,
    }
    EVAL_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# [SUPERSEDED] 확장 검증셋 평가 (TASK I)", "",
        "> ⚠ 평가 결과는 `output/validated_suite.json`(experiment_validated_suite.py)으로",
        "> 대체되었다. 이 스크립트의 존속 이유는 `data/validated_queries_expanded.json` 병합이다.",
        "",
        f"- 표본: **n={len(queries)}** (영어 {n_en}, 한국어 {n_ko}) — 원본 검증 13 + TASK G 슬라이스 병합",
        f"- 매칭: exact full eCFR code (충돌 0) / 노출 {MODE} / Dense {DENSE_MODEL}",
        "- 라벨: 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).", "",
        "## R@10 by retriever", "",
        "| retriever | 전체 R@10 | 영어 R@10 | 한국어 R@10 |", "|---|---:|---:|---:|",
    ]
    for a in ALPHAS:
        r = summary[f"alpha={a}"]
        nm = {1.0: "BM25 (1.0)", 0.0: "Dense (0.0)"}.get(a, f"hybrid ({a})")
        lines.append(f"| {nm} | {r['recall@10']:.4f} | {r['en_recall@10']:.4f} | {r['ko_recall@10']:.4f} |")
    lines += ["", "## 핵심 비교 (exact McNemar primary + paired bootstrap 보조)", "",
              "| 비교 | 평균차 | bootstrap 95% CI | 승/패/무 | exact p (양측) |",
              "|---|---:|---|---:|---:|"]
    for name, c in comparisons.items():
        ci = c["diff_95_ci"]
        lines.append(f"| {name} | {c['mean_diff']:+.4f} | [{ci[0]:.4f}, {ci[1]:.4f}] | "
                     f"{c['wins']}/{c['losses']}/{c['ties']} | "
                     f"{c['exact_mcnemar']['p_two_sided_exact']:.3g} |")
    lines += ["", "> 소표본에서 percentile bootstrap CI가 0을 포함하는 것은 이산 경계 인공물일 수",
              "> 있으므로 primary는 exact McNemar다(`docs/statistics.md` §5)."]
    lines += ["", "## 해석", "",
              f"- n=13 → n={len(queries)}로 확대. 핵심 질문: hybrid>BM25 / 한국어 회복의 95% CI가 0을 벗어났는가.",
              "- 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 법적·전문가 판정이 아니다.", ""]
    EVAL_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"n": len(queries), "n_en": n_en, "n_ko": n_ko,
                      "summary": summary, "comparisons": comparisons}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
