#!/usr/bin/env python3
"""자기참조 게이트 + 대칭 ablation 회귀 검증 (M4).

핵심 회귀 항목
--------------
1. **한국어에서 어휘 Jaccard가 상수 0** — 기존 gate 3이 구조적으로 공허했던 이유.
   이 사실 자체를 검증하고(코퍼스가 영어인 한 계속 참이다), 고쳐진 게이트가 이것을
   **경고로 잡아내는지** 확인한다. 경고가 사라지면 진단이 퇴행한 것이다.
2. **치환 사다리의 단조성** — level 0..3에서 적용 규칙 집합이 중첩되고 압력이
   비감소해야 한다. 사전이 편집되어도 이 성질이 깨지지 않아야 한다.

무거운 인코더가 없어도 돌아가야 하므로 모델이 필요한 검증은 산출물
(`output/selfreference_audit.json`)이 있을 때만 수행하고, 없으면 건너뛴 사실을 표시한다.

Run: python tests/test_selfreference.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import retrieval_core as rc            # noqa: E402
import selfreference_gate as sg        # noqa: E402
import experiment_symmetric_ablation as ex   # noqa: E402

FAILURES: list[str] = []
SKIPPED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(f"{name} {detail}")


def skip(name: str, why: str) -> None:
    print(f"  skip {name} ({why})")
    SKIPPED.append(f"{name}: {why}")


def load_corpus() -> list[dict]:
    return json.loads((ROOT / "data" / "corpus" / "combined.json").read_text(encoding="utf-8"))


def load_queries() -> list[dict]:
    return json.loads(
        (ROOT / "data" / "validated_queries_expanded.json").read_text(encoding="utf-8")
    )["queries"]


# --------------------------------------------------------------------------
# 1. 어휘 게이트의 구조적 공허성
# --------------------------------------------------------------------------


def test_lexical_gate_is_void_for_korean() -> None:
    print("[어휘 게이트 공허성]")
    corpus = load_corpus()
    queries = load_queries()
    by_code = {e["code"]: e for e in corpus}

    rows = []
    for q in queries:
        code = q["validated_labels"][0]
        if code not in by_code:
            continue
        ans = rc.index_text(by_code[code], "minimal_text")
        rows.append({
            "id": q["id"], "lang": q["lang"],
            "lexical_jaccard": round(sg.jaccard(rc.tokenize(q["query"]), rc.tokenize(ans)), 4),
        })

    ko = [r["lexical_jaccard"] for r in rows if r["lang"] == "ko"]
    en = [r["lexical_jaccard"] for r in rows if r["lang"] == "en"]

    check("한국어 질의가 존재한다", len(ko) > 0, f"n={len(ko)}")
    # n=71 시절 이 값은 전부 정확히 0이었다. 확장 질의에 숫자·라틴 약어가 섞이면서
    # 극소수가 0을 벗어나므로, 검사해야 할 성질은 '전부 0'이 아니라 '게이트가 검사할
    # 것이 사실상 없다'는 쪽이다. 임계 0.30 대비 최대값이 한 자릿수 퍼센트에 머무는지를 본다.
    n_zero_ko = sum(1 for v in ko if v == 0.0)
    check("한국어 어휘 Jaccard가 사실상 전부 0 (교집합이 원리상 거의 공집합)",
          n_zero_ko >= 0.9 * len(ko) and max(ko) < sg.MAX_JACCARD / 3,
          f"zero={n_zero_ko}/{len(ko)} max={max(ko)}")
    check("영어 어휘 Jaccard는 0이 아닌 값을 가진다(토크나이저가 실제로 동작함)",
          any(v > 0.0 for v in en), f"max={max(en) if en else None}")
    check("어휘 게이트는 임계 0.30에서 한 번도 발동하지 않는다",
          all(v < sg.MAX_JACCARD for v in rows and [r['lexical_jaccard'] for r in rows]),
          f"max={max(r['lexical_jaccard'] for r in rows):.4f}")

    # 고쳐진 게이트가 이 공허성을 경고로 잡아내는가
    void = sg.lexical_void_warning(rows)
    check("게이트가 한국어의 구조적 공허를 경고로 보고한다",
          void.get("ko", {}).get("effectively_void") is True
          and bool(void.get("ko", {}).get("warning")),
          f"ko={void.get('ko')}")
    check("게이트가 영어에는 잘못된 경고를 내지 않는다",
          void.get("en", {}).get("warning") is None, f"en={void.get('en')}")
    check("게이트가 '한 번도 발동 안 함'을 언어별로 기록한다",
          all(v["ever_triggered_at_0.30"] is False for v in void.values()),
          f"{ {k: v['ever_triggered_at_0.30'] for k, v in void.items()} }")

    # 코퍼스가 실제로 영어인지 — 위 성질의 전제
    hangul_docs = sum(1 for e in corpus if sg.has_hangul(e.get("text") or ""))
    check("코퍼스에 한글 본문이 없다 (한국어 교집합이 0인 이유)",
          hangul_docs == 0, f"hangul_docs={hangul_docs}")


def test_gate_model_independence() -> None:
    print("[게이트 모델 독립성]")
    check("게이트 모델이 평가용 3모델과 겹치지 않는다",
          sg.GATE_MODEL not in sg.EVAL_MODELS, sg.GATE_MODEL)
    try:
        sg.assert_gate_model_is_independent()
        check("assert_gate_model_is_independent() 통과", True)
    except AssertionError as exc:
        check("assert_gate_model_is_independent() 통과", False, str(exc))
    check("ablation의 dense 모델과 게이트 모델이 다르다",
          ex.GATE_MODEL != ex.DENSE_MODEL, f"{ex.GATE_MODEL} vs {ex.DENSE_MODEL}")


# --------------------------------------------------------------------------
# 2. 치환 사다리
# --------------------------------------------------------------------------


def test_substitution_ladder() -> None:
    print("[치환 사다리]")
    subs = ex.load_substitutions()
    rules = subs["rules"]
    queries = load_queries()

    # 사전 스키마
    bad = [r for r in rules
           if not isinstance(r.get("tier"), int)
           or r.get("lang") not in ("ko", "en")
           or not r.get("phrase") or not r.get("hypernym")]
    check("모든 규칙이 tier/lang/phrase/hypernym을 갖는다", not bad, f"{bad[:2]}")
    check("tier가 1..3 범위", all(1 <= r["tier"] <= 3 for r in rules))
    check("치환어가 원구와 다르다", all(r["phrase"] != r["hypernym"] for r in rules))

    # 규칙 집합의 중첩성: level N의 규칙 집합 ⊆ level N+1
    for q in queries[:]:
        sets = []
        for lv in ex.LEVELS:
            sets.append({(r["tier"], r["phrase"])
                         for r in ex.rules_for(q["id"], q["lang"], rules, lv)})
        nested = all(sets[i] <= sets[i + 1] for i in range(len(sets) - 1))
        if not nested:
            check(f"{q['id']}: 규칙 집합이 level에 대해 중첩", False)
            break
    else:
        check("모든 질의에서 규칙 집합이 level에 대해 중첩(nested)", True)

    # 적용 건수 단조 비감소 + 전체 압력 단조증가
    totals = []
    per_query_monotone = True
    offenders = []
    for lv in ex.LEVELS:
        tot = 0
        for q in queries:
            res = ex.substitute(q["query"], q["id"], q["lang"], rules, lv)
            tot += res["n_applied"]
        totals.append(tot)
    for q in queries:
        counts = [ex.substitute(q["query"], q["id"], q["lang"], rules, lv)["n_applied"]
                  for lv in ex.LEVELS]
        if any(counts[i] > counts[i + 1] for i in range(len(counts) - 1)):
            per_query_monotone = False
            offenders.append((q["id"], counts))
    check("전체 적용 규칙 수가 level에 대해 단조 비감소",
          all(totals[i] <= totals[i + 1] for i in range(len(totals) - 1)), f"{totals}")
    check("질의별 적용 규칙 수도 단조 비감소", per_query_monotone, f"{offenders[:3]}")
    check("level 0에서는 아무것도 치환되지 않는다", totals[0] == 0, f"{totals[0]}")
    # 치환 사전은 원본 71개 질의를 보고 만든 것이라 TASK J 확장 질의(80건)에는
    # tier1/2 질의별 규칙이 없다. 이는 사전의 한계이지 버그가 아니므로 '전량 치환'을
    # 요구하지 않고, 대신 **커버리지를 명시적으로 세어 고정**한다 — 커버리지가 조용히
    # 더 떨어지면 실패한다(PAPER 4.6 이 이 수치를 인용한다).
    cov1 = sum(1 for q in queries
               if ex.substitute(q["query"], q["id"], q["lang"], rules, 1)["n_applied"] >= 1)
    cov3 = sum(1 for q in queries
               if ex.substitute(q["query"], q["id"], q["lang"], rules, 3)["n_applied"] >= 1)
    check("level 1 치환 커버리지 71건 (원본 질의 전량)", cov1 == 71, f"{cov1}/{len(queries)}")
    check("level 3 치환 커버리지 121건 이상 (전역 규칙까지 적용)",
          cov3 >= 121, f"{cov3}/{len(queries)}")
    uncovered = [q["id"] for q in queries
                 if ex.substitute(q["query"], q["id"], q["lang"], rules, 3)["n_applied"] < 1]
    check("미커버 질의가 전부 확장분(TASK G/J)이다 — 원본 71개는 빠짐없이 압력을 받는다",
          all(not q.startswith("ext-") for q in uncovered), str(uncovered[:5]))

    # 결정론: 같은 입력 → 같은 출력
    a = [ex.substitute(q["query"], q["id"], q["lang"], rules, 3)["text"] for q in queries]
    b = [ex.substitute(q["query"], q["id"], q["lang"], rules, 3)["text"] for q in queries]
    check("치환이 결정론적", a == b)

    # 텍스트가 실제로 변한다 & 원문과 다르다
    changed = sum(1 for q, t in zip(queries, a) if t != q["query"])
    check("level 3에서 커버된 질의는 텍스트가 실제로 변경된다", changed == cov3,
          f"{changed}/{cov3}")

    # ---- 치환이 자기참조를 늘리지 않는다 --------------------------------
    # Jaccard는 |교집합|/|합집합| 이므로 질의가 짧아지면 교집합이 그대로여도 값이
    # **올라간다**. 따라서 압력의 방향은 Jaccard가 아니라 **공유 토큰 수**로 검증한다
    # (분모 축소 artifact와 실제 자기참조 증가를 구분하기 위함).
    corpus = load_corpus()
    by_code = {e["code"]: e for e in corpus}
    worse_count, worse_jacc = [], []
    for q in queries:
        code = q["validated_labels"][0]
        if code not in by_code:
            continue
        ans = set(rc.tokenize(rc.index_text(by_code[code], "minimal_text")))
        cnt, jac = [], []
        for lv in ex.LEVELS:
            t = ex.substitute(q["query"], q["id"], q["lang"], rules, lv)["text"]
            toks = set(rc.tokenize(t))
            cnt.append(len(toks & ans))
            jac.append(sg.jaccard(list(toks), list(ans)))
        if any(cnt[i] < cnt[i + 1] for i in range(len(cnt) - 1)):
            worse_count.append((q["id"], cnt))
        if jac[-1] > jac[0] + 1e-12:
            worse_jacc.append((q["id"], [round(x, 4) for x in jac]))
    check("정답과 공유하는 토큰 수가 level에 대해 단조 비감소하지 않는다(=압력 방향이 맞다)",
          not worse_count, f"{worse_count[:3]}")
    # 이것은 실패가 아니라 기록: Jaccard 상승은 분모 축소 artifact일 수 있다.
    if worse_jacc:
        print(f"  note Jaccard가 오른 질의 {len(worse_jacc)}건 — 질의가 짧아져 합집합이 "
              f"줄어든 artifact(공유 토큰 수는 줄었음): {worse_jacc[:3]}")

    # 치환어가 정답 원문의 토큰을 새로 들여오지 않는다 (사전 자체의 결함 검사).
    # 실측으로 9건을 잡아 사전을 고쳤다: 예) 'stress-analysis devices' →
    # 'physiological monitoring devices' 는 정답 3A981의 'monitoring'을 들여왔고,
    # 전역 규칙 equipment→items 는 거의 모든 영어 정답에 있는 '(see List of Items
    # Controlled)'의 'items'를 들여왔다.
    qtext = {q["id"]: q["query"] for q in queries}
    qlang = {q["id"]: q["lang"] for q in queries}
    ans_tok = {q["id"]: set(rc.tokenize(rc.index_text(
        by_code[q["validated_labels"][0]], "minimal_text")))
        for q in queries if q["validated_labels"][0] in by_code}
    introduced = []
    for r in rules:
        new = set(rc.tokenize(r["hypernym"])) - set(rc.tokenize(r["phrase"]))
        for qid, txt in qtext.items():
            if qlang[qid] != r["lang"] or qid not in ans_tok:
                continue
            if r["query_ids"] is not None and qid not in r["query_ids"]:
                continue
            if r["phrase"] not in txt:
                continue
            hit = new & ans_tok[qid]
            if hit:
                introduced.append((r["phrase"], r["hypernym"], qid, sorted(hit)))
    check("어떤 치환어도 정답 원문의 토큰을 새로 들여오지 않는다",
          not introduced, f"{introduced[:3]}")


# --------------------------------------------------------------------------
# 3. 산출물 정합성 (있을 때만)
# --------------------------------------------------------------------------


def test_audit_artifact() -> None:
    print("[감사 산출물]")
    path = ROOT / "output" / "selfreference_audit.json"
    if not path.exists():
        skip("selfreference_audit.json 정합성", "산출물 없음 — selfreference_gate.py 실행 필요")
        return
    p = json.loads(path.read_text(encoding="utf-8"))
    c = p["calibration"]
    check("게이트 모델이 기록되어 있다", c["gate_model"] == sg.GATE_MODEL, c["gate_model"])
    check("평가 3모델이 제외 목록에 기록되어 있다",
          set(c["eval_models_excluded"]) == set(sg.EVAL_MODELS))
    check("env_meta와 seed가 기록되어 있다",
          "env" in p and p["env"].get("seed") == sg.SEED)
    tau = c["tau_semantic"]
    check("tau가 소수 2자리로 내려졌다(데이터 소수점까지 맞추지 않음)",
          abs(tau * 100 - round(tau * 100)) < 1e-9, f"tau={tau}")
    pos_b = [x["cos"] for x in c["pos_b_korean_basis_vs_answer"]["pairs"]]
    if pos_b:
        import numpy as np
        expected = np.floor(np.percentile(np.asarray(pos_b), sg.CALIBRATION_PERCENTILE)
                            * 100) / 100
        check("tau가 POS-B의 p10에서 유도된 값과 일치(임계값 규칙 준수)",
              abs(tau - float(expected)) < 1e-9, f"tau={tau} expected={expected}")
    check("보수적 컷이 민감도 컷보다 작거나 같다",
          tau <= c["tau_semantic_sensitivity_median_cut"] + 1e-9)
    check("NEG 평균 < POS-B 평균 (대조군이 실제로 분리된다)",
          c["neg_unrelated_pairs"]["stats"]["mean"]
          < c["pos_b_korean_basis_vs_answer"]["stats"]["mean"],
          f"neg={c['neg_unrelated_pairs']['stats']['mean']} "
          f"pos_b={c['pos_b_korean_basis_vs_answer']['stats']['mean']}")
    check("한국어 어휘 Jaccard가 산출물에서도 사실상 전부 0",
          p["verdict_primary"]["lexical_void_by_lang"]["ko"]["effectively_void"] is True,
          str(p["verdict_primary"]["lexical_void_by_lang"]["ko"]))
    check("상위 15건이 원문과 나란히 기록되어 있다",
          len(p["top_side_by_side"]) > 0
          and all(r.get("query") and r.get("answer_minimal_text")
                  for r in p["top_side_by_side"]))
    check("질의 전량이 per_query에 있다", len(p["per_query"]) == p["meta"]["n"],
          f"{len(p['per_query'])} vs {p['meta']['n']}")


def test_ablation_artifact() -> None:
    print("[ablation 산출물]")
    path = ROOT / "output" / "symmetric_ablation.json"
    if not path.exists():
        skip("symmetric_ablation.json 정합성",
             "산출물 없음 — experiment_symmetric_ablation.py 실행 필요")
        return
    p = json.loads(path.read_text(encoding="utf-8"))
    check("치환 사다리 단조성이 기록되어 있고 참",
          p["substitution_ladder_monotone"] is True)
    check("env_meta와 seed가 기록되어 있다",
          "env" in p and p["env"].get("seed") == ex.SEED)
    check("단일 dense 모델이다", p["meta"]["dense_model"] == ex.DENSE_MODEL)
    check("진단 모델이 평가 모델과 다르다",
          p["manipulation_diagnostics"]["gate_model"] != p["meta"]["dense_model"])
    cov = p["substitution_coverage"]
    tot = [cov[str(lv)]["total_rules_applied"] for lv in p["meta"]["levels"]]
    check("적용 규칙 수가 산출물에서도 단조 비감소",
          all(tot[i] <= tot[i + 1] for i in range(len(tot) - 1)), f"{tot}")
    diag = p["manipulation_diagnostics"]["per_level"]
    cos = [diag[str(lv)]["mean_gate_cos"] for lv in p["meta"]["levels"]]
    # 이것은 '통과해야 하는' 검증이 아니라 기록된 사실의 일관성 확인이다.
    check("게이트 cos 단조성 플래그가 실제 수열과 일치",
          p["manipulation_diagnostics"]["mean_gate_cos_monotone_nonincreasing"]
          == all(cos[i] >= cos[i + 1] - 1e-9 for i in range(len(cos) - 1)),
          f"{cos}")
    for imode in p["meta"]["index_modes"]:
        for nm in ("BM25", "dense", "hybrid_0.5"):
            rates = [p["decay"][imode][nm]["recall@10"][str(lv)]["overall"]["rate"]
                     for lv in p["meta"]["levels"]]
            check(f"{imode}/{nm}: R@10이 [0,1] 범위",
                  all(0.0 <= r <= 1.0 for r in rates), f"{rates}")


def main() -> int:
    test_lexical_gate_is_void_for_korean()
    test_gate_model_independence()
    test_substitution_ladder()
    test_audit_artifact()
    test_ablation_artifact()
    print()
    if SKIPPED:
        print(f"건너뜀 {len(SKIPPED)}건:")
        for s in SKIPPED:
            print(f"  - {s}")
    if FAILURES:
        print(f"\n{len(FAILURES)}건 실패:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("모든 검증 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
