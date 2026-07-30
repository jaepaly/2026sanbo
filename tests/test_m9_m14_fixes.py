#!/usr/bin/env python3
"""M9 / M14 정정 사항 검증.

임베딩을 내려받지 않고(=dense 모델 로드 없이) 확인 가능한 것만 검사한다.
`sentence_transformers` import는 각 스크립트의 함수 안에 있으므로 모듈 import는
모델 다운로드를 유발하지 않는다.

Run: python tests/test_m9_m14_fixes.py
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import retrieval_core as rc  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(f"{name} {detail}")


def called_attrs(path: Path) -> set[str]:
    """실제로 *호출되는* 속성 이름 집합.

    소스를 문자열로 grep 하면 정정 내역을 설명한 docstring("np.argsort를 제거했다")
    까지 걸린다. AST로 호출 노드만 본다.
    """
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                names.add(func.attr)
            elif isinstance(func, ast.Name):
                names.add(func.id)
    return names


# ------------------------------------------------------------------ A. 가짜 hit 재구성 제거


def test_no_fake_hit_reconstruction() -> None:
    print("[A] 가짜 hit 벡터 재구성 제거")
    import experiment_stats as st

    for gone in ("infer_hits", "bootstrap_diff_ci", "bootstrap_mean_ci"):
        check(f"{gone}() 삭제됨", not hasattr(st, gone))

    # unpaired 이항 시뮬레이션의 흔적이 남아 있으면 안 된다 (호출 노드 기준)
    check("rng.binomial 호출 없음",
          "binomial" not in called_attrs(ROOT / "experiment_stats.py"))
    check("paired_contrast()가 존재", hasattr(st, "paired_contrast"))
    check("absolute_only()가 존재 (벡터 없을 때 추정 대신 표시)",
          hasattr(st, "absolute_only"))

    # paired_contrast는 실제 벡터에서 exact McNemar를 계산해야 한다
    a = [1, 1, 1, 0, 0, 0, 1, 0]
    b = [0, 0, 0, 0, 0, 0, 1, 1]
    out = st.paired_contrast("t", "src", "A", a, "B", b)
    mc_ref = rc.exact_mcnemar(a, b)
    check("paired_contrast의 McNemar가 retrieval_core와 일치",
          out["mcnemar"] == mc_ref)
    check("paired_contrast가 짝지음 평균차를 그대로 보고",
          abs(out["effect_size"]["value"] - (sum(a) - sum(b)) / len(a)) < 1e-12,
          f"{out['effect_size']['value']}")
    check("primary_test가 exact_mcnemar", out["primary_test"] == "exact_mcnemar")


# ------------------------------------------------------------------ C. bootstrap 경계 인공물


def test_bootstrap_boundary_artifact() -> None:
    print("[C] 소표본 bootstrap 이산 경계 인공물")
    import experiment_stats as st

    art = st.bootstrap_boundary_artifact(wins=3, ties=10, losses=0)
    expected = (10 / 13) ** 13
    check("(10/13)^13 = 0.0330 계산 일치",
          abs(art["p_no_winning_query_in_a_resample"] - expected) < 1e-6,
          f"{art['p_no_winning_query_in_a_resample']} vs {expected}")
    check("0.025를 초과", art["exceeds_2.5pct_threshold"] is True)
    check("percentile bootstrap 하한이 구조적으로 0",
          art["lower_bound_is_structurally_zero"] is True,
          str(art["bootstrap_95_ci"]))
    # 실측 비율이 이론값 근처여야 한다 (20000회 재표본, 오차 ~0.003)
    check("실측 0-비율이 이론값 근처",
          abs(art["empirical_fraction_of_resamples_equal_zero"] - expected) < 0.01,
          f"{art['empirical_fraction_of_resamples_equal_zero']} vs {expected:.4f}")
    check("같은 구성의 exact McNemar 양측 p = 0.25",
          abs(art["exact_mcnemar"]["p_two_sided_exact"] - 0.25) < 1e-9,
          str(art["exact_mcnemar"]["p_two_sided_exact"]))

    # n이 커지면 인공물이 사라진다
    big = st.bootstrap_boundary_artifact(wins=30, ties=41, losses=0)
    check("n=71, 30승이면 하한이 0이 아니다",
          big["lower_bound_is_structurally_zero"] is False,
          str(big["bootstrap_95_ci"]))


# ------------------------------------------------------------------ D2. 입력 비대칭


def test_input_symmetry() -> None:
    print("[D2] retriever_compare 입력 비대칭 정정")
    import experiment_retriever_compare as rcmp

    check("bm25_scores_from_tokens 제거 (토큰 리스트 경로)",
          not hasattr(rcmp, "bm25_scores_from_tokens"))
    check("ablate_text() 존재", hasattr(rcmp, "ablate_text"))

    text = "High-purity Titanium alloy, 6Al-4V, for aerospace fasteners."
    out = rcmp.ablate_text(text, {"titanium", "aerospace"})
    check("지정 토큰이 삭제됨",
          "titanium" not in out.lower() and "aerospace" not in out.lower(), out)
    check("나머지 원문 형태 보존(구두점·대문자)",
          "High-purity" in out and "6Al-4V" in out, out)
    # word boundary: 부분 문자열은 지우면 안 된다
    check("부분 문자열은 삭제하지 않음",
          rcmp.ablate_text("titanium titaniumalloy", {"titanium"}).strip()
          == "titaniumalloy",
          rcmp.ablate_text("titanium titaniumalloy", {"titanium"}))
    check("빈 drop 집합이면 원문 그대로", rcmp.ablate_text(text, set()) == text)

    # BM25와 dense가 같은 문자열을 보는지: 소스에서 확인
    src = (ROOT / "experiment_retriever_compare.py").read_text(encoding="utf-8")
    check("dense에 ' '.join(tokens)를 넘기지 않음", '" ".join(toks)' not in src)
    check("BM25도 동일한 ablated_texts를 입력받음",
          "index.scores(ablated_texts[qi])" in src)
    check("dense도 동일한 ablated_texts를 입력받음",
          "model.encode(ablated_texts" in src)


# ------------------------------------------------------------------ D1. 모델별 seed 분리


def test_bootstrap_seed_separation() -> None:
    print("[D1] embedding_robustness 모델별 bootstrap seed 분리")
    import experiment_embedding_robustness as er

    import ast

    sig = inspect.signature(er.evaluate_model)
    check("evaluate_model이 model_seed를 받는다", "model_seed" in sig.parameters)
    path = ROOT / "experiment_embedding_robustness.py"
    src = path.read_text(encoding="utf-8")
    check("SEED + i 로 seed를 분리", "SEED + i" in src)
    # 모든 모델이 같은 리샘플을 쓰게 만드는 default_rng(SEED) 호출이 실제로 없어야 한다
    bad = []
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "default_rng"
                and len(node.args) == 1
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "SEED"):
            bad.append(node.lineno)
    check("전역 default_rng(SEED) 호출 제거", not bad, str(bad))
    check("모델별 seed가 meta에 기록됨",
          "bootstrap_seed_per_model" in src)

    # 서로 다른 seed는 서로 다른 리샘플을 만들어야 한다
    diffs = [1, 0, 1, 0, 0, 1, 0, 1, 1, 0] * 4
    a = rc.paired_bootstrap_ci(diffs, iters=2000, seed=er.SEED)
    b = rc.paired_bootstrap_ci(diffs, iters=2000, seed=er.SEED + 1)
    check("seed가 다르면 CI가 비트단위로 같지 않다", a["ci"] != b["ci"] or a["boot_se"] != b["boot_se"])


# ------------------------------------------------------------------ D3. 죽은 코드 / 반환형


def test_dead_code_and_return_types() -> None:
    print("[D3] 죽은 코드 및 반환형 불일치")
    import experiment_embedding_robustness as er
    import experiment_crosslingual_eval as cl

    check("embedding_robustness.encode() 삭제됨 (호출 즉시 ValueError였음)",
          not hasattr(er, "encode"))

    # 빈 track에서도 2-튜플을 반환해야 한다 (이전에는 dict 하나 → TypeError)
    result = cl.eval_track([], index=None, codes=None, model=None, doc_emb=None)
    check("eval_track([])가 2-튜플 반환", isinstance(result, tuple) and len(result) == 2,
          type(result).__name__)
    summary, per_query = result   # 호출부와 동일한 언패킹이 성공해야 한다
    check("빈 track의 per_query가 빈 리스트", per_query == [])
    check("빈 track의 summary에 모든 alpha 키가 있다",
          all(f"alpha={a}" in summary for a in cl.ALPHAS))


# ------------------------------------------------------------------ D4. rank_indices 전면 적용


def test_no_argsort_in_ranking() -> None:
    print("[D4] np.argsort(-...) 랭킹 제거")
    owned = [
        "experiment_stats.py", "make_figures.py",
        "experiment_retriever_compare.py", "experiment_external_retriever.py",
        "experiment_crosslingual_eval.py", "experiment_paraphrase_gap.py",
        "evaluate_validated_queries.py", "experiment_embedding_robustness.py",
        "experiment_exposure_frontier_validated.py", "build_expanded_validated.py",
    ]
    for name in owned:
        # 문자열/주석에 적힌 정정 설명은 무시하고 실제 호출 노드만 본다
        check(f"{name}: 실행 코드에 argsort 호출 없음",
              "argsort" not in called_attrs(ROOT / name))


# ------------------------------------------------------------------ FastTokenScorer 동치


def test_fast_token_scorer() -> None:
    print("[paraphrase_gap] FastTokenScorer 수식 동치")
    import experiment_paraphrase_gap as pg

    docs = [
        "titanium alloy forging press 6al 4v",
        "numerical control machine tool five axis",
        "titanium powder atomisation equipment",
        "optical fibre preform lathe",
        "titanium titanium titanium repeated token doc",
    ]
    index = rc.BM25(docs)
    scorer = pg.FastTokenScorer(index)
    cases = [
        rc.tokenize("titanium alloy press"),
        rc.tokenize("titanium titanium alloy"),          # 중복 토큰
        rc.tokenize("완전히 없는 토큰들"),                  # 어휘 밖 → 전점수 0
        [],                                              # 빈 질의
        rc.tokenize("optical fibre preform lathe five axis"),
    ]
    worst = 0.0
    for toks in cases:
        fast = scorer.scores(toks)
        slow = pg.score_tokens(index, toks)
        worst = max(worst, float(np.abs(fast - slow).max()) if fast.size else 0.0)
    check("참조 구현과 수식 일치 (max|diff| < 1e-12)", worst < 1e-12, f"{worst:.3g}")
    check("self_check가 통과", scorer.self_check(cases) < 1e-12)

    # 어휘 밖 질의는 전점수 0 → has_signal False → 검색 실패
    zero = scorer.scores(rc.tokenize("완전히 없는 토큰들"))
    check("어휘 밖 질의는 전점수 0", not rc.has_signal(zero))
    check("전점수 0이면 retrieve()가 빈 결과", rc.retrieve(zero, 10) == [])


# ------------------------------------------------------------------ 산출물 정합성


def test_regenerated_artifacts() -> None:
    print("[산출물] 재생성 결과 정합성")
    out = ROOT / "output"

    pg_path = out / "paraphrase_gap.json"
    if pg_path.is_file():
        pg = json.loads(pg_path.read_text(encoding="utf-8"))
        res = pg["results"]["minimal_text"]
        check("paraphrase_gap에 hit_vectors 저장됨", "hit_vectors" in res)
        if "hit_vectors" in res:
            n = pg["query_count"]
            for key, vec in res["hit_vectors"].items():
                if len(vec["recall@10"]) != n:
                    check(f"hit_vectors[{key}] 길이", False, f"{len(vec['recall@10'])} != {n}")
                    break
            else:
                check("hit_vectors 길이가 query_count와 일치", True)
            # 저장된 벡터의 평균이 보고된 rate와 일치해야 한다
            by_n = {r["n_removed_high_idf_shared_terms"]: r for r in res["summary"]}
            ok = True
            for key, vec in res["hit_vectors"].items():
                rate = round(sum(vec["recall@10"]) / len(vec["recall@10"]), 4)
                if abs(rate - by_n[int(key)]["recall@10"]) > 1e-9:
                    ok = False
            check("hit_vectors 평균 == 보고된 R@10", ok)
        # 주장 1의 헤드라인 수치는 불변이어야 한다
        headline = {0: 0.9792, 5: 0.7596, 10: 0.4407}
        by_n = {r["n_removed_high_idf_shared_terms"]: r["recall@10"] for r in res["summary"]}
        for k, v in headline.items():
            check(f"주장1 불변: minimal_text N={k} R@10 == {v}",
                  abs(by_n[k] - v) < 1e-9, f"{by_n[k]}")
        full = {r["n_removed_high_idf_shared_terms"]: r["recall@10"]
                for r in pg["results"]["full_text"]["summary"]}
        check("주장1 불변: full_text N=0 R@10 == 0.9968", abs(full[0] - 0.9968) < 1e-9,
              f"{full[0]}")
    else:
        check("paraphrase_gap.json 존재", False, "미생성")

    stats_path = out / "stats_summary.json"
    if stats_path.is_file():
        s = json.loads(stats_path.read_text(encoding="utf-8"))
        check("stats_summary에 env_meta 기록", "env" in s and "numpy" in s["env"])
        check("stats_summary에 seed 기록", s["meta"]["seed"] == 20260626)
        check("dataset_sizes.validated_queries == 71",
              s["dataset_sizes"]["validated_queries"] == 71,
              str(s["dataset_sizes"]["validated_queries"]))
        check("n13 결과가 보존됨", s["dataset_sizes"]["superseded_validated_n13"] == 13)
        check("before/after 기록 존재", len(s["n13_to_n71_before_after"]) >= 1)
        check("결정론적 랭킹 감사 기록 존재", "ranking_determinism_audit" in s)
        paired = [c for c in s["comparisons"]
                  if c["method"].startswith("paired_per_query")]
        check("paired 비교가 하나 이상 있다", len(paired) >= 1)
        for c in s["comparisons"]:
            if c["method"] == "absolute_rate_only":
                check(f"{c['label']}: 추정 대신 사유 표시", "paired_test_unavailable" in c)
                break
    else:
        check("stats_summary.json 존재", False, "미생성")

    md = ROOT / "docs" / "statistics.md"
    if md.is_file():
        text = md.read_text(encoding="utf-8")
        check("statistics.md에 n=13 표기가 헤드라인으로 남아있지 않다",
              "검증셋 평가 표본: 13개" not in text)
        check("statistics.md에 '경향으로 보고' 문구가 헤드라인에 없다",
              "hybrid 우위는 경향으로 보고하고" not in text)
        check("statistics.md에 n=71 표기", "n=71" in text)
        check("statistics.md에 이산 경계 인공물 절 존재", "이산 경계 인공물" in text)
    else:
        check("docs/statistics.md 존재", False)

    sup = ROOT / "docs" / "statistics_n13_superseded.md"
    check("n=13 보존 문서 존재", sup.is_file())
    if sup.is_file():
        text = sup.read_text(encoding="utf-8")
        check("보존 문서 상단에 경고", "SUPERSEDED" in text and "⚠" in text)
        check("보존 문서에 인용 금지 명시", "인용하지 마라" in text)

    for fig in ("fig_validated_retriever.png", "fig_exposure_recall.png",
                "fig_embedding_robustness.png", "fig_paraphrase_gap.png",
                "fig_retriever_alpha.png"):
        check(f"{fig} 생성됨", (out / fig).is_file())


# ------------------------------------------------------------------ figure 폰트 폴백


def test_figure_font_fallback() -> None:
    print("[figure] 한글 폰트 폴백")
    import make_figures as mf

    mf.KOREAN_OK = True
    check("폰트 있으면 한국어 라벨", mf.T("한국어", "English") == "한국어")
    mf.KOREAN_OK = False
    check("폰트 없으면 영문 폴백", mf.T("한국어", "English") == "English")
    mf.setup_font()
    check("setup_font가 폰트를 선택하고 상태를 남긴다", mf.CHOSEN_FONT is not None)
    print(f"       (선택된 폰트: {mf.CHOSEN_FONT}, 한글라벨={mf.KOREAN_OK})")
    check("DPI >= 150", mf.DPI >= 150, str(mf.DPI))


def main() -> int:
    for fn in (test_no_fake_hit_reconstruction, test_bootstrap_boundary_artifact,
               test_input_symmetry, test_bootstrap_seed_separation,
               test_dead_code_and_return_types, test_no_argsort_in_ranking,
               test_fast_token_scorer, test_regenerated_artifacts,
               test_figure_font_fallback):
        fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S)")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
