#!/usr/bin/env python3
"""검증셋(현행 n=151) 기준 통계 재집계 — 실제 per-query hit 벡터만 사용한다.

정정 내역 (감사 항목 M9 / M14-A):

A. **가짜 hit 벡터 재구성 제거.**
   이전 버전은 `infer_hits(rate, n)`으로 반올림된 aggregate R@10에서
   `[1]*k + [0]*(n-k)` 형태의 per-query 벡터를 *합성*하고, paired 설계인
   비교에 `rng.binomial(n_a, p_a) - rng.binomial(n_b, p_b)`라는 **unpaired**
   이항 시뮬레이션을 적용했다. 두 문제가 겹쳐서
   - 짝지음 정보(같은 질의에서 A는 맞고 B는 틀렸다)가 전부 버려졌고,
   - 차이의 CI가 실제보다 넓게(또는 방향이 뒤바뀌게) 나왔다.
   이제 `run_experiments.py`(합성셋)와 `experiment_validated_suite.py`
   (검증셋)가 `hit_vectors`를 JSON에 저장하므로 재구성이 불필요하다.
   `bootstrap_diff_ci` / `infer_hits` / `bootstrap_mean_ci`는 삭제했다.
   per-query 벡터가 없는 산출물은 **추정하지 않고** 절대율 + Clopper-Pearson
   구간만 보고하고 `paired_test_unavailable` 이유를 남긴다.

B. **stale 산출물 정정.**
   헤드라인 표본은 n=13(`output/validated_eval.json`)이 아니라
   현행 검증셋(`output/validated_suite*.json`, n=151)이다. n=13 결과는 삭제하지 않고
   `docs/statistics_n13_superseded.md`로 보존한다.

C. **소표본 bootstrap 이산 경계 인공물 정량화.**
   n=13에서 (3승, 10무, 0패)이면 부트스트랩 재표본에 승리 질의가 하나도
   포함되지 않을 확률이 (10/13)^13 = 0.0330 > 0.025 이므로, 2.5분위수가
   **구조적으로** 0이 된다. 즉 3승 0패인 어떤 결과도 percentile bootstrap
   에서는 자동으로 "CI가 0을 포함"한다. 이 값을 실제로 계산해 기록한다.
   따라서 소표본 이진 짝지음의 primary 검정은 exact McNemar와
   Clopper-Pearson이며, percentile bootstrap은 보조로만 쓴다.

출력: output/stats_summary.json, docs/statistics.md,
      docs/statistics_n13_superseded.md
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"
DOCS_DIR = ROOT / "docs"
OUT_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)

STATS_JSON = OUT_DIR / "stats_summary.json"
STATS_MD = DOCS_DIR / "statistics.md"
SUPERSEDED_MD = DOCS_DIR / "statistics_n13_superseded.md"

BOOTSTRAP_ITERATIONS = 20000
SEED = 20260626

# 검증셋의 primary 조건 (experiment_validated_suite.py의 사전지정과 동일)
PRIMARY_INDEX_MODE = "minimal_text"
PRIMARY_RETRIEVER = "hybrid_0.5"

# --------------------------------------------------------------------------
# 감사 기록: 결정론적 랭킹(rank_indices) 전환 전/후 수치 변동
#
# `np.argsort(-scores)`는 동점의 순서를 정렬 구현에 맡긴다. 이를 '점수 내림차순 +
# 인덱스 오름차순'으로 바꾸면 동점 구간에서 몇 개 질의의 순위가 달라진다. 아래는
# `experiment_paraphrase_gap.py`를 정정 전/후로 각각 실행해 **실측**한 차이다.
# 값이 조용히 바뀌지 않도록 before/after를 코드에 박아 산출물에 함께 싣는다.
#
# 요지: 논문 주장 1의 헤드라인 R@10 (합성 full_text 0.9968 / minimal_text 0.9792 /
# 고-IDF 5개 제거 0.7596 / 10개 제거 0.4407)은 **전부 불변**이다. 바뀐 것은 동점이
# 흔한 R@1·R@5와, full_text N=5의 R@10 한 칸(질의 1개분)뿐이다.
# --------------------------------------------------------------------------
RANKING_DETERMINISM_AUDIT = {
    "source_script": "experiment_paraphrase_gap.py",
    "change": "np.argsort(-scores) -> retrieval_core.rank_indices "
              "(내림차순 + 인덱스 오름차순 동점처리) + 전점수 0 질의를 검색 실패로 처리",
    "headline_claim1_unchanged": {
        "synthetic_full_text_recall@10_N0": 0.9968,
        "synthetic_minimal_text_recall@10_N0": 0.9792,
        "synthetic_minimal_text_recall@10_N5": 0.7596,
        "synthetic_minimal_text_recall@10_N10": 0.4407,
    },
    "changed_cells": [
        {"mode": "minimal_text", "N": 0, "metric": "recall@1", "before": 0.7837, "after": 0.7804},
        {"mode": "minimal_text", "N": 0, "metric": "recall@5", "before": 0.9583, "after": 0.9599},
        {"mode": "minimal_text", "N": 1, "metric": "recall@1", "before": 0.7340, "after": 0.7324},
        {"mode": "minimal_text", "N": 2, "metric": "recall@1", "before": 0.6923, "after": 0.6891},
        {"mode": "minimal_text", "N": 2, "metric": "recall@5", "before": 0.8942, "after": 0.8926},
        {"mode": "minimal_text", "N": 3, "metric": "recall@1", "before": 0.6202, "after": 0.6234},
        {"mode": "minimal_text", "N": 3, "metric": "recall@5", "before": 0.8397, "after": 0.8349},
        {"mode": "minimal_text", "N": 5, "metric": "recall@1", "before": 0.5256, "after": 0.5192},
        {"mode": "minimal_text", "N": 5, "metric": "recall@5", "before": 0.7099, "after": 0.7067},
        {"mode": "full_text", "N": 0, "metric": "recall@1", "before": 0.8702, "after": 0.8686},
        {"mode": "full_text", "N": 1, "metric": "recall@1", "before": 0.8526, "after": 0.8510},
        {"mode": "full_text", "N": 2, "metric": "recall@1", "before": 0.8317, "after": 0.8333},
        {"mode": "full_text", "N": 2, "metric": "recall@5", "before": 0.9760, "after": 0.9776},
        {"mode": "full_text", "N": 3, "metric": "recall@1", "before": 0.8077, "after": 0.8061},
        {"mode": "full_text", "N": 5, "metric": "recall@1", "before": 0.7452, "after": 0.7468},
        {"mode": "full_text", "N": 5, "metric": "recall@5", "before": 0.9103, "after": 0.9087},
        {"mode": "full_text", "N": 5, "metric": "recall@10", "before": 0.9295, "after": 0.9311},
        {"mode": "full_text", "N": 10, "metric": "recall@5", "before": 0.7276, "after": 0.7260},
    ],
    "reading": "변동 폭은 전부 |Δ| ≤ 0.0064 (624개 중 최대 4개 질의)이며, 동점이 흔한 R@1·R@5에 "
               "몰려 있다. 방향이 양쪽으로 섞여 있는 것도 이것이 체계적 편향이 아니라 동점 "
               "순서 인공물이었음을 보여준다.",
}

# --------------------------------------------------------------------------
# 감사 기록: retriever_compare 입력 비대칭 정정 전/후
#
# 정정 전에는 dense에만 `" ".join(tokens)` — 구두점이 사라지고 전부 소문자화된
# detokenize 문자열 — 을 주고 BM25에는 토큰 형태를 주었다. 두 검색기를 비교하면서
# 전처리를 다르게 준 것이므로 격차 자체가 인공물일 수 있었다. 정정 후에는 원문에서
# 대상 토큰만 word-boundary 삭제한 **동일한 문자열**을 양쪽에 준다.
#
# 실측 결과: 격차는 거의 그대로다(전 조건 |Δ| ≤ 0.016). 즉 입력 비대칭은 **실재하는
# 방법론적 결함이었지만 관측된 BM25 우위의 원인은 아니었다.** 원인은 합성 질의가
# 정답 문서에서 파생되어 어휘 중첩이 인위적으로 높다는 것(자기참조)이다.
# --------------------------------------------------------------------------
INPUT_SYMMETRY_AUDIT = {
    "source_script": "experiment_retriever_compare.py",
    "change": 'dense에만 주던 `" ".join(ablated_tokens)`를 폐기하고, 원문에서 대상 토큰만 '
              "word-boundary 삭제한 동일 문자열을 BM25와 dense에 똑같이 입력",
    "metric": "recall@10 (합성 테스트 질의 624개)",
    "rows": [
        {"N": 0, "alpha": 1.0, "before": 0.9792, "after": 0.9792},
        {"N": 0, "alpha": 0.5, "before": 0.9647, "after": 0.9728},
        {"N": 0, "alpha": 0.0, "before": 0.8654, "after": 0.8686},
        {"N": 3, "alpha": 1.0, "before": 0.8862, "after": 0.8862},
        {"N": 3, "alpha": 0.5, "before": 0.8734, "after": 0.8718},
        {"N": 3, "alpha": 0.0, "before": 0.6731, "after": 0.6603},
        {"N": 5, "alpha": 1.0, "before": 0.7596, "after": 0.7596},
        {"N": 5, "alpha": 0.5, "before": 0.7452, "after": 0.7356},
        {"N": 5, "alpha": 0.0, "before": 0.4904, "after": 0.4984},
        {"N": 10, "alpha": 1.0, "before": 0.4407, "after": 0.4423},
        {"N": 10, "alpha": 0.5, "before": 0.4038, "after": 0.3990},
        {"N": 10, "alpha": 0.0, "before": 0.2532, "after": 0.2516},
    ],
    "max_abs_delta": 0.016,
    "reading": "입력을 대칭으로 맞춘 뒤에도 합성셋에서는 모든 어휘격차 수준에서 BM25(α=1.0)가 "
               "dense(α=0.0)를 크게 앞선다. 즉 이 격차는 전처리 비대칭이 만든 것이 아니라 "
               "**합성 질의가 정답 문서 본문에서 파생됐다는 자기참조 구조**가 만든 것이다. "
               "따라서 이 셋은 검색기 비교에 부적합하며, 검색기 비교는 검증셋으로 해야 "
               "한다 — 거기서는 부호가 뒤집혀 dense 성분이 BM25를 크게 앞선다(§2).",
}


def load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validated_source() -> tuple[dict, str, bool]:
    """검증셋 통합 산출물. 본 파일이 아직 없으면 smoke 파일로 대체한다."""
    full = OUT_DIR / "validated_suite.json"
    smoke = OUT_DIR / "validated_suite_smoke.json"
    data = load_json(full)
    if data is not None:
        return data, "output/validated_suite.json", False
    data = load_json(smoke)
    if data is None:
        raise FileNotFoundError(
            "output/validated_suite.json 도 validated_suite_smoke.json 도 없다. "
            "experiment_validated_suite.py를 먼저 실행해야 한다."
        )
    return data, "output/validated_suite_smoke.json", True


# --------------------------------------------------------------------------
# 비교 레코드 생성기
# --------------------------------------------------------------------------


def paired_contrast(
    label: str,
    source: str,
    treatment_label: str,
    treatment: list[int],
    baseline_label: str,
    baseline: list[int],
    note: str = "",
) -> dict[str, Any]:
    """실제 per-query 벡터로 paired bootstrap + exact McNemar."""
    diffs = [float(a) - float(b) for a, b in zip(treatment, baseline)]
    boot = rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERATIONS, seed=SEED)
    mc = rc.exact_mcnemar(treatment, baseline)
    return {
        "label": label,
        "source": source,
        "method": "paired_per_query_bootstrap+exact_mcnemar",
        "n": len(treatment),
        "baseline": {"label": baseline_label, **rc.rate_with_ci(baseline)},
        "treatment": {"label": treatment_label, **rc.rate_with_ci(treatment)},
        "effect_size": {
            "type": "paired_mean_difference_in_recall_at_10",
            "value": round(boot["mean"], 6),
            "percentage_points": round(boot["mean"] * 100, 3),
        },
        "difference_bootstrap_95_ci": boot["ci"],
        "bootstrap_excludes_zero": bool(boot["ci"][0] > 0 or boot["ci"][1] < 0),
        "mcnemar": mc,
        "primary_test": "exact_mcnemar",
        "note": note,
    }


def absolute_only(
    label: str, source: str, name: str, rate: float, n: int, reason: str
) -> dict[str, Any]:
    """per-query 벡터가 저장되지 않은 산출물: 절대율 + 정확 이항구간만."""
    k = int(round(rate * n))
    return {
        "label": label,
        "source": source,
        "method": "absolute_rate_only",
        "n": n,
        "point": {"label": name, "k_recovered_from_rate": k, "rate": rate,
                  "ci95_clopper_pearson": rc.clopper_pearson(k, n)},
        "paired_test_unavailable": reason,
    }


# --------------------------------------------------------------------------
# C. bootstrap 이산 경계 인공물
# --------------------------------------------------------------------------


def bootstrap_boundary_artifact(wins: int, ties: int, losses: int = 0) -> dict[str, Any]:
    """(wins, ties, losses) 구성에서 percentile bootstrap이 0을 포함하게 되는 구조적 이유."""
    n = wins + ties + losses
    diffs = [1.0] * wins + [0.0] * ties + [-1.0] * losses
    p_no_win_drawn = ((n - wins) / n) ** n if n else 1.0
    boot = rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERATIONS, seed=SEED)
    rng = np.random.default_rng(SEED)
    arr = np.asarray(diffs, dtype=float)
    draws = arr[rng.integers(0, n, size=(BOOTSTRAP_ITERATIONS, n))].mean(axis=1)
    mc = rc.exact_mcnemar([1] * wins + [0] * ties + [0] * losses,
                          [0] * wins + [0] * ties + [1] * losses)
    return {
        "configuration": {"n": n, "wins": wins, "ties": ties, "losses": losses},
        "p_no_winning_query_in_a_resample": rc.sig(p_no_win_drawn),
        "formula": f"(({n}-{wins})/{n})^{n}",
        "exceeds_2.5pct_threshold": bool(p_no_win_drawn > 0.025),
        "empirical_fraction_of_resamples_equal_zero": round(float((draws == 0).mean()), 6),
        "bootstrap_mean_diff": boot["mean"],
        "bootstrap_95_ci": boot["ci"],
        "lower_bound_is_structurally_zero": bool(boot["ci"][0] == 0.0),
        "exact_mcnemar": mc,
        "reading": (
            f"승리 질의가 {wins}개뿐이면 크기 {n}의 재표본에 승리가 전혀 포함되지 않을 확률이 "
            f"{p_no_win_drawn:.4f}로 0.025를 넘는다. 따라서 2.5분위수가 구조적으로 0이 되고, "
            f"{wins}승 {losses}패인 어떤 결과도 percentile bootstrap에서는 자동으로 "
            "'CI가 0을 포함'한다. 이는 효과가 없다는 증거가 아니라 표본이 작다는 증거다. "
            f"동일 구성의 exact McNemar 양측 p={mc['p_two_sided_exact']:.4g}이며, 이쪽이 "
            "소표본 이진 짝지음의 primary 검정이다."
        ),
    }


# --------------------------------------------------------------------------
# 요약 생성
# --------------------------------------------------------------------------


def build_summary() -> dict[str, Any]:
    logs = load_json(OUT_DIR / "experiment_logs.json")
    paraphrase = load_json(OUT_DIR / "paraphrase_gap.json")
    retriever = load_json(OUT_DIR / "retriever_compare.json")
    external = load_json(OUT_DIR / "external_retriever.json")
    n13 = load_json(OUT_DIR / "validated_eval.json")
    validated, validated_src, is_smoke = validated_source()

    comparisons: list[dict[str, Any]] = []

    # ---------------------------------------------------- 1. 합성셋 (paired, 실측 벡터)
    n_synthetic = int(logs["test_query_count"])
    hv = logs.get("hit_vectors") or {}
    if "full_text" in hv:
        base = hv["full_text"]["recall@10"]
        for mode in ("minimal_text", "minimal_no_code", "route_only"):
            if mode not in hv:
                continue
            note = "route_only는 퇴화 색인(sanity check)이므로 해석 금지" if mode == "route_only" else ""
            comparisons.append(paired_contrast(
                f"synthetic_{mode}_vs_full_text", "output/experiment_logs.json",
                mode, hv[mode]["recall@10"], "full_text", base, note,
            ))
    else:
        for mode in ("minimal_text", "minimal_no_code"):
            comparisons.append(absolute_only(
                f"synthetic_{mode}_vs_full_text", "output/experiment_logs.json",
                mode, logs["metrics"][mode]["recall@10"], n_synthetic,
                "hit_vectors 미저장 — run_experiments.py 재실행 필요",
            ))

    # ---------------------------------------------------- 2. 자기참조 민감도 (paraphrase gap)
    n_paraphrase = None
    if paraphrase:
        n_paraphrase = int(paraphrase["results"]["minimal_text"]["query_count"])
        pv = paraphrase["results"]["minimal_text"].get("hit_vectors")
        if pv:
            base = pv["0"]["recall@10"]
            for n_removed in (5, 10):
                key = str(n_removed)
                if key not in pv:
                    continue
                comparisons.append(paired_contrast(
                    f"paraphrase_gap_minimal_text_N{n_removed}_vs_N0",
                    "output/paraphrase_gap.json",
                    f"minimal_text_N{n_removed}", pv[key]["recall@10"],
                    "minimal_text_N0", base, "자기참조 의존성 민감도",
                ))
        else:
            by_n = {r["n_removed_high_idf_shared_terms"]: r
                    for r in paraphrase["results"]["minimal_text"]["summary"]}
            for n_removed in (5, 10):
                comparisons.append(absolute_only(
                    f"paraphrase_gap_minimal_text_N{n_removed}_vs_N0",
                    "output/paraphrase_gap.json",
                    f"minimal_text_N{n_removed}", by_n[n_removed]["recall@10"], n_paraphrase,
                    "hit_vectors 미저장 — experiment_paraphrase_gap.py 재실행 필요",
                ))

    # ---------------------------------------------------- 3. 합성 어휘격차 dense vs bm25
    n_retriever = None
    if retriever:
        n_retriever = int(retriever["query_count"])
        rv = retriever["results"].get("hit_vectors")
        if rv and "10" in rv:
            comparisons.append(paired_contrast(
                "synthetic_vocab_gap_N10_dense_vs_bm25", "output/retriever_compare.json",
                "alpha=0.0", rv["10"]["alpha=0.0"], "alpha=1.0", rv["10"]["alpha=1.0"],
                "어휘격차 N=10에서 dense가 BM25를 역전하는가",
            ))
        else:
            s = retriever["results"]["summary"]["10"]
            comparisons.append(absolute_only(
                "synthetic_vocab_gap_N10_dense_vs_bm25", "output/retriever_compare.json",
                "alpha=0.0", s["alpha=0.0"]["recall@10"], n_retriever,
                "hit_vectors 미저장 — experiment_retriever_compare.py 재실행 필요",
            ))

    # ---------------------------------------------------- 4. 외부 모사 후보 라벨셋
    n_external = None
    if external:
        n_external = int(external["query_count"])
        ev = external.get("hit_vectors")
        for alpha in (0.7, 0.5, 0.3, 0.0):
            name = "dense" if alpha == 0.0 else f"hybrid_alpha_{str(alpha).replace('.', '_')}"
            if ev:
                comparisons.append(paired_contrast(
                    f"external_candidate_label_{name}_vs_bm25",
                    "output/external_retriever.json",
                    f"alpha={alpha}", ev[f"alpha={alpha}"], "alpha=1.0", ev["alpha=1.0"],
                    "외부 모사 후보 라벨 기준(추정 라벨) — 해석 주의",
                ))
            else:
                comparisons.append(absolute_only(
                    f"external_candidate_label_{name}_vs_bm25",
                    "output/external_retriever.json",
                    f"alpha={alpha}", external["summary"][f"alpha={alpha}"]["recall@10"],
                    n_external,
                    "hit_vectors 미저장 — experiment_external_retriever.py 재실행 필요",
                ))

    # ---------------------------------------------------- 5. 검증셋 (헤드라인)
    meta = validated["meta"]
    langs = validated["langs"]
    primary_model = meta["primary_model"]
    imode = PRIMARY_INDEX_MODE if PRIMARY_INDEX_MODE in meta["index_modes"] else meta["index_modes"][0]
    hits71 = validated["hit_vectors"][primary_model][imode]

    def subgroup(vec: list[int], lang: str | None) -> list[int]:
        return [h for h, lg in zip(vec, langs) if lang is None or lg == lang]

    validated_family: dict[str, float] = {}
    for lang in (None, "en", "ko"):
        tag = lang or "overall"
        for treat, basel, name in [
            (PRIMARY_RETRIEVER, "BM25", "hybrid_vs_bm25"),
            ("dense", "BM25", "dense_vs_bm25"),
            (PRIMARY_RETRIEVER, "dense", "hybrid_vs_dense"),
        ]:
            label = f"validated71_{name}[{tag}]"
            comp = paired_contrast(
                label, validated_src, treat, subgroup(hits71[treat], lang),
                basel, subgroup(hits71[basel], lang),
                f"색인={imode}, 모델={primary_model}, 언어={tag}",
            )
            comparisons.append(comp)
            validated_family[label] = comp["mcnemar"]["p_two_sided_exact"]
    validated_holm = rc.holm(validated_family)

    # 절대율 표
    validated_rates = {}
    for retr, vec in hits71.items():
        validated_rates[retr] = {
            "overall": rc.rate_with_ci(vec),
            "en": rc.rate_with_ci(subgroup(vec, "en")),
            "ko": rc.rate_with_ci(subgroup(vec, "ko")),
        }

    # ---------------------------------------------------- 6. n=13 → 현행 before/after
    before_after: list[dict[str, Any]] = []
    if n13:
        n13_n = int(n13["meta"]["evaluated_count"])
        for a, name in [(0.5, "hybrid_vs_bm25"), (0.0, "dense_vs_bm25")]:
            old_t = [int(r["by_alpha"][f"alpha={a}"]["hit@10"]) for r in n13["per_query"]]
            old_b = [int(r["by_alpha"]["alpha=1.0"]["hit@10"]) for r in n13["per_query"]]
            old = paired_contrast(f"n13_{name}", "output/validated_eval.json",
                                  f"alpha={a}", old_t, "alpha=1.0", old_b)
            new_key = f"validated71_{name}[overall]"
            new = next(c for c in comparisons if c["label"] == new_key)
            before_after.append({
                "comparison": name,
                "before": {
                    "source": "output/validated_eval.json", "n": n13_n,
                    "treatment_rate": old["treatment"]["rate"],
                    "baseline_rate": old["baseline"]["rate"],
                    "mean_diff": old["effect_size"]["value"],
                    "bootstrap_95_ci": old["difference_bootstrap_95_ci"],
                    "bootstrap_excludes_zero": old["bootstrap_excludes_zero"],
                    "mcnemar_p_two_sided": old["mcnemar"]["p_two_sided_exact"],
                    "wins_losses_ties": [old["mcnemar"]["wins"], old["mcnemar"]["losses"],
                                         old["mcnemar"]["ties"]],
                },
                "after": {
                    "source": validated_src, "n": new["n"],
                    "treatment_rate": new["treatment"]["rate"],
                    "baseline_rate": new["baseline"]["rate"],
                    "mean_diff": new["effect_size"]["value"],
                    "bootstrap_95_ci": new["difference_bootstrap_95_ci"],
                    "bootstrap_excludes_zero": new["bootstrap_excludes_zero"],
                    "mcnemar_p_two_sided": new["mcnemar"]["p_two_sided_exact"],
                    "wins_losses_ties": [new["mcnemar"]["wins"], new["mcnemar"]["losses"],
                                         new["mcnemar"]["ties"]],
                },
            })

    # ---------------------------------------------------- 7. 경계 인공물
    artifacts = {}
    if n13:
        for a, name in [(0.5, "hybrid_vs_bm25"), (0.0, "dense_vs_bm25")]:
            old_t = [int(r["by_alpha"][f"alpha={a}"]["hit@10"]) for r in n13["per_query"]]
            old_b = [int(r["by_alpha"]["alpha=1.0"]["hit@10"]) for r in n13["per_query"]]
            mc = rc.exact_mcnemar(old_t, old_b)
            artifacts[f"n13_{name}"] = bootstrap_boundary_artifact(
                mc["wins"], mc["ties"], mc["losses"])
    # 일반 규칙: 0패일 때, 승리 수 w가 몇 개 이하면 하한이 구조적으로 0인가.
    # P(재표본에 승리 0개) = ((n-w)/n)^n ≈ exp(-w) 이므로 **표본 크기 n이 아니라
    # 승리 개수 w가 결정한다**. exp(-3)=0.0498 > 0.025 > 0.0183 = exp(-4).
    threshold_table = []
    # 현행 검증셋 크기를 표에 포함시킨다(예전에는 71에서 끝나 낡아 보였다).
    for n in sorted({13, 20, 30, 50, 71, meta['n']}):
        max_w = 0
        for w in range(1, n + 1):
            if ((n - w) / n) ** n > 0.025:
                max_w = w
        threshold_table.append({
            "n": n,
            "max_wins_with_structurally_zero_lower_bound": max_w,
            "p_no_win_at_that_w": rc.sig(((n - max_w) / n) ** n) if max_w else None,
            "p_no_win_at_w_plus_1": rc.sig(((n - max_w - 1) / n) ** n) if max_w < n else None,
            "note": f"n={n}, 0패일 때 승리 수가 {max_w}개 이하이면 percentile bootstrap "
                    f"2.5분위수가 구조적으로 0",
        })
    threshold_rule = (
        "P(재표본에 승리 질의가 0개) = ((n-w)/n)^n ≈ exp(-w) 이므로 이 인공물은 "
        "**표본 크기 n이 아니라 승리 개수 w가 결정한다**. exp(-3)=0.0498 > 0.025 > "
        "0.0183=exp(-4) 이므로, 0패인 상황에서 승리가 3개 이하이면 n이 얼마든 "
        "percentile bootstrap의 하한이 0이 되고, 4개 이상이면 하한이 0을 벗어난다. "
        "n=13은 승리가 3개뿐이라 걸렸고, 현행 검증셋은 승리가 그보다 훨씬 많아 걸리지 않는다."
    )

    _n_now = meta["n"]
    dataset_sizes = {
        "synthetic_test_queries": n_synthetic,
        "paraphrase_gap_queries": n_paraphrase,
        "retriever_compare_queries": n_retriever,
        "external_candidate_label_queries": n_external,
        "validated_queries": meta["n"],
        "validated_en_n": meta["n_en"],
        "validated_ko_n": meta["n_ko"],
        "superseded_validated_n13": int(n13["meta"]["evaluated_count"]) if n13 else None,
    }

    return {
        "meta": {
            "task": f"검증셋 n={_n_now} 기준 통계 재집계 (M9/M14-A 정정판)",
            "created_from_existing_json_only": True,
            "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
            "seed": SEED,
            "primary_index_mode": imode,
            "primary_retriever": PRIMARY_RETRIEVER,
            "primary_dense_model": primary_model,
            "validated_source": validated_src,
            "validated_source_is_smoke": is_smoke,
            "source_files": [
                "output/experiment_logs.json",
                "output/paraphrase_gap.json",
                "output/retriever_compare.json",
                "output/external_retriever.json",
                validated_src,
                "output/validated_eval.json (n=13, superseded — 감사 보존용)",
            ],
            "corrections": [
                "삭제: infer_hits() — 반올림된 aggregate rate에서 per-query 벡터를 합성했다.",
                "삭제: bootstrap_diff_ci() — paired 설계에 unpaired 이항 시뮬레이션을 적용했다.",
                "삭제: bootstrap_mean_ci() — 합성 벡터의 이항 재표본. 절대율은 Clopper-Pearson으로 대체.",
                f"헤드라인 표본을 n=13에서 n={_n_now}로 교체. n=13은 docs/statistics_n13_superseded.md에 보존.",
                "소표본 이진 짝지음의 primary 검정을 exact McNemar / Clopper-Pearson으로 변경.",
                "per-query 벡터가 없는 산출물은 추정하지 않고 paired_test_unavailable로 표시.",
            ],
            "notes": [
                "새 검색·임베딩·외부 API 호출은 수행하지 않는다(기존 JSON만 읽는다).",
                "검증셋/외부셋 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 법적 판정이 아니다.",
            ],
        },
        "env": rc.env_meta({"seed": SEED, "bootstrap_iterations": BOOTSTRAP_ITERATIONS}),
        "dataset_sizes": dataset_sizes,
        "validated_recall_at_10": {
            "source": validated_src,
            "index_mode": imode,
            "dense_model": primary_model,
            "rates": validated_rates,
        },
        "validated_holm_within_family": validated_holm,
        "comparisons": comparisons,
        "ranking_determinism_audit": RANKING_DETERMINISM_AUDIT,
        "input_symmetry_audit": INPUT_SYMMETRY_AUDIT,
        "n13_to_current_before_after": before_after,
        "small_sample_bootstrap_artifact": {
            "cases": artifacts,
            "threshold_table": threshold_table,
            "rule": threshold_rule,
        },
    }


# --------------------------------------------------------------------------
# 마크다운
# --------------------------------------------------------------------------


def fmt_ci(ci: list[float]) -> str:
    return f"[{ci[0]:.4f}, {ci[1]:.4f}]"


def markdown(summary: dict[str, Any]) -> str:
    m = summary["meta"]
    ds = summary["dataset_sizes"]
    by_label = {c["label"]: c for c in summary["comparisons"]}
    holm = summary["validated_holm_within_family"]

    L = [
        "# 통계 요약 (검증셋 n=%d 기준)" % ds["validated_queries"],
        "",
        "> **정정 이력.** 이 문서의 이전 판은 검증셋 표본을 **13개**로 적고 hybrid 우위를",
        "> \"경향으로 보고\"했다. 그 판단의 근거였던 95% CI [0.0000, 0.4615]는 아래 §5에서",
        "> 보이는 것처럼 **소표본 bootstrap의 이산 경계 인공물**이었다. 헤드라인 표본은",
        f"> `{m['validated_source']}`의 **n={ds['validated_queries']}**",
        f"> (영어 {ds['validated_en_n']} / 한국어 {ds['validated_ko_n']})로 교체했다.",
        "> n=13 판 수치는 삭제하지 않고 `docs/statistics_n13_superseded.md`에 보존했다.",
        "",
        "> **방법 정정.** 이전 판은 반올림된 aggregate R@10에서 per-query 성공/실패 벡터를",
        "> *합성*한 뒤(`infer_hits`) paired 비교에 **unpaired 이항 시뮬레이션**",
        "> (`bootstrap_diff_ci`)을 적용했다. 두 함수는 삭제했고, 이제 실제 per-query",
        "> `hit_vectors`로 paired bootstrap과 exact McNemar를 계산한다. 벡터가 저장되지",
        "> 않은 산출물은 추정하지 않고 절대율 + Clopper-Pearson만 보고한다.",
        "",
        f"- Bootstrap 반복: {m['bootstrap_iterations']:,} / Seed: {m['seed']}",
        f"- 검증셋 primary 조건: 색인 `{m['primary_index_mode']}`, retriever `{m['primary_retriever']}`, "
        f"dense `{m['primary_dense_model']}`",
        f"- 합성 테스트 쿼리 {ds['synthetic_test_queries']}개 / "
        f"외부 모사 질의 {ds['external_candidate_label_queries']}개",
        "- 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 법적 판정·전문가 검증이 아니다.",
        "",
    ]
    if m["validated_source_is_smoke"]:
        L += [
            "> ⚠ **확인 필요**: 현재 `output/validated_suite.json`(3모델 본실행)이 아직 없어",
            "> 단일 모델 smoke 산출물 `output/validated_suite_smoke.json`을 읽었다. 본실행이",
            "> 끝나면 `python experiment_stats.py`를 다시 실행해 이 문서를 갱신해야 한다.",
            "",
        ]

    # --- 1. 검증셋 절대율
    L += [
        "## 1. 검증셋 R@10 (95% CI = Clopper-Pearson 정확 이항구간)",
        "",
        f"- source: `{summary['validated_recall_at_10']['source']}` / "
        f"색인 `{summary['validated_recall_at_10']['index_mode']}`",
        "",
        "| retriever | 전체 R@10 | 95% CI | 영어 R@10 | 한국어 R@10 |",
        "|---|---:|---|---:|---:|",
    ]
    for retr, r in summary["validated_recall_at_10"]["rates"].items():
        L.append(
            f"| {retr} | {r['overall']['rate']:.4f} | {fmt_ci(r['overall']['ci95'])} | "
            f"{r['en']['rate']:.4f} | {r['ko']['rate']:.4f} |"
        )
    # 이 문장은 예전에 값이 문자열에 박혀 있었다(0.0000 / 45개 중 44개). 표본이 커지면서
    # 실제 값이 0.0275 로 바뀌었는데도 문장은 그대로여서 같은 절의 표와 모순됐다.
    # 이제 표와 같은 출처에서 뽑아 쓴다.
    _ko = summary["validated_recall_at_10"]["rates"]["BM25"]["ko"]["rate"]
    _ns = (summary["validated_recall_at_10"].get("bm25_no_signal_queries")
           or summary["validated_recall_at_10"].get("diagnostics", {}).get("bm25_no_signal_queries"))
    _nstxt = f"(무신호 질의 {_ns}건) " if _ns else ""
    L += [
        "",
        f"> 한국어 BM25 R@10은 **{_ko:.4f}**이다 {_nstxt}— 코퍼스가 100% 영어라 대부분의 한국어",
        "> 질의는 BM25 점수 벡터가 전부 0이다. 이런 질의는 top-10을 만들 수 없으므로 검색 실패로",
        "> 집계한다. 이전 산출물의 0.0222는 전부 0인 벡터를 정렬해 코퍼스 앞머리 10행을 결과로",
        "> 집계한 데서 나온 오류였다.",
        "",
    ]

    # --- 2. 검증셋 비교
    L += [
        "## 2. 검증셋 검색기 비교 (primary = exact McNemar, 보조 = paired bootstrap)",
        "",
        "| 비교 | 언어 | 평균차 | bootstrap 95% CI | 승/패/무 | exact p (양측) | Holm p | 유의 |",
        "|---|---|---:|---|---:|---:|---:|---|",
    ]
    for lang in ("overall", "en", "ko"):
        for name in ("hybrid_vs_bm25", "dense_vs_bm25", "hybrid_vs_dense"):
            key = f"validated71_{name}[{lang}]"
            c = by_label.get(key)
            if not c:
                continue
            h = holm[key]
            mc = c["mcnemar"]
            L.append(
                f"| `{name}` | {lang} | {c['effect_size']['value']:+.4f} | "
                f"{fmt_ci(c['difference_bootstrap_95_ci'])} | "
                f"{mc['wins']}/{mc['losses']}/{mc['ties']} | "
                f"{mc['p_two_sided_exact']:.3g} | {h['p_adjusted']:.3g} | "
                f"{'**예**' if h['significant_at_0.05'] else '아니오'} |"
            )
    L += [
        "",
        "> `hybrid_vs_dense`가 한국어에서 0승 0패인 것은 정상이다. BM25 점수가 항등 0이면",
        "> α<1의 혼합 점수는 dense 점수의 양의 배수이므로 **랭킹이 수학적으로 동일**하다.",
        "> 즉 데이터가 지지하는 진술은 '하이브리드가 필요하다'가 아니라 'dense 성분이 필요하다'다.",
        "",
    ]

    # --- 3. before/after
    if summary["n13_to_current_before_after"]:
        L += [
            "## 3. n=13 → n=71 before / after (조용한 덮어쓰기 방지)",
            "",
            "| 비교 | 표본 | 처리 R@10 | 기준 R@10 | 평균차 | bootstrap 95% CI | 승/패/무 | exact p |",
            "|---|---:|---:|---:|---:|---|---:|---:|",
        ]
        for row in summary["n13_to_current_before_after"]:
            for tag in ("before", "after"):
                d = row[tag]
                w, l, t = d["wins_losses_ties"]
                L.append(
                    f"| `{row['comparison']}` ({tag}) | {d['n']} | {d['treatment_rate']:.4f} | "
                    f"{d['baseline_rate']:.4f} | {d['mean_diff']:+.4f} | "
                    f"{fmt_ci(d['bootstrap_95_ci'])} | {w}/{l}/{t} | "
                    f"{d['mcnemar_p_two_sided']:.3g} |"
                )
        L += ["", "> before 행은 `output/validated_eval.json`(n=13), after 행은 "
                  f"`{m['validated_source']}`(n={ds['validated_queries']})이다.", ""]

    # --- 4. 기타 비교
    L += [
        "## 4. 그 밖의 비교",
        "",
        "| 비교 | source | 방법 | 기준 R@10 | 처리 R@10 | 평균차 | 차이 95% CI | 승/패/무 | exact p |",
        "|---|---|---|---:|---:|---:|---|---:|---:|",
    ]
    for c in summary["comparisons"]:
        if c["label"].startswith("validated71_"):
            continue
        src = c["source"].replace("output/", "")
        if c["method"] == "absolute_rate_only":
            p = c["point"]
            L.append(
                f"| `{c['label']}` | `{src}` | 절대율만 | - | "
                f"{p['rate']:.4f} {fmt_ci(p['ci95_clopper_pearson'])} | - | "
                f"짝지음 불가 | - | - |"
            )
            continue
        mc = c["mcnemar"]
        L.append(
            f"| `{c['label']}` | `{src}` | paired | "
            f"{c['baseline']['rate']:.4f} {fmt_ci(c['baseline']['ci95'])} | "
            f"{c['treatment']['rate']:.4f} {fmt_ci(c['treatment']['ci95'])} | "
            f"{c['effect_size']['value']:+.4f} | "
            f"{fmt_ci(c['difference_bootstrap_95_ci'])} | "
            f"{mc['wins']}/{mc['losses']}/{mc['ties']} | {mc['p_two_sided_exact']:.3g} |"
        )
    unavailable = [c for c in summary["comparisons"] if c["method"] == "absolute_rate_only"]
    if unavailable:
        L += ["", "> '짝지음 불가' 행은 해당 산출물에 per-query `hit_vectors`가 저장되지 않아",
              "> paired 검정을 계산할 수 없는 경우다. **이전 판은 여기서 aggregate rate로부터",
              "> 가짜 hit 벡터를 만들어 CI를 계산했다.** 그 추정은 제거했고, 해당 스크립트를",
              "> 재실행해 벡터를 저장하는 것이 정상 경로다:", ""]
        for c in unavailable:
            L.append(f"> - `{c['label']}`: {c['paired_test_unavailable']}")
        L.append("")
    else:
        L.append("")

    # --- 5. bootstrap 경계 인공물
    L += [
        "## 5. 소표본 bootstrap의 이산 경계 인공물 (n=13 '비유의' 판정의 정체)",
        "",
        "이전 판은 `validated_hybrid_alpha_0_5_vs_bm25`의 95% CI가 [0.0000, 0.4615]로",
        "0을 포함한다는 이유로 hybrid 우위를 \"경향\"으로만 보고했다. 그 CI의 하한 0은",
        "**데이터가 아니라 재표본 공간의 이산성이 만든 값**이다.",
        "",
    ]
    for key, art in summary["small_sample_bootstrap_artifact"]["cases"].items():
        cfg = art["configuration"]
        L += [
            f"### `{key}` — {cfg['wins']}승 {cfg['losses']}패 {cfg['ties']}무 (n={cfg['n']})",
            "",
            f"- 재표본에 승리 질의가 하나도 안 뽑힐 확률 = {art['formula']} = "
            f"**{art['p_no_winning_query_in_a_resample']:.4f}**",
            f"- 0.025 초과? **{'예' if art['exceeds_2.5pct_threshold'] else '아니오'}** → "
            f"2.5분위수가 구조적으로 0",
            f"- 실측: {m['bootstrap_iterations']:,}회 재표본 중 평균차가 정확히 0인 비율 = "
            f"{art['empirical_fraction_of_resamples_equal_zero']:.4f}",
            f"- percentile bootstrap 95% CI = {fmt_ci(art['bootstrap_95_ci'])} "
            f"(하한이 구조적으로 0: {'예' if art['lower_bound_is_structurally_zero'] else '아니오'})",
            f"- 같은 구성의 exact McNemar 양측 p = "
            f"**{art['exact_mcnemar']['p_two_sided_exact']:.4g}**",
            "",
        ]
    art_block = summary["small_sample_bootstrap_artifact"]
    L += [
        "**결론.** n=13에서 3승 0패는 percentile bootstrap으로는 *원리상* 유의해질 수 없다.",
        "동시에 exact McNemar p=0.25이므로 n=13은 **실제로 검정력이 부족**했다. 즉 이전 판의",
        "'경향으로 보고'는 결론 자체는 옳았지만 근거로 든 통계량이 잘못됐다. 소표본 이진",
        "짝지음에서는 percentile bootstrap 대신 **exact McNemar(짝지음 차이) /",
        "Clopper-Pearson(절대율)을 primary로 쓴다.**",
        "",
        "### 일반 규칙 — 이것은 n이 아니라 '승리 개수'가 결정한다",
        "",
        f"{art_block['rule']}",
        "",
        "| n | 0패일 때 하한이 구조적으로 0이 되는 최대 승리 수 w | 그 w에서 P(승리 0개) | w+1에서 P(승리 0개) |",
        "|---:|---:|---:|---:|",
    ]
    for row in art_block["threshold_table"]:
        L.append(f"| {row['n']} | {row['max_wins_with_structurally_zero_lower_bound']} | "
                 f"{row['p_no_win_at_that_w']:.4f} | {row['p_no_win_at_w_plus_1']:.4f} |")
    L += [
        "",
        "> 표본을 13개에서 71개로 늘린 것 자체가 문제를 푼 게 아니다. **승리 질의가 3개에서",
        "> 30개로 늘어난 것**이 풀었다. 표본만 늘리고 승리가 3개에 머물렀다면 CI 하한은",
        "> 여전히 0이었을 것이다.",
        "",
    ]

    # --- 6. 결정론적 랭킹 전환 감사
    rda = summary["ranking_determinism_audit"]
    L += [
        "## 6. 결정론적 랭킹 전환에 따른 수치 변동 (조용한 덮어쓰기 방지)",
        "",
        f"- 대상: `{rda['source_script']}`",
        f"- 변경: {rda['change']}",
        "",
        "**논문 주장 1의 헤드라인 R@10은 전부 불변이다:**",
        "",
        "| 수치 | 값 |",
        "|---|---:|",
    ]
    for k, v in rda["headline_claim1_unchanged"].items():
        L.append(f"| `{k}` | {v:.4f} (불변) |")
    L += [
        "",
        "바뀐 칸은 다음이 전부다(동점이 흔한 R@1·R@5에 집중).",
        "",
        "| 조건 | N | 지표 | before | after | Δ |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for c in rda["changed_cells"]:
        L.append(f"| {c['mode']} | {c['N']} | {c['metric']} | {c['before']:.4f} | "
                 f"{c['after']:.4f} | {c['after'] - c['before']:+.4f} |")
    L += ["", f"> {rda['reading']}", ""]

    # --- 6b. 입력 비대칭 정정 감사
    isa = summary["input_symmetry_audit"]
    L += [
        "### 6-2. 검색기 비교의 입력 비대칭 정정 (before / after)",
        "",
        f"- 대상: `{isa['source_script']}`",
        f"- 변경: {isa['change']}",
        f"- 지표: {isa['metric']}",
        "",
        "| 어휘격차 N | alpha | before | after | Δ |",
        "|---:|---:|---:|---:|---:|",
    ]
    for r in isa["rows"]:
        L.append(f"| {r['N']} | {r['alpha']:.1f} | {r['before']:.4f} | {r['after']:.4f} | "
                 f"{r['after'] - r['before']:+.4f} |")
    L += ["", f"> {isa['reading']}", ""]

    # --- 7. 가드레일
    L += [
        "## 7. 해석 가드레일",
        "",
        "- 합성셋 R@10(full_text 0.9968 / minimal_text 0.9792)은 **자기참조 재검색** 조건의",
        "  값이므로 단독 헤드라인으로 쓰지 않는다. 고-IDF 공유토큰 5개 제거 시 0.7596,",
        "  10개 제거 시 0.4407로 붕괴한다(`output/paraphrase_gap.md`).",
        f"- 검증셋의 한국어 BM25 R@10은 {summary['validated_recall_at_10']['rates']['BM25']['ko']['rate']:.4f}"
        "이다. 어휘 교집합이 0인 질의는 top-10을 만들 수",
        "  없으며, 이를 '코퍼스 앞머리 10행'으로 채워 집계하면 안 된다.",
        "- 외부 모사 질의의 후보 라벨은 연구자 예비 추정값이며 법적 판정이 아니다.",
        "- `route_only`는 고유 색인문서가 소수인 퇴화 조건이므로 소수 4자리 수치에 해석을",
        "  부여하지 않는다.",
        "- 본 결과는 전부 후보검색 통계이며 전략물자 해당 여부 판정을 의미하지 않는다.",
        "",
    ]
    return "\n".join(L)


def superseded_markdown(summary: dict[str, Any]) -> str:
    """n=13 판 수치 보존 문서 (감사 가능성 유지)."""
    n13 = load_json(OUT_DIR / "validated_eval.json")
    ds = summary["dataset_sizes"]
    L = [
        "# [SUPERSEDED] n=13 검증셋 통계 (보존용, 인용 금지)",
        "",
        "> ## ⚠ 경고 — 이 문서는 대체되었다",
        "> ",
        "> 이 문서는 `docs/statistics.md`의 **이전 판**에 실렸던 n=13 수치를 감사 가능성을",
        "> 위해 보존한 것이다. **논문·발표·요약에 인용하지 마라.** 현행 수치는",
        f"> `docs/statistics.md`(n={ds['validated_queries']})에 있다.",
        "> ",
        "> 이 판이 대체된 이유:",
        "> ",
        "> 1. **표본.** 검증셋 표본을 13개로 적었다. 역생성 슬라이스 병합 후 표본은",
        f">    n={ds['validated_queries']}(영어 {ds['validated_en_n']} / 한국어 {ds['validated_ko_n']})이다.",
        "> 2. **가짜 hit 벡터.** aggregate R@10을 반올림해 `[1]*k+[0]*(n-k)` 벡터를 합성했고,",
        ">    paired 설계에 unpaired 이항 시뮬레이션을 적용했다.",
        "> 3. **경계 인공물 오독.** 95% CI [0.0000, 0.4615]의 하한 0은 데이터가 아니라",
        ">    재표본 공간의 이산성 때문이다(`docs/statistics.md` §5).",
        "> 4. **BM25 한국어 R@10.** 확장셋(n=71) 산출물에는 0.0222로 적혀 있었으나 실제",
        ">    값은 0.0000이다. 점수 벡터가 전부 0인 질의(한국어 45개 중 44개)에 코퍼스",
        ">    앞머리 10행을 결과로 집계한 결과였다.",
        "",
        "## 보존된 n=13 수치",
        "",
        "> 아래 표는 **정정 전 코드로 산출된 값 그대로**다(랭킹 결정론화·무신호 처리 이전).",
        "> 정정된 코드로 다시 계산하려면 `python evaluate_validated_queries.py`를 실행하면",
        "> 되지만, 이 문서는 '당시 무엇이 보고됐는가'를 보존하는 것이 목적이므로 갱신하지",
        "> 않는다.",
        "",
    ]
    if not n13:
        L += ["`output/validated_eval.json`이 없어 수치를 복원할 수 없다. **확인 필요**.", ""]
        return "\n".join(L)

    L += [
        f"- source: `output/validated_eval.json` (평가 {n13['meta']['evaluated_count']}개 / "
        f"제외 {n13['meta']['excluded_count']}개)",
        f"- EN n={n13['summary']['alpha=1.0']['en_n']}, KO n={n13['summary']['alpha=1.0']['ko_n']}",
        "",
        "| alpha | retriever | Overall R@10 | EN R@10 | KO R@10 |",
        "|---:|---|---:|---:|---:|",
    ]
    for a in n13["meta"]["alphas"]:
        r = n13["summary"][f"alpha={a}"]
        nm = {1.0: "BM25", 0.0: "Dense"}.get(a, "Hybrid")
        L.append(f"| {a:.1f} | {nm} | {r['recall@10']:.4f} | "
                 f"{r['en_recall@10']:.4f} | {r['ko_recall@10']:.4f} |")

    L += ["", "## 대체된 문장 (원문 그대로 보존)", "",
          "> 검증셋은 13개 소표본이므로 hybrid 우위는 경향으로 보고하고 표본 확대 필요성을 함께 적는다.",
          "",
          "## before / after 대조", "",
          "| 비교 | n=13 평균차 | n=13 bootstrap CI | n=13 exact p | "
          f"n={ds['validated_queries']} 평균차 | n={ds['validated_queries']} bootstrap CI | "
          f"n={ds['validated_queries']} exact p |",
          "|---|---:|---|---:|---:|---|---:|"]
    for row in summary["n13_to_current_before_after"]:
        b, a = row["before"], row["after"]
        L.append(
            f"| `{row['comparison']}` | {b['mean_diff']:+.4f} | {fmt_ci(b['bootstrap_95_ci'])} | "
            f"{b['mcnemar_p_two_sided']:.3g} | {a['mean_diff']:+.4f} | "
            f"{fmt_ci(a['bootstrap_95_ci'])} | {a['mcnemar_p_two_sided']:.3g} |"
        )
    L += ["", "> n=13 판의 CI는 이 문서 상단 경고 3번의 이산 경계 인공물에 해당한다.", ""]
    return "\n".join(L)


def main() -> None:
    summary = build_summary()
    STATS_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    STATS_MD.write_text(markdown(summary), encoding="utf-8")
    SUPERSEDED_MD.write_text(superseded_markdown(summary), encoding="utf-8")
    print(json.dumps({
        "created": [str(STATS_JSON), str(STATS_MD), str(SUPERSEDED_MD)],
        "validated_source": summary["meta"]["validated_source"],
        "validated_source_is_smoke": summary["meta"]["validated_source_is_smoke"],
        "validated_n": summary["dataset_sizes"]["validated_queries"],
        "paired_test_unavailable": [
            c["label"] for c in summary["comparisons"]
            if c["method"] == "absolute_rate_only"
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
