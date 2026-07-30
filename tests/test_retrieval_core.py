#!/usr/bin/env python3
"""Correctness checks for retrieval_core.

Statistics helpers are validated against scipy where an independent
implementation exists, so a silent regression in the hand-rolled
incomplete-beta / exact-binomial code cannot go unnoticed.

Run: python tests/test_retrieval_core.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import retrieval_core as rc  # noqa: E402
import run_experiments as re_mod  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(f"{name} {detail}")


# ---------------------------------------------------------------- ranking


def test_ranking() -> None:
    print("[ranking]")
    s = np.array([0.0, 0.0, 0.0, 0.0])
    check("all-zero has_signal is False", rc.has_signal(s) is False)
    check("all-zero retrieve -> []", rc.retrieve(s, 10) == [])
    check("all-zero permissive -> corpus order",
          rc.retrieve(s, 3, zero_is_failure=False) == [0, 1, 2])

    s = np.array([1.0, 5.0, 5.0, 2.0])
    check("descending with ascending-index tiebreak",
          list(rc.rank_indices(s)) == [1, 2, 3, 0],
          f"got {list(rc.rank_indices(s))}")

    # tie order must not depend on sort kind, unlike argsort
    rng = np.random.default_rng(7)
    for _ in range(50):
        v = rng.integers(0, 3, size=40).astype(float)
        a = list(rc.rank_indices(v))
        b = list(rc.rank_indices(v.copy()))
        if a != b:
            check("rank_indices stable", False)
            return
    check("rank_indices stable across repeats", True)


# ---------------------------------------------------------------- BM25 parity


def test_bm25_parity() -> None:
    print("[BM25 parity with original implementation]")
    corpus = json.loads((ROOT / "data" / "corpus" / "combined.json").read_text(encoding="utf-8"))
    docs = [rc.index_text(e, "minimal_text") for e in corpus]
    old_docs = [re_mod.build_doc_text(e, "minimal_text") for e in corpus]
    check("index_text == build_doc_text", docs == old_docs)

    new = rc.BM25(docs)
    old = re_mod.BM25(old_docs)
    queries = [
        "spray cooling dielectric fluid sealed enclosure",
        "high power direct current power supplies",
        "반도체 식각 공정용 플라즈마 발생장비",
        "mass spectrometers ion sources resolution",
    ]
    worst = 0.0
    for q in queries:
        d = float(np.abs(new.scores(q) - old.scores(q)).max())
        worst = max(worst, d)
    check("BM25 scores identical (max abs diff < 1e-12)", worst < 1e-12, f"worst={worst:g}")


# ---------------------------------------------------------------- exposure


def test_exposure() -> None:
    print("[exposure accounting]")
    corpus = json.loads((ROOT / "data" / "corpus" / "combined.json").read_text(encoding="utf-8"))
    same_legacy = sum(
        1 for e in corpus
        if rc.legacy_exposure_chars(e, "minimal_text") == rc.legacy_exposure_chars(e, "minimal_no_code")
    )
    check("legacy proxy could not distinguish the two modes",
          same_legacy == len(corpus), f"{same_legacy}/{len(corpus)}")

    diff_now = sum(
        1 for e in corpus
        if rc.exposure_chars(e, "minimal_text") != rc.exposure_chars(e, "minimal_no_code")
    )
    check("fixed proxy distinguishes them for every entry",
          diff_now == len(corpus), f"{diff_now}/{len(corpus)}")

    e = corpus[0]
    check("exposure == len(returned_text)",
          rc.exposure_chars(e, "full_text") == len(rc.returned_text(e, "full_text")))
    check("minimal_text exposure > minimal_no_code exposure by len(code)+1",
          rc.exposure_chars(e, "minimal_text") - rc.exposure_chars(e, "minimal_no_code")
          == len(e["code"]) + 1)


# ---------------------------------------------------------------- statistics


def test_stats_against_scipy() -> None:
    print("[statistics vs scipy]")
    try:
        from scipy import stats as sps
    except ImportError:
        print("  skip (scipy unavailable)")
        return

    # Clopper-Pearson
    worst = 0.0
    for k, n in [(0, 10), (1, 45), (11, 26), (12, 71), (41, 71), (71, 71), (3, 8)]:
        lo, hi = rc.clopper_pearson(k, n)
        ref_lo = 0.0 if k == 0 else float(sps.beta.ppf(0.025, k, n - k + 1))
        ref_hi = 1.0 if k == n else float(sps.beta.ppf(0.975, k + 1, n - k))
        worst = max(worst, abs(lo - ref_lo), abs(hi - ref_hi))
    check("clopper_pearson matches scipy (<1e-4)", worst < 1e-4, f"worst={worst:g}")

    # exact binomial tail
    worst = 0.0
    for k, n in [(29, 29), (14, 26), (5, 8), (3, 8), (20, 30)]:
        mine = rc._binom_sf_ge(k, n, 0.5)
        ref = float(sps.binom.sf(k - 1, n, 0.5))
        worst = max(worst, abs(mine - ref))
    check("exact binomial tail matches scipy (<1e-12)", worst < 1e-12, f"worst={worst:g}")

    # exact McNemar two-sided vs scipy binomtest
    a = [1] * 29 + [0] * 42
    b = [0] * 29 + [0] * 42
    mc = rc.exact_mcnemar(a, b)
    ref = float(sps.binomtest(29, 29, 0.5).pvalue)
    # reported p-values are rounded to 6 significant figures, so compare relatively
    check("mcnemar 29/0 two-sided matches binomtest",
          abs(mc["p_two_sided_exact"] - ref) <= 1e-6 * ref,
          f"{mc['p_two_sided_exact']} vs {ref}")
    check("mcnemar reports ties", mc["ties"] == 42 and mc["discordant"] == 29)

    # 3 gains / 5 losses -> two-sided p should be 0.7266 (exact)
    a2 = [1] * 3 + [0] * 5 + [0] * 63
    b2 = [0] * 3 + [1] * 5 + [0] * 63
    mc2 = rc.exact_mcnemar(a2, b2)
    ref2 = float(sps.binomtest(5, 8, 0.5).pvalue)
    check("mcnemar 3/5 two-sided matches binomtest",
          abs(mc2["p_two_sided_exact"] - ref2) <= 1e-6 * ref2,
          f"{mc2['p_two_sided_exact']} vs {ref2}")
    check("sig() preserves tiny p-values",
          rc.sig(3.725290298461914e-09) == 3.72529e-09, f"{rc.sig(3.725290298461914e-09)}")


def test_bootstrap_and_tost() -> None:
    print("[bootstrap / TOST]")
    # paired bootstrap must be reproducible for a fixed seed
    diffs = [1] * 3 + [-1] * 5 + [0] * 63
    a = rc.paired_bootstrap_ci(diffs, seed=20260626)
    b = rc.paired_bootstrap_ci(diffs, seed=20260626)
    check("bootstrap reproducible for fixed seed", a == b)
    check("bootstrap mean correct", abs(a["mean"] - (-2 / 71)) < 1e-4, f"{a['mean']}")

    t_small = rc.tost_paired(diffs, 0.03)
    t_big = rc.tost_paired(diffs, 0.15)
    check("TOST fails at a tight margin", not t_small["equivalent_at_0.05"],
          f"p_max={t_small['p_max']}")
    check("TOST passes at a loose margin", t_big["equivalent_at_0.05"],
          f"p_max={t_big['p_max']}")
    check("TOST p_max >= both one-sided p",
          t_small["p_max"] >= max(t_small["p_lower"], t_small["p_upper"]) - 1e-12)

    n_req = rc.required_n_for_equivalence(diffs, 0.05)
    check("required n for delta=0.05 is a plausible magnitude",
          n_req is not None and 100 < n_req < 2000, f"n={n_req}")

    # a zero-difference vector is equivalent at any positive margin
    t0 = rc.tost_paired([0] * 71, 0.05)
    check("all-zero diffs are equivalent", t0["equivalent_at_0.05"])


def test_holm() -> None:
    print("[Holm correction]")
    pv = {"a": 0.001, "b": 0.01, "c": 0.04, "d": 0.5}
    out = rc.holm(pv)
    check("smallest p scaled by family size", abs(out["a"]["p_adjusted"] - 0.004) < 1e-12)
    check("second p scaled by k-1", abs(out["b"]["p_adjusted"] - 0.03) < 1e-12)
    check("monotone non-decreasing",
          out["a"]["p_adjusted"] <= out["b"]["p_adjusted"] <= out["c"]["p_adjusted"]
          <= out["d"]["p_adjusted"])
    check("step-down stops after first failure", out["d"]["significant_at_0.05"] is False)
    single = rc.holm({"only": 0.03})
    check("family of one is unchanged", abs(single["only"]["p_adjusted"] - 0.03) < 1e-12)


def test_blend_identity() -> None:
    print("[hybrid blend]")
    bm = np.zeros(50)
    dn = np.linspace(0, 1, 50)
    for alpha in (0.7, 0.5, 0.3):
        r_hybrid = list(rc.rank_indices(rc.blend(bm, dn, alpha)))
        r_dense = list(rc.rank_indices(rc.blend(bm, dn, 0.0)))
        check(f"alpha={alpha} ranking == dense ranking when BM25 is all-zero",
              r_hybrid == r_dense)


def main() -> int:
    test_ranking()
    test_bm25_parity()
    test_exposure()
    test_stats_against_scipy()
    test_bootstrap_and_tost()
    test_holm()
    test_blend_identity()
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
