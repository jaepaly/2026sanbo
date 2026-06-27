#!/usr/bin/env python3
"""TASK H — embedding robustness on the expanded validated set (n=71).

TASK I showed multilingual hybrid beats BM25 with a 95% CI that excludes 0,
using paraphrase-multilingual-MiniLM-L12-v2. This script checks whether that
advantage is model-specific by swapping in other multilingual dense models and
re-running BM25 / Dense / Hybrid on the SAME expanded set with the SAME exact
full-eCFR-code matching.

Models (each downloaded locally on first run; no external inference API):
  - paraphrase-multilingual-MiniLM-L12-v2  (baseline, already used in TASK I)
  - intfloat/multilingual-e5-base          (needs 'query:'/'passage:' prefixes)
  - BAAI/bge-m3                            (no prefix)

BM25 is model-independent and computed once. For each dense model we report
R@10 (overall/EN/KO) at several alphas and the paired bootstrap 95% CI of
hybrid(α=0.5) vs BM25.

Run all models, or one at a time:  python experiment_embedding_robustness.py [model_id]
Outputs: output/embedding_robustness.json, output/embedding_robustness.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from run_experiments import BM25, build_doc_text

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "validated_queries_expanded.json"
JSON_PATH = OUT_DIR / "embedding_robustness.json"
MD_PATH = OUT_DIR / "embedding_robustness.md"

MODE = "minimal_text"
ALPHAS = [1.0, 0.7, 0.5, 0.3, 0.0]
BOOTSTRAP_ITERS = 20000
SEED = 20260626

# (model_id, prefix_scheme)  prefix_scheme: None or "e5"
MODELS = [
    ("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", None),
    ("intfloat/multilingual-e5-base", "e5"),
    ("BAAI/bge-m3", None),
]


def minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def paired_diff_ci(diffs, rng):
    arr = np.asarray(diffs, dtype=float)
    n = len(arr)
    idx = rng.integers(0, n, size=(BOOTSTRAP_ITERS, n))
    draws = arr[idx].mean(axis=1)
    return [round(float(np.quantile(draws, 0.025)), 4), round(float(np.quantile(draws, 0.975)), 4)]


def encode(model, texts, prefix):
    if prefix == "e5":
        texts = [f"{prefix_role}: {t}" for prefix_role, t in texts]
    return model.encode(texts, batch_size=32, normalize_embeddings=True,
                        show_progress_bar=False).astype(np.float32)


def evaluate_model(model_id, scheme, corpus, docs, codes, index, queries, langs):
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_id)

    if scheme == "e5":
        doc_emb = model.encode([f"passage: {d}" for d in docs], batch_size=32,
                               normalize_embeddings=True, show_progress_bar=False).astype(np.float32)
        q_emb = model.encode([f"query: {q['query']}" for q in queries], batch_size=32,
                             normalize_embeddings=True, show_progress_bar=False).astype(np.float32)
    else:
        doc_emb = model.encode(docs, batch_size=32, normalize_embeddings=True,
                               show_progress_bar=False).astype(np.float32)
        q_emb = model.encode([q["query"] for q in queries], batch_size=32,
                             normalize_embeddings=True, show_progress_bar=False).astype(np.float32)

    hits = {a: [] for a in ALPHAS}
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

    summary = {f"alpha={a}": {
        "recall@10": rate(hits[a]),
        "en_recall@10": rate(hits[a], "en"),
        "ko_recall@10": rate(hits[a], "ko"),
    } for a in ALPHAS}

    rng = np.random.default_rng(SEED)
    diffs = [t - b for t, b in zip(hits[0.5], hits[1.0])]
    ci = paired_diff_ci(diffs, rng)
    hybrid_vs_bm25 = {
        "mean_diff": round(sum(diffs) / len(diffs), 4),
        "diff_95_ci": ci, "significant": not (ci[0] <= 0 <= ci[1]),
        "wins": sum(d > 0 for d in diffs), "losses": sum(d < 0 for d in diffs),
    }
    return {"summary": summary, "hybrid0.5_vs_bm25": hybrid_vs_bm25}


def main() -> None:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    queries = payload["queries"]
    langs = [q["lang"] for q in queries]
    docs = [build_doc_text(e, MODE) for e in corpus]
    codes = [e["code"] for e in corpus]
    index = BM25(docs)

    results = {}
    for model_id, scheme in MODELS:
        if only and only not in model_id:
            continue
        short = model_id.split("/")[-1]
        print(f"[model] {model_id} ...", flush=True)
        try:
            results[short] = evaluate_model(model_id, scheme, corpus, docs, codes, index, queries, langs)
            results[short]["model_id"] = model_id
        except Exception as exc:  # keep going if one model fails to download/load
            print(f"[model] {model_id} FAILED: {exc}", flush=True)
            results[short] = {"error": str(exc), "model_id": model_id}

    n_en = langs.count("en"); n_ko = langs.count("ko")
    out = {"meta": {"mode": MODE, "n": len(queries), "n_en": n_en, "n_ko": n_ko,
                    "alphas": ALPHAS, "bootstrap_iters": BOOTSTRAP_ITERS, "seed": SEED,
                    "note": "BM25 identical across models; only the dense model changes."},
           "results": results}
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# TASK H — 임베딩 robustness (확장셋 n=%d)" % len(queries), "",
        f"- 표본: n={len(queries)} (영어 {n_en}, 한국어 {n_ko}) / 노출 {MODE} / 매칭 exact eCFR code",
        "- BM25는 모델 불문 동일. dense 모델만 교체해 hybrid 우위가 유지되는지 확인.", "",
        "## 모델별 R@10 (전체 / 영어 / 한국어)", "",
        "| dense 모델 | BM25 | Dense(α0) | hybrid α0.7 | hybrid α0.5 | hybrid α0.3 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for short, r in results.items():
        if "error" in r:
            lines.append(f"| {short} | (실패: {r['error'][:40]}) | | | | |")
            continue
        s = r["summary"]
        lines.append(
            f"| {short} | {s['alpha=1.0']['recall@10']:.3f} | {s['alpha=0.0']['recall@10']:.3f} | "
            f"{s['alpha=0.7']['recall@10']:.3f} | {s['alpha=0.5']['recall@10']:.3f} | {s['alpha=0.3']['recall@10']:.3f} |"
        )
    lines += ["", "## 한국어 R@10 (BM25 vs 각 dense hybrid α0.5)", "",
              "| dense 모델 | BM25 KO | hybrid α0.5 KO |", "|---|---:|---:|"]
    for short, r in results.items():
        if "error" in r:
            continue
        s = r["summary"]
        lines.append(f"| {short} | {s['alpha=1.0']['ko_recall@10']:.3f} | {s['alpha=0.5']['ko_recall@10']:.3f} |")
    lines += ["", "## hybrid(α0.5) vs BM25 — paired bootstrap 95% CI", "",
              "| dense 모델 | 평균차 | 95% CI | 유의? | wins/losses |", "|---|---:|---|---|---:|"]
    for short, r in results.items():
        if "error" in r:
            continue
        c = r["hybrid0.5_vs_bm25"]
        ci = c["diff_95_ci"]
        lines.append(f"| {short} | {c['mean_diff']:+.4f} | [{ci[0]:.4f}, {ci[1]:.4f}] | "
                     f"{'**예**' if c['significant'] else '아니오'} | {c['wins']}/{c['losses']} |")
    lines += ["", "## 해석", "",
              "- 핵심: 여러 다국어 임베딩에서 hybrid > BM25 우위와 한국어 회복이 유지되면, 결과가 특정 모델 때문이 아님을 보인다.",
              "- 라벨은 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).", ""]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: (v.get("summary", {}).get("alpha=0.5") if "error" not in v else v)
                      for k, v in results.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
