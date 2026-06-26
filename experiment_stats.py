#!/usr/bin/env python3
"""Create TASK F bootstrap statistics from existing output/*.json files only.

This script does not run retrieval, embeddings, reranking, or any external API.
It reads prior JSON artifacts, computes bootstrap confidence intervals from
stored per-query hits where available, and reconstructs Bernoulli hit vectors
from aggregate counts where per-query hits were not stored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"
DOCS_DIR = ROOT / "docs"
OUT_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)

STATS_JSON = OUT_DIR / "stats_summary.json"
STATS_MD = DOCS_DIR / "statistics.md"

BOOTSTRAP_ITERATIONS = 20000
SEED = 20260626


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def bootstrap_mean_ci(values: list[float], rng: np.random.Generator) -> list[float]:
    n = len(values)
    p = float(sum(values) / n)
    draws = rng.binomial(n, p, BOOTSTRAP_ITERATIONS) / n
    return [round(float(np.quantile(draws, 0.025)), 6), round(float(np.quantile(draws, 0.975)), 6)]


def bootstrap_diff_ci(a: list[float], b: list[float], rng: np.random.Generator) -> list[float]:
    n_a, n_b = len(a), len(b)
    p_a = float(sum(a) / n_a)
    p_b = float(sum(b) / n_b)
    draws = rng.binomial(n_a, p_a, BOOTSTRAP_ITERATIONS) / n_a
    draws -= rng.binomial(n_b, p_b, BOOTSTRAP_ITERATIONS) / n_b
    return [round(float(np.quantile(draws, 0.025)), 6), round(float(np.quantile(draws, 0.975)), 6)]


def bootstrap_paired_diff_ci(diffs: list[float], rng: np.random.Generator) -> list[float]:
    n = len(diffs)
    arr = np.asarray(diffs, dtype=float)
    idx = rng.integers(0, n, size=(BOOTSTRAP_ITERATIONS, n))
    draws = arr[idx].mean(axis=1)
    return [round(float(np.quantile(draws, 0.025)), 6), round(float(np.quantile(draws, 0.975)), 6)]


def infer_hits(rate: float, n: int) -> tuple[int, list[float]]:
    successes = int(round(rate * n))
    successes = max(0, min(n, successes))
    return successes, [1.0] * successes + [0.0] * (n - successes)


def aggregate_comparison(
    label: str,
    treatment_label: str,
    treatment_rate: float,
    baseline_label: str,
    baseline_rate: float,
    n: int,
    rng: np.random.Generator,
    source: str,
    existing_p_value: float | None = None,
) -> dict[str, Any]:
    treatment_successes, treatment_hits = infer_hits(treatment_rate, n)
    baseline_successes, baseline_hits = infer_hits(baseline_rate, n)
    diff = (treatment_successes - baseline_successes) / n
    out: dict[str, Any] = {
        "label": label,
        "source": source,
        "method": "aggregate_binary_bootstrap_from_json_rate",
        "n": n,
        "baseline": {
            "label": baseline_label,
            "point_estimate": baseline_rate,
            "inferred_successes": baseline_successes,
            "bootstrap_95_ci": bootstrap_mean_ci(baseline_hits, rng),
        },
        "treatment": {
            "label": treatment_label,
            "point_estimate": treatment_rate,
            "inferred_successes": treatment_successes,
            "bootstrap_95_ci": bootstrap_mean_ci(treatment_hits, rng),
        },
        "effect_size": {
            "type": "mean_difference_in_recall_at_10",
            "value": round(diff, 6),
            "percentage_points": round(diff * 100, 3),
        },
        "difference_bootstrap_95_ci": bootstrap_diff_ci(treatment_hits, baseline_hits, rng),
    }
    if existing_p_value is not None:
        out["existing_permutation_p_value"] = existing_p_value
    return out


def paired_validated_comparison(
    label: str,
    treatment_alpha: str,
    baseline_alpha: str,
    validated: dict,
    rng: np.random.Generator,
) -> dict[str, Any]:
    rows = validated["per_query"]
    treatment_hits = [float(row["by_alpha"][treatment_alpha]["hit@10"]) for row in rows]
    baseline_hits = [float(row["by_alpha"][baseline_alpha]["hit@10"]) for row in rows]
    diffs = [a - b for a, b in zip(treatment_hits, baseline_hits)]
    wins = sum(1 for d in diffs if d > 0)
    losses = sum(1 for d in diffs if d < 0)
    no_change = sum(1 for d in diffs if d == 0)
    n = len(diffs)
    mean_diff = sum(diffs) / n
    return {
        "label": label,
        "source": "output/validated_eval.json",
        "method": "paired_per_query_bootstrap",
        "n": n,
        "baseline": {
            "label": baseline_alpha,
            "point_estimate": validated["summary"][baseline_alpha]["recall@10"],
            "bootstrap_95_ci": bootstrap_mean_ci(baseline_hits, rng),
        },
        "treatment": {
            "label": treatment_alpha,
            "point_estimate": validated["summary"][treatment_alpha]["recall@10"],
            "bootstrap_95_ci": bootstrap_mean_ci(treatment_hits, rng),
        },
        "effect_size": {
            "type": "paired_mean_difference_in_recall_at_10",
            "value": round(mean_diff, 6),
            "percentage_points": round(mean_diff * 100, 3),
            "wins": wins,
            "losses": losses,
            "no_change": no_change,
        },
        "difference_bootstrap_95_ci": bootstrap_paired_diff_ci(diffs, rng),
    }


def alpha_summary(
    source: str,
    summary: dict[str, Any],
    alphas: list[float],
    n_overall: int,
    n_en: int | None,
    n_ko: int | None,
) -> dict[str, Any]:
    rows = []
    for alpha in alphas:
        key = f"alpha={alpha}"
        metrics = summary[key]
        rows.append(
            {
                "alpha": alpha,
                "label": "BM25" if alpha == 1.0 else "Dense" if alpha == 0.0 else "Hybrid",
                "overall_n": n_overall,
                "en_n": n_en,
                "ko_n": n_ko,
                "recall@10": metrics["recall@10"],
                "en_recall@10": metrics["en_recall@10"],
                "ko_recall@10": metrics["ko_recall@10"],
            }
        )
    return {"source": source, "rows": rows}


def build_summary() -> dict[str, Any]:
    rng = np.random.default_rng(SEED)
    logs = load_json(OUT_DIR / "experiment_logs.json")
    paraphrase = load_json(OUT_DIR / "paraphrase_gap.json")
    retriever = load_json(OUT_DIR / "retriever_compare.json")
    external = load_json(OUT_DIR / "external_retriever.json")
    validated = load_json(OUT_DIR / "validated_eval.json")

    n_synthetic = int(logs["test_query_count"])
    n_external = int(external["query_count"])
    n_validated = int(validated["meta"]["evaluated_count"])

    comparisons: list[dict[str, Any]] = []
    comparisons.append(
        aggregate_comparison(
            "synthetic_minimal_text_vs_full_text",
            "minimal_text",
            logs["metrics"]["minimal_text"]["recall@10"],
            "full_text",
            logs["metrics"]["full_text"]["recall@10"],
            n_synthetic,
            rng,
            "output/experiment_logs.json",
            logs["statistical_tests"]["minimal_text_vs_full_text"]["p_value"],
        )
    )
    comparisons.append(
        aggregate_comparison(
            "synthetic_minimal_no_code_vs_full_text",
            "minimal_no_code",
            logs["metrics"]["minimal_no_code"]["recall@10"],
            "full_text",
            logs["metrics"]["full_text"]["recall@10"],
            n_synthetic,
            rng,
            "output/experiment_logs.json",
            logs["statistical_tests"]["minimal_no_code_vs_full_text"]["p_value"],
        )
    )
    comparisons.append(
        aggregate_comparison(
            "synthetic_route_only_vs_full_text",
            "route_only",
            logs["metrics"]["route_only"]["recall@10"],
            "full_text",
            logs["metrics"]["full_text"]["recall@10"],
            n_synthetic,
            rng,
            "output/experiment_logs.json",
            logs["statistical_tests"]["route_only_vs_full_text"]["p_value"],
        )
    )

    minimal_rows = paraphrase["results"]["minimal_text"]["summary"]
    minimal_by_n = {r["n_removed_high_idf_shared_terms"]: r for r in minimal_rows}
    comparisons.append(
        aggregate_comparison(
            "paraphrase_gap_minimal_text_N5_vs_N0",
            "minimal_text_N5",
            minimal_by_n[5]["recall@10"],
            "minimal_text_N0",
            minimal_by_n[0]["recall@10"],
            int(paraphrase["results"]["minimal_text"]["query_count"]),
            rng,
            "output/paraphrase_gap.json",
        )
    )
    comparisons.append(
        aggregate_comparison(
            "paraphrase_gap_minimal_text_N10_vs_N0",
            "minimal_text_N10",
            minimal_by_n[10]["recall@10"],
            "minimal_text_N0",
            minimal_by_n[0]["recall@10"],
            int(paraphrase["results"]["minimal_text"]["query_count"]),
            rng,
            "output/paraphrase_gap.json",
        )
    )

    synth_n10 = retriever["results"]["summary"]["10"]
    comparisons.append(
        aggregate_comparison(
            "synthetic_vocab_gap_N10_dense_vs_bm25",
            "alpha=0.0",
            synth_n10["alpha=0.0"]["recall@10"],
            "alpha=1.0",
            synth_n10["alpha=1.0"]["recall@10"],
            int(retriever["query_count"]),
            rng,
            "output/retriever_compare.json",
        )
    )

    for alpha in [0.7, 0.5, 0.3, 0.0]:
        label = "dense" if alpha == 0.0 else f"hybrid_alpha_{str(alpha).replace('.', '_')}"
        comparisons.append(
            aggregate_comparison(
                f"external_candidate_label_{label}_vs_bm25",
                f"alpha={alpha}",
                external["summary"][f"alpha={alpha}"]["recall@10"],
                "alpha=1.0",
                external["summary"]["alpha=1.0"]["recall@10"],
                n_external,
                rng,
                "output/external_retriever.json",
            )
        )

    for alpha in [0.7, 0.5, 0.3, 0.0]:
        label = "dense" if alpha == 0.0 else f"hybrid_alpha_{str(alpha).replace('.', '_')}"
        comparisons.append(paired_validated_comparison(f"validated_{label}_vs_bm25", f"alpha={alpha}", "alpha=1.0", validated, rng))
    comparisons.append(paired_validated_comparison("validated_hybrid_alpha_0_5_vs_dense", "alpha=0.5", "alpha=0.0", validated, rng))

    return {
        "meta": {
            "task": "TASK F statistics",
            "created_from_existing_json_only": True,
            "bootstrap_iterations": BOOTSTRAP_ITERATIONS,
            "seed": SEED,
            "source_files": [
                "output/experiment_logs.json",
                "output/paraphrase_gap.json",
                "output/retriever_compare.json",
                "output/external_retriever.json",
                "output/validated_eval.json",
            ],
            "notes": [
                "No new retrieval, embedding, reranking, or external API calls are run.",
                "For aggregate-only artifacts, bootstrap vectors are reconstructed from JSON rates and evaluation counts.",
                "For validated_eval.json, paired bootstrap uses stored per-query hit@10 values.",
                "External candidate labels and validated corpus-text labels are not legal determinations.",
            ],
        },
        "dataset_sizes": {
            "synthetic_test_queries": n_synthetic,
            "external_candidate_label_queries": n_external,
            "validated_evaluated_queries": n_validated,
            "validated_ko_n": validated["summary"]["alpha=1.0"]["ko_n"],
            "validated_en_n": validated["summary"]["alpha=1.0"]["en_n"],
        },
        "alpha_summaries": {
            "external_retriever": alpha_summary(
                "output/external_retriever.json",
                external["summary"],
                external["alphas"],
                n_external,
                None,
                None,
            ),
            "validated_eval": alpha_summary(
                "output/validated_eval.json",
                validated["summary"],
                validated["meta"]["alphas"],
                n_validated,
                validated["summary"]["alpha=1.0"]["en_n"],
                validated["summary"]["alpha=1.0"]["ko_n"],
            ),
        },
        "comparisons": comparisons,
    }


def fmt_ci(ci: list[float]) -> str:
    return f"[{ci[0]:.4f}, {ci[1]:.4f}]"


def markdown(summary: dict[str, Any]) -> str:
    by_label = {c["label"]: c for c in summary["comparisons"]}
    rows = [
        "synthetic_minimal_text_vs_full_text",
        "synthetic_minimal_no_code_vs_full_text",
        "paraphrase_gap_minimal_text_N5_vs_N0",
        "paraphrase_gap_minimal_text_N10_vs_N0",
        "external_candidate_label_hybrid_alpha_0_7_vs_bm25",
        "external_candidate_label_hybrid_alpha_0_5_vs_bm25",
        "external_candidate_label_hybrid_alpha_0_3_vs_bm25",
        "external_candidate_label_dense_vs_bm25",
        "validated_hybrid_alpha_0_7_vs_bm25",
        "validated_hybrid_alpha_0_5_vs_bm25",
        "validated_hybrid_alpha_0_3_vs_bm25",
        "validated_dense_vs_bm25",
        "validated_hybrid_alpha_0_5_vs_dense",
    ]
    lines = [
        "# TASK F Statistics",
        "",
        "이 문서는 기존 `output/*.json`만 읽어 만든 통계 보강 결과다. 새 검색 실험, 임베딩 계산, 외부 API 호출은 수행하지 않았다.",
        "",
        f"- Bootstrap 반복: {summary['meta']['bootstrap_iterations']:,}",
        f"- Seed: {summary['meta']['seed']}",
        f"- 합성 테스트 쿼리: {summary['dataset_sizes']['synthetic_test_queries']}개",
        f"- 외부 모사 질의: {summary['dataset_sizes']['external_candidate_label_queries']}개",
        f"- 검증셋 평가 표본: {summary['dataset_sizes']['validated_evaluated_queries']}개 "
        f"(EN {summary['dataset_sizes']['validated_en_n']}, KO {summary['dataset_sizes']['validated_ko_n']})",
        "",
        "## 방법",
        "",
        "- 집계값만 저장된 파일은 JSON의 R@10과 표본 수에서 성공/실패 벡터를 재구성해 bootstrap CI를 계산했다.",
        "- `output/validated_eval.json`은 질의별 hit@10이 저장되어 있어 paired bootstrap으로 비교했다.",
        "- 효과크기는 R@10 평균차로 보고했다.",
        "- 외부 후보 라벨 및 검증셋 라벨은 후보검색 평가용 카테고리 라벨이며 법적 판정이나 전문가 검증 결과가 아니다.",
        "",
        "## Alpha별 원천 수치",
        "",
        "### 외부 모사 후보 라벨셋",
        "",
        f"- source: `{summary['alpha_summaries']['external_retriever']['source']}`",
        f"- overall n={summary['dataset_sizes']['external_candidate_label_queries']} (JSON에 EN/KO n은 별도 저장되지 않아 R@10만 그대로 표시)",
        "",
        "| alpha | retriever | Overall R@10 | EN R@10 | KO R@10 |",
        "|---:|---|---:|---:|---:|",
    ]
    for row in summary["alpha_summaries"]["external_retriever"]["rows"]:
        lines.append(
            f"| {row['alpha']:.1f} | {row['label']} | {row['recall@10']:.4f} | "
            f"{row['en_recall@10']:.4f} | {row['ko_recall@10']:.4f} |"
        )
    lines += [
        "",
        "### 검증셋",
        "",
        f"- source: `{summary['alpha_summaries']['validated_eval']['source']}`",
        f"- overall n={summary['dataset_sizes']['validated_evaluated_queries']}, "
        f"EN n={summary['dataset_sizes']['validated_en_n']}, KO n={summary['dataset_sizes']['validated_ko_n']}",
        "",
        "| alpha | retriever | Overall R@10 | EN R@10 | KO R@10 |",
        "|---:|---|---:|---:|---:|",
    ]
    for row in summary["alpha_summaries"]["validated_eval"]["rows"]:
        lines.append(
            f"| {row['alpha']:.1f} | {row['label']} | {row['recall@10']:.4f} | "
            f"{row['en_recall@10']:.4f} | {row['ko_recall@10']:.4f} |"
        )
    lines += [
        "",
        "## 주요 비교",
        "",
        "| 비교 | 기준 R@10 (95% CI) | 처리 R@10 (95% CI) | 효과크기: 평균차 | 차이 95% CI | 비고 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    note_by_label = {
        "synthetic_minimal_text_vs_full_text": "집계 재구성, 기존 permutation p 포함",
        "synthetic_minimal_no_code_vs_full_text": "집계 재구성, 기존 permutation p 포함",
        "paraphrase_gap_minimal_text_N5_vs_N0": "자기참조 의존성 민감도",
        "paraphrase_gap_minimal_text_N10_vs_N0": "자기참조 의존성 민감도",
        "external_candidate_label_hybrid_alpha_0_7_vs_bm25": "외부 모사 후보 라벨 기준, 해석 주의",
        "external_candidate_label_hybrid_alpha_0_5_vs_bm25": "외부 모사 후보 라벨 기준, 해석 주의",
        "external_candidate_label_hybrid_alpha_0_3_vs_bm25": "외부 모사 후보 라벨 기준, 해석 주의",
        "external_candidate_label_dense_vs_bm25": "외부 모사 후보 라벨 기준, 해석 주의",
        "validated_hybrid_alpha_0_7_vs_bm25": "paired bootstrap",
        "validated_hybrid_alpha_0_5_vs_bm25": "paired bootstrap",
        "validated_hybrid_alpha_0_3_vs_bm25": "paired bootstrap",
        "validated_dense_vs_bm25": "paired bootstrap",
        "validated_hybrid_alpha_0_5_vs_dense": "paired bootstrap",
    }
    for key in rows:
        comp = by_label[key]
        base = comp["baseline"]
        treatment = comp["treatment"]
        effect = comp["effect_size"]
        note = note_by_label[key]
        if "existing_permutation_p_value" in comp:
            note += f"; p={comp['existing_permutation_p_value']:.4g}"
        if comp["method"] == "paired_per_query_bootstrap":
            note += f"; wins/losses/no-change={effect['wins']}/{effect['losses']}/{effect['no_change']}"
        lines.append(
            f"| `{key}` | {base['point_estimate']:.4f} {fmt_ci(base['bootstrap_95_ci'])} | "
            f"{treatment['point_estimate']:.4f} {fmt_ci(treatment['bootstrap_95_ci'])} | "
            f"{effect['value']:.4f} ({effect['percentage_points']:+.2f}pp) | "
            f"{fmt_ci(comp['difference_bootstrap_95_ci'])} | {note} |"
        )
    lines += [
        "",
        "## 해석 가드레일",
        "",
        "- 합성 R@10 0.9792는 자기참조 재검색 조건에서 나온 값이므로 단독 헤드라인으로 쓰지 않는다.",
        "- 외부 모사 질의의 후보 라벨은 평가용 라벨이며 법적 판정으로 해석하지 않는다.",
        "- 검증셋은 13개 소표본이므로 hybrid 우위는 경향으로 보고하고 표본 확대 필요성을 함께 적는다.",
        "- 본 결과는 후보검색 통계이며 전략물자 해당 여부 판정을 의미하지 않는다.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    summary = build_summary()
    STATS_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    STATS_MD.write_text(markdown(summary), encoding="utf-8")
    print(json.dumps({"created": [str(STATS_JSON), str(STATS_MD)]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
