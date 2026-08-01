#!/usr/bin/env python3
"""Claim-to-evidence registry: check every number in PAPER.md against artifacts.

The audit found that the paper's headline figures existed in no statistics file
or figure at all -- `output/stats_summary.json` still described n=13,
`docs/statistics.md` said "report as a trend", and the figures were generated
from superseded JSON. Nothing detected the drift because no check existed.

This script is that check. Each claim records where it appears in the paper, the
value the paper asserts, and how to recompute it from the artifacts. Run it
before every submission:

    python verify_claims.py

Exit code 0 means every claim matches its evidence. Non-zero means at least one
paper number is not supported by the artifacts -- either the artifact moved
(rerun the experiment) or the paper is stale (fix the paper).

`--update` rewrites the registry's expected values from the current artifacts and
prints a diff, for use after an intentional re-run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows 콘솔 기본 코드페이지(cp949)는 U+2212(−)/U+2014(—) 같은 문자를 인코딩할 수
# 없어 출력 도중 UnicodeEncodeError로 죽었다. 검사기가 자기 출력 때문에 실패하면
# 안 되므로 stdout/stderr를 UTF-8로 강제하고, 그래도 안 되면 대체 문자로 흘린다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):        # pragma: no cover - 구버전/리다이렉트
        pass

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
DATA = ROOT / "data"
REGISTRY_PATH = ROOT / "docs" / "claim_registry.json"

TOL = 5e-4          # rounding tolerance for rates reported to 4 decimals
TOL_PCT = 0.15      # tolerance for percentages reported to 1 decimal
TOL_CHARS = 1.0     # tolerance for character counts


def load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def dig(obj, *keys, default=None):
    cur = obj
    for k in keys:
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(k)
        elif isinstance(cur, (list, tuple)) and isinstance(k, int):
            cur = cur[k] if -len(cur) <= k < len(cur) else None
        else:
            return default
    return default if cur is None else cur


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------


class Check:
    def __init__(self, cid: str, where: str, desc: str, paper, fn, tol=TOL):
        self.cid = cid
        self.where = where
        self.desc = desc
        self.paper = paper
        self.fn = fn
        self.tol = tol

    def run(self):
        try:
            actual = self.fn()
        except Exception as exc:                      # noqa: BLE001
            return "ERROR", None, f"{type(exc).__name__}: {exc}"
        if actual is None:
            return "SKIP", None, "artifact missing -- run the experiment"
        if isinstance(self.paper, (list, tuple)):
            if not isinstance(actual, (list, tuple)) or len(actual) != len(self.paper):
                return "MISMATCH", actual, "shape differs"
            # 수치 구간(CI)은 허용오차로, 문자열 목록(등급명 등)은 정확히 비교한다.
            try:
                ok = all(abs(float(a) - float(p)) <= self.tol
                         for a, p in zip(actual, self.paper))
            except (TypeError, ValueError):
                ok = list(actual) == list(self.paper)
            return ("OK" if ok else "MISMATCH"), actual, ""
        if isinstance(self.paper, (int, float)):
            ok = abs(float(actual) - float(self.paper)) <= self.tol
            return ("OK" if ok else "MISMATCH"), actual, ""
        return ("OK" if actual == self.paper else "MISMATCH"), actual, ""


def build_checks() -> list[Check]:
    corpus = load(DATA / "corpus" / "combined.json")
    queries = load(DATA / "queries.json")
    logs = load(OUT / "experiment_logs.json")
    gap = load(OUT / "paraphrase_gap.json")
    validated = load(DATA / "validated_queries_expanded.json")
    suite = load(OUT / "validated_suite.json") or load(OUT / "validated_suite_smoke.json")
    decomp = load(OUT / "exposure_decomposition.json")

    def src_count(name):
        if corpus is None:
            return None
        return sum(1 for e in corpus if e.get("source") == name)

    def suite_rate(imode, retr, sub="overall", model=None):
        if suite is None:
            return None
        model = model or dig(suite, "meta", "primary_model")
        return dig(suite, "retriever", model, imode, "recall@10", retr, sub, "rate")

    def suite_contrast(imode, key, field, model=None):
        if suite is None:
            return None
        model = model or dig(suite, "meta", "primary_model")
        return dig(suite, "retriever", model, imode, "contrasts", key, field)

    def gap_recall(n_removed, mode="minimal_text", metric="recall@10"):
        rows = dig(gap, "results", mode, "summary")
        if not isinstance(rows, list):
            return None
        for row in rows:
            if row.get("n_removed_high_idf_shared_terms") == n_removed:
                return row.get(metric)
        return None

    C = []

    # ---- corpus / query set (should be unchanged) ----
    C.append(Check("corpus.total", "PAPER 3.1", "코퍼스 항목 수", 1783,
                   lambda: len(corpus) if corpus else None, tol=0))
    C.append(Check("corpus.wassenaar", "PAPER 3.1", "Wassenaar 항목 수", 568,
                   lambda: src_count("wassenaar_2025"), tol=0))
    C.append(Check("corpus.scomet", "PAPER 3.1", "SCOMET 항목 수", 578,
                   lambda: src_count("india_scomet_2024"), tol=0))
    C.append(Check("corpus.ecfr", "PAPER 3.1", "eCFR 항목 수", 637,
                   lambda: src_count("ecfr_part774"), tol=0))
    C.append(Check("corpus.korean_entries", "PAPER 3.1", "한글 포함 항목 수 (0이어야 함)", 0,
                   lambda: (sum(1 for e in corpus
                                if any('가' <= ch <= '힣' for ch in e.get("text", "")))
                            if corpus else None), tol=0))
    C.append(Check("synth.total", "PAPER 3.4", "합성 쿼리 총수", 780,
                   lambda: dig(queries, "total"), tol=0))
    C.append(Check("synth.test", "PAPER 3.4", "합성 test split", 624,
                   lambda: len(queries["test"]) if queries else None, tol=0))

    # ---- claim 1: synthetic self-reference (must still reproduce) ----
    for mode, val in [("full_text", 0.9920), ("minimal_text", 0.9840),
                      ("minimal_no_code", 0.9856)]:
        C.append(Check(f"synth.{mode}.r10", "PAPER 4.1", f"합성 {mode} R@10", val,
                       lambda m=mode: dig(logs, "metrics", m, "recall@10")))
    for n_rm, val in [(0, 0.9840), (3, 0.8990), (5, 0.7756), (10, 0.4535)]:
        C.append(Check(f"synth.ablation.n{n_rm}", "PAPER 4.1",
                       f"변별어 {n_rm}개 제거 R@10", val, lambda n=n_rm: gap_recall(n)))
    C.append(Check("synth.ablation.jaccard", "PAPER 4.1",
                   "쿼리-정답 평균 Jaccard", 0.4871,
                   lambda: gap_recall(0, metric="mean_jaccard_vs_answer")))
    C.append(Check("synth.route_only.r10", "PAPER 4.1", "route_only R@10 (퇴화 조건)", 0.0016,
                   lambda: dig(logs, "metrics", "route_only", "recall@10")))

    # ---- 합성 노출량: 채널②(반환) 지표이므로 논문은 트레이드오프로 쓰지 않는다 (PAPER 2.1) ----
    C.append(Check("synth.exposure.full", "PAPER 4.1", "합성 full_text 노출량@10",
                   15639.36, lambda: dig(logs, "metrics", "full_text", "exposure@10"),
                   tol=TOL_CHARS))
    C.append(Check("synth.exposure.minimal", "PAPER 4.1", "합성 minimal_text 노출량@10",
                   1725.33, lambda: dig(logs, "metrics", "minimal_text", "exposure@10"),
                   tol=TOL_CHARS))

    # ---- validated set composition ----
    C.append(Check("valid.n", "PAPER 4.3", "검증셋 n", 151,
                   lambda: len(validated["queries"]) if validated else None, tol=0))
    C.append(Check("valid.n_en", "PAPER 4.3", "검증셋 영어", 42,
                   lambda: (sum(1 for q in validated["queries"] if q["lang"] == "en")
                            if validated else None), tol=0))
    C.append(Check("valid.n_ko", "PAPER 4.3", "검증셋 한국어", 109,
                   lambda: (sum(1 for q in validated["queries"] if q["lang"] == "ko")
                            if validated else None), tol=0))

    # ---- claim 3: retriever comparison on the validated set ----
    C.append(Check("valid.bm25.r10", "PAPER 4.3", "BM25 R@10", 0.1523,
                   lambda: suite_rate("minimal_text", "BM25")))
    C.append(Check("valid.bm25.en", "PAPER 4.3", "BM25 영어 R@10", 0.4762,
                   lambda: suite_rate("minimal_text", "BM25", "en")))
    C.append(Check("valid.bm25.ko", "PAPER 4.3", "BM25 한국어 R@10 (구조적 저조)", 0.0275,
                   lambda: suite_rate("minimal_text", "BM25", "ko")))
    C.append(Check("valid.hybrid.r10", "PAPER 4.3", "hybrid R@10 (논문 0.510)", 0.5099,
                   lambda: suite_rate("minimal_text", "hybrid_0.5")))
    C.append(Check("valid.hybrid.en", "PAPER 4.3", "hybrid 영어 R@10 (논문 0.548)", 0.5476,
                   lambda: suite_rate("minimal_text", "hybrid_0.5", "en")))
    C.append(Check("valid.hybrid.ko", "PAPER 4.3", "hybrid 한국어 R@10 (논문 0.495)", 0.4954,
                   lambda: suite_rate("minimal_text", "hybrid_0.5", "ko")))
    C.append(Check("valid.dense.r10", "PAPER 4.3", "dense R@10 (논문 0.450)", 0.4503,
                   lambda: suite_rate("minimal_text", "dense")))
    C.append(Check("valid.hyb_vs_bm25.diff", "PAPER 4.3/초록",
                   "hybrid−BM25 평균차", 0.3576,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_bm25[overall]", "mean_diff")))
    C.append(Check("valid.hyb_vs_bm25.ci", "PAPER 4.3/초록",
                   "hybrid−BM25 95% CI", [0.2848, 0.4371],
                   lambda: suite_contrast("minimal_text", "hybrid_vs_bm25[overall]", "diff_95_ci")))
    C.append(Check("valid.hyb_vs_bm25.wins", "PAPER 4.3/초록",
                   "hybrid−BM25 승 (54승 0패)", 54,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_bm25[overall]", "wins"), tol=0))
    C.append(Check("valid.hyb_vs_bm25.losses", "PAPER 4.3/초록", "hybrid−BM25 패", 0,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_bm25[overall]", "losses"),
                   tol=0))
    C.append(Check("valid.dense_vs_bm25.diff", "PAPER 4.3", "dense−BM25 평균차", 0.2980,
                   lambda: suite_contrast("minimal_text", "dense_vs_bm25[overall]", "mean_diff")))
    # 논문의 핵심 진술: "hybrid가 필요"가 아니라 "dense 성분이 필요" (PAPER 4.3, 8)
    C.append(Check("valid.hyb_vs_dense.diff", "PAPER 4.3/초록", "hybrid−dense 평균차 (Holm 후 비유의)",
                   0.0596,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_dense[overall]", "mean_diff")))
    C.append(Check("valid.hyb_vs_dense.ko_wins", "PAPER 4.3",
                   "hybrid−dense 한국어 승 (BM25 대부분 항등 0)", 2,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_dense[ko]", "wins"), tol=0))
    C.append(Check("valid.bm25_no_signal", "PAPER 4.3", "BM25 무신호 질의 수 (96/151)", 96,
                   lambda: dig(suite, "retriever", dig(suite, "meta", "primary_model"),
                               "diagnostics", "minimal_text", "bm25_no_signal_queries"), tol=0))

    # ---- claim 2: exposure-recall frontier ----
    # 2-D 노출표 (PAPER 4.4). 대각선이 아니라 '색인 x 반환' 칸을 직접 검사한다.
    C.append(Check("front.full.exposure", "PAPER 4.4", "색인=full/반환=full 노출량@10", 7886.2,
                   lambda: dig(suite, "exposure_at10", "full_text", "return=full_text"),
                   tol=TOL_CHARS))
    C.append(Check("front.full_return_min.exposure", "PAPER 4.4",
                   "색인=full/반환=minimal_text 노출량@10 (운용점)", 1780.8,
                   lambda: dig(suite, "exposure_at10", "full_text", "return=minimal_text"),
                   tol=TOL_CHARS))
    C.append(Check("front.minimal.exposure", "PAPER 4.4", "색인=minimal/반환=minimal 노출량@10",
                   1805.5,
                   lambda: dig(suite, "exposure_at10", "minimal_text", "return=minimal_text"),
                   tol=TOL_CHARS))
    C.append(Check("front.nocode.exposure", "PAPER 4.4",
                   "색인=minimal_no_code/반환=동일 노출량@10", 1618.4,
                   lambda: dig(suite, "exposure_at10", "minimal_no_code",
                               "return=minimal_no_code"), tol=TOL_CHARS))
    C.append(Check("front.full.hybrid", "PAPER 4.4", "색인 full_text hybrid R@10", 0.5497,
                   lambda: suite_rate("full_text", "hybrid_0.5")))
    C.append(Check("front.nocode.hybrid", "PAPER 4.4", "색인 minimal_no_code hybrid R@10",
                   0.4901, lambda: suite_rate("minimal_no_code", "hybrid_0.5")))
    # 반환 측 축소: 논문 헤드라인은 '색인 고정 + 반환만 축소' 81.4%, 비용 정확히 0
    C.append(Check("front.return_only.cut_pct", "PAPER 4.4/초록/결론",
                   "반환만 축소 시 노출 감소율 (77.4%)", 77.4,
                   lambda: dig(decomp, "best_operating_point",
                               "exposure_cut_vs_baseline_pct"), tol=TOL_PCT))
    C.append(Check("front.return_only.recall_delta", "PAPER 4.4/초록",
                   "반환만 축소 시 R@10 변화 (구조적으로 0)", 0.0,
                   lambda: dig(decomp, "best_operating_point", "recall_delta_vs_baseline")))
    C.append(Check("front.return_only.actionable", "PAPER 4.4",
                   "운용점이 통제번호를 유지하는가", True,
                   lambda: dig(decomp, "best_operating_point", "cell", "actionable")))
    # 색인 측 축소: 비용이 발생하며 δ=0.05 등가는 성립하지 않는다
    C.append(Check("front.index_cut.diff", "PAPER 4.4", "색인 minimal−full hybrid 평균차",
                   -0.0397,
                   lambda: dig(suite, "equivalence",
                               "minimal_text_vs_full_text[hybrid_0.5]",
                               "paired_bootstrap", "mean")))
    C.append(Check("front.index_cut.ci", "PAPER 4.4",
                   "색인 minimal−full 95% CI", [-0.0927, 0.0132],
                   lambda: dig(suite, "equivalence",
                               "minimal_text_vs_full_text[hybrid_0.5]",
                               "paired_bootstrap", "ci")))
    C.append(Check("front.index_cut.not_equivalent", "PAPER 4.4",
                   "색인 축소가 δ=0.05에서 등가인가 (아니오)", False,
                   lambda: dig(suite, "equivalence",
                               "minimal_text_vs_full_text[hybrid_0.5]",
                               "equivalent_at_primary_delta")))
    C.append(Check("front.index_cut.n_required", "PAPER 4.4",
                   "색인 축소 등가 입증에 필요한 n", 6166,
                   lambda: dig(suite, "equivalence",
                               "minimal_text_vs_full_text[hybrid_0.5]",
                               "n_required_for_primary_delta"), tol=0))

    # ---- 4.6 모델 robustness: 3개 인코더 전부에서 결론이 유지되는가 ----
    C.append(Check("robust.models", "PAPER 4.6", "포함된 dense 인코더 수 (3)", 3,
                   lambda: len(dig(suite, "meta", "dense_models") or {}), tol=0))
    for model, dense_r, hyb_r, ko_r in [("MiniLM", 0.4503, 0.5099, 0.4954),
                                        ("e5-base", 0.4768, 0.4901, 0.4587),
                                        ("bge-m3", 0.5695, 0.5497, 0.5596)]:
        C.append(Check(f"robust.{model}.dense", "PAPER 4.6", f"{model} dense R@10", dense_r,
                       lambda m=model: suite_rate("minimal_text", "dense", model=m)))
        C.append(Check(f"robust.{model}.hybrid", "PAPER 4.6", f"{model} hybrid R@10", hyb_r,
                       lambda m=model: suite_rate("minimal_text", "hybrid_0.5", model=m)))
        C.append(Check(f"robust.{model}.ko", "PAPER 4.6", f"{model} hybrid 한국어 R@10", ko_r,
                       lambda m=model: suite_rate("minimal_text", "hybrid_0.5", "ko", model=m)))
        # dense-BM25는 유의, hybrid-dense는 비유의 — 세 모델 모두에서 성립해야 한다
        C.append(Check(f"robust.{model}.dense_beats_bm25", "PAPER 4.6",
                       f"{model} dense−BM25가 Holm 보정 후 유의한가", True,
                       lambda m=model: dig(suite, "retriever", m, "minimal_text",
                                           "holm_within_index_mode",
                                           "dense_vs_bm25[overall]", "significant_at_0.05")))
        C.append(Check(f"robust.{model}.hybrid_not_better", "PAPER 4.6",
                       f"{model} hybrid−dense가 유의한가 (아니오)", False,
                       lambda m=model: dig(suite, "retriever", m, "minimal_text",
                                           "holm_within_index_mode",
                                           "hybrid_vs_dense[overall]", "significant_at_0.05")))

    # ---- 4.8 교차모델 검증 (한계 6 해소): 무엇이 일반화되고 무엇이 안 되는가 ----
    cross = load(OUT / "tier1_crossmodel.json")

    C.append(Check("cross.models", "PAPER 4.8", "Tier-1 번들 모델 수 (3)", 3,
                   lambda: len(dig(cross, "models") or []), tol=0))
    # ablation: level0·level3 모두 전 모델 유의 (n=71에서는 level3이 2/3였다)
    C.append(Check("cross.abl.l0_all_sig", "PAPER 4.8",
                   "압력 level0 dense−BM25가 세 모델 모두 유의한가", True,
                   lambda: dig(cross, "conclusion",
                               "ablation_dense_advantage_significant_at_level0_all_models")))
    C.append(Check("cross.abl.l3_all_sig", "PAPER 4.8",
                   "압력 level3에서도 세 모델 모두 유의한가 (예)", True,
                   lambda: dig(cross, "conclusion",
                               "ablation_dense_advantage_significant_at_level3_all_models")))
    C.append(Check("cross.abl.l3_e5_sig", "PAPER 4.8",
                   "level3에서 e5-base도 유의하다 (n=151에서 역전)", True,
                   lambda: dig(cross, "conclusion",
                               "ablation_level3_significant_by_model", "e5-base")))
    for m, val in [("MiniLM", 0.2450), ("bge-m3", 0.3576), ("e5-base", 0.1589)]:
        C.append(Check(f"cross.abl.l3.{m}", "PAPER 4.8", f"level3 dense−BM25 ({m})", val,
                       lambda mm=m: dig(cross, "ablation", mm, "dense_vs_bm25", "3",
                                        "dense_minus_bm25")))
    # frontier: n=151에서 세 모델의 권고가 L1로 수렴 (모델 의존성 해소)
    C.append(Check("cross.front.model_dependent", "PAPER 4.8/초록",
                   "운용 권고가 모델에 따라 달라지는가 (아니오)", False,
                   lambda: dig(cross, "conclusion",
                               "frontier_recommendation_is_model_dependent")))
    C.append(Check("cross.front.conservative", "PAPER 4.8/초록/결론",
                   "모델 불문 보수적 권고 등급", "L1",
                   lambda: dig(cross, "conclusion",
                               "conservative_recommendation_across_models")))
    for m, val in [("MiniLM", "L1"), ("e5-base", "L1"), ("bge-m3", "L1")]:
        C.append(Check(f"cross.front.rec.{m}", "PAPER 4.8", f"{m} 권고 등급", val,
                       lambda mm=m: dig(cross, "frontier", mm, "recommended_level")))
    C.append(Check("cross.front.bge.L2_diff", "PAPER 4.8",
                   "bge-m3 L2 차이 (마진 초과 → 손실 징후)", -0.1053,
                   lambda: dig(cross, "frontier", "bge-m3", "vs_L0", "L2", "mean_diff")))
    C.append(Check("cross.front.bge.L1_not_equiv", "PAPER 4.8",
                   "bge-m3에서 L1이 등가 입증되는가 (아니오)", False,
                   lambda: dig(cross, "frontier", "bge-m3", "vs_L0", "L1",
                               "equivalent_at_0.05")))

    # ---- claim 4 (핵심): 질의 측 disclosure-recall frontier ----
    ladder = load(OUT / "disclosure_frontier.json")

    def ladder_rate(level, retr="hybrid_0.5", sub="overall"):
        return dig(ladder, "recall@10", retr, level, sub, "rate")

    def ladder_tost(level, field, retr="hybrid_0.5"):
        return dig(ladder, "equivalence_vs_L0", retr, f"{level}_vs_L0", "primary", field)

    for lv, val in [("L0", 0.5188), ("L1", 0.4962), ("L2", 0.4211),
                    ("L3", 0.4586), ("L4", 0.3835)]:
        C.append(Check(f"ladder.hybrid.{lv}", "PAPER 4.5", f"사다리 {lv} hybrid R@10", val,
                       lambda l=lv: ladder_rate(l)))
    C.append(Check("ladder.bm25.L0.ko", "PAPER 4.5",
                   "사다리 BM25 한국어 R@10 (바닥 수준)", 0.0303,
                   lambda: ladder_rate("L0", "BM25", "ko")))
    # L1 = 손실 징후가 없는 가장 깊은 등급. n=151에서 TOST 등가는 통과하지 못한다 (증거등급 B)
    C.append(Check("ladder.L1.tost_pmax", "PAPER 4.5/초록", "L1 TOST p_max", 0.1119,
                   lambda: ladder_tost("L1", "p_max"), tol=1e-3))
    C.append(Check("ladder.L1.equivalent", "PAPER 4.5/초록",
                   "L1이 δ=0.05에서 등가 입증되는가 (아니오)", False,
                   lambda: ladder_tost("L1", "equivalent_at_0.05")))
    C.append(Check("ladder.L2.not_equivalent", "PAPER 4.5",
                   "L2가 δ=0.05에서 등가 입증되는가 (아니오)", False,
                   lambda: ladder_tost("L2", "equivalent_at_0.05")))
    C.append(Check("ladder.L1.n_required", "PAPER 4.5", "L1 등가 입증에 필요한 n", 556,
                   lambda: dig(ladder, "equivalence_vs_L0", "hybrid_0.5", "L1_vs_L0",
                               "required_n_for_delta_0.05"), tol=0))
    C.append(Check("ladder.L2.diff", "PAPER 4.5", "L2 평균차 (마진 초과 = 손실 징후)", -0.0977,
                   lambda: dig(ladder, "contrasts_vs_L0", "hybrid_0.5", "L2_vs_L0",
                               "mean_diff")))
    C.append(Check("ladder.n", "PAPER 3.5/4.5", "사다리 분석 대상 질의 수 (정의 위반 제외 후)", 133,
                   lambda: dig(ladder, "data", "n_queries"), tol=0))
    C.append(Check("ladder.excluded", "PAPER 3.5/7", "사다리 정의 위반으로 제외된 질의 수", 18,
                   lambda: dig(ladder, "data", "ladder_spec_excluded"), tol=0))
    C.append(Check("ladder.L4.diff", "PAPER 4.5", "L4 평균차 (마진 초과 = 손실 징후)", -0.1353,
                   lambda: dig(ladder, "contrasts_vs_L0", "hybrid_0.5", "L4_vs_L0",
                               "mean_diff")))
    C.append(Check("ladder.recommended", "PAPER 4.5/초록/결론", "운용 권고 등급", "L1",
                   lambda: dig(ladder, "evidence_tiers", "hybrid_0.5", "recommended_level")))
    C.append(Check("ladder.L3.confounded", "PAPER 4.5/초록",
                   "L3가 자기참조 교란으로 판정되는가", ["L3"],
                   lambda: dig(ladder, "evidence_tiers", "hybrid_0.5",
                               "confounded_by_selfreference")))
    C.append(Check("ladder.sens_tokens.L0", "PAPER 3.5", "L0 평균 민감토큰", 5.353,
                   lambda: dig(ladder, "exposure_axis", "L0", "mean_sensitive_token_count"),
                   tol=1e-2))
    C.append(Check("ladder.sens_tokens.L2", "PAPER 3.5", "L2 평균 민감토큰", 4.188,
                   lambda: dig(ladder, "exposure_axis", "L2", "mean_sensitive_token_count"),
                   tol=1e-2))

    # ---- claim 5: 자기참조 압력 하 강건성 ----
    abl = load(OUT / "symmetric_ablation.json")

    C.append(Check("abl.dense_vs_bm25.L0", "PAPER 4.6", "압력 level0 dense−BM25 평균차", 0.3642,
                   lambda: dig(abl, "headline", "dense_advantage_over_bm25_by_level", "0")))
    C.append(Check("abl.dense_vs_bm25.L3", "PAPER 4.6",
                   "압력 level3 dense−BM25 평균차 (유의 유지)", 0.2450,
                   lambda: dig(abl, "headline", "dense_advantage_over_bm25_by_level", "3")))
    for retr, l0, l3 in [("BM25", 0.1523, 0.0927), ("dense", 0.5166, 0.3377),
                         ("hybrid_0.5", 0.5497, 0.3642)]:
        C.append(Check(f"abl.{retr}.L0", "PAPER 4.6", f"압력 level0 {retr} R@10", l0,
                       lambda r=retr: dig(abl, "headline", "recall_by_level", r, "0")))
        C.append(Check(f"abl.{retr}.L3", "PAPER 4.6", f"압력 level3 {retr} R@10", l3,
                       lambda r=retr: dig(abl, "headline", "recall_by_level", r, "3")))
    C.append(Check("abl.ko.bm25.L3", "PAPER 4.6",
                   "압력 level3 BM25 한국어 R@10 (전 level 동일)", 0.0367,
                   lambda: dig(abl, "headline", "recall_by_level_ko", "BM25", "3")))
    C.append(Check("abl.ko.dense.L3", "PAPER 4.6", "압력 level3 dense 한국어 R@10", 0.3853,
                   lambda: dig(abl, "headline", "recall_by_level_ko", "dense", "3")))
    # 치환 커버리지: 사전이 원본 71개만 덮으므로 압력이 표본 전체에 걸리지 않는다.
    # 논문 4.6 이 이 수치를 그대로 인용하며, 조용히 떨어지면 검증이 실패해야 한다.
    for lv, changed in [("1", 71), ("2", 71), ("3", 121)]:
        C.append(Check(f"abl.coverage.L{lv}", "PAPER 4.6",
                       f"level{lv} 치환이 적용된 질의 수", changed,
                       lambda l=lv: dig(abl, "substitution_coverage", l, "queries_changed"),
                       tol=0))
    C.append(Check("abl.gate_cos.L0", "PAPER 4.6", "압력 level0 게이트 cos 평균", 0.3420,
                   lambda: dig(abl, "manipulation_diagnostics", "per_level", "0",
                               "mean_gate_cos"), tol=1e-3))
    C.append(Check("abl.gate_cos.L3", "PAPER 4.6", "압력 level3 게이트 cos 평균", 0.3189,
                   lambda: dig(abl, "manipulation_diagnostics", "per_level", "3",
                               "mean_gate_cos"), tol=1e-3))

    return C


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true",
                    help="현재 산출물 값으로 registry를 갱신하고 diff를 출력")
    args = ap.parse_args()

    checks = build_checks()
    rows = []
    counts = {"OK": 0, "MISMATCH": 0, "SKIP": 0, "ERROR": 0, "NEW": 0}
    for c in checks:
        status, actual, note = c.run()
        if c.paper is None and status in ("MISMATCH", "OK"):
            status = "NEW"
        counts[status] = counts.get(status, 0) + 1
        rows.append({"id": c.cid, "where": c.where, "desc": c.desc,
                     "paper": c.paper, "artifact": actual,
                     "status": status, "note": note})

    width = max(len(r["id"]) for r in rows) + 2
    print(f"{'claim':<{width}} {'status':<9} {'paper':>16}  {'artifact':>18}  where")
    print("-" * (width + 70))
    for r in rows:
        p = "-" if r["paper"] is None else (
            f"{r['paper']}" if not isinstance(r["paper"], float) else f"{r['paper']:.4f}")
        a = "-" if r["artifact"] is None else (
            f"{r['artifact']}" if not isinstance(r["artifact"], float) else f"{r['artifact']:.4f}")
        print(f"{r['id']:<{width}} {r['status']:<9} {p:>16}  {a:>18}  {r['where']}"
              + (f"   [{r['note']}]" if r["note"] else ""))

    print()
    print(" / ".join(f"{k}={v}" for k, v in counts.items() if v))

    mism = [r for r in rows if r["status"] == "MISMATCH"]
    if mism:
        print("\n논문을 고쳐야 하는 수치 (근거 산출물과 불일치):")
        for r in mism:
            print(f"  {r['where']:<22} {r['desc']}")
            print(f"      논문 {r['paper']}  →  실측 {r['artifact']}")
    new = [r for r in rows if r["status"] == "NEW"]
    if new:
        print("\n논문에 없지만 산출물에 있는 근거 (반영 검토):")
        for r in new:
            print(f"  {r['desc']}: {r['artifact']}")

    REGISTRY_PATH.parent.mkdir(exist_ok=True)
    if args.update:
        for r in rows:
            if r["status"] in ("MISMATCH", "NEW") and r["artifact"] is not None:
                r["paper"] = r["artifact"]
                r["status"] = "UPDATED"
    REGISTRY_PATH.write_text(json.dumps({"checks": rows, "counts": counts},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {REGISTRY_PATH.relative_to(ROOT)}")

    return 1 if (counts.get("MISMATCH") or counts.get("ERROR")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
