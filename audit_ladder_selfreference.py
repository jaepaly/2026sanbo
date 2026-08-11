#!/usr/bin/env python3
"""Does the disclosure ladder reduce exposure, or just increase self-reference?

`output/disclosure_frontier.md` reports that stripping every sensitive field (L3)
leaves hybrid R@10 unchanged at 0.5775, and that L3 actually scores *higher* than
L2 (0.5493). Removing information should not improve retrieval, so the ladder is
non-monotone and the frontier's headline needs a competing explanation ruled out:

  benign      the removed spans (destination, end user, transaction intent) were
              retrieval noise. Stripping them concentrates the query on function,
              which is what the corpus describes, so recall holds.

  confounded  the higher levels rewrite queries into pure function descriptions,
              which is exactly the register of the control-list text itself. The
              queries drift *toward* the gold document, so recall holds because
              self-reference went up, not because disclosure reduction is free.

These predict opposite things about semantic similarity to the gold entry. Benign
says cos(query, gold) stays flat or falls as spans are removed. Confounded says it
rises with the level.

This script measures that, reusing the language-neutral LaBSE gate from
`selfreference_gate.py` (an encoder deliberately not used for evaluation) so the
answer does not depend on the retrievers being tested. It also reports how the
similarity to non-gold corpus entries moves, since a query getting closer to
*every* control-list entry is a register shift rather than targeted leakage:
`margin = cos(query, gold) - mean cos(query, 20 non-gold entries)`.

Outputs: output/ladder_selfreference.{json,md}
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import retrieval_core as rc
import selfreference_gate as gate

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"
CORPUS_PATH = ROOT / "data" / "corpus" / "combined.json"
LADDER_PATH = ROOT / "data" / "disclosure_ladder.json"
FRONTIER_PATH = OUT_DIR / "disclosure_frontier.json"
JSON_PATH = OUT_DIR / "ladder_selfreference.json"
MD_PATH = OUT_DIR / "ladder_selfreference.md"

LEVELS = ["L0", "L1", "L2", "L3", "L4"]
N_NEG = 20
SEED = 20260626


def main() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    ladder = json.loads(LADDER_PATH.read_text(encoding="utf-8"))["queries"]
    by_code = {e["code"]: e for e in corpus}

    gate.assert_gate_model_is_independent()
    model = gate.load_gate_model()

    # gold entry text, encoded once
    gold_entries = [by_code[q["validated_labels"][0]] for q in ladder]
    gold_texts = [rc.index_text(e, "minimal_text") for e in gold_entries]
    gold_emb = gate.encode(gold_texts, model)

    # a fixed random set of non-gold entries per query, for the margin
    rng = np.random.default_rng(SEED)
    neg_idx = [rng.choice(len(corpus), size=N_NEG, replace=False) for _ in ladder]
    corpus_texts = [rc.index_text(e, "minimal_text") for e in corpus]
    corpus_emb = gate.encode(corpus_texts, model)

    per_level: dict[str, dict] = {}
    per_query: list[dict] = []
    cos_by_level: dict[str, list[float]] = {}

    for lvl in LEVELS:
        qtexts = [q["levels"][lvl]["query"] for q in ladder]
        q_emb = gate.encode(qtexts, model)
        cos_gold = [float(q_emb[i] @ gold_emb[i]) for i in range(len(ladder))]
        cos_neg = [float(np.mean(corpus_emb[neg_idx[i]] @ q_emb[i])) for i in range(len(ladder))]
        margin = [g - n for g, n in zip(cos_gold, cos_neg)]
        lex = [gate.lexical_overlap(qtexts[i], gold_texts[i])["jaccard"]
               for i in range(len(ladder))]
        cos_by_level[lvl] = cos_gold

        langs = [q["lang"] for q in ladder]
        def by_lang(vals, lang):
            v = [x for x, lg in zip(vals, langs) if lg == lang]
            return round(float(np.mean(v)), 4) if v else None

        per_level[lvl] = {
            "cos_gold_mean": round(float(np.mean(cos_gold)), 4),
            "cos_gold_median": round(float(np.median(cos_gold)), 4),
            "cos_gold_ko": by_lang(cos_gold, "ko"),
            "cos_gold_en": by_lang(cos_gold, "en"),
            "cos_nongold_mean": round(float(np.mean(cos_neg)), 4),
            "margin_mean": round(float(np.mean(margin)), 4),
            "margin_ko": by_lang(margin, "ko"),
            "margin_en": by_lang(margin, "en"),
            "lexical_jaccard_mean": round(float(np.mean(lex)), 4),
            "lexical_jaccard_ko": by_lang(lex, "ko"),
            "mean_sensitive_tokens": round(float(np.mean(
                [q["levels"][lvl]["sensitive_token_count"] for q in ladder])), 3),
            "mean_query_tokens": round(float(np.mean(
                [q["levels"][lvl]["token_count"] for q in ladder])), 2),
        }

    # paired tests: each level vs L0 on cos(query, gold)
    contrasts = {}
    pfam = {}
    for lvl in LEVELS[1:]:
        diffs = [a - b for a, b in zip(cos_by_level[lvl], cos_by_level["L0"])]
        boot = rc.paired_bootstrap_ci(diffs, seed=SEED)
        # sign test on the direction of drift
        up = sum(1 for d in diffs if d > 0)
        down = sum(1 for d in diffs if d < 0)
        mc = rc.exact_mcnemar([1 if d > 0 else 0 for d in diffs],
                              [1 if d < 0 else 0 for d in diffs])
        contrasts[f"{lvl}_vs_L0"] = {
            "mean_cos_shift": boot["mean"],
            "ci95": boot["ci"],
            "drifted_toward_gold": up,
            "drifted_away": down,
            "p_two_sided_exact": mc["p_two_sided_exact"],
            "significant_drift": bool(boot["ci"][0] > 0 or boot["ci"][1] < 0),
        }
        pfam[f"{lvl}_vs_L0"] = mc["p_two_sided_exact"]
    holm = rc.holm(pfam)

    # adjacent-level drift, to locate where a shift happens
    adjacent = {}
    for a, b in zip(LEVELS, LEVELS[1:]):
        diffs = [x - y for x, y in zip(cos_by_level[b], cos_by_level[a])]
        boot = rc.paired_bootstrap_ci(diffs, seed=SEED)
        adjacent[f"{b}_vs_{a}"] = {"mean_cos_shift": boot["mean"], "ci95": boot["ci"]}

    for i, q in enumerate(ladder):
        per_query.append({
            "id": q["id"], "lang": q["lang"], "gold": q["validated_labels"][0],
            "cos_gold": {lvl: round(cos_by_level[lvl][i], 4) for lvl in LEVELS},
            "shift_L3_minus_L0": round(cos_by_level["L3"][i] - cos_by_level["L0"][i], 4),
        })

    # link back to the recall figures the frontier reported
    recall = {}
    if FRONTIER_PATH.exists():
        fr = json.loads(FRONTIER_PATH.read_text(encoding="utf-8"))
        for block in (fr.get("frontier"), fr.get("recall_by_level"), fr):
            if isinstance(block, dict) and "hybrid_0.5" in json.dumps(block)[:4000]:
                recall = block
                break

    verdict = interpret(per_level, contrasts)

    out = {
        "question": "L3에서 R@10이 유지된 것이 노출 축소가 무해하기 때문인가, "
                    "아니면 질의가 정답 문서 쪽으로 표류(자기참조 증가)했기 때문인가",
        "method": {
            "gate_model": gate.GATE_MODEL,
            "why": "평가에 쓰지 않는 제3의 인코더라서 답이 피검정 검색기에 의존하지 않는다",
            "margin": "cos(질의, 정답) - 평균 cos(질의, 비정답 20건). 레지스터 이동과 "
                      "표적 누출을 구분한다.",
            "n_negatives": N_NEG, "seed": SEED,
        },
        "env": rc.env_meta({"seed": SEED}),
        # 이 감사는 **전체 질의**를 본다. 사다리 정의 위반 여부와 무관하게 재작성
        # 전반이 정답 쪽으로 표류했는지를 물어야 하기 때문이다. frontier(n=133)와
        # 기준이 다르므로 명시한다 — 예전에는 라벨이 없어 두 n 이 섞여 보였다.
        "basis": {
            "n": len(per_query),
            "subset": "전체 질의(사다리 정의 위반 포함)",
            "why": ("표류 판정은 사다리 정의 준수 여부와 무관하게 재작성 전반을 봐야 한다. "
                    "회수율 비교(frontier)는 정의를 지키는 부분집합만 쓰므로 n 이 다르다."),
            "frontier_basis_n": recall.get("data", {}).get("n_queries"),
        },
        "per_level": per_level,
        "vs_L0": contrasts,
        "vs_L0_holm": holm,
        "adjacent": adjacent,
        "verdict": verdict,
        # frontier 산출물을 통째로 복사하지 않고 경로와 기준만 남긴다. 예전에는 전체를
        # 임베드해서, frontier 가 갱신돼도 여기 박힌 사본은 옛 판(n=119)으로 남았다.
        "recall_reference": {
            "path": "output/disclosure_frontier.json",
            "n_queries": recall.get("data", {}).get("n_queries"),
            "ladder_spec_excluded": recall.get("data", {}).get("ladder_spec_excluded"),
            "hybrid_recall_at_10": {
                lv: recall["recall@10"]["hybrid_0.5"][lv]["overall"]["rate"]
                for lv in recall.get("recall@10", {}).get("hybrid_0.5", {})
            },
            "note": "전체 사본 대신 참조만 둔다. 값이 필요하면 위 경로를 읽을 것.",
        },
        "per_query": per_query,
    }
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(render(out), encoding="utf-8")
    print(json.dumps({"per_level": per_level, "vs_L0": contrasts, "verdict": verdict},
                     ensure_ascii=False, indent=2))


def interpret(per_level: dict, contrasts: dict) -> dict:
    l0, l3 = per_level["L0"], per_level["L3"]
    shift = contrasts["L3_vs_L0"]
    cos_up = shift["mean_cos_shift"] > 0
    sig = shift["significant_drift"]
    margin_up = l3["margin_mean"] > l0["margin_mean"]
    if sig and cos_up and margin_up:
        label = "confounded"
        text = ("L3 질의가 정답 문서와 유의하게 더 비슷해졌고 비정답 대비 여유(margin)도 "
                "커졌다. 즉 R@10 유지는 노출 축소가 무해해서가 아니라 자기참조가 증가한 "
                "결과로 보아야 한다. frontier의 'L3까지 안전' 서술을 철회해야 한다.")
    elif sig and cos_up and not margin_up:
        label = "register_shift"
        text = ("정답과의 유사도는 올랐으나 비정답과의 유사도도 함께 올라 margin은 "
                "커지지 않았다. 질의가 통제목록 문체 전반에 가까워진 레지스터 이동이며, "
                "정답에 대한 표적 누출은 아니다. R@10 유지 해석은 유효하지만 "
                "'질의가 통제목록 문체로 수렴한다'는 한계를 명시해야 한다.")
    elif not sig:
        label = "benign"
        text = ("정답과의 유사도가 유의하게 변하지 않았다. 제거된 필드가 검색 신호가 "
                "아니었다는 해석이 지지된다. 다만 비유의는 검정력 한계일 수 있으므로 "
                "'자기참조 증가 근거 없음'까지만 말할 수 있다.")
    else:
        label = "diverged"
        text = ("L3 질의가 정답에서 오히려 멀어졌는데도 R@10이 유지되었다. 자기참조 "
                "증가로는 설명되지 않으며, 노출 축소가 무해하다는 해석이 강해진다.")
    return {"label": label, "explanation": text,
            "cos_L0": l0["cos_gold_mean"], "cos_L3": l3["cos_gold_mean"],
            "margin_L0": l0["margin_mean"], "margin_L3": l3["margin_mean"]}


def render(out: dict) -> str:
    pl = out["per_level"]
    v = out["verdict"]
    L = [
        "# 노출 등급 사다리의 자기참조 감사",
        "",
        f"**질문.** {out['question']}",
        "",
        f"게이트 인코더 `{out['method']['gate_model']}` — {out['method']['why']}.",
        f"margin = {out['method']['margin']}",
        "",
        "## 등급별 정답 유사도",
        "",
        "| 등급 | 민감토큰 | 질의토큰 | cos(정답) | 한국어 | 영어 | cos(비정답) | margin | 어휘 Jaccard |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for lvl in LEVELS:
        r = pl[lvl]
        L.append(f"| {lvl} | {r['mean_sensitive_tokens']:.2f} | {r['mean_query_tokens']:.1f} | "
                 f"**{r['cos_gold_mean']:.4f}** | {r['cos_gold_ko']:.4f} | {r['cos_gold_en']:.4f} | "
                 f"{r['cos_nongold_mean']:.4f} | {r['margin_mean']:+.4f} | "
                 f"{r['lexical_jaccard_mean']:.4f} |")
    L += ["", "## L0 대비 표류 (paired bootstrap + sign test, Holm)", "",
          "| 비교 | cos 변화 | 95% CI | 정답쪽/반대쪽 | exact p | Holm p | 유의 |",
          "|---|---:|---|---:|---:|---:|---|"]
    for k, c in out["vs_L0"].items():
        h = out["vs_L0_holm"][k]
        L.append(f"| {k} | {c['mean_cos_shift']:+.4f} | "
                 f"[{c['ci95'][0]:+.4f}, {c['ci95'][1]:+.4f}] | "
                 f"{c['drifted_toward_gold']}/{c['drifted_away']} | "
                 f"{c['p_two_sided_exact']:.3g} | {h['p_adjusted']:.3g} | "
                 f"{'**예**' if c['significant_drift'] else '아니오'} |")
    L += ["", "## 인접 등급 간 표류", "", "| 비교 | cos 변화 | 95% CI |", "|---|---:|---|"]
    for k, c in out["adjacent"].items():
        L.append(f"| {k} | {c['mean_cos_shift']:+.4f} | "
                 f"[{c['ci95'][0]:+.4f}, {c['ci95'][1]:+.4f}] |")
    L += ["", "## 판정", "", f"**{v['label']}**", "", v["explanation"], "",
          f"- cos(정답): L0 {v['cos_L0']:.4f} → L3 {v['cos_L3']:.4f}",
          f"- margin: L0 {v['margin_L0']:+.4f} → L3 {v['margin_L3']:+.4f}", "",
          "## 해석 주의", "",
          "- 이 감사는 유사도만 본다. 유사도 하나로 '라벨이 맞는 좋은 질의'와 "
          "'정답을 베낀 질의'를 원리적으로 구분할 수는 없다(`docs/selfreference.md` 참조).",
          "- 게이트 인코더가 하나이므로 다른 인코더에서 같은 방향이 나오는지는 "
          "확인하지 않았다. **확인 필요.**", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
