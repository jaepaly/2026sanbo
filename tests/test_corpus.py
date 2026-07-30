#!/usr/bin/env python3
"""코퍼스 파싱 교정(M7) 회귀 검증.

두 계층으로 나뉜다.

A. **오프라인 단위 검증** — PDF 없이 정규식/분류 함수만 검사한다. 항상 실행된다.
B. **산출물 검증** — ``data/corpus/combined_v2.json`` 이 있으면 실제 코퍼스를 검사한다.
   (없으면 SKIP. 생성: ``python build_corpus_clean.py --v2``)

실행: ``python tests/test_corpus.py``
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build_corpus as bc  # noqa: E402
from build_corpus_clean import CODE_PATTERNS, source_valid_code  # noqa: E402

FAILURES: list[str] = []
SKIPPED: list[str] = []

V2_PATH = ROOT / "data" / "corpus" / "combined_v2.json"
V1_PATH = ROOT / "data" / "corpus" / "combined.json"


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(f"{name} {detail}")


def skip(name: str, why: str) -> None:
    print(f"  skip {name} ({why})")
    SKIPPED.append(name)


# =========================================================================
# A. 오프라인 단위 검증
# =========================================================================


def test_fake_code_rejection() -> None:
    """번호목록이 항목 코드로 오인되지 않는지."""
    print("[fake-code rejection]")
    # v1이 가짜 항목으로 만들었던 원문 행 (실측: PDF에서 26회 등장, 고유 코드 15개)
    fake_lines = [
        "2. In the form of uncomminuted flakes, ribbons or thin rods; and",
        "3. In a liquid state at 273 K (0°C); and",
        "5. CP (2-(5-cyanotetrazolato) penta amine-cobalt (III) perchlorate) (CAS 70247-32-4);",
        "2. Is \"allocated by the ITU\" for radio-communications",
        "2. To an output power greater than 100 mW (20 dBm)",
        "1. To meet paragraph a. of Note 3, all of the following must apply:",
        "1. It is restricted for use in equipment or systems to",
        "2. It cannot be reprogrammed for any other use; or",
        "2. CW \"Laser\" Induced Damage Threshold (LIDT) greater",
        "1. CW nerve agents:",
        "4. CW defoliants, such as:",
        "2. AP (ammonium perchlorate) (CAS 7790-98-9);",
        "3. An organic \"matrix\" and \"fibrous or filamentary materials\"",
        "5. At the output of the amplifier;",
    ]
    for line in fake_lines:
        m = bc.WASS_ENTRY_V2_RE.match(line)
        code = None
        if m:
            parts = [str(t) for t in m.groups()[:-1] if t is not None]
            code, _, _ = bc.repair_wassenaar_code(parts, m.groups()[-1])
        check(f"번호목록이 항목이 아님: {line[:44]!r}", code is None, f"-> {code}")

    # v1 정규식은 실제로 이 행들을 잡아냈다(교정이 유효함을 증명)
    caught_by_v1 = 0
    for line in fake_lines:
        if bc.WASS_ENTRY_RE.match(line) or bc.WASS_ENTRY_SHORT_RE.match(line):
            caught_by_v1 += 1
    check("v1 정규식은 같은 행들을 항목으로 오인했다(회귀 대비 기준선)",
          caught_by_v1 >= 12, f"v1 matched {caught_by_v1}/{len(fake_lines)}")


def test_real_entry_lines_still_parse() -> None:
    """실제 항목 행은 계속 인식되는지 (교정이 과잉이지 않은지)."""
    print("[real entry lines]")
    cases = {
        "1. A. 3. Manufactures of non-\"fusible\" aromatic polyimides in film": "1.A.3",
        "1. A. 4. a. 1. \"Biological agents\";": "1.A.4.a.1",
        "3. A. 2. d. 4. A Single Sideband (SSB) phase noise, in dBc/Hz": "3.A.2.d.4",
        "6. A. 1. a. 1. a. 2. Underwater survey equipment designed for seabed": "6.A.1.a.1.a.2",
        "2. E. TECHNOLOGY": "2.E",
        "1. A. SYSTEMS, EQUIPMENT AND COMPONENTS": "1.A",
    }
    for line, want in cases.items():
        m = bc.WASS_ENTRY_V2_RE.match(line)
        got = None
        if m:
            parts = [str(t) for t in m.groups()[:-1] if t is not None]
            got, _, _ = bc.repair_wassenaar_code(parts, m.groups()[-1])
        check(f"{want} 인식", got == want, f"got {got!r}")


def test_cross_reference_lines_are_not_entries() -> None:
    """줄바꿈된 상호참조 행을 새 항목으로 오인하지 않는지 (붙임표 없는 형태)."""
    print("[cross-reference continuation lines]")
    lines = [
        "3.A.1.a.10. and 3.A.1.a.12., based upon any compound semiconductor",
        "5.D.2.c.3.a.;",
        "6.A.3.a.3., 6.A.3.a.4. or 6.A.3.a.5., according to the",
        "7.E.4.a.3., 7.E.4.a.5., 7.E.4.a.6. or 7.E.4.b., for any of the following:",
        "8.E.2.a. & 8.E.2.b.",
    ]
    for line in lines:
        check(f"상호참조 행이 항목이 아님: {line[:44]!r}",
              bc.WASS_ENTRY_V2_RE.match(line) is None)


def test_header_footer_filters() -> None:
    """러닝 헤더·푸터·각주가 본문에서 제거되는지."""
    print("[header/footer/footnote filters]")
    drop = [
        "____________________________________________________________________",
        "WA-LIST (25) 1 Corr.",
        "- 40 - 15-01-2026",
        "15-01-2026 - 95 -",              # v1 skip_tail 이 놓치던 변형
        "DUAL-USE LIST - CATEGORY 2 – MATERIALS PROCESSING",
        "MUNITIONS LIST",
        "* The Russian Federation and Ukraine view this list as a reference list",
    ]
    for line in drop:
        cleaned, _ = bc._wassenaar_clean_line(line)
        check(f"제거: {line[:44]!r}", cleaned is None, f"-> {cleaned!r}")

    keep = [
        "Wassenaar Arrangement Participating States; and",   # v1 이 prefix 매칭으로 잘못 버린 본문
        "Items having a specified frequency range of less than ±0.05% around",
        "a. A thickness exceeding 0.254 mm; or",
    ]
    for line in keep:
        cleaned, _ = bc._wassenaar_clean_line(line)
        check(f"보존: {line[:44]!r}", cleaned == line, f"-> {cleaned!r}")


def test_footnote_marker_strip() -> None:
    """문말 각주 표식(*)만 떼고 본문은 보존하는지. (결함 4: 정규식 잔재가 아님)"""
    print("[footnote marker]")
    cleaned, stripped = bc._wassenaar_clean_line("Note 2.d.*")
    check("'Note 2.d.*' -> 'Note 2.d.'", cleaned == "Note 2.d." and stripped, f"-> {cleaned!r}")
    cleaned, stripped = bc._wassenaar_clean_line(
        "N.B. For propulsion systems ... see the Munitions List.*"
    )
    check("문말 '*' 제거", cleaned is not None and cleaned.endswith("Munitions List.") and stripped,
          f"-> {cleaned!r}")
    cleaned, stripped = bc._wassenaar_clean_line("a. A thickness exceeding 0.254 mm; or")
    check("표식 없는 행은 무변경", cleaned == "a. A thickness exceeding 0.254 mm; or" and not stripped)


def test_scomet_category_heading_filter() -> None:
    """SCOMET 표의 카테고리 표제행이 직전 항목 본문에 붙지 않는지."""
    print("[scomet category headings]")
    headings = [
        "0A2 Special Fissionable Material",
        "8A3 ELECTRONICS (SYSTEMS, EQUIPMENT AND COMPONENTS)",
        "3A5 Stealth materials",
    ]
    for line in headings:
        check(f"표제행 인식: {line[:44]!r}",
              bool(bc.SCOMET_CATEGORY_HEADING_RE.match(line))
              and not bc.SCOMET_ENTRY_RE.match(line))
    not_headings = ["8B1 or 8C.", "8D2 and 8E2."]
    for line in not_headings:
        check(f"문장 중간 연속행은 표제행 아님: {line!r}",
              not bc.SCOMET_CATEGORY_HEADING_RE.match(line))
    check("실제 SCOMET 코드행은 표제행 필터에 걸리지 않음",
          bool(bc.SCOMET_ENTRY_RE.match("8A301 Electronic items as follows:")))


def test_completeness_classifier() -> None:
    print("[text_completeness]")
    cases = [
        ("1.C.5", "Not used since 2017", "stub"),
        ("3D002", "[Reserved]", "stub"),
        ("8A301", "(Reserved)", "stub"),
        ("1.A", "SYSTEMS, EQUIPMENT AND COMPONENTS", "heading_only"),
        ("1.E", "TECHNOLOGY", "heading_only"),
        ("1.A.3", "Manufactures of non-\"fusible\" aromatic polyimides.", "full"),
    ]
    for code, text, want in cases:
        got = bc.classify_completeness(code, text)
        check(f"{code!r} -> {want}", got == want, f"got {got}")


def test_finalize_keeps_longest() -> None:
    """중복 코드에서 v1은 '첫 등장'을, v2는 '최장 본문'을 남긴다."""
    print("[_finalize dedupe]")
    entries = [
        {"code": "1.A.1", "text": "short text here.", "source": "wassenaar_2025",
         "page": 1, "pages": [1], "parse_flags": []},
        {"code": "1.A.1", "text": "a much longer and more complete body of text here.",
         "source": "wassenaar_2025", "page": 9, "pages": [9], "parse_flags": ["page_continuation"]},
    ]
    out = bc._finalize([dict(e) for e in entries], min_len=10)
    check("코드 1개로 축약", len(out) == 1, f"got {len(out)}")
    check("최장 본문 유지", out[0]["text"].startswith("a much longer"), out[0]["text"][:30])
    check("duplicate_occurrences 기록", out[0]["duplicate_occurrences"] == 1)
    check("플래그 병합", "duplicate_occurrences" in out[0]["parse_flags"])


# =========================================================================
# B. 산출물 검증 (combined_v2.json)
# =========================================================================


def load_v2() -> list[dict] | None:
    if not V2_PATH.exists():
        return None
    return json.loads(V2_PATH.read_text(encoding="utf-8"))


def test_v2_corpus(corpus: list[dict]) -> None:
    print("[combined_v2.json 구조]")
    required = {"code", "text", "source", "text_completeness", "parse_flags"}
    check("필수 필드 존재", all(required <= set(e) for e in corpus))
    check("text_completeness 값 집합",
          set(e["text_completeness"] for e in corpus) <= {"full", "heading_only", "stub"},
          str(Counter(e["text_completeness"] for e in corpus)))

    print("[코드 중복 0]")
    dup = [c for c, n in Counter((e["source"], e["code"]) for e in corpus).items() if n > 1]
    check("(source, code) 중복 없음", not dup, str(dup[:5]))
    dup_global = [c for c, n in Counter(e["code"] for e in corpus).items() if n > 1]
    check("코드 전역 중복 없음", not dup_global, str(dup_global[:5]))

    print("[가짜 코드 제거]")
    fake = ["2.I.n", "3.I.n", "5.C.P", "2.I.s", "2.T.o", "1.T.o", "1.I.t", "2.I.t",
            "2.C.W", "1.C.W", "4.C.W", "2.A.P", "3.A.2.d.4.A", "3.A.2.d.5.A", "3.A.2.d.6.A",
            "1.A.n", "2.A.n", "3.A.n", "5.A.n", "2.A.t"]
    present = sorted({e["code"] for e in corpus} & set(fake))
    check("v1의 가짜 코드가 하나도 없음", not present, str(present))
    bad = [e["code"] for e in corpus if not source_valid_code(e["source"], e["code"])]
    check("모든 코드가 소스별 정규 문법을 만족", not bad, str(bad[:5]))

    print("[복구된 코드]")
    for code in ("3.A.2.d.4", "3.A.2.d.5", "3.A.2.d.6"):
        e = next((x for x in corpus if x["code"] == code), None)
        check(f"{code} 존재(v1에서는 통째로 폐기됐다)", e is not None)

    print("[페이지 경계 이어붙이기]")
    byc = {e["code"]: e for e in corpus}
    # 1.A.4.c 의 Note 목록은 5쪽 'j.' 에서 끊겨 6쪽 'k.'~'o.' 로 이어진다
    e = byc.get("1.A.4.c")
    check("1.A.4.c 존재", e is not None)
    if e:
        check("1.A.4.c 가 다음 페이지 항목(k~o)을 포함",
              "Chloropicrin" in e["text"] and "Bromo methylethylketone" in e["text"],
              e["text"][-90:])
        check("1.A.4.c 가 page_continuation 플래그 보유",
              "page_continuation" in e["parse_flags"], str(e["parse_flags"]))
    # 1.A.2 는 v1에서 표제만 남고 열거목록 전체가 소실됐다
    e = byc.get("1.A.2")
    check("1.A.2 존재", e is not None)
    if e:
        check("1.A.2 에 열거목록이 복원됨(v1은 83자)", len(e["text"]) > 800, f"len={len(e['text'])}")
    # SCOMET 표의 하위 문단 병합
    e = byc.get("6A001")
    check("6A001 존재", e is not None)
    if e:
        check("6A001 이 하위문단 b/c/d 를 포함", "Smooth-bore weapons as follows" in e["text"]
              or "Weapons using caseless ammunition" in e["text"], e["text"][:80])
        check("6A001 이 table_row_merged 플래그 보유",
              "table_row_merged" in e["parse_flags"], str(e["parse_flags"]))

    print("[푸터·각주 잔재 제거]")
    footer = [e["code"] for e in corpus if re.search(r"\d{2}-\d{2}-\d{4}\s*-\s*\d{1,3}\s*-", e["text"])]
    check("본문에 날짜/페이지 푸터 잔재 없음", not footer, str(footer[:5]))
    star = [e["code"] for e in corpus if ".*" in e["text"]]
    check("본문에 리터럴 '.*' 없음", not star, str(star))
    fn = [e["code"] for e in corpus
          if "The Russian Federation and Ukraine view this list" in e["text"]]
    check("각주 본문 혼입 없음", not fn, str(fn[:5]))
    walist = [e["code"] for e in corpus if "WA-LIST (25)" in e["text"]]
    check("WA-LIST 푸터 혼입 없음", not walist, str(walist[:5]))

    print("[비교: v1 대비 미완 비율 감소]")
    if V1_PATH.exists():
        v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
        for src in ("wassenaar_2025", "india_scomet_2024"):
            a = [e for e in v1 if e["source"] == src]
            b = [e for e in corpus if e["source"] == src]
            ra = sum(1 for e in a if not bc.TERMINATOR_RE.search(e["text"].strip())) / max(len(a), 1)
            rb = sum(1 for e in b if not bc.TERMINATOR_RE.search(e["text"].strip())) / max(len(b), 1)
            check(f"{src} 종결부호 미완 비율 감소 ({ra:.4f} -> {rb:.4f})", rb <= ra)
            ca = sum(len(e["text"]) for e in a)
            cb = sum(len(e["text"]) for e in b)
            check(f"{src} 본문 총량 증가 ({ca} -> {cb})", cb > ca)
        check("combined.json 은 v1 그대로(1797건)", len(v1) == 1797, f"len={len(v1)}")
    else:
        skip("v1 대비 비교", "combined.json 없음")


def main() -> int:
    test_fake_code_rejection()
    test_real_entry_lines_still_parse()
    test_cross_reference_lines_are_not_entries()
    test_header_footer_filters()
    test_footnote_marker_strip()
    test_scomet_category_heading_filter()
    test_completeness_classifier()
    test_finalize_keeps_longest()

    corpus = load_v2()
    if corpus is None:
        skip("combined_v2.json 검증", "python build_corpus_clean.py --v2 로 먼저 생성하라")
    else:
        test_v2_corpus(corpus)

    print()
    if SKIPPED:
        print(f"{len(SKIPPED)} skipped")
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S)")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
