#!/usr/bin/env python3
"""data/disclosure_ladder.json 및 build_disclosure_ladder.py 검증.

검증 항목
  1. 등급이 올라갈수록 sensitive_token_count / sensitive_field_count 단조 비증가
  2. 정답 라벨이 등급 간 동일 (단일 저장 + 원본 JSON과 일치)
  3. 언어 구성 보존 (ko 45 / en 26) 및 등급별 언어 불변
  4. 모든 등급에서 통제번호 누출 0
  5. 등급 정의 준수: L1+ 숫자 없음, L3/L4 계수 민감토큰 0, L4 단어 2~5
  6. 계량기(detector) 자체의 동작: 계수/비계수 카테고리 분리, 스팬 중복 소비 금지

Run: python tests/test_disclosure_ladder.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_disclosure_ladder as bdl  # noqa: E402
import retrieval_core as rc  # noqa: E402

LEVELS = bdl.LEVELS
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(f"{name} {detail}")


LADDER_PATH = ROOT / "data" / "disclosure_ladder.json"
SRC_PATH = ROOT / "data" / "validated_queries_expanded.json"


def load() -> tuple[dict, dict]:
    payload = json.loads(LADDER_PATH.read_text(encoding="utf-8"))
    src = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    return payload, src


# ------------------------------------------------------------------ 구조


def test_structure(payload: dict, src: dict) -> None:
    print("[구조]")
    entries = payload["queries"]
    check("질의 71개", len(entries) == 71, f"{len(entries)}")
    check("원본과 id 집합 동일",
          {e["id"] for e in entries} == {q["id"] for q in src["queries"]})
    check("모든 항목이 5등급 전부 보유",
          all(set(e["levels"]) == set(LEVELS) for e in entries))
    check("빌더 자체 검증 통과 플래그", payload["validation"]["passed"] is True,
          str(payload["validation"]["problems"][:3]))
    check("등급 정의 5개 기록", set(payload["meta"]["levels"]) == set(LEVELS))
    check("카테고리 사전에 계수/비계수 구분이 있다",
          all("counted" in v for v in payload["meta"]["category_definitions"].values()))
    check("function / item_category 는 계수 제외",
          payload["meta"]["category_definitions"]["function"]["counted"] is False
          and payload["meta"]["category_definitions"]["item_category"]["counted"] is False)
    check("env_meta 와 seed 기록", "env" in payload["meta"] and payload["meta"]["seed"] == 20260626)


# ------------------------------------------------------------ 1. 단조성


def test_monotonic(payload: dict) -> None:
    print("[단조성]")
    bad_tok, bad_fld, strict = [], [], 0
    for e in payload["queries"]:
        tok = [e["levels"][lv]["sensitive_token_count"] for lv in LEVELS]
        fld = [e["levels"][lv]["sensitive_field_count"] for lv in LEVELS]
        if any(b > a for a, b in zip(tok, tok[1:])):
            bad_tok.append((e["id"], tok))
        if any(b > a for a, b in zip(fld, fld[1:])):
            bad_fld.append((e["id"], fld))
        if tok[0] > tok[-1]:
            strict += 1
    check("sensitive_token_count 단조 비증가", not bad_tok, str(bad_tok[:3]))
    check("sensitive_field_count 단조 비증가", not bad_fld, str(bad_fld[:3]))
    check("L0 > L4 인 질의가 전체의 90% 이상", strict >= 64, f"{strict}/71")

    means = [payload["per_level_summary"][lv]["mean_sensitive_token_count"] for lv in LEVELS]
    check("평균 민감토큰도 등급별 단조 비증가",
          all(b <= a + 1e-9 for a, b in zip(means, means[1:])), str(means))
    check("L0 평균 민감토큰 > 0", means[0] > 0, str(means[0]))
    check("L3 평균 민감토큰 == 0", abs(means[3]) < 1e-9, str(means[3]))
    check("L4 평균 민감토큰 == 0", abs(means[4]) < 1e-9, str(means[4]))
    tokens = [payload["per_level_summary"][lv]["mean_token_count"] for lv in LEVELS]
    check("L4 질의 길이가 L3보다 짧다 (L3/L4 구분이 유지된다)",
          tokens[4] < tokens[3], f"L3={tokens[3]} L4={tokens[4]}")


# ---------------------------------------------------- 2. 라벨 등급 간 동일


def test_labels(payload: dict, src: dict) -> None:
    print("[라벨 불변]")
    by_id = {q["id"]: q for q in src["queries"]}
    mismatch = [e["id"] for e in payload["queries"]
                if e["validated_labels"] != by_id[e["id"]]["validated_labels"]]
    check("원본 라벨과 완전 일치", not mismatch, str(mismatch[:5]))
    # 라벨은 등급별로 복제되지 않고 엔트리 1회 저장 -> 등급 간 불일치가 구조적으로 불가
    per_level_label_keys = {
        k for e in payload["queries"] for lv in LEVELS for k in e["levels"][lv]
        if "label" in k
    }
    check("등급 내부에 라벨 사본이 없다(등급별 라벨 드리프트 불가)",
          not per_level_label_keys, str(per_level_label_keys))
    check("라벨이 비어 있는 질의 없음",
          all(e["validated_labels"] for e in payload["queries"]))


# ------------------------------------------------------- 3. 언어 구성 보존


def test_language(payload: dict, src: dict) -> None:
    print("[언어 구성]")
    counts = Counter(e["lang"] for e in payload["queries"])
    check("언어 구성 ko 45 / en 26", counts == Counter({"ko": 45, "en": 26}), str(dict(counts)))
    by_id = {q["id"]: q for q in src["queries"]}
    check("항목별 lang 이 원본과 동일",
          all(e["lang"] == by_id[e["id"]]["lang"] for e in payload["queries"]))

    # 재작성된 등급의 문자 종류가 원문 언어를 따르는지 (ko 는 한글 포함, en 은 한글 없음)
    han = re.compile(r"[가-힣]")
    bad = []
    for e in payload["queries"]:
        for lv in LEVELS:
            q = e["levels"][lv]["query"]
            if e["lang"] == "ko" and not han.search(q):
                bad.append((e["id"], lv, "ko without hangul"))
            if e["lang"] == "en" and han.search(q):
                bad.append((e["id"], lv, "en with hangul"))
    check("모든 등급에서 질의 언어가 원문과 동일", not bad, str(bad[:5]))
    check("meta 의 언어 분포도 45:26",
          payload["meta"]["language_distribution"] == {"ko": 45, "en": 26},
          str(payload["meta"]["language_distribution"]))


# --------------------------------------------------- 4. 통제번호 누출 0


def test_no_leak(payload: dict) -> None:
    print("[통제번호 누출]")
    hits = []
    for e in payload["queries"]:
        for lv in LEVELS:
            h = bdl.leak_hits(e["levels"][lv]["query"], e["validated_labels"])
            if h:
                hits.append((e["id"], lv, h))
    check("정답코드 문자열 + CONTROL_CODE_RE 누출 0건", not hits, str(hits[:5]))

    # 독립 감사: 생성기가 쓰지 않은 패턴으로 다시 본다
    independent = [
        re.compile(r"\bML\s?\d{1,2}\b", re.I),
        re.compile(r"\b[0-9]\s?[A-EY]\s?[0-9]{3}\b", re.I),
        re.compile(r"\b[0-9]-[A-EY]-[0-9]{3}\b", re.I),
        re.compile(r"\b[0-9]\.[A-E]\.[0-9]{1,2}\b", re.I),
    ]
    ind = []
    for e in payload["queries"]:
        for lv in LEVELS:
            q = e["levels"][lv]["query"]
            for p in independent:
                if p.search(q):
                    ind.append((e["id"], lv, p.pattern))
    check("독립 패턴 감사도 0건", not ind, str(ind[:5]))

    # 'ECCN' 이라는 규제 용어 자체는 코드가 아니므로 누출이 아니지만, L2 이상에서
    # 제거하도록 설계했으므로 그 설계가 지켜졌는지 확인한다.
    eccn = re.compile(r"\becc?n\b", re.I)
    residual = [(e["id"], lv) for e in payload["queries"] for lv in ("L2", "L3", "L4")
                if eccn.search(e["levels"][lv]["query"])]
    check("L2 이상에 'ECCN' 규제 용어 잔존 0건", not residual, str(residual[:5]))


# ------------------------------------------------------- 5. 등급 정의 준수


def test_level_definitions(payload: dict) -> None:
    print("[등급 정의 준수]")
    digits = [(e["id"], lv) for e in payload["queries"] for lv in LEVELS[1:]
              if re.search(r"\d", e["levels"][lv]["query"])]
    check("L1 이상 숫자 0건", not digits, str(digits[:5]))

    for lv in ("L3", "L4"):
        bad = [(e["id"], e["levels"][lv]["counted_sensitive_fields"])
               for e in payload["queries"] if e["levels"][lv]["sensitive_token_count"]]
        check(f"{lv} 계수 민감토큰 0", not bad, str(bad[:5]))

    words = [(e["id"], len(e["levels"]["L4"]["query"].split())) for e in payload["queries"]]
    check("L4 단어 수 2~5", all(2 <= w <= 5 for _, w in words),
          str([x for x in words if not 2 <= x[1] <= 5][:5]))

    # L3 은 기능 서술이 남아야 한다(잔존 필드에 function 포함)
    no_fn = [e["id"] for e in payload["queries"]
             if "function" not in e["levels"]["L3"]["sensitive_fields_disclosed"]]
    check("L3 은 function 잔존", not no_fn, str(no_fn[:5]))
    no_item = [e["id"] for e in payload["queries"] for lv in LEVELS
               if "item_category" not in e["levels"][lv]["sensitive_fields_disclosed"]]
    check("모든 등급에 item_category 잔존", not no_item, str(no_item[:5]))

    # removed 목록은 L0 에서 비어 있고, 실제로 줄어든 등급에서는 비어 있지 않아야 한다
    check("L0 의 removed 는 비어 있다",
          all(e["levels"]["L0"]["removed"] == [] for e in payload["queries"]))
    missing_removed = [
        (e["id"], lv) for e in payload["queries"] for lv in LEVELS[1:]
        if e["levels"][lv]["sensitive_token_count"]
        < e["levels"][LEVELS[LEVELS.index(lv) - 1]]["sensitive_token_count"]
        and not e["levels"][lv]["removed"]
    ]
    check("민감토큰이 줄어든 등급에는 removed 근거가 기록되어 있다",
          not missing_removed, str(missing_removed[:5]))

    distinct = [payload["per_level_summary"][lv]["distinct_queries"] for lv in LEVELS]
    check("등급별 질의문이 서로 다른 71개 (퇴화 색인 아님)",
          all(d == 71 for d in distinct), str(distinct))


# ----------------------------------------------------------- 6. 계량기 동작


def test_detector() -> None:
    print("[계량기]")
    m = bdl.measure("300밀리미터 실리콘 웨이퍼를 외국 파운드리에 이전하려 합니다.")
    cats = set(m["counted_sensitive_fields"])
    check("수치+단위 -> quantitative_spec", "quantitative_spec" in cats, str(cats))
    check("재료 고유명칭 -> product_identifier", "product_identifier" in cats, str(cats))
    check("불특정 목적지 -> destination", "destination" in cats, str(cats))
    check("수요기관 -> end_user", "end_user" in cats, str(cats))
    check("거래 형태 -> transaction_intent", "transaction_intent" in cats, str(cats))

    # 단위어 단독은 정량 사양이 아니다(밀리미터파는 대역 이름)
    m2 = bdl.measure("밀리미터파 스캐너")
    check("단위어 단독은 quantitative_spec 이 아니다",
          "quantitative_spec" not in m2["counted_sensitive_fields"],
          str(m2["counted_sensitive_fields"]))

    # 스팬은 중복 소비되지 않는다
    m3 = bdl.measure("silicon carbide films")
    surfaces = [s["surface"].lower() for s in m3["spans"]]
    check("긴 항목이 먼저 매칭되어 중복 계수되지 않는다",
          "silicon carbide" in " ".join(surfaces) or surfaces.count("silicon") <= 1,
          str(surfaces))
    spans = bdl.annotate("독일 연구소에 수출하려 합니다")
    ranges = sorted((s["start"], s["start"] + len(s["surface"])) for s in spans)
    overlap = any(a[1] > b[0] for a, b in zip(ranges, ranges[1:]))
    check("스팬 구간이 겹치지 않는다", not overlap, str(ranges))

    # 계수 제외 카테고리는 sensitive_token_count 에 들어가지 않는다
    check("계수 카테고리 목록에 function/item_category 없음",
          "function" not in bdl.COUNTED and "item_category" not in bdl.COUNTED)

    # 순수 기능 서술은 0
    m4 = bdl.measure("회전 각속도를 감지하는 관성 센서 모듈의 통제 분류를 알고 싶습니다.")
    check("기능 서술만 남은 문장은 민감토큰 0", m4["sensitive_token_count"] == 0,
          str(m4["counted_sensitive_fields"]))

    # 사전 항목이 모두 컴파일되었는지
    n_terms = sum(len(v) for v in bdl.TERMS.values())
    check("사전 항목 전부 컴파일", len(bdl.COMPILED) == n_terms,
          f"{len(bdl.COMPILED)} vs {n_terms}")
    check("rc.tokenize 기반 토큰 수와 일치",
          m["token_count"] == len(rc.tokenize("300밀리미터 실리콘 웨이퍼를 외국 파운드리에 이전하려 합니다.")))


def test_slice_ladder_source() -> None:
    """슬라이스 파일에 실린 사다리를 빌더가 읽는가 (TASK J 통합 경로).

    원본 71개의 L1~L4 는 build_disclosure_ladder.py 안 LADDER dict 에 하드코딩되어
    있다. TASK J 이후의 확장 질의는 슬라이스 JSON 의 `ladder` 필드로 들어오는데,
    (a) 병합 스크립트가 그 필드를 떨어뜨리고 (b) 빌더가 하드코딩만 보던 탓에 새 질의의
    사다리가 파이프라인에 도달하지 못했다. 두 구멍을 다시 열지 않도록 고정한다.
    """
    import importlib.util

    root = LADDER_PATH.parent.parent
    spec = importlib.util.spec_from_file_location(
        "bdl", root / "build_disclosure_ladder.py")
    bdl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bdl)

    # (a) 슬라이스에 실린 온전한 사다리는 인식되어야 한다
    good = {"id": "slice-x", "query": "A",
            "ladder": {"L0": "A", "L1": "b", "L2": "c", "L3": "d", "L4": "e"}}
    got = bdl.ladder_for(good)
    if got != {"L1": "b", "L2": "c", "L3": "d", "L4": "e"}:
        FAILURES.append(f"슬라이스 ladder 미인식: {got}")

    # (b) 결함 있는 사다리는 거부되어야 한다 (조용히 통과하면 안 된다)
    for name, q in [
        ("L4 누락", {"id": "x", "query": "A",
                    "ladder": {"L0": "A", "L1": "b", "L2": "c", "L3": "d"}}),
        ("L0≠query", {"id": "y", "query": "A",
                      "ladder": {"L0": "B", "L1": "b", "L2": "c", "L3": "d", "L4": "e"}}),
        ("ladder 없음", {"id": "z", "query": "A"}),
    ]:
        if bdl.ladder_for(q) is not None:
            FAILURES.append(f"결함 사다리를 거부하지 않음: {name}")

    # (c) 원본 71개는 하드코딩이 우선이어야 한다 (슬라이스가 덮어쓰지 못하게)
    if bdl.LADDER:
        qid = next(iter(bdl.LADDER))
        spoof = {"id": qid, "query": "A",
                 "ladder": {"L0": "A", "L1": "!", "L2": "!", "L3": "!", "L4": "!"}}
        if bdl.ladder_for(spoof) != bdl.LADDER[qid]:
            FAILURES.append("하드코딩 LADDER 가 슬라이스에 의해 덮어쓰였다")

    # (d) 병합 스크립트가 ladder 를 보존하는가
    spec2 = importlib.util.spec_from_file_location(
        "bev", root / "build_expanded_validated.py")
    bev = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(bev)
    merged = bev.merge_queries()
    j = [q for q in merged if str(q.get("origin", "")).startswith("slice_j_")]
    if j and not all(q.get("ladder") for q in j):
        n = sum(1 for q in j if not q.get("ladder"))
        FAILURES.append(f"병합이 TASK J 사다리를 떨어뜨렸다: {n}/{len(j)}건")
    print(f"  slice ladder source: 슬라이스 질의 {len(j)}건, 사다리 보존 확인")


def main() -> int:
    if not LADDER_PATH.exists():
        print(f"FAIL {LADDER_PATH} 없음 — 먼저 python build_disclosure_ladder.py 실행")
        return 1
    payload, src = load()
    test_structure(payload, src)
    test_monotonic(payload)
    test_labels(payload, src)
    test_language(payload, src)
    test_no_leak(payload)
    test_level_definitions(payload)
    test_detector()
    test_slice_ladder_source()
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
