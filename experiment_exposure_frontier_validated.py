#!/usr/bin/env python3
"""Close the thesis-evidence gap — exposure vs recall on the validated set.

All prior validated/expanded evaluations fixed exposure at minimal_text, so the
paper's central information-minimization claim ("cut returned information while
keeping recall") still rested only on the self-derived synthetic set that TASK A
showed is inflated. This script measures the exposure-recall frontier on the
non-self-referential expanded validated set (n=71) by varying the exposure mode
(full_text / minimal_text / minimal_no_code) for BM25, Dense, and Hybrid.

For each (mode, retriever) we report R@10 (overall/EN/KO) and the mean
exposure@10 (characters returned in the top-10). The key test: does moving from
full_text to minimal_text reduce exposure substantially while keeping hybrid
recall (paired bootstrap CI of the difference)?

Outputs: output/exposure_frontier_validated.json, .md
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from run_experiments import BM25, build_doc_text, exposure_for_entry

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "validated_queries_expanded.json"
JSON_PATH = OUT_DIR / "exposure_frontier_validated.json"
MD_PATH = OUT_DIR / "exposure_frontier_validated.md"

MODES = ["full_text", "minimal_text", "minimal_no_code"]
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ALPHAS = {"BM25": 1.0, "hybrid": 0.5, "dense": 0.0}
BOOTSTRAP_ITERS = 20000
SEED = 20260626


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


def main() -> None:
    from sentence_transformers import SentenceTransformer

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))["queries"]
    langs = [q["lang"] for q in queries]
    codes = [e["code"] for e in corpus]
    model = SentenceTransformer(DENSE_MODEL)

    # per-mode hit vectors for each retriever, and exposure@10 (hybrid top-10)
    per_mode = {}
    hybrid_hits_by_mode = {}
    for mode in MODES:
        docs = [build_doc_text(e, mode) for e in corpus]
        exposure = [exposure_for_entry(e, mode) for e in corpus]
        index = BM25(docs)
        doc_emb = model.encode(docs, batch_size=64, normalize_embeddings=True,
                               show_progress_bar=False).astype(np.float32)
        q_emb = model.encode([q["query"] for q in queries], batch_size=64,
                             normalize_embeddings=True, show_progress_bar=False).astype(np.float32)

        hits = {name: [] for name in ALPHAS}
        exp10 = []  # exposure@10 measured on the hybrid ranking
        for qi, q in enumerate(queries):
            labels = set(q["validated_labels"])
            bm = minmax(index.scores(q["query"]))
            dn = minmax(doc_emb @ q_emb[qi])
            for name, a in ALPHAS.items():
                ranked = np.argsort(-(a * bm + (1 - a) * dn))
                top10 = ranked[:10]
                hits[name].append(int(any(codes[i] in labels for i in top10)))
                if name == "hybrid":
                    exp10.append(sum(exposure[i] for i in top10))
        hybrid_hits_by_mode[mode] = hits["hybrid"]

        def rate(vec, mask=None):
            v = [h for h, lg in zip(vec, langs) if (mask is None or lg == mask)]
            return round(sum(v) / len(v), 4) if v else 0.0

        per_mode[mode] = {
            "exposure@10_mean": round(float(np.mean(exp10)), 1),
            "retrievers": {
                name: {"recall@10": rate(hits[name]),
                       "en_recall@10": rate(hits[name], "en"),
                       "ko_recall@10": rate(hits[name], "ko")}
                for name in ALPHAS
            },
        }

    # key test: hybrid minimal_text vs hybrid full_text (does cutting exposure hurt?)
    rng = np.random.default_rng(SEED)
    diffs = [m - f for m, f in zip(hybrid_hits_by_mode["minimal_text"], hybrid_hits_by_mode["full_text"])]
    ci = paired_diff_ci(diffs, rng)
    exp_full = per_mode["full_text"]["exposure@10_mean"]
    exp_min = per_mode["minimal_text"]["exposure@10_mean"]
    cut = round(100 * (exp_full - exp_min) / exp_full, 1)
    key = {
        "hybrid_minimal_text_vs_full_text": {
            "mean_diff_recall@10": round(sum(diffs) / len(diffs), 4),
            "diff_95_ci": ci,
            "significant_loss": ci[1] < 0,
            "exposure_cut_pct": cut,
        }
    }

    out = {"meta": {"n": len(queries), "n_en": langs.count("en"), "n_ko": langs.count("ko"),
                    "dense_model": DENSE_MODEL, "modes": MODES, "seed": SEED,
                    "label_nature": "corpus-text-grounded category labels; not legal/expert"},
           "per_mode": per_mode, "key_comparison": key}
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# 노출-성능 frontier (검증 확장셋, n={len(queries)})", "",
        f"- 표본 n={len(queries)} (영어 {langs.count('en')}, 한국어 {langs.count('ko')}) / Dense {DENSE_MODEL}",
        "- **비자기참조 데이터**에서 노출 모드별 R@10과 노출량@10을 측정(정보최소화 주장 직접 검증).",
        "- 라벨: 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).", "",
        "## 노출 모드 × retriever R@10 (노출량@10)", "",
        "| 노출 모드 | 노출량@10 | BM25 | hybrid(α0.5) | dense |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        pm = per_mode[mode]
        r = pm["retrievers"]
        lines.append(f"| {mode} | {pm['exposure@10_mean']:.0f} | {r['BM25']['recall@10']:.3f} | "
                     f"{r['hybrid']['recall@10']:.3f} | {r['dense']['recall@10']:.3f} |")
    k = key["hybrid_minimal_text_vs_full_text"]
    lines += ["", "## 핵심: 노출 축소가 hybrid 성능을 해치는가?", "",
              f"- full_text → minimal_text 노출량 **{k['exposure_cut_pct']:.0f}% 감소**.",
              f"- hybrid R@10 차이(minimal − full): {k['mean_diff_recall@10']:+.4f}, 95% CI [{k['diff_95_ci'][0]:.4f}, {k['diff_95_ci'][1]:.4f}].",
              f"- 유의한 성능 손실? **{'예' if k['significant_loss'] else '아니오(노출 축소가 성능을 유의하게 해치지 않음)'}**.",
              "",
              "## 해석", "",
              "- 정보최소화 주장을 자기참조 합성셋이 아니라 **검증 확장셋**에서 직접 평가했다.",
              "- frontier가 '노출 대폭 감소 + hybrid 성능 유지'를 보이면, 논문 제목(최소노출)과 증거가 정렬된다.", ""]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"per_mode_exposure_and_hybrid": {
        m: {"exposure@10": per_mode[m]["exposure@10_mean"],
            "hybrid_R@10": per_mode[m]["retrievers"]["hybrid"]["recall@10"],
            "BM25_R@10": per_mode[m]["retrievers"]["BM25"]["recall@10"]} for m in MODES},
        "key": key}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
