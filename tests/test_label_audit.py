#!/usr/bin/env python3
"""audit_label_quality (M8, 정답셋 오염 교정) 검증.

무거운 인코더는 쓰지 않는다. 랭킹은 라벨 정의와 무관하므로 등가 라벨 채점
로직은 합성 top-k 로 결정론적으로 검증할 수 있다.

Run: python tests/test_label_audit.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import audit_label_quality as alq  # noqa: E402
import validate_query_slice as vqs  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(f"{name} {detail}")


CORPUS = alq.load_corpus()
BY_CODE = {e["code"]: e for e in CORPUS}
QUERIES_V1 = alq.load_queries_v1()


# ------------------------------------------------------- 구조적 코드 대응 규칙


def test_structural_rule() -> None:
    print("[structural code rule]")
    got = dict(alq.structural_counterparts("ECCN-3A003", BY_CODE))
    check("3A003 -> Wassenaar 3.A.3", got.get("3.A.3") == "wassenaar_2025", got)
    check("3A003 -> SCOMET 8A303", got.get("8A303") == "india_scomet_2024", got)

    got = dict(alq.structural_counterparts("ECCN-8B001", BY_CODE))
    check("8B001 -> 8.B.1 / 8B801",
          got.get("8.B.1") == "wassenaar_2025" and got.get("8B801") == "india_scomet_2024", got)

    # 규칙은 Wassenaar core list(세 번째 자리 0)에만 적용해야 한다. MTCR 계열에
    # 적용하면 1A001 과 1A101 이 모두 8A101 로 붕괴해 잘못된 등가가 생긴다.
    check("MTCR 1A101 은 구조 규칙 대상이 아니다",
          alq.structural_counterparts("ECCN-1A101", BY_CODE) == [])
    check("미국단독 5A991 은 구조 규칙 대상이 아니다",
          alq.structural_counterparts("ECCN-5A991", BY_CODE) == [])
    check("600 시리즈 8A620 은 구조 규칙 대상이 아니다",
          alq.structural_counterparts("ECCN-8A620", BY_CODE) == [])


# ------------------------------------------------------------- 표제 스텁 판정


def test_stub_detection() -> None:
    print("[heading stub]")
    check("3A002 는 표제 스텁", alq.is_stub(BY_CODE["ECCN-3A002"]))
    check("3E004 는 표제 스텁이 아님", not alq.is_stub(BY_CODE["ECCN-3E004"]))
    stubs = [e for e in CORPUS
             if e.get("source") == "ecfr_part774" and alq.is_stub(e)]
    ecfr = [e for e in CORPUS if e.get("source") == "ecfr_part774"]
    check("eCFR 표제 스텁이 절반을 넘는다",
          len(stubs) > len(ecfr) / 2, f"{len(stubs)}/{len(ecfr)}")
    # validate_query_slice 가 쓰는 정의와 같아야 한다
    same = all(bool(alq.STUB_RE.search(e.get("text") or ""))
               == bool(vqs.HEADING_STUB_RE.search(e.get("text") or ""))
               for e in CORPUS)
    check("STUB_RE 정의가 두 스크립트에서 동일", same)


# ------------------------------------------------------------------- 실측 감사


def test_audits_reproduce() -> None:
    print("[audit counts]")
    d5 = alq.audit_duplicate_codes(QUERIES_V1)
    check("재사용 코드 3건", d5["reused_code_count"] == 3, d5["reused_codes"])
    check("재사용 코드 목록",
          set(d5["reused_codes"]) == {"ECCN-3B001", "ECCN-1C002", "ECCN-6A001"},
          d5["reused_codes"])
    check("1질의 1항목 미충족", d5["one_query_one_item_satisfied"] is False)

    # 라벨공간은 eCFR full code 로만 한정되므로, 코퍼스 크기와 무관하게
    # non-eCFR 항목 전부가 원리상 정답이 될 수 없다. 절대 건수는 코퍼스 버전에
    # 따라 바뀌므로(v1 1160/1797, v2 1146/1783) 항등식으로 검증한다.
    d6 = alq.audit_label_space(CORPUS)
    non_ecfr = d6["corpus_size"] - d6["labelable_entries"]
    check("도달 불가 문서 == 비-eCFR 항목수 (라벨공간이 eCFR 한정)",
          d6["unreachable_entries"] == non_ecfr, d6)
    check("도달 불가 비율이 과반", d6["unreachable_share"] > 0.5, d6["unreachable_share"])
    check("labelable == eCFR 항목수",
          d6["labelable_entries"] == d6["per_source"].get("ecfr_part774"), d6["per_source"])

    d1 = alq.audit_stub_text(CORPUS, QUERIES_V1)
    # n=71 시절에는 정답 코드의 과반(58.6%)이 스텁이었다. TASK G/J 확장이 비스텁
    # 항목을 우선 고르도록 지시받아 이 비율이 희석됐다. 검사할 성질은 '과반'이
    # 아니라 **오염이 여전히 무시할 수 없는 규모**라는 것이다(PAPER 7 한계 1).
    check("정답 코드의 표제 스텁 비율이 여전히 유의미하다 (>0.2)",
          d1["gold_stub_share"] > 0.2, d1["gold_stub_share"])
    check("스텁 정답 질의 비율이 코퍼스 전체 스텁 비율보다 낮다 (확장이 희석했다)",
          d1["queries_all_gold_labels_stub_share"] < d1["stub_share"],
          f"query={d1['queries_all_gold_labels_stub_share']} corpus={d1['stub_share']}")

    d2 = alq.audit_cross_regime_twins(CORPUS, QUERIES_V1)
    first = d2["minimal_text|first_label_only"]
    allb = d2["minimal_text|all_labels"]
    # 첫 라벨만 보던 정의보다 전 라벨을 보면 반드시 같거나 커야 한다.
    check("전 라벨 검사가 첫 라벨 검사보다 작지 않다",
          allb["queries_with_twin_j_ge_0.40"] >= first["queries_with_twin_j_ge_0.40"]
          and allb["queries_with_twin_j_ge_0.30"] >= first["queries_with_twin_j_ge_0.30"],
          (first, allb))
    check("쌍둥이 J>=0.40 이 20건 이상",
          allb["queries_with_twin_j_ge_0.40"] >= 20,
          allb["queries_with_twin_j_ge_0.40"])


def test_item_term_warning() -> None:
    print("[item term coverage]")
    df = alq.corpus_document_frequency(CORPUS)
    rows = {r["query_id"]: r for r in
            alq.audit_item_term_coverage(QUERIES_V1, BY_CODE, df)["per_query"]}
    ext015 = rows["ext-015"]
    check("ext-015 는 oscilloscope 누락으로 경고",
          "oscilloscope" in ext015["discriminative_terms_missing_from_gold_text"],
          ext015["discriminative_terms_missing_from_gold_text"])
    check("ext-015 warn 플래그", ext015["warn_discriminative_term_absent"] is True)
    ko = [r for r in rows.values() if r["lang"] == "ko"]
    check("한국어 질의는 라틴 토큰이 없으면 검사 불가로 표시",
          all(r["checkable"] or r["reason_not_checkable"] for r in ko))


# -------------------------------------------------------------- 등가 라벨 사전


def test_equivalent_labels_file() -> None:
    print("[equivalent_labels.json]")
    if not alq.EQUIV_PATH.exists():
        check("파일 존재", False, "먼저 `python audit_label_quality.py emit`")
        return
    doc = json.loads(alq.EQUIV_PATH.read_text(encoding="utf-8"))
    check("env_meta 기록", "numpy" in doc["meta"]["env"])
    check("seed 기록", doc["meta"]["seed"] == alq.SEED)

    # 코퍼스 파서 교정으로 등가 코드가 병합·개칭될 수 있다. "전부 존재해야 한다"로
    # 단정하면 정당한 코퍼스 교체에서 깨지고, 조용히 빠뜨리면 R@10_equiv 가 소리 없이
    # 줄어든다. 그래서 요구사항은 "없는 코드는 반드시 명시적으로 표시되어 있어야 한다"다
    # (repair_equivalent_labels.py 가 표시한다).
    bad_missing, bad_source, bad_self, unflagged = [], [], [], []
    for m in doc["mappings"]:
        check_eccn = BY_CODE.get(m["eccn"])
        if check_eccn is None or check_eccn.get("source") != "ecfr_part774":
            bad_self.append(m["eccn"])
        for e in m["equivalents"]:
            entry = BY_CODE.get(e["code"])
            if entry is None:
                bad_missing.append(e["code"])
                if not e.get("absent_from_active_corpus"):
                    unflagged.append(e["code"])
            elif entry.get("source") == "ecfr_part774":
                bad_source.append(e["code"])
            elif e.get("absent_from_active_corpus"):
                unflagged.append(f"{e['code']}(존재하는데 부재로 표시됨)")
    check("코퍼스에 없는 등가 코드는 전부 명시적으로 표시되어 있다",
          not unflagged, str(unflagged[:5]))
    if bad_missing:
        print(f"       (부재 등가 코드 {len(bad_missing)}개, 전부 표시됨: "
              f"{', '.join(bad_missing[:5])} — repair_equivalent_labels.py 참조)")
    check("등가 코드는 전부 non-eCFR", not bad_source, bad_source[:5])
    check("매핑 키는 전부 eCFR 정답 코드", not bad_self, bad_self[:5])

    gold = {c for q in QUERIES_V1 for c in q["validated_labels"]}
    check("매핑 키가 정답 코드 집합의 부분집합",
          {m["eccn"] for m in doc["mappings"]} <= gold)

    rels = {e["relation"] for m in doc["mappings"] for e in m["equivalents"]}
    check("relation 값이 정의된 것뿐", rels <= {"equivalent", "broader"}, rels)
    confs = {e["confidence"] for m in doc["mappings"] for e in m["equivalents"]}
    check("confidence 값이 정의된 것뿐", confs <= {"low", "medium", "high"}, confs)
    check("모든 쌍에 양쪽 원문 근거",
          all(e["evidence"]["eccn_quote"] and e["evidence"]["counterpart_quote"]
              for m in doc["mappings"] for e in m["equivalents"]))
    check("거부한 후보를 이유와 함께 남긴다", len(doc["rejected_candidates"]) >= 10)

    strict = alq.equiv_index(doc, allow_broader=False)
    incl = alq.equiv_index(doc, allow_broader=True)
    check("strict 는 inclusive 의 부분집합",
          all(strict[k] <= incl[k] for k in strict))
    check("broader 쌍이 strict 에서 빠진다",
          sum(len(v) for v in strict.values()) < sum(len(v) for v in incl.values()))


# -------------------------------------------------------------------- v2 셋


def test_queries_v2() -> None:
    print("[validated_queries_expanded_v2.json]")
    if not alq.QUERIES_V2_PATH.exists():
        check("파일 존재", False, "먼저 `python audit_label_quality.py emit`")
        return
    doc = json.loads(alq.QUERIES_V2_PATH.read_text(encoding="utf-8"))
    qs = doc["queries"]
    by_id = {q["id"]: q for q in qs}
    check("151개 유지", len(qs) == 151, len(qs))
    check("id 집합이 v1 과 동일",
          {q["id"] for q in qs} == {q["id"] for q in QUERIES_V1})
    check("env_meta / seed 기록",
          "numpy" in doc["meta"]["env"] and doc["meta"]["seed"] == alq.SEED)
    # context 는 TASK G 단계 71개(validated_base + slice_seungwoo + slice_yechan)에서
    # 병합 버그로 누락됐다가 복원된 필드다. TASK J 슬라이스에서는 선택 필드이므로
    # 그 구간에서만 전량을 요구한다.
    G_ORIGINS = {"validated_base", "slice_seungwoo", "slice_yechan"}
    base = [q for q in qs if q.get("origin") in G_ORIGINS]
    check("TASK G 단계 71개 context 전부 복원",
          len(base) == 71 and all(q["context"] for q in base),
          f"n={len(base)} 누락={[q['id'] for q in base if not q['context']][:5]}")
    check("primary_label 지정", all(q["primary_label"] for q in qs))
    check("primary_label 은 validated_labels 의 원소",
          all(q["primary_label"] in q["validated_labels"] for q in qs))

    check("ext-005 의 5D991 제거",
          by_id["ext-005"]["validated_labels"] == ["ECCN-5D002"]
          and by_id["ext-005"]["validated_labels_v1"] == ["ECCN-5D002", "ECCN-5D991"])
    check("ext-023 의 5A991 제거",
          by_id["ext-023"]["validated_labels"] == ["ECCN-5A002"]
          and by_id["ext-023"]["validated_labels_v1"] == ["ECCN-5A002", "ECCN-5A991"])
    check("제거 이유 기록",
          all(by_id[q]["removed_labels"][0]["reason"] for q in ("ext-005", "ext-023")))

    e28 = by_id["ext-028"]
    check("ext-028 excluded_from_metrics", e28["excluded_from_metrics"] is True)
    check("ext-028 원문 보존", e28["query_original"] == e28["query"])
    check("ext-028 교정문에 '군용입니다' 없음", "군용입니다" not in e28["query_corrected"])
    check("ext-028 원문에는 '군용입니다' 있음", "군용입니다" in e28["query_original"])

    check("중복 코드 질의에 duplicate_gold_code 표시",
          all("duplicate_gold_code" in by_id[q]["label_issues"]
              for q in ("ext-002", "ext-029", "ext-006", "ext-016", "ext-007")))
    # 등가 라벨(타 규제체계 쌍둥이)이 붙는 비율도 확장으로 희석됐다(71개 기준 과반
    # → 151개 기준 32.5%). 성질은 '과반'이 아니라 '무시할 수 없는 규모'다.
    n_equiv = sum(1 for q in qs if q["equivalent_labels"])
    check("등가 라벨이 붙은 질의가 4분의 1 이상",
          n_equiv >= len(qs) / 4, f"{n_equiv}/{len(qs)}")
    check("등가 라벨에 정답 코드가 섞여 있지 않다",
          all(not (set(q["equivalent_labels"]) & set(q["validated_labels"])) for q in qs))


# --------------------------------------------------- 등가 채점 로직 (합성 랭킹)


def test_equiv_scoring_logic() -> None:
    print("[R@10_equiv scoring logic]")
    corpus = [
        {"code": "ECCN-3A003", "text": "gold", "source": "ecfr_part774"},
        {"code": "8A303", "text": "scomet twin", "source": "india_scomet_2024"},
        {"code": "ECCN-0A002", "text": "unrelated", "source": "ecfr_part774"},
    ]
    queries = [{"id": "q1", "lang": "en", "query": "x", "validated_labels": ["ECCN-3A003"]}]
    equiv_doc = {"mappings": [{"eccn": "ECCN-3A003", "equivalents": [
        {"code": "8A303", "regime": "india_scomet_2024", "relation": "equivalent",
         "confidence": "high"}]}]}
    eq = alq.equiv_index(equiv_doc, allow_broader=False)

    tops_twin_only = [[1, 2]]     # 쌍둥이만 회수
    hits_gold = alq.score_hits(corpus, queries, tops_twin_only,
                               lambda q: set(q["validated_labels"]))
    hits_equiv = alq.score_hits(
        corpus, queries, tops_twin_only,
        lambda q: set(q["validated_labels"]) | {
            x for c in q["validated_labels"] for x in eq.get(c, set())})
    check("정답 코드만 채점하면 miss", hits_gold == [0], hits_gold)
    check("등가 허용하면 hit", hits_equiv == [1], hits_equiv)

    tops_none = [[2]]
    check("무관 문서만 회수하면 등가 허용에도 miss",
          alq.score_hits(corpus, queries, tops_none,
                         lambda q: set(q["validated_labels"]) | {
                             x for c in q["validated_labels"] for x in eq.get(c, set())})
          == [0])

    # broader 를 금지하면 broader 쌍은 채점에 쓰이지 않는다
    equiv_broader = {"mappings": [{"eccn": "ECCN-3A003", "equivalents": [
        {"code": "8A303", "regime": "india_scomet_2024", "relation": "broader",
         "confidence": "medium"}]}]}
    check("strict 모드는 broader 를 제외",
          alq.equiv_index(equiv_broader, allow_broader=False) == {})
    check("inclusive 모드는 broader 를 포함",
          alq.equiv_index(equiv_broader, allow_broader=True)
          == {"ECCN-3A003": {"8A303"}})
    check("min_confidence 필터 동작",
          alq.equiv_index(equiv_broader, allow_broader=True,
                          min_confidence="high") == {})


# ------------------------------------------------- validate_query_slice 회귀


def test_validator_contract() -> None:
    print("[validate_query_slice]")
    check("context 는 더 이상 필수가 아니다", "context" not in vqs.REQUIRED_FIELDS)
    check("context 는 권고 필드", "context" in vqs.RECOMMENDED_FIELDS)
    check("채점에 필요한 필드는 필수 유지",
          set(vqs.REQUIRED_FIELDS) == {"id", "lang", "query", "validated_labels"},
          vqs.REQUIRED_FIELDS)
    # 두 번째 라벨에만 코드가 누출된 경우도 잡아야 한다 (예전에는 첫 라벨에서 멈췄다)
    q = "We ship telecom gear, is 5A991 relevant?"
    labels = ["ECCN-5D002", "ECCN-5A991"]
    leaked = [l for l in labels if vqs.has_code_leak(q, l)]
    check("두 번째 라벨의 누출도 검출", "ECCN-5A991" in leaked, leaked)


def main() -> int:
    for fn in (test_structural_rule, test_stub_detection, test_audits_reproduce,
               test_item_term_warning, test_equivalent_labels_file, test_queries_v2,
               test_equiv_scoring_logic, test_validator_contract):
        fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S)")
        for f in FAILURES:
            print(" -", f)
        return 1
    print("all label-audit checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
