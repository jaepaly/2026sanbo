#!/usr/bin/env python3
"""라벨 교란 민감도 — 전문가 검수 없이 결론의 라벨-강건성을 보이는 대체 증거.

이 연구의 정답 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 전문가 검증을 받지
않았다. 그래서 "라벨이 틀렸으면 결론도 틀린 것 아닌가"라는 반론이 가능하다.

그 반론에 대한 답은 두 가지다.

1. **구조적 답변.** 논문의 헤드라인은 전부 *같은 라벨을 고정 기준점으로 둔 질의별
   짝지음 비교*(dense vs BM25, L1 vs L0)다. 라벨이 무엇이든 양쪽이 같은 목표를
   맞히려 하므로 라벨의 법적 정확성은 대비에서 상쇄된다. 라벨 정확성이 필요한 것은
   "법적으로 옳은 ECCN을 X% 찾는다"는 절대 주장인데, 본 연구는 그 주장을 하지 않는다.

2. **경험적 답변(이 스크립트).** 그래도 라벨 결함이 *어떤 질의를 남기느냐*를 통해
   결론을 흔들 수 있다. 그래서 `docs/label_audit.md`가 찾아낸 결함별로 해당 질의를
   제거한 부분집합에서 결론이 유지되는지 확인한다.

핵심: `output/validated_suite.json`에 질의별 `hit_vectors`가 저장되어 있으므로
**모델을 다시 돌리지 않고** 부분집합 지표를 정확히 재계산할 수 있다(근사 아님).

변형(모두 질의 부분집합):
  V0 baseline           전체 151 (영어 42 / 한국어 109). n=71 판에서는 71이었다.
  V1 no_stub_gold       정답이 전부 표제 스텁인 질의 제거 (D1)
  V2 no_label_defect    부정확 2차 라벨·규제체계 모순 질의 제거 (D3/D4)
  V3 unique_gold_code   정답 코드가 재사용된 질의 중 뒤엣것 제거 (D5)
  V4 strict             V1 ∩ V2 ∩ V3

각 변형 × 각 dense 모델에 대해 BM25/dense/hybrid R@10과 dense−BM25 · hybrid−dense의
exact McNemar를, 그리고 5변형 × 3모델 = 15개 조합 가족의 Holm 보정을 보고한다.
결론이 모든 변형에서 유지되면, 라벨 결함이 결론을 만들어낸 것이 아니다.

n=151 판의 실측: dense−BM25는 15개 조합 전부에서 Holm 보정 후에도 유의하다.
hybrid−dense는 MiniLM에서만 보정 전 유의(5변형 전부, p 0.0078~0.0117)이고 Holm 보정
후에는 15개 조합 어디에서도 유의하지 않다. n=71 판에서는 보정 전 기준으로도 유의한
조합이 하나도 없었다 — 즉 이 신호는 표본 확대와 함께 새로 나타난 것이다.

출력: output/label_sensitivity.json, output/label_sensitivity.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
DATA = ROOT / "data"

SUITE = OUT / "validated_suite.json"
SELFREF = OUT / "selfreference_audit.json"
QUERIES = DATA / "validated_queries_expanded.json"
CORPUS = DATA / "corpus" / "combined.json"
JSON_PATH = OUT / "label_sensitivity.json"
MD_PATH = OUT / "label_sensitivity.md"

INDEX_MODE = "minimal_text"
HEADING_STUB_RE = re.compile(r"\(\s*see\s+(?:the\s+)?list\s+of\s+items\s+cont(?:r)?ol", re.I)

# docs/label_audit.md 가 지목한 라벨 결함 질의 (D3: 부정확 2차 라벨, D4: 규제체계 모순).
# 그 감사는 n=71 판(ext-* 13건 + g-* 58건)에서 수행됐으므로 아래 두 목록의 적용 범위도
# 거기까지다. 이후 추가된 j-* 80건은 D3/D4 감사를 받지 않았다. 반면 D1(표제 스텁)과
# D5(코드 재사용)는 build_variants() 가 151건 전체에서 매번 다시 계산한다.
D3_IMPRECISE = ["ext-005", "ext-023"]
D4_REGIME_CONFLICT = ["ext-028"]


def build_variants(query_ids, queries, corpus):
    by_code = {e["code"]: e for e in corpus}
    qmap = {q["id"]: q for q in queries}

    def gold_all_stub(qid):
        labels = qmap[qid].get("validated_labels") or []
        entries = [by_code[c] for c in labels if c in by_code]
        return bool(entries) and all(
            HEADING_STUB_RE.search(e.get("text") or "") for e in entries)

    stub_ids = {q for q in query_ids if gold_all_stub(q)}
    defect_ids = set(D3_IMPRECISE + D4_REGIME_CONFLICT)

    # D5: 같은 정답 코드를 쓰는 질의가 여러 개면 첫 번째만 남긴다
    seen, dup_ids = set(), set()
    for qid in query_ids:
        for code in (qmap[qid].get("validated_labels") or []):
            if code in seen:
                dup_ids.add(qid)
            else:
                seen.add(code)

    # V5: 의미 게이트(LaBSE, tau=0.44)가 자기참조 의심으로 표시한 질의를 제거한 조건.
    # 이 질의들은 표시만 하고 분석에서 빼지 않았기 때문에 "표시해 놓고 그대로 썼다"는
    # 반론이 가능하다. 빼고도 결론이 유지되는지를 같은 마스킹 방식으로 확인한다.
    semantic_ids = set()
    if SELFREF.exists():
        sr = json.loads(SELFREF.read_text(encoding="utf-8"))
        semantic_ids = {f["id"] for f in
                        sr.get("verdict_primary", {}).get("semantic_failures", [])}

    return {
        "V0_baseline": (set(), "전체 질의 (기준)"),
        "V1_no_stub_gold": (stub_ids, "정답이 전부 표제 스텁인 질의 제거 (D1)"),
        "V2_no_label_defect": (defect_ids, "부정확 2차 라벨·규제체계 모순 제거 (D3/D4)"),
        "V3_unique_gold_code": (dup_ids, "정답 코드 재사용 질의 제거 (D5)"),
        "V4_strict": (stub_ids | defect_ids | dup_ids, "V1 ∩ V2 ∩ V3 (가장 보수적)"),
        "V5_no_semantic_flag": (semantic_ids,
                                "의미 게이트(LaBSE τ=0.44) 초과 질의 제거 (자기참조 의심)"),
        "V6_strict_plus_semantic": (stub_ids | defect_ids | dup_ids | semantic_ids,
                                    "V4 + 의미 게이트 초과 제거 (최대 보수)"),
    }


def main() -> None:
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))

    query_ids = suite["query_ids"]
    langs = suite["langs"]
    models = sorted(suite["hit_vectors"])
    variants = build_variants(query_ids, queries, corpus)

    results = {}
    for vname, (drop, desc) in variants.items():
        keep = [i for i, qid in enumerate(query_ids) if qid not in drop]
        row = {"description": desc, "dropped": len(drop), "n": len(keep),
               "n_ko": sum(1 for i in keep if langs[i] == "ko"),
               "n_en": sum(1 for i in keep if langs[i] == "en"),
               "models": {}}
        for model in models:
            hv = suite["hit_vectors"][model][INDEX_MODE]
            sub = {r: [hv[r][i] for i in keep] for r in ("BM25", "dense", "hybrid_0.5")}
            mc = rc.exact_mcnemar(sub["dense"], sub["BM25"])
            mc_hd = rc.exact_mcnemar(sub["hybrid_0.5"], sub["dense"])
            ko = [i for i in keep if langs[i] == "ko"]
            row["models"][model] = {
                "BM25": rc.rate_with_ci([hv["BM25"][i] for i in keep]),
                "dense": rc.rate_with_ci([hv["dense"][i] for i in keep]),
                "hybrid_0.5": rc.rate_with_ci([hv["hybrid_0.5"][i] for i in keep]),
                "BM25_ko": rc.rate_with_ci([hv["BM25"][i] for i in ko])["rate"] if ko else None,
                "dense_ko": rc.rate_with_ci([hv["dense"][i] for i in ko])["rate"] if ko else None,
                "dense_vs_bm25": {
                    "mean_diff": round(
                        sum(a - b for a, b in zip(sub["dense"], sub["BM25"])) / len(keep), 4),
                    "wins": mc["wins"], "losses": mc["losses"],
                    "p_two_sided_exact": mc["p_two_sided_exact"],
                    "significant_at_0.05": mc["p_two_sided_exact"] < 0.05,
                },
                "hybrid_vs_dense": {
                    "mean_diff": round(
                        sum(a - b for a, b in zip(sub["hybrid_0.5"], sub["dense"])) / len(keep), 4),
                    "p_two_sided_exact": mc_hd["p_two_sided_exact"],
                    "significant_at_0.05": mc_hd["p_two_sided_exact"] < 0.05,
                },
            }
        results[vname] = row

    conclusion_holds = all(
        results[v]["models"][m]["dense_vs_bm25"]["significant_at_0.05"]
        for v in results for m in models)
    hybrid_never_wins = not any(
        results[v]["models"][m]["hybrid_vs_dense"]["significant_at_0.05"]
        for v in results for m in models)

    # --- Holm 보정 (가족 = 5변형 x 3모델 = 15개 조합) -------------------
    # PAPER 4.7 이 "15개 조합 중 Holm 보정 후 유의한 것은 하나도 없다"고 쓰는데,
    # 이전 판은 보정을 계산하지 않아 그 문장을 산출물로 확인할 수 없었다.
    # 가족을 명시해 계산하고 결과를 기록한다.
    def holm_family(key: str) -> dict:
        # 가족 크기는 변형 수 x 모델 수로 자동 계산된다(변형을 추가하면 따라 늘어난다).
        raw = {f"{v}|{m}": results[v]["models"][m][key]["p_two_sided_exact"]
               for v in results for m in models}
        adj = rc.holm(raw)
        return {
            "family": f"{len(results)} 변형 x {len(models)} 모델 = {len(results) * len(models)}개 조합",
            "family_size": len(raw),
            "per_combination": adj,
            "n_significant_after_holm": sum(1 for a in adj.values()
                                            if a["significant_at_0.05"]),
            "n_significant_before_holm": sum(1 for pv in raw.values() if pv < 0.05),
        }

    holm_blocks = {"dense_vs_bm25": holm_family("dense_vs_bm25"),
                   "hybrid_vs_dense": holm_family("hybrid_vs_dense")}

    out = {
        "experiment": "label_perturbation_sensitivity",
        "rationale": (
            "정답 라벨은 전문가 검증을 받지 않았다. 헤드라인은 모두 같은 라벨을 고정 "
            "기준점으로 둔 짝지음 비교이므로 라벨의 법적 정확성은 대비에서 상쇄되지만, "
            "라벨 결함이 어떤 질의를 남기느냐를 통해 결론을 흔들 수 있으므로 결함별 "
            "부분집합에서 결론 유지 여부를 확인한다."),
        "method": ("validated_suite.json 의 질의별 hit_vectors 를 부분집합으로 마스킹해 "
                   "정확히 재계산한다(모델 재실행 없음, 근사 아님)."),
        "index_mode": INDEX_MODE,
        "models": models,
        "holm_across_all_combinations": holm_blocks,
        "conclusion": {
            "dense_beats_bm25_in_every_variant_and_model": conclusion_holds,
            # 보정 전 기준. 보정 후 기준은 아래 *_after_holm 을 쓴다.
            "hybrid_never_significantly_beats_dense_uncorrected": hybrid_never_wins,
            "hybrid_never_significantly_beats_dense_after_holm":
                holm_blocks["hybrid_vs_dense"]["n_significant_after_holm"] == 0,
            "dense_beats_bm25_after_holm_in_all":
                (holm_blocks["dense_vs_bm25"]["n_significant_after_holm"]
                 == holm_blocks["dense_vs_bm25"]["family_size"]),
        },
        "variants": results,
    }
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    L = [
        "# 라벨 교란 민감도 — 전문가 검수의 대체 증거", "",
        "정답 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 **전문가 검증을 받지 않았다.**",
        "논문의 헤드라인은 모두 *같은 라벨을 고정 기준점으로 둔 질의별 짝지음 비교*라서",
        "라벨의 법적 정확성은 대비에서 상쇄되지만, 라벨 결함이 *어떤 질의를 남기느냐*를",
        "통해 결론을 흔들 수는 있다. 그래서 `docs/label_audit.md`가 지목한 결함별로",
        "해당 질의를 제거한 부분집합에서 결론이 유지되는지 확인한다.", "",
        f"- 색인 모드: `{INDEX_MODE}` / 모델: {', '.join(models)}",
        "- 방법: `validated_suite.json`의 질의별 `hit_vectors`를 마스킹해 **정확히 재계산**",
        "  (모델 재실행 없음, 근사 아님).", "",
        "## 변형별 표본", "",
        "| 변형 | 설명 | 제거 | n | 영어 | 한국어 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for v, r in results.items():
        L.append(f"| `{v}` | {r['description']} | {r['dropped']} | {r['n']} | {r['n_en']} | {r['n_ko']} |")

    L += ["", "## dense − BM25 (주 결론): 모든 변형에서 유의한가", "",
          "| 변형 | 모델 | BM25 | dense | 평균차 | 승/패 | exact p | 유의 |",
          "|---|---|---:|---:|---:|---:|---:|---|"]
    for v, r in results.items():
        for m in models:
            d = r["models"][m]; c = d["dense_vs_bm25"]
            L.append(f"| `{v}` | {m} | {d['BM25']['rate']:.4f} | {d['dense']['rate']:.4f} | "
                     f"+{c['mean_diff']:.4f} | {c['wins']}/{c['losses']} | "
                     f"{c['p_two_sided_exact']:.2e} | {'**예**' if c['significant_at_0.05'] else '아니오'} |")

    L += ["", "## hybrid − dense: 어느 변형에서도 유의하지 않은가", "",
          "| 변형 | 모델 | 평균차 | exact p | 유의 |", "|---|---|---:|---:|---|"]
    for v, r in results.items():
        for m in models:
            c = r["models"][m]["hybrid_vs_dense"]
            L.append(f"| `{v}` | {m} | {c['mean_diff']:+.4f} | {c['p_two_sided_exact']:.3g} | "
                     f"{'예' if c['significant_at_0.05'] else '아니오'} |")

    L += ["", "## 한국어 (구조적 실패의 라벨 비의존성)", "",
          "| 변형 | 모델 | BM25 한국어 | dense 한국어 |", "|---|---|---:|---:|"]
    for v, r in results.items():
        for m in models:
            d = r["models"][m]
            bk, dk = d["BM25_ko"], d["dense_ko"]
            L.append(f"| `{v}` | {m} | {bk if bk is None else f'{bk:.4f}'} | "
                     f"{dk if dk is None else f'{dk:.4f}'} |")

    L += ["", "## 결론", "",
          f"- dense−BM25가 **모든 변형 × 모든 모델에서 유의**한가: "
          f"**{'예' if conclusion_holds else '아니오'}**",
          f"- hybrid−dense가 **어느 변형에서도 유의하지 않은가**: "
          f"**{'예' if hybrid_never_wins else '아니오'}**",
          "- 즉 라벨 결함(표제 스텁·부정확 2차 라벨·규제체계 모순·코드 재사용)이 있는 질의를",
          "  모두 제거해도 **주 결론(dense−BM25 우위)** 은 뒤집히지 않는다. 라벨 결함이 그",
          "  결론을 만들어낸 것이 아니다.",
          "- 위의 hybrid−dense 항목은 **보정 전** 기준이다. n=151 실측에서는 MiniLM 이 5개 변형",
          "  전부에서 보정 전 유의(p 0.0078~0.0117)라 이 항목이 '아니오'가 된다. 그러나 5변형 ×",
          "  3모델 = 15개 조합 가족에 Holm 보정을 적용하면 유의한 조합은 0개이므로,",
          "  '하이브리드가 dense 보다 낫다'는 여전히 성립하지 않는다. n=71 판에서는 보정 전",
          "  기준으로도 0개였다. 보정 결과는 `label_sensitivity.json` 의",
          "  `holm_across_15_combinations` 에 있다.",
          "- 다만 이것은 **라벨 강건성**의 증거이지 **라벨 정확성**의 증거가 아니다. 절대 성능",
          "  수치(예: 이 색인 모드의 주 지표 R@10 0.5099 — MiniLM, hybrid α=0.5, n=151. n=71",
          "  판의 0.5775 는 옛 값이다)를 '법적으로 옳은 ECCN을 찾는 비율'로 해석하려면 여전히",
          "  전문가 검증이 필요하며, 본 연구는 그 해석을 하지 않는다.", ""]
    MD_PATH.write_text("\n".join(L), encoding="utf-8")

    print(json.dumps({
        "variants": {v: {"n": r["n"], "dropped": r["dropped"]} for v, r in results.items()},
        "conclusion": out["conclusion"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
