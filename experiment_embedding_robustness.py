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

정정 (M14-D1 / D3 / D4):

* **모델별 bootstrap 리샘플 분리.** 이전 판은 `evaluate_model()` 안에서
  `np.random.default_rng(SEED)`를 매번 같은 seed로 새로 만들었다. 그래서 세 모델이
  **완전히 동일한 리샘플 인덱스 행렬**을 공유했고, 모델 간 CI가 독립적으로 얻어진
  것처럼 보이지만 실제로는 같은 재표본 위에서 계산된 값이었다. 이제 모델 순번 i로
  `default_rng(SEED + i)`를 만들어 분리한다(seed는 JSON에 모델별로 기록).
* **죽은 코드 삭제.** 모듈 수준 `encode(model, texts, prefix)`는 `prefix == "e5"`
  분기에서 `texts`를 (role, text) 튜플로 언패킹하려 하므로 문자열 리스트를 넘기면
  즉시 ValueError였다. 호출부도 없었다. 삭제했다.
* **결정론적 랭킹.** `np.argsort(-...)` → `retrieval_core.rank_indices`, BM25
  점수가 전부 0인 질의는 α=1.0에서 검색 실패로 집계.

무거운 3모델 전체 실행 대신 단일 모델 스모크로 검증하려면:
  python experiment_embedding_robustness.py paraphrase-multilingual-MiniLM
Outputs: output/embedding_robustness.json, output/embedding_robustness.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

import retrieval_core as rc
from retrieval_core import BM25, index_text as build_doc_text

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


minmax = rc.minmax


def evaluate_model(model_id, scheme, corpus, docs, codes, index, queries, langs,
                   model_seed: int):
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

    summary = {f"alpha={a}": {
        "recall@10": rate(hits[a]),
        "recall@10_ci95": rc.rate_with_ci(hits[a])["ci95"],
        "en_recall@10": rate(hits[a], "en"),
        "ko_recall@10": rate(hits[a], "ko"),
    } for a in ALPHAS}

    # 모델별로 분리된 seed. 이전 판은 세 모델이 동일한 리샘플 행렬을 공유했다.
    diffs = [t - b for t, b in zip(hits[0.5], hits[1.0])]
    boot = rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERS, seed=model_seed)
    mc = rc.exact_mcnemar(hits[0.5], hits[1.0])
    ci = boot["ci"]
    hybrid_vs_bm25 = {
        "mean_diff": boot["mean"],
        "diff_95_ci": ci,
        "bootstrap_excludes_zero": not (ci[0] <= 0 <= ci[1]),
        "bootstrap_seed": model_seed,
        "exact_mcnemar": mc,
        "primary_test": "exact_mcnemar",
        "wins": mc["wins"], "losses": mc["losses"], "ties": mc["ties"],
    }
    return {"summary": summary, "hybrid0.5_vs_bm25": hybrid_vs_bm25,
            "hit_vectors": {f"alpha={a}": hits[a] for a in ALPHAS},
            "diagnostics": {"bm25_no_signal_queries": no_signal}}


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
    # 모델 순번을 seed offset으로 써서 리샘플 행렬을 모델별로 분리한다.
    for i, (model_id, scheme) in enumerate(MODELS):
        if only and only not in model_id:
            continue
        short = model_id.split("/")[-1]
        model_seed = SEED + i
        print(f"[model] {model_id} (bootstrap seed {model_seed}) ...", flush=True)
        try:
            results[short] = evaluate_model(model_id, scheme, corpus, docs, codes,
                                            index, queries, langs, model_seed)
            results[short]["model_id"] = model_id
        except Exception as exc:  # keep going if one model fails to download/load
            print(f"[model] {model_id} FAILED: {exc}", flush=True)
            results[short] = {"error": str(exc), "model_id": model_id,
                              "bootstrap_seed": model_seed}

    n_en = langs.count("en"); n_ko = langs.count("ko")
    out = {"meta": {"mode": MODE, "n": len(queries), "n_en": n_en, "n_ko": n_ko,
                    "alphas": ALPHAS, "bootstrap_iters": BOOTSTRAP_ITERS,
                    "seed_base": SEED,
                    "bootstrap_seed_per_model": {
                        m.split("/")[-1]: SEED + i for i, (m, _) in enumerate(MODELS)},
                    "primary_test": "exact_mcnemar (paired bootstrap is secondary)",
                    "note": "BM25 identical across models; only the dense model changes. "
                            "Each model uses its own bootstrap seed (SEED + model index) "
                            "so the three CIs are not computed on one shared resample matrix."},
           "env": rc.env_meta({"seed_base": SEED}),
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
    lines += ["", "## hybrid(α0.5) vs BM25 — exact McNemar(primary) + paired bootstrap(보조)", "",
              "| dense 모델 | 평균차 | bootstrap 95% CI | bootstrap seed | 승/패/무 | exact p (양측) |",
              "|---|---:|---|---:|---:|---:|"]
    for short, r in results.items():
        if "error" in r:
            continue
        c = r["hybrid0.5_vs_bm25"]
        ci = c["diff_95_ci"]
        lines.append(f"| {short} | {c['mean_diff']:+.4f} | [{ci[0]:.4f}, {ci[1]:.4f}] | "
                     f"{c['bootstrap_seed']} | {c['wins']}/{c['losses']}/{c['ties']} | "
                     f"{c['exact_mcnemar']['p_two_sided_exact']:.3g} |")
    lines += ["", "> 모델마다 bootstrap seed가 다르다. 이전 판은 세 모델이 동일한 리샘플 행렬을",
              "> 공유해 CI가 독립적으로 얻어진 것처럼 보였다.", "",
              "## 해석", "",
              "- 핵심: 여러 다국어 임베딩에서 hybrid > BM25 우위와 한국어 회복이 유지되면, 결과가 특정 모델 때문이 아님을 보인다.",
              "- 라벨은 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).", ""]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: (v.get("summary", {}).get("alpha=0.5") if "error" not in v else v)
                      for k, v in results.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
