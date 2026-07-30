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

**대체 공지 (M9-B).** 2차원(색인 모드 × 반환 모드) 노출표는
`experiment_validated_suite.py`가 `exposure_at10`으로 산출한다. 이 스크립트는 색인
모드와 반환 모드를 동일하게 묶은 1차원 대각선만 측정하므로 '반환량만 줄이기'
조건(예: 색인=minimal_text, 반환=minimal_no_code)을 표현할 수 없다.

정정 (M14-D4): `np.argsort(-...)` → `retrieval_core.rank_indices`, BM25 점수가 전부
0인 질의는 BM25 단독에서 검색 실패로 집계, 노출량은 `retrieval_core.exposure_chars`
(반환 텍스트에서 파생)로 계산하고 정정 전 정의를 함께 기록, per-query `hit_vectors`
저장, primary 검정을 exact McNemar로 변경.

Outputs: output/exposure_frontier_validated.json, .md
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import retrieval_core as rc
from retrieval_core import BM25, index_text as build_doc_text, exposure_chars as exposure_for_entry

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


minmax = rc.minmax


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
    hits_by_mode = {}
    for mode in MODES:
        docs = [build_doc_text(e, mode) for e in corpus]
        # 노출량은 '반환 텍스트'에서 파생된다. 정정 전 정의는 minimal_text와
        # minimal_no_code에 동일한 값을 부여했으므로 비교용으로 함께 기록한다.
        exposure = [exposure_for_entry(e, mode) for e in corpus]
        exposure_legacy = [rc.legacy_exposure_chars(e, mode) for e in corpus]
        index = BM25(docs)
        doc_emb = model.encode(docs, batch_size=64, normalize_embeddings=True,
                               show_progress_bar=False).astype(np.float32)
        q_emb = model.encode([q["query"] for q in queries], batch_size=64,
                             normalize_embeddings=True, show_progress_bar=False).astype(np.float32)

        hits = {name: [] for name in ALPHAS}
        exp10 = []          # exposure@10 measured on the hybrid ranking
        exp10_legacy = []
        no_signal = 0
        for qi, q in enumerate(queries):
            labels = set(q["validated_labels"])
            raw_bm = index.scores(q["query"])
            signal = rc.has_signal(raw_bm)
            if not signal:
                no_signal += 1
            bm = minmax(raw_bm)
            dn = minmax(doc_emb @ q_emb[qi])
            for name, a in ALPHAS.items():
                if a == 1.0 and not signal:
                    top10: list[int] = []
                else:
                    top10 = list(rc.rank_indices(rc.blend(bm, dn, a))[:10])
                hits[name].append(int(any(codes[i] in labels for i in top10)))
                if name == "hybrid":
                    exp10.append(sum(exposure[i] for i in top10))
                    exp10_legacy.append(sum(exposure_legacy[i] for i in top10))
        hybrid_hits_by_mode[mode] = hits["hybrid"]
        hits_by_mode[mode] = {name: list(v) for name, v in hits.items()}

        def rate(vec, mask=None):
            v = [h for h, lg in zip(vec, langs) if (mask is None or lg == mask)]
            return round(sum(v) / len(v), 4) if v else 0.0

        per_mode[mode] = {
            "exposure@10_mean": round(float(np.mean(exp10)), 1),
            "exposure@10_mean_legacy_definition": round(float(np.mean(exp10_legacy)), 1),
            "bm25_no_signal_queries": no_signal,
            "retrievers": {
                name: {"recall@10": rate(hits[name]),
                       "recall@10_ci95": rc.rate_with_ci(hits[name])["ci95"],
                       "en_recall@10": rate(hits[name], "en"),
                       "ko_recall@10": rate(hits[name], "ko")}
                for name in ALPHAS
            },
        }

    # key test: hybrid minimal_text vs hybrid full_text (does cutting exposure hurt?)
    diffs = [m - f for m, f in zip(hybrid_hits_by_mode["minimal_text"], hybrid_hits_by_mode["full_text"])]
    boot = rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERS, seed=SEED)
    mc = rc.exact_mcnemar(hybrid_hits_by_mode["minimal_text"], hybrid_hits_by_mode["full_text"])
    ci = boot["ci"]
    exp_full = per_mode["full_text"]["exposure@10_mean"]
    exp_min = per_mode["minimal_text"]["exposure@10_mean"]
    cut = round(100 * (exp_full - exp_min) / exp_full, 1)
    key = {
        "hybrid_minimal_text_vs_full_text": {
            "mean_diff_recall@10": boot["mean"],
            "diff_95_ci": ci,
            "significant_loss": ci[1] < 0,
            "exact_mcnemar": mc,
            "primary_test": "exact_mcnemar",
            "tost_delta_0.05": rc.tost_paired(diffs, 0.05, iters=BOOTSTRAP_ITERS, seed=SEED),
            "exposure_cut_pct": cut,
            "warning": "CI가 0을 포함한다는 것은 등가성의 근거가 아니다(귀무가설 수용). "
                       "등가 주장은 사전지정 마진 δ에 대한 TOST로만 한다.",
        }
    }

    out = {"meta": {"n": len(queries), "n_en": langs.count("en"), "n_ko": langs.count("ko"),
                    "dense_model": DENSE_MODEL, "modes": MODES, "seed": SEED,
                    "superseded_by": "output/validated_suite.json (exposure_at10: "
                                     "색인 모드 × 반환 모드 2차원표)",
                    "label_nature": "corpus-text-grounded category labels; not legal/expert"},
           "env": rc.env_meta({"seed": SEED}),
           "per_mode": per_mode, "hit_vectors": hits_by_mode, "langs": langs,
           "key_comparison": key}
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# 노출-성능 frontier (검증 확장셋, n={len(queries)})", "",
        f"- 표본 n={len(queries)} (영어 {langs.count('en')}, 한국어 {langs.count('ko')}) / Dense {DENSE_MODEL}",
        "- **비자기참조 데이터**에서 노출 모드별 R@10과 노출량@10을 측정(정보최소화 주장 직접 검증).",
        "- 라벨: 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).", "",
        "## 노출 모드 × retriever R@10 (노출량@10)", "",
        "| 노출 모드 | 노출량@10 | 노출량@10(정정 전 정의) | BM25 무신호 질의 | BM25 | hybrid(α0.5) | dense |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode in MODES:
        pm = per_mode[mode]
        r = pm["retrievers"]
        lines.append(f"| {mode} | {pm['exposure@10_mean']:.0f} | "
                     f"{pm['exposure@10_mean_legacy_definition']:.0f} | "
                     f"{pm['bm25_no_signal_queries']}/{len(queries)} | "
                     f"{r['BM25']['recall@10']:.3f} | "
                     f"{r['hybrid']['recall@10']:.3f} | {r['dense']['recall@10']:.3f} |")
    lines += ["", "> 정정 전 정의는 `minimal_text`와 `minimal_no_code`에 동일한 값을 부여했다."]
    k = key["hybrid_minimal_text_vs_full_text"]
    t = k["tost_delta_0.05"]
    lines += ["", "## 핵심: 노출 축소가 hybrid 성능을 해치는가?", "",
              f"- full_text → minimal_text 노출량 **{k['exposure_cut_pct']:.0f}% 감소**.",
              f"- hybrid R@10 차이(minimal − full): {k['mean_diff_recall@10']:+.4f}, 95% CI [{k['diff_95_ci'][0]:.4f}, {k['diff_95_ci'][1]:.4f}].",
              f"- exact McNemar(primary): 승/패/무 {k['exact_mcnemar']['wins']}/{k['exact_mcnemar']['losses']}/{k['exact_mcnemar']['ties']}, "
              f"양측 p={k['exact_mcnemar']['p_two_sided_exact']:.3g}.",
              f"- 유의한 성능 손실? **{'예' if k['significant_loss'] else '아니오'}**.",
              f"- 사전지정 마진 δ=0.05 등가성(TOST): **{'등가' if t.get('equivalent_at_0.05') else '등가 아님'}** "
              f"(p_max={t.get('p_max')}).",
              "",
              "> **주의**: 'CI가 0을 포함' 은 등가성의 근거가 아니다(귀무가설 수용). 노출 축소가",
              "> 성능을 해치지 않는다는 주장은 사전지정 마진 δ에 대한 TOST가 통과할 때만 한다.",
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
