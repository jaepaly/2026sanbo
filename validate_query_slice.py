#!/usr/bin/env python3
"""TASK G helper — validate a teammate's expanded query slice before merge.

Each TASK G query is built FROM a known eCFR corpus entry (reverse generation),
so its ground-truth label is certain by construction. This checker enforces the
mechanical gates that keep the expanded set clean and comparable to the existing
validated set, so the team lead can verify a slice with ONE command instead of
reviewing every query by hand.

Gates per query:
  1. label_exact       : every validated_labels code is an exact corpus code
                         from source=ecfr_part774 (collision-free).
  2. no_code_leak      : the query text contains no control-code-shaped token
                         and does not quote ANY of the answer codes (the old
                         version stopped at the first label, so a leak in a
                         second label was invisible).
  3. low_overlap       : 자기참조 게이트 — 어휘와 의미를 둘 다 검사한다.
                         (a) 어휘: Jaccard(query, answer minimal_text) < MAX_JACCARD
                         (b) 의미: cos(query, answer minimal_text) < tau_semantic,
                             평가용 3모델과 겹치지 않는 제3의 다국어 인코더로 측정
                             (selfreference_gate.py).
                         (a)만 있던 기존 게이트는 구조적으로 공허했다: `tokenize` 가
                         [A-Za-z0-9가-힣]+ 이고 코퍼스는 100% 영어이므로 한국어 질의의
                         교집합은 원리상 공집합이다. 검증셋 45개 한국어 질의 전부가
                         정확히 0.0000 이었고(영어 26개는 평균 0.0941, 최대 0.2364)
                         게이트는 전체의 63%에서 아무것도 검사하지 않았으며 한 번도
                         발동하지 않았다. 어휘 값은 계속 보고하되, 구조적으로 공허한
                         언어에는 경고를 출력한다.
  4. schema            : required fields present, lang in {ko, en}, no duplicate
                         labels inside one query.

Slice-level checks: minimum count, Korean ratio, unique query ids, and
'one query = one item' (no gold ECCN may be the answer to two queries).

Warnings (not failures): missing `context`, and gold labels whose corpus text is
only a heading stub — see `audit_label_quality.py` for the full label audit.

Usage:
  python validate_query_slice.py data/validated_queries_slice_<name>.json
Exit code 0 = all gates pass; 1 = at least one failure (details printed).

M8 수정 이력
------------
* 모든 라벨 검사: gate 2 가 첫 라벨에서 멈추던 것을 전 라벨로 확장했고, gate 1 은
  유효 라벨 전부를 `ans_entries` 로 모은다(`ans_entry` 는 하위호환 별칭).
* `context` 를 필수에서 권고로 낮췄다. 필수였던 탓에 병합셋
  data/validated_queries_expanded.json 의 71건 전부가 gate 4 에서 실패했다.
* `excluded_from_metrics` 질의는 빈 validated_labels 를 허용한다.
* 슬라이스 레벨에 정답 코드 재사용 검사와 표제 스텁 경고를 추가했다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import selfreference_gate as sg
from run_experiments import build_doc_text, tokenize, CONTROL_CODE_RE, has_code_leak

# 정답 본문이 표제만 있고 기술 파라미터를 별도 문서로 넘기는 형태인지 판정한다.
# audit_label_quality.py 의 STUB_RE 와 동일한 정의를 쓴다.
HEADING_STUB_RE = re.compile(r"\(\s*see\s+(?:the\s+)?list\s+of\s+items\s+cont(?:r)?ol", re.I)

ROOT = Path(__file__).resolve().parent
CORPUS_PATH = ROOT / "data" / "corpus" / "combined.json"

MAX_JACCARD = 0.30
MIN_QUERIES = 25
MIN_KO_RATIO = 0.40

# `context` 는 리뷰용 메모이지 채점에 쓰이는 필드가 아니다. 필수 목록에 있었던
# 탓에 병합셋 data/validated_queries_expanded.json 의 71건 전부가 gate 4 에서
# 실패했다(병합 스크립트가 context 를 옮기지 않았다). 이제는 경고로 낮추고,
# 실제 채점에 필요한 필드만 실패 조건으로 둔다.
# data/validated_queries_expanded_v2.json 은 context 를 복원해 두었다.
REQUIRED_FIELDS = ["id", "lang", "query", "validated_labels"]
RECOMMENDED_FIELDS = ["context"]


def jaccard(a: list[str], b: list[str]) -> float:
    """어휘 Jaccard. selfreference_gate.jaccard 와 동일 정의(두 곳에서 쓰이므로 위임)."""
    return sg.jaccard(a, b)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python validate_query_slice.py <slice.json>")
        return 1
    slice_path = Path(sys.argv[1])
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    by_code = {e["code"]: e for e in corpus}

    payload = json.loads(slice_path.read_text(encoding="utf-8"))
    queries = payload["queries"] if isinstance(payload, dict) else payload

    failures: list[str] = []
    warnings: list[str] = []
    gate3_rows: list[dict] = []      # gate 3b(의미 게이트)를 배치로 돌리기 위한 수집
    ko = en = 0
    label_owners: dict[str, list[str]] = {}   # 코드 -> 그 코드를 정답으로 쓴 질의 id들
    for q in queries:
        qid = q.get("id", "<no-id>")
        excluded = bool(q.get("excluded_from_metrics"))

        # gate 4: schema
        missing = [f for f in REQUIRED_FIELDS
                   if q.get(f) in (None, "", [])
                   and not (f == "validated_labels" and excluded)]
        if missing:
            failures.append(f"{qid}: missing fields {missing}")
            continue
        soft = [f for f in RECOMMENDED_FIELDS if not q.get(f)]
        if soft:
            warnings.append(f"{qid}: missing recommended fields {soft}")
        if q["lang"] not in ("ko", "en"):
            failures.append(f"{qid}: lang must be ko/en, got {q['lang']!r}")
        if q["lang"] == "ko":
            ko += 1
        else:
            en += 1

        labels = q["validated_labels"]
        if not labels:
            if excluded:
                warnings.append(f"{qid}: empty validated_labels (excluded_from_metrics)")
                continue
            failures.append(f"{qid}: empty validated_labels")
            continue
        if len(set(labels)) != len(labels):
            failures.append(f"{qid}: validated_labels contains duplicates: {labels}")

        # gate 1: label exact + eCFR source
        # 모든 라벨을 검사한다. `ans_entries` 는 유효한 라벨의 코퍼스 항목 전부이고,
        # `ans_entry` 는 하위 게이트의 하위호환을 위해 그 첫 번째를 가리킨다.
        ans_entries: list[dict] = []
        for lbl in labels:
            entry = by_code.get(lbl)
            if entry is None:
                failures.append(f"{qid}: label {lbl!r} is not an exact corpus code")
            elif entry.get("source") != "ecfr_part774":
                failures.append(f"{qid}: label {lbl!r} source={entry.get('source')} (must be ecfr_part774)")
            else:
                ans_entries.append(entry)
                label_owners.setdefault(lbl, []).append(qid)
        ans_entry = ans_entries[0] if ans_entries else None

        # gate 1b: 정답 본문이 표제 스텁이면 어휘적으로 맞출 수 없다 (경고).
        # 상세 감사는 audit_label_quality.py 를 보라.
        if ans_entries and all(HEADING_STUB_RE.search(e.get("text") or "")
                               for e in ans_entries):
            warnings.append(
                f"{qid}: every gold label is a heading stub "
                f"({', '.join(e['code'] for e in ans_entries)}) — "
                "기술 파라미터가 코퍼스에 없다")

        # gate 2: no code leak — 라벨 하나가 아니라 전부에 대해 검사한다.
        leaked = [lbl for lbl in labels if has_code_leak(q["query"], lbl)]
        if leaked:
            failures.append(
                f"{qid}: code leak — query contains code variant of {', '.join(leaked)}")
        elif CONTROL_CODE_RE.search(q["query"]):
            failures.append(f"{qid}: query contains a control-code-shaped token")

        # gate 3a: 어휘 중첩 (기존 정의 유지 — 비교 가능성 때문에 임계값도 그대로)
        if ans_entry is not None:
            j = jaccard(tokenize(q["query"]), tokenize(build_doc_text(ans_entry, "minimal_text")))
            if j >= MAX_JACCARD:
                failures.append(f"{qid}: Jaccard {j:.3f} >= {MAX_JACCARD} (too close to entry wording — paraphrase more)")
            # gate 3b 는 인코더 호출이므로 슬라이스 전체를 모아 한 번에 처리한다.
            gate3_rows.append({"id": qid, "lang": q["lang"], "query": q["query"],
                               "lexical_jaccard": round(j, 4),
                               "answer_code": ans_entry["code"]})

    # ---- gate 3b: 언어중립 의미 게이트 -------------------------------------
    # 어휘 게이트만으로는 한국어 질의를 전혀 검사하지 못한다(위 docstring 참조).
    # 인코더를 쓸 수 없으면 조용히 통과시키지 않고 실패로 보고한다.
    gate3_semantic: dict = {"checked": False}
    if gate3_rows:
        void = sg.lexical_void_warning(gate3_rows)
        for lang, w in sorted(void.items()):
            if w["warning"]:
                warnings.append(f"gate3[{lang}]: {w['warning']}")
        try:
            model = sg.load_gate_model()
            tau = sg.cached_tau(corpus, queries, model)
            texts = [r["query"] for r in gate3_rows]
            ans_texts = [build_doc_text(by_code[r["answer_code"]], "minimal_text")
                         for r in gate3_rows]
            uniq = sorted(set(ans_texts))
            a_emb = sg.encode(uniq, model)
            a_idx = {t: i for i, t in enumerate(uniq)}
            q_emb = sg.encode(texts, model)
            over = []
            for i, r in enumerate(gate3_rows):
                r["semantic_cos"] = round(float(q_emb[i] @ a_emb[a_idx[ans_texts[i]]]), 4)
                if r["semantic_cos"] >= tau:
                    over.append(r)
                    failures.append(
                        f"{r['id']}: semantic cos {r['semantic_cos']:.4f} >= tau {tau:.2f} "
                        f"vs {r['answer_code']} — 정답 원문의 번역/직역에 가깝다 "
                        f"(어휘 Jaccard {r['lexical_jaccard']:.4f} 는 이것을 잡지 못한다)")
            gate3_semantic = {
                "checked": True,
                "gate_model": sg.GATE_MODEL,
                "tau_semantic": tau,
                "n_over_tau": len(over),
                "over_tau": [{"id": r["id"], "lang": r["lang"],
                              "answer_code": r["answer_code"],
                              "semantic_cos": r["semantic_cos"],
                              "lexical_jaccard": r["lexical_jaccard"]} for r in over],
                "lexical_void_by_lang": void,
                "per_query": gate3_rows,
            }
        except Exception as exc:   # noqa: BLE001 — 게이트 미실행은 통과가 아니다
            failures.append(
                f"gate3: 의미 게이트를 실행할 수 없었다 ({type(exc).__name__}: {exc}). "
                "어휘 게이트만으로는 한국어 질의를 검사할 수 없으므로 통과로 처리하지 않는다.")
            gate3_semantic = {"checked": False, "error": f"{type(exc).__name__}: {exc}",
                              "lexical_void_by_lang": void}

    n = len(queries)
    ko_ratio = ko / n if n else 0.0
    if n < MIN_QUERIES:
        failures.append(f"slice: only {n} queries (need >= {MIN_QUERIES})")
    if ko_ratio < MIN_KO_RATIO:
        failures.append(f"slice: Korean ratio {ko_ratio:.2f} < {MIN_KO_RATIO} (ko={ko}, en={en})")

    # 슬라이스 레벨: '1질의 1항목'. 같은 ECCN 이 두 질의의 정답이면 두 질의는
    # 사실상 같은 문항이므로 난이도와 분산 추정이 왜곡된다.
    reused = {code: ids for code, ids in sorted(label_owners.items()) if len(ids) > 1}
    for code, ids in reused.items():
        failures.append(
            f"slice: gold code {code} reused by {len(ids)} queries ({', '.join(ids)}) "
            "— 1질의 1항목 위반")

    duplicate_ids = sorted({qid for qid in
                            [q.get("id") for q in queries]
                            if [x.get("id") for x in queries].count(qid) > 1})
    if duplicate_ids:
        failures.append(f"slice: duplicate query ids {duplicate_ids}")

    print(json.dumps({
        "slice": slice_path.name,
        "queries": n,
        "ko": ko,
        "en": en,
        "ko_ratio": round(ko_ratio, 3),
        "max_jaccard_allowed": MAX_JACCARD,
        "gate3_selfreference": gate3_semantic,
        "distinct_gold_codes": len(label_owners),
        "gold_label_occurrences": sum(len(v) for v in label_owners.values()),
        "reused_gold_codes": reused,
        "failures": failures,
        "warnings": warnings,
        "passed": not failures,
    }, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
