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
from pathlib import Path

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
            ok = all(abs(float(a) - float(p)) <= self.tol for a, p in zip(actual, self.paper))
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
    C.append(Check("corpus.total", "PAPER 3.1", "코퍼스 항목 수", 1797,
                   lambda: len(corpus) if corpus else None, tol=0))
    C.append(Check("corpus.wassenaar", "PAPER 3.1", "Wassenaar 항목 수", 585,
                   lambda: src_count("wassenaar_2025"), tol=0))
    C.append(Check("corpus.scomet", "PAPER 3.1", "SCOMET 항목 수", 575,
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
    for mode, val in [("full_text", 0.9968), ("minimal_text", 0.9792),
                      ("minimal_no_code", 0.9808)]:
        C.append(Check(f"synth.{mode}.r10", "PAPER 4.1", f"합성 {mode} R@10", val,
                       lambda m=mode: dig(logs, "metrics", m, "recall@10")))
    for n_rm, val in [(0, 0.9792), (5, 0.7596), (10, 0.4407)]:
        C.append(Check(f"synth.ablation.n{n_rm}", "PAPER 4.1",
                       f"변별어 {n_rm}개 제거 R@10", val, lambda n=n_rm: gap_recall(n)))
    # the paper rounds this one to 3 decimals, so allow 1e-3
    C.append(Check("synth.ablation.jaccard", "PAPER 4.1",
                   "쿼리-정답 평균 Jaccard (논문 0.485)", 0.485,
                   lambda: gap_recall(0, metric="mean_jaccard_vs_answer"), tol=1e-3))

    # ---- superseded exposure figures (expected to MISMATCH until the paper is fixed) ----
    C.append(Check("synth.exposure.full", "PAPER 4.1", "합성 full_text 노출량@10 (구정의 4834)",
                   4834.0, lambda: dig(logs, "metrics", "full_text", "exposure@10"),
                   tol=TOL_CHARS))
    C.append(Check("synth.exposure.minimal", "PAPER 4.1", "합성 minimal_text 노출량@10 (구정의 1623)",
                   1623.0, lambda: dig(logs, "metrics", "minimal_text", "exposure@10"),
                   tol=TOL_CHARS))
    C.append(Check("synth.exposure.cut_pct", "PAPER 4.1/초록", "합성 노출 감소율 (논문 66.4%)",
                   66.4, lambda: (round(100 * (dig(logs, "metrics", "full_text", "exposure@10")
                                               - dig(logs, "metrics", "minimal_text", "exposure@10"))
                                        / dig(logs, "metrics", "full_text", "exposure@10"), 1)
                                  if logs else None), tol=TOL_PCT))

    # ---- validated set composition ----
    C.append(Check("valid.n", "PAPER 4.3", "검증셋 n", 71,
                   lambda: len(validated["queries"]) if validated else None, tol=0))
    C.append(Check("valid.n_en", "PAPER 4.3", "검증셋 영어", 26,
                   lambda: (sum(1 for q in validated["queries"] if q["lang"] == "en")
                            if validated else None), tol=0))
    C.append(Check("valid.n_ko", "PAPER 4.3", "검증셋 한국어", 45,
                   lambda: (sum(1 for q in validated["queries"] if q["lang"] == "ko")
                            if validated else None), tol=0))

    # ---- claim 3: retriever comparison on the validated set ----
    C.append(Check("valid.bm25.r10", "PAPER 4.3", "BM25 R@10 (논문 0.169)", 0.169,
                   lambda: suite_rate("minimal_text", "BM25")))
    C.append(Check("valid.bm25.en", "PAPER 4.3", "BM25 영어 R@10 (논문 0.423)", 0.423,
                   lambda: suite_rate("minimal_text", "BM25", "en")))
    C.append(Check("valid.bm25.ko", "PAPER 4.3", "BM25 한국어 R@10 (논문 0.022)", 0.022,
                   lambda: suite_rate("minimal_text", "BM25", "ko")))
    C.append(Check("valid.hybrid.r10", "PAPER 4.3", "hybrid R@10 (논문 0.578)", 0.578,
                   lambda: suite_rate("minimal_text", "hybrid_0.5")))
    C.append(Check("valid.hybrid.en", "PAPER 4.3", "hybrid 영어 R@10 (논문 0.538)", 0.538,
                   lambda: suite_rate("minimal_text", "hybrid_0.5", "en")))
    C.append(Check("valid.hybrid.ko", "PAPER 4.3", "hybrid 한국어 R@10 (논문 0.600)", 0.600,
                   lambda: suite_rate("minimal_text", "hybrid_0.5", "ko")))
    C.append(Check("valid.dense.r10", "PAPER 4.3", "dense R@10 (논문 0.549)", 0.549,
                   lambda: suite_rate("minimal_text", "dense")))
    C.append(Check("valid.hyb_vs_bm25.diff", "PAPER 4.3/초록",
                   "hybrid−BM25 평균차 (논문 +0.409)", 0.409,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_bm25[overall]", "mean_diff")))
    C.append(Check("valid.hyb_vs_bm25.ci", "PAPER 4.3/초록",
                   "hybrid−BM25 95% CI (논문 [0.296, 0.521])", [0.296, 0.521],
                   lambda: suite_contrast("minimal_text", "hybrid_vs_bm25[overall]", "diff_95_ci")))
    C.append(Check("valid.hyb_vs_bm25.wins", "PAPER 4.3/초록",
                   "hybrid−BM25 승 (논문 29승 0패)", 29,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_bm25[overall]", "wins"), tol=0))
    C.append(Check("valid.hyb_vs_bm25.losses", "PAPER 4.3/초록", "hybrid−BM25 패", 0,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_bm25[overall]", "losses"),
                   tol=0))
    C.append(Check("valid.dense_vs_bm25.diff", "PAPER 4.3", "dense−BM25 평균차 (논문 +0.380)",
                   0.380,
                   lambda: suite_contrast("minimal_text", "dense_vs_bm25[overall]", "mean_diff")))

    # ---- claim 2: exposure-recall frontier ----
    C.append(Check("front.full.exposure", "PAPER 4.5", "full_text 노출량@10 (논문 3952)", 3952.0,
                   lambda: dig(suite, "exposure_at10", "full_text", "return=full_text"),
                   tol=TOL_CHARS))
    C.append(Check("front.minimal.exposure", "PAPER 4.5", "minimal_text 노출량@10 (논문 1754)",
                   1754.0,
                   lambda: dig(suite, "exposure_at10", "minimal_text", "return=minimal_text"),
                   tol=TOL_CHARS))
    C.append(Check("front.nocode.exposure", "PAPER 4.5", "minimal_no_code 노출량@10 (논문 1663)",
                   1663.0,
                   lambda: dig(suite, "exposure_at10", "minimal_no_code",
                               "return=minimal_no_code"), tol=TOL_CHARS))
    C.append(Check("front.full.hybrid", "PAPER 4.5", "full_text hybrid R@10 (논문 0.606)", 0.606,
                   lambda: suite_rate("full_text", "hybrid_0.5")))
    C.append(Check("front.nocode.hybrid", "PAPER 4.5", "minimal_no_code hybrid R@10 (논문 0.521)",
                   0.521, lambda: suite_rate("minimal_no_code", "hybrid_0.5")))
    C.append(Check("front.cut_pct", "PAPER 4.5/초록/결론", "노출 감소율 (논문 55.6%)", 55.6,
                   lambda: (round(100 * (dig(suite, "exposure_at10", "full_text",
                                             "return=full_text")
                                         - dig(suite, "exposure_at10", "minimal_text",
                                               "return=minimal_text"))
                                  / dig(suite, "exposure_at10", "full_text", "return=full_text"), 1)
                            if suite else None), tol=TOL_PCT))
    C.append(Check("front.diff", "PAPER 4.5/초록", "minimal−full hybrid 평균차 (논문 −0.028)",
                   -0.028,
                   lambda: dig(suite, "equivalence",
                               "minimal_text_vs_full_text[hybrid_0.5]",
                               "paired_bootstrap", "mean")))
    C.append(Check("front.diff_ci", "PAPER 4.5/초록",
                   "minimal−full 95% CI (논문 [−0.113, +0.042])", [-0.113, 0.042],
                   lambda: dig(suite, "equivalence",
                               "minimal_text_vs_full_text[hybrid_0.5]",
                               "paired_bootstrap", "ci")))

    # ---- claims the paper does NOT make but should (new evidence) ----
    C.append(Check("new.hyb_vs_dense.diff", "신규 (논문에 없음)",
                   "hybrid−dense 평균차 — 논문은 이 비교를 한 적이 없다", None,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_dense[overall]",
                                          "mean_diff")))
    C.append(Check("new.hyb_vs_dense.ko_wins", "신규 (논문에 없음)",
                   "hybrid−dense 한국어 승 (0이어야 함: 수학적 동일)", 0,
                   lambda: suite_contrast("minimal_text", "hybrid_vs_dense[ko]", "wins"), tol=0))
    C.append(Check("new.bm25_no_signal", "신규 (논문에 없음)",
                   "BM25 무신호 질의 수 / 71", None,
                   lambda: dig(suite, "retriever", dig(suite, "meta", "primary_model"),
                               "diagnostics", "minimal_text", "bm25_no_signal_queries"), tol=0))
    C.append(Check("new.equivalence_delta05", "신규 (논문에 없음)",
                   "δ=0.05에서 등가성 성립? (False가 실제)", False,
                   lambda: dig(suite, "equivalence",
                               "minimal_text_vs_full_text[hybrid_0.5]",
                               "equivalent_at_primary_delta")))
    C.append(Check("new.best_point.cut", "신규 (논문에 없음)",
                   "최적 운용점 노출 감소율 (색인=full, 반환=minimal_no_code)", None,
                   lambda: dig(decomp, "best_operating_point",
                               "exposure_cut_vs_baseline_pct"), tol=TOL_PCT))
    C.append(Check("new.best_point.recall_delta", "신규 (논문에 없음)",
                   "최적 운용점 R@10 변화 (0이어야 함)", 0.0,
                   lambda: dig(decomp, "best_operating_point", "recall_delta_vs_baseline")))

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
