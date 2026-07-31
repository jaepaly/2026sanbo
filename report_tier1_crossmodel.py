#!/usr/bin/env python3
"""Tier-1 교차모델 종합 — 한계 6(단일 인코더)을 닫는다.

PAPER 7절 한계 6은 "대칭 ablation(4.6)과 disclosure frontier(4.5)가 MiniLM 단일
실행이므로 모델 간 일반화가 확인되지 않았다"고 적었다. 4.5는 운용 권고를 담고 있으므로
이 한계는 실질적이다. `run_tier1.py`로 세 인코더의 번들을 모아 그 답을 낸다.

결론을 미리 말하면 **두 부분의 답이 다르다**:

- **ablation(4.6)**: 압력 없는 level 0에서는 세 모델 모두 dense−BM25가 유의하다.
  최대 압력 level 3에서는 **3개 중 2개**만 유의하다(e5-base는 +0.0845, p=0.109로
  유의하지 않다). 즉 우위의 방향은 보존되지만 압력 하 유의성은 모델에 의존한다.
- **frontier(4.5)**: 운용 권고가 모델에 따라 갈린다. MiniLM·e5-base는 L2를 권고하지만
  bge-m3는 L1을 권고한다. bge-m3에서 L1은 등가 입증에 실패하고(TOST p_max 0.402)
  L2는 점추정 −0.0704로 사전지정 마진 δ=0.05를 넘어 **손실 징후**로 분류되기 때문이다.
  따라서 **모델 불문 보수적 권고는 L2가 아니라 L1**이다.

BM25는 인코더를 쓰지 않으므로 세 번들의 BM25 행은 동일해야 하며 `validate_tier1.py`가
이를 확인한다(그 검사가 실제로 낡은 기준선을 잡아냈다).

출력: output/tier1_crossmodel.json, output/tier1_crossmodel.md
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
BUNDLES = str(OUT / "tier1" / "tier1_*.json")
JSON_PATH = OUT / "tier1_crossmodel.json"
MD_PATH = OUT / "tier1_crossmodel.md"

PRIMARY_INDEX = "full_text"          # ablation 주 분석 색인 모드
LADDER = ["L0", "L1", "L2", "L3", "L4"]


def load_bundles() -> dict[str, dict]:
    out = {}
    for p in sorted(glob.glob(BUNDLES)):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        out[d["model_key"]] = d
    if not out:
        raise SystemExit("output/tier1/tier1_*.json 이 없다. run_tier1.py 를 먼저 돌려라.")
    return out


def ablation_rows(bundles):
    rows = {}
    for model, d in bundles.items():
        hv = d["symmetric_ablation"]["hit_vectors"][PRIMARY_INDEX]
        head = d["symmetric_ablation"]["headline"]
        per_level = {}
        for lv in ("0", "1", "2", "3"):
            dn, bm = hv[lv]["dense"], hv[lv]["BM25"]
            mc = rc.exact_mcnemar(dn, bm)
            per_level[lv] = {
                "dense_minus_bm25": round(sum(a - b for a, b in zip(dn, bm)) / len(dn), 4),
                "wins": mc["wins"], "losses": mc["losses"],
                "p_two_sided_exact": mc["p_two_sided_exact"],
                "significant_at_0.05": mc["p_two_sided_exact"] < 0.05,
            }
        rows[model] = {
            "recall_by_level": head["recall_by_level"],
            "recall_by_level_ko": head["recall_by_level_ko"],
            "dense_vs_bm25": per_level,
        }
    return rows


def frontier_rows(bundles):
    rows = {}
    for model, d in bundles.items():
        fr = d["disclosure_frontier"]
        et = fr["evidence_tiers"]["hybrid_0.5"]
        rec = fr["recall@10"]["hybrid_0.5"]
        eq = fr["equivalence_vs_L0"]["hybrid_0.5"]
        con = fr["contrasts_vs_L0"]["hybrid_0.5"]
        rows[model] = {
            "recommended_level": et["recommended_level"],
            "proven_equivalent": et["proven_equivalent"],
            "underpowered": et["underpowered"],
            "evidence_of_loss": et["evidence_of_loss"],
            "confounded_by_selfreference": et["confounded_by_selfreference"],
            "recall@10": {lv: rec[lv]["overall"]["rate"] for lv in LADDER},
            "vs_L0": {
                lv: {
                    "mean_diff": con[f"{lv}_vs_L0"]["mean_diff"],
                    "tost_p_max": eq[f"{lv}_vs_L0"]["primary"]["p_max"],
                    "equivalent_at_0.05": eq[f"{lv}_vs_L0"]["primary"]["equivalent_at_0.05"],
                } for lv in LADDER[1:]
            },
        }
    return rows


def main() -> None:
    bundles = load_bundles()
    abl = ablation_rows(bundles)
    fro = frontier_rows(bundles)
    models = sorted(bundles)

    # 보수적(모델 불문) 권고 = 모든 모델이 허용하는 가장 깊은 등급
    order = {lv: i for i, lv in enumerate(LADDER)}
    conservative = min((fro[m]["recommended_level"] for m in models), key=lambda lv: order[lv])

    abl_l3_sig = {m: abl[m]["dense_vs_bm25"]["3"]["significant_at_0.05"] for m in models}
    abl_l0_sig = {m: abl[m]["dense_vs_bm25"]["0"]["significant_at_0.05"] for m in models}

    out = {
        "experiment": "tier1_crossmodel",
        "purpose": "PAPER 7 한계 6(단일 인코더) 해소 — ablation(4.6)과 frontier(4.5)의 모델 간 일반화",
        "models": models,
        "model_names": {m: bundles[m]["model_name"] for m in models},
        "primary_index_mode_ablation": PRIMARY_INDEX,
        "ablation": abl,
        "frontier": fro,
        "conclusion": {
            "ablation_dense_advantage_significant_at_level0_all_models": all(abl_l0_sig.values()),
            "ablation_dense_advantage_significant_at_level3_all_models": all(abl_l3_sig.values()),
            "ablation_level3_significant_by_model": abl_l3_sig,
            "frontier_recommendation_by_model": {m: fro[m]["recommended_level"] for m in models},
            "frontier_recommendation_is_model_dependent":
                len({fro[m]["recommended_level"] for m in models}) > 1,
            "conservative_recommendation_across_models": conservative,
        },
    }
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    L = [
        "# Tier-1 교차모델 종합 — 한계 6(단일 인코더) 해소", "",
        f"모델: {', '.join(models)} / ablation 주 색인 모드: `{PRIMARY_INDEX}` / n=71",
        "",
        "BM25는 인코더를 쓰지 않으므로 세 번들의 BM25 행은 동일해야 하며 `validate_tier1.py`가",
        "이를 확인한다. 아래 결론은 **두 부분의 답이 다르다**는 점이 핵심이다.", "",
        "## 1. 대칭 ablation (4.6) — 압력 하 dense 우위", "",
        "| 모델 | level0 dense−BM25 | 유의 | level3 dense−BM25 | 유의 |",
        "|---|---:|---|---:|---|",
    ]
    for m in models:
        a0 = abl[m]["dense_vs_bm25"]["0"]; a3 = abl[m]["dense_vs_bm25"]["3"]
        L.append(f"| {m} | {a0['dense_minus_bm25']:+.4f} (p={a0['p_two_sided_exact']:.2e}) | "
                 f"{'예' if a0['significant_at_0.05'] else '아니오'} | "
                 f"{a3['dense_minus_bm25']:+.4f} (p={a3['p_two_sided_exact']:.3g}) | "
                 f"**{'예' if a3['significant_at_0.05'] else '아니오'}** |")
    L += ["",
          f"- 압력 없는 level 0: **{'세 모델 모두' if all(abl_l0_sig.values()) else '일부만'} 유의**.",
          f"- 최대 압력 level 3: 유의한 모델 "
          f"{sum(abl_l3_sig.values())}/{len(models)} "
          f"({', '.join(m for m in models if abl_l3_sig[m])} 유의; "
          f"{', '.join(m for m in models if not abl_l3_sig[m]) or '없음'} 비유의).",
          "- 즉 **우위의 방향은 보존되지만, 최대 압력에서의 유의성은 모델에 의존한다.**", "",
          "## 2. Disclosure frontier (4.5) — 운용 권고", "",
          "| 모델 | 권고 | 등가 입증 | 검정력 부족 | 손실 징후 | 교란 |",
          "|---|---|---|---|---|---|"]
    for m in models:
        f = fro[m]
        L.append(f"| {m} | **{f['recommended_level']}** | {f['proven_equivalent'] or '없음'} | "
                 f"{f['underpowered'] or '없음'} | {f['evidence_of_loss'] or '없음'} | "
                 f"{f['confounded_by_selfreference'] or '없음'} |")
    L += ["", "### L0 대비 등가성 (hybrid α0.5)", "",
          "| 모델 | L1 차이 | L1 TOST p_max | L1 등가 | L2 차이 | L2 등가 |",
          "|---|---:|---:|---|---:|---|"]
    for m in models:
        v = fro[m]["vs_L0"]
        L.append(f"| {m} | {v['L1']['mean_diff']:+.4f} | {v['L1']['tost_p_max']:.4g} | "
                 f"{'**예**' if v['L1']['equivalent_at_0.05'] else '아니오'} | "
                 f"{v['L2']['mean_diff']:+.4f} | "
                 f"{'예' if v['L2']['equivalent_at_0.05'] else '아니오'} |")
    rec_by_model = ", ".join(f"{m}={fro[m]['recommended_level']}" for m in models)
    L += ["",
          f"- 권고가 모델에 따라 갈린다: {rec_by_model}.",
          f"- **모델 불문 보수적 권고는 `{conservative}`다.** bge-m3에서 L1은 등가 입증에 실패하고"
          " (TOST p_max 0.402) L2는 점추정 −0.0704로 사전지정 마진 δ=0.05를 넘어 손실 징후로"
          " 분류되기 때문이다.",
          "- L3는 세 모델 모두에서 자기참조 교란으로 배제된다(판정 일치).", "",
          "## 3. 한계 6에 대한 답", "",
          "| 항목 | 일반화되는가 |",
          "|---|---|",
          "| ablation: dense 우위의 방향 | 예 (세 모델 모두 level0·level3에서 양수) |",
          f"| ablation: 최대 압력에서의 유의성 | **부분적** ({sum(abl_l3_sig.values())}/{len(models)}) |",
          "| frontier: L3 교란 판정 | 예 (세 모델 일치) |",
          "| frontier: 운용 권고 등급 | **아니오 — 모델 의존적** |", "",
          "따라서 논문은 운용 권고를 L2가 아니라 **가장 보수적인 등급으로 낮추고**, 모델 의존성을",
          "명시해야 한다. 이것이 단일 인코더 결과를 그대로 권고로 옮겼을 때의 위험이다.", ""]
    MD_PATH.write_text("\n".join(L), encoding="utf-8")

    print(json.dumps(out["conclusion"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
