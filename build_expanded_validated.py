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

from run_experiments import BM25, build_doc_text

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


def minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def paired_diff_ci(diffs: list[float], rng: np.random.Generator) -> list[float]:
    arr = np.asarray(diffs, dtype=float)
    n = len(arr)
    idx = rng.integers(0, n, size=(BOOTSTRAP_ITERS, n))
    draws = arr[idx].mean(axis=1)
    return [round(float(np.quantile(draws, 0.025)), 4), round(float(np.quantile(draws, 0.975)), 4)]


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
    for qi, q in enumerate(queries):
        labels = set(q["validated_labels"])
        bm = minmax(index.scores(q["query"]))
        dn = minmax(doc_emb @ q_emb[qi])
        for a in ALPHAS:
            ranked = np.argsort(-(a * bm + (1 - a) * dn))
            top10 = [codes[i] for i in ranked[:10]]
            hits[a].append(int(any(c in labels for c in top10)))

    def rate(vec, mask=None):
        v = [h for h, lg in zip(vec, langs) if (mask is None or lg == mask)]
        return round(sum(v) / len(v), 4) if v else 0.0

    summary = {}
    for a in ALPHAS:
        summary[f"alpha={a}"] = {
            "recall@10": rate(hits[a]),
            "en_recall@10": rate(hits[a], "en"),
            "ko_recall@10": rate(hits[a], "ko"),
        }

    rng = np.random.default_rng(SEED)
    bm25 = hits[1.0]
    comparisons = {}
    for a, name in [(0.5, "hybrid_0.5_vs_bm25"), (0.0, "dense_vs_bm25"), (0.7, "hybrid_0.7_vs_bm25")]:
        diffs = [t - b for t, b in zip(hits[a], bm25)]
        comparisons[name] = {
            "mean_diff": round(sum(diffs) / len(diffs), 4),
            "diff_95_ci": paired_diff_ci(diffs, rng),
            "wins": sum(d > 0 for d in diffs), "losses": sum(d < 0 for d in diffs),
        }

    n_en = langs.count("en"); n_ko = langs.count("ko")
    out = {
        "meta": {"mode": MODE, "dense_model": DENSE_MODEL, "n": len(queries),
                 "n_en": n_en, "n_ko": n_ko, "bootstrap_iters": BOOTSTRAP_ITERS, "seed": SEED,
                 "label_nature": "corpus-text-grounded category labels; not legal/expert determinations"},
        "summary": summary, "comparisons": comparisons,
    }
    EVAL_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 확장 검증셋 평가 (TASK I)", "",
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
    lines += ["", "## 핵심 비교 (paired bootstrap 95% CI)", "",
              "| 비교 | 평균차 | 95% CI | wins/losses | 0 포함? |", "|---|---:|---|---:|---|"]
    for name, c in comparisons.items():
        ci = c["diff_95_ci"]
        zero = "예(유의X)" if ci[0] <= 0 <= ci[1] else "**아니오(유의)**"
        lines.append(f"| {name} | {c['mean_diff']:+.4f} | [{ci[0]:.4f}, {ci[1]:.4f}] | {c['wins']}/{c['losses']} | {zero} |")
    lines += ["", "## 해석", "",
              f"- n=13 → n={len(queries)}로 확대. 핵심 질문: hybrid>BM25 / 한국어 회복의 95% CI가 0을 벗어났는가.",
              "- 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 법적·전문가 판정이 아니다.", ""]
    EVAL_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"n": len(queries), "n_en": n_en, "n_ko": n_ko,
                      "summary": summary, "comparisons": comparisons}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
