#!/usr/bin/env python3
"""Decompose 'information minimisation' into its two independent channels.

The original design used one function (`build_doc_text`) as both the retrieval
index text and the definition of how much information is disclosed. That single
coupling produced the paper's central claim and, at the same time, made the
claim untestable: any reduction in disclosure necessarily degraded the index, so
the observed recall drop was attributed to disclosing less when it was actually
caused by indexing less.

Once the two are separated (`retrieval_core.index_text` vs `returned_text`) the
question splits cleanly:

  return-side reduction   the service ranks on the full text but hands back
                          less of it. The ranking is bit-identical, so recall is
                          unchanged *by construction* -- disclosure reduction on
                          this channel is free, and the only question is how much
                          text the caller actually needs.

  index-side reduction    the service indexes less text. This genuinely changes
                          the ranking and is where a recall cost can appear.
                          This is the only channel where an equivalence test is
                          meaningful.

Reads output/validated_suite.json (or the MiniLM smoke variant) and writes
output/exposure_decomposition.{json,md}, including the Pareto frontier over all
(index_mode, return_mode) cells.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"
FULL = OUT_DIR / "validated_suite.json"
SMOKE = OUT_DIR / "validated_suite_smoke.json"
JSON_PATH = OUT_DIR / "exposure_decomposition.json"
MD_PATH = OUT_DIR / "exposure_decomposition.md"


def load() -> tuple[dict, str]:
    if FULL.exists():
        return json.loads(FULL.read_text(encoding="utf-8")), FULL.name
    if SMOKE.exists():
        print(f"note: {FULL.name} not found, using {SMOKE.name} (single encoder)")
        return json.loads(SMOKE.read_text(encoding="utf-8")), SMOKE.name
    print("error: run experiment_validated_suite.py first", file=sys.stderr)
    raise SystemExit(1)


# A return mode is only a usable operating point if the caller can still tell
# *which* control item was retrieved. `minimal_no_code` strips the control number
# from the returned text, so recall@10 -- which is scored against corpus metadata,
# not against what was actually handed back -- overstates its usefulness: the
# caller receives sentences with no identifier to act on. The task is candidate
# *lookup*, so the control number is the deliverable, not an optional extra.
ACTIONABLE_RETURN_MODES = {"full_text", "minimal_text"}


def is_actionable(return_mode: str) -> bool:
    return return_mode in ACTIONABLE_RETURN_MODES


def pareto(cells: list[dict]) -> list[dict]:
    """Cells not dominated by another with <= exposure and >= recall."""
    out = []
    for c in cells:
        dominated = any(
            o is not c
            and o["exposure_at10"] <= c["exposure_at10"]
            and o["recall@10"] >= c["recall@10"]
            and (o["exposure_at10"] < c["exposure_at10"] or o["recall@10"] > c["recall@10"])
            for o in cells
        )
        if not dominated:
            out.append(c)
    return sorted(out, key=lambda c: c["exposure_at10"])


def main() -> None:
    suite, src = load()
    m = suite["meta"]
    pm = m["primary_model"]
    prim_alpha = m["primary_alpha"]
    prim_name = "hybrid_%s" % prim_alpha if prim_alpha not in (0.0, 1.0) else (
        "dense" if prim_alpha == 0.0 else "BM25")
    index_modes = m["index_modes"]
    return_modes = m["return_modes"]

    hits = suite["hit_vectors"][pm]
    exposure_at10 = suite["exposure_at10"]

    # ---- all 9 cells: recall depends only on index mode, exposure on both ----
    cells = []
    for imode in index_modes:
        r = rc.rate_with_ci(hits[imode][prim_name])
        for rmode in return_modes:
            cells.append({
                "index_mode": imode,
                "return_mode": rmode,
                "exposure_at10": exposure_at10[imode][f"return={rmode}"],
                "recall@10": r["rate"],
                "recall@10_ci95": r["ci95"],
                "k": r["k"],
                "n": r["n"],
                "actionable": is_actionable(rmode),
            })

    baseline = next(c for c in cells
                    if c["index_mode"] == "full_text" and c["return_mode"] == "full_text")

    # ---- channel 1: return-side (index fixed) -> recall invariant ----
    return_side = {}
    for imode in index_modes:
        base = next(c for c in cells if c["index_mode"] == imode and c["return_mode"] == imode)
        rows = []
        for rmode in return_modes:
            c = next(x for x in cells if x["index_mode"] == imode and x["return_mode"] == rmode)
            rows.append({
                "return_mode": rmode,
                "actionable": c["actionable"],
                "exposure_at10": c["exposure_at10"],
                "exposure_cut_pct_vs_same_mode": round(
                    100 * (base["exposure_at10"] - c["exposure_at10"]) / base["exposure_at10"], 1),
                "recall@10": c["recall@10"],
                "recall_delta": round(c["recall@10"] - base["recall@10"], 4),
            })
        return_side[imode] = {
            "ranking_invariant": True,
            "reason": "return_text never enters the index, so top-10 is bit-identical "
                      "across return modes for a fixed index mode",
            "rows": rows,
        }

    # ---- channel 2: index-side (the only channel with a real trade-off) ----
    index_side = {}
    base_hits = hits["full_text"][prim_name]
    for imode in index_modes:
        if imode == "full_text":
            continue
        a = hits[imode][prim_name]
        diffs = [x - y for x, y in zip(a, base_hits)]
        eq_key = f"{imode}_vs_full_text[{prim_name}]"
        eq = suite["equivalence"].get(eq_key, {})
        index_side[imode] = {
            "paired_bootstrap": rc.paired_bootstrap_ci(diffs, iters=m["bootstrap_iters"],
                                                       seed=m["seed"]),
            "mcnemar": rc.exact_mcnemar(a, base_hits),
            "tost_primary_delta": eq.get("tost", {}).get(
                f"delta={m['primary_equivalence_delta']}"),
            "equivalent_at_primary_delta": eq.get("equivalent_at_primary_delta"),
            "n_required_for_primary_delta": eq.get("n_required_for_primary_delta"),
        }

    frontier = pareto(cells)
    actionable_cells = [c for c in cells if c["actionable"]]
    frontier_actionable = pareto(actionable_cells)
    best_recall = max(actionable_cells, key=lambda c: (c["recall@10"], -c["exposure_at10"]))
    cheapest_at_best_recall = min(
        (c for c in actionable_cells if c["recall@10"] == best_recall["recall@10"]),
        key=lambda c: c["exposure_at10"])

    out = {
        "meta": {
            "source": src,
            "primary_model": pm,
            "primary_retriever": prim_name,
            "n": m["n"],
            "note": "recall@10 is a function of index_mode only; exposure_at10 is a "
                    "function of both. The original design tied them together.",
        },
        "env": rc.env_meta({"seed": m["seed"]}),
        "cells": cells,
        "baseline_cell": baseline,
        "return_side_channel": return_side,
        "index_side_channel": index_side,
        "pareto_frontier_all_cells": frontier,
        "pareto_frontier_actionable_only": frontier_actionable,
        "actionability_note": (
            "return_mode=minimal_no_code strips the control number from the returned "
            "text. recall@10 is scored against corpus metadata, so it does not fall, "
            "but the caller receives no identifier and cannot act on the result. Such "
            "cells are excluded from the operating-point search."
        ),
        "best_operating_point": {
            "cell": cheapest_at_best_recall,
            "exposure_cut_vs_baseline_pct": round(
                100 * (baseline["exposure_at10"] - cheapest_at_best_recall["exposure_at10"])
                / baseline["exposure_at10"], 1),
            "recall_delta_vs_baseline": round(
                cheapest_at_best_recall["recall@10"] - baseline["recall@10"], 4),
        },
    }
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(render(out, m), encoding="utf-8")
    print(json.dumps({
        "best_actionable_operating_point": out["best_operating_point"],
        "pareto_actionable": [(c["index_mode"], c["return_mode"], c["exposure_at10"],
                               c["recall@10"]) for c in frontier_actionable],
        "pareto_all_cells_incl_unactionable": [
            (c["index_mode"], c["return_mode"], c["exposure_at10"], c["recall@10"],
             c["actionable"]) for c in frontier],
    }, ensure_ascii=False, indent=2))


def render(out: dict, m: dict) -> str:
    mm = out["meta"]
    bp = out["best_operating_point"]
    base = out["baseline_cell"]
    L = [
        "# 정보최소화의 두 채널 분해 (반환 축소 vs 색인 축소)",
        "",
        f"출처 `{mm['source']}` / 검색기 {mm['primary_retriever']} / 임베딩 {mm['primary_model']} / n={mm['n']}",
        "",
        "## 왜 분해가 필요한가",
        "",
        "정정 전 설계는 하나의 함수(`build_doc_text`)를 **검색 색인 텍스트**와 **노출량 정의**에",
        "동시에 사용했다. 두 축이 묶여 있었으므로 노출을 줄이면 반드시 색인도 훼손되었고,",
        "그 결과 관측된 성능 하락이 '정보를 덜 공개한 탓'으로 귀속되었다. 실제 원인은",
        "'색인을 덜 넣은 탓'이다. 두 축을 분리하면 질문이 둘로 갈라진다.",
        "",
        "## 채널 1 — 반환 축소 (색인 고정): 성능 비용이 구조적으로 0",
        "",
        "반환 텍스트는 색인에 들어가지 않으므로 색인 모드가 같으면 top-10이 비트 단위로 동일하다.",
        "따라서 R@10은 반환 모드와 **무관**하다. 이는 실험 결과가 아니라 설계상의 항등식이다.",
        "",
        "| 색인 모드 | 반환 모드 | 노출량@10 | 노출 감소 | R@10 | R@10 변화 | 실사용 가능 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for imode, blk in out["return_side_channel"].items():
        for r in blk["rows"]:
            act = "예" if r.get("actionable") else "**아니오**"
            L.append(f"| {imode} | {r['return_mode']} | {r['exposure_at10']:.0f} | "
                     f"{r['exposure_cut_pct_vs_same_mode']:+.1f}% | {r['recall@10']:.4f} | "
                     f"{r['recall_delta']:+.4f} | {act} |")
    L += [
        "",
        "> 즉 **'서비스가 돌려주는 공개 통제목록 텍스트를 줄이는 것'은 성능을 전혀 해치지 않는다.**",
        "> 정정 전 설계는 이 조건을 표현할 수 없었기 때문에 유리한 운용점을 스스로 버리고 있었다.",
        "",
        "> **실사용 가능 열 주의.** `minimal_no_code`는 반환 텍스트에서 통제번호를 제거한다.",
        "> R@10은 코퍼스 메타데이터의 코드로 채점하므로 떨어지지 않지만, 사용자는 식별자 없는",
        "> 문장만 받게 되어 후보를 특정할 수 없다. 이 과업의 산출물은 '후보 통제번호'이므로",
        "> 통제번호를 지운 반환 모드는 운용점 후보에서 제외한다. 지표가 떨어지지 않는다는 것이",
        "> 곧 쓸 수 있다는 뜻은 아니다.",
        "",
        "> 이 채널이 절약하는 것은 공개 문서이므로 기업 영업비밀 보호와는 무관하다",
        "> (위협모형은 `docs/threat_model.md`, 실제 기업정보 노출은 질의 측 채널 참조).",
        "",
        "## 채널 2 — 색인 축소: 유일하게 실제 트레이드오프가 발생하는 축",
        "",
        f"사전지정 등가성 마진 δ={m['primary_equivalence_delta']}. 'CI가 0을 포함'은 등가성의 근거가 아니다.",
        "",
        "| 색인 축소 | 평균차 | 95% CI | 승/패/무 | exact p | δ=0.05 등가? | δ=0.05 필요 n |",
        "|---|---:|---|---:|---:|---|---:|",
    ]
    for imode, blk in out["index_side_channel"].items():
        b = blk["paired_bootstrap"]
        mc = blk["mcnemar"]
        L.append(f"| full_text → {imode} | {b['mean']:+.4f} | "
                 f"[{b['ci'][0]:.4f}, {b['ci'][1]:.4f}] | "
                 f"{mc['wins']}/{mc['losses']}/{mc['ties']} | {mc['p_two_sided_exact']:.3g} | "
                 f"{'예' if blk['equivalent_at_primary_delta'] else '**아니오**'} | "
                 f"{blk['n_required_for_primary_delta'] or '-'} |")
    L += [
        "",
        "## Pareto frontier — 실사용 가능한 반환 모드만",
        "",
        "| 색인 | 반환 | 노출량@10 | R@10 | 95% CI |",
        "|---|---|---:|---:|---|",
    ]
    for c in out["pareto_frontier_actionable_only"]:
        L.append(f"| {c['index_mode']} | {c['return_mode']} | {c['exposure_at10']:.0f} | "
                 f"{c['recall@10']:.4f} | [{c['recall@10_ci95'][0]:.3f}, {c['recall@10_ci95'][1]:.3f}] |")
    L += ["", "### 참고: 통제번호를 지운 반환 모드를 포함한 frontier", "",
          "| 색인 | 반환 | 노출량@10 | R@10 | 실사용 가능 |", "|---|---|---:|---:|---|"]
    for c in out["pareto_frontier_all_cells"]:
        L.append(f"| {c['index_mode']} | {c['return_mode']} | {c['exposure_at10']:.0f} | "
                 f"{c['recall@10']:.4f} | {'예' if c['actionable'] else '**아니오**'} |")
    c = bp["cell"]
    L += [
        "",
        "## 최적 운용점 (실사용 가능 조건 하)",
        "",
        f"**색인={c['index_mode']} / 반환={c['return_mode']}**",
        "",
        f"- 노출량@10: {base['exposure_at10']:.0f} → {c['exposure_at10']:.0f} "
        f"(**{bp['exposure_cut_vs_baseline_pct']:.1f}% 감소**)",
        f"- R@10: {base['recall@10']:.4f} → {c['recall@10']:.4f} "
        f"(**변화 {bp['recall_delta_vs_baseline']:+.4f}**)",
        "",
        "통제번호를 유지한 채 성능 손실 없이 반환 정보량을 줄일 수 있다. 이것이 '정보최소화가",
        "성능을 해치지 않는다'는 주장의 방어 가능한 형태다 — 단, 그 근거는 통계적 비유의가",
        "아니라 **반환 텍스트가 랭킹에 관여하지 않는다는 구조적 사실**이다. 정정 전 논문은",
        "같은 크기의 감소율을 보고했지만 그것은 색인을 훼손해 얻은 것이었고, 그래서 성능 손실이",
        "따라왔으며 그 손실을 '노출 축소의 대가'로 잘못 귀속했다.",
        "",
        "두 가지를 반드시 함께 적어야 한다.",
        "",
        "1. 이 채널이 절약하는 것은 **공개된** 통제목록 문언이다. 기업 영업비밀 보호와 무관하다.",
        "   실제 기업 기술정보는 질의 측에서 나가므로 그 측정이 별도로 필요하다",
        "   (`output/disclosure_frontier.md`, `docs/threat_model.md`).",
        "2. 색인 축소 채널에서는 사전지정 마진 δ=0.05의 등가성이 **성립하지 않는다**. 표본이",
        "   부족한 것이며(필요 n은 위 표 참조), '차이가 없다'로 서술할 수 없다.",
        "",
    ]
    return "\n".join(L)


if __name__ == "__main__":
    main()
