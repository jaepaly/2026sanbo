#!/usr/bin/env python3
"""fetch_sources.py / fetch_ecfr.py 검증.

네트워크 없이 돌아가는 검사만 넣었다. eCFR 파싱은 저장해 둔 XML 조각(fixture)을
쓰므로 오프라인에서도 결정론적으로 통과한다.

Run: python tests/test_fetch_sources.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import fetch_ecfr as fe  # noqa: E402
import fetch_sources as fs  # noqa: E402

FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(f"{name} {detail}".strip())


# ---------------------------------------------------------------------------
# eCFR XML fixture: 실제 원문 구조의 변형 사례를 모두 담은 최소 표본
#   - 0A501: 표준형 <FP-2><B>, <FP-1><E>절, <FP><I>Items:</I>
#   - 3A090: 절 표제를 <HD1>로 쓴 사례 (경계로 오인하면 본문 유실)
#   - 8D001: 표제를 <FP-2>가 아니라 <FP-1><B>로 쓴 사례 (기존 파일이 놓친 항목)
#   - 9D604: 'Items' 뒤 콜론이 빠진 사례
#   - 5A001: 'Items' 마커가 아예 없어 LOIC 본문으로 대체해야 하는 사례
#   - 6E003: 항목 내부 소제목 <HD2> (경계로 오인하면 본문 유실)
# ---------------------------------------------------------------------------

FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<DIV9 N="Supplement No. 1 to Part 774" TYPE="APPENDIX">
<HEAD>Supplement No. 1 to Part 774-The Commerce Control List</HEAD>
<HD1>Category 0—Nuclear Materials, Facilities, and Equipment</HD1>
<HD1>A. “End Items”, “Equipment”</HD1>
<FP-2><B>0A501 Firearms as follows (see List of Items controlled).</B></FP-2>
<FP-1><E T="04">License Requirements</E></FP-1>
<FP-1><I>Reason for Control:</I> NS, RS, FC, UN, AT</FP-1>
<DIV><TABLE><TBODY>
<TR><TD>NS applies to entire entry</TD><TD>NS Column 1.</TD></TR>
</TBODY></TABLE></DIV>
<FP-1><E T="04">List of Items Controlled</E></FP-1>
<FP-1><I>Related Controls:</I> See USML Category I.</FP-1>
<FP-1><I>Related Definitions:</I> N/A</FP-1>
<FP><I>Items:</I> a. Non-automatic firearms equal to .50 caliber or less.</FP>
<P>b. Detachable magazines with a capacity of 17 to 50 rounds.</P>
<NOTE><HED><I>Note 1:</I></HED><P><I>Magazines with 16 rounds or less are 0A501.x.</I></P></NOTE>
<HD1>Category 3—Electronics</HD1>
<HD1>A. “End Items”</HD1>
<FP-2><B>3A090 Integrated circuits as follows (see List of Items Controlled).</B></FP-2>
<FP-1><E T="04">License Requirements</E></FP-1>
<FP-1><I>Reason for Control:</I> RS, AT</FP-1>
<HD1>List Based License Exceptions (See Part 740 for a Description of All License Exceptions)</HD1>
<FP-1><I>LVS:</I> N/A</FP-1>
<HD1>List of Items Controlled</HD1>
<FP-1><I>Related Controls:</I> See ECCNs 3D001, 3E001.</FP-1>
<FP><I>Items:</I></FP>
<P>a. Integrated circuits having a total processing performance of 4800 or more.</P>
<HD1>Category 5—Telecommunications</HD1>
<HD1>A. “End Items”</HD1>
<FP-2><B>5A001 Telecommunications systems as follows (see List of Items Controlled).</B></FP-2>
<FP-1><E T="04">License Requirements</E></FP-1>
<FP-1><E T="04">List of Items Controlled</E></FP-1>
<FP-1><I>Related Controls:</I> See USML Category XI.</FP-1>
<P>a. Any type of telecommunications equipment having underwater operation.</P>
<P>b. Radio equipment operating below 30 MHz.</P>
<HD1>Category 6—Sensors and Lasers</HD1>
<HD1>E. “Technology”</HD1>
<FP-2><B>6E003 Other “technology” as follows (see List of Items Controlled).</B></FP-2>
<FP-1><E T="04">List of Items Controlled</E></FP-1>
<FP-1><I>Related Controls:</I> N/A</FP-1>
<FP><I>Items:</I></FP>
<HD2>Acoustics</HD2>
<P>a. [Reserved]</P>
<HD2>Optics</HD2>
<P>d. “Technology” required for the coating of optical surfaces.</P>
<HD1>Category 8—Marine</HD1>
<HD1>D. “Software”</HD1>
<FP-1><B>8D001 “Software” for the “Development” of Equipment Controlled by 8A</B>.</FP-1>
<FP-1><E T="04">License Requirements</E></FP-1>
<FP-1><I>List of Items Controlled</I></FP-1>
<FP-1><I>Related Controls:</I> N/A</FP-1>
<FP><I>Items:</I> The list of items controlled is contained in the ECCN heading.</FP>
<HD1>Category 9—Aerospace and Propulsion</HD1>
<HD1>D. “Software”</HD1>
<FP-2><B>9D604 “Software” for commodities controlled by 9A604.</B></FP-2>
<FP-1><E T="04">List of Items Controlled</E></FP-1>
<FP-1><I>Related Definitions:</I> N/A</FP-1>
<FP><I>Items</I> a. “Software” specially designed for the production of 9A604 commodities.</FP>
<P>b. [Reserved]</P>
<FP-2><B>9A007 Solid rocket propulsion systems. (These items are subject to the ITAR.)</B></FP-2>
<FP-1><E T="04">License Requirements</E></FP-1>
</DIV9>
"""


def parsed():
    entries = fe.finalize(fe.parse_supplement(FIXTURE.encode("utf-8")), "full")
    return {e["code"]: e for e in entries}, entries


def test_entry_detection() -> None:
    print("[fetch_ecfr] 항목 검출")
    by_code, entries = parsed()
    check("항목 수 = 7", len(entries) == 7, f"got {len(entries)}")
    check("표준 <FP-2><B> 표제 검출 (0A501)", "ECCN-0A501" in by_code)
    check("비표준 <FP-1><B> 표제 검출 (8D001)", "ECCN-8D001" in by_code,
          "기존 ecfr_supp1.json이 놓친 항목")
    check("코드 중복 없음", len(by_code) == len(entries))
    check("category는 코드 첫 글자에서 파생", all(e["category"] == e["code"][5] for e in entries))


def test_no_false_heading_from_crossreference() -> None:
    print("[fetch_ecfr] 상호참조를 표제로 오인하지 않음")
    by_code, _ = parsed()
    # 본문 안의 '3D001', '9A604', '8A' 등은 표제가 아니다.
    for bogus in ("ECCN-3D001", "ECCN-3E001", "ECCN-9A604", "ECCN-0A501x"):
        check(f"{bogus}는 항목으로 만들어지지 않음", bogus not in by_code)


def test_items_recovery() -> None:
    print("[fetch_ecfr] List of Items Controlled 본문 수집")
    by_code, _ = parsed()

    e = by_code["ECCN-0A501"]
    check("0A501 Items 수집", "Non-automatic firearms" in e["items"])
    check("0A501 후속 <P> 이어붙임", "Detachable magazines" in e["items"])
    check("0A501 <NOTE> 이어붙임", "16 rounds or less" in e["items"])
    check("0A501 related_controls 분리", e["related_controls"] == "See USML Category I.")
    check("0A501 related_controls에 본문이 섞이지 않음",
          "Detachable magazines" not in e["related_controls"])
    check("0A501 표에서 Reason for Control 추출", e["reason_for_control"].startswith("NS, RS"))
    check("0A501 License Requirements 절에 표가 평문화됨",
          "NS Column 1." in e["sections"]["License Requirements"])

    e = by_code["ECCN-3A090"]
    check("3A090 <HD1> 절 표제를 경계로 오인하지 않음",
          "total processing performance of 4800" in e["items"], e["items"][:60])

    e = by_code["ECCN-6E003"]
    check("6E003 항목 내부 <HD2> 소제목을 경계로 오인하지 않음",
          "coating of optical surfaces" in e["items"], e["items"][:60])
    check("6E003 소제목 자체도 본문에 남음", "Acoustics" in e["items"])

    e = by_code["ECCN-9D604"]
    check("9D604 콜론 없는 <I>Items</I> 처리", "specially designed" in e["items"])

    e = by_code["ECCN-5A001"]
    check("5A001 Items 마커 없을 때 LOIC 본문으로 대체",
          e["items_source"] == "loic_body_fallback", e["items_source"])
    check("5A001 본문 수집", "underwater operation" in e["items"] and "below 30 MHz" in e["items"])
    check("5A001 related_controls 오염 없음",
          e["related_controls"] == "See USML Category XI.", e["related_controls"][:80])

    e = by_code["ECCN-9A007"]
    check("Items가 정말 없는 항목은 heading_only", e["heading_only"] is True)
    check("heading_only 항목의 items_source는 none", e["items_source"] == "none")


def test_section_canonicalization() -> None:
    print("[fetch_ecfr] 절 표제 정규화")
    variants = [
        "List Based License Exceptions (See Part 740 for a Description of All License Exceptions)",
        "List Based License Exceptions (see Part 740 for a description of all license exceptions)",
        "List Based License Exceptions",
        "License Exceptions",
    ]
    canon = {fe.canon_section(v) for v in variants}
    check("License Exceptions 표기 흔들림이 한 키로 모임", canon == {"List Based License Exceptions"}, str(canon))
    check("'List of Items Controlled:' 도 같은 키",
          fe.canon_section("List of Items Controlled:") == fe.SECTION_LIST_OF_ITEMS)


def test_text_field_modes() -> None:
    print("[fetch_ecfr] text 필드 모드")
    raw = fe.parse_supplement(FIXTURE.encode("utf-8"))
    heading_mode = {e["code"]: e for e in fe.finalize(raw, "heading")}
    full_mode = {e["code"]: e for e in fe.finalize(raw, "full")}
    a = heading_mode["ECCN-0A501"]
    b = full_mode["ECCN-0A501"]
    check("heading 모드 text == heading", a["text"] == a["heading"])
    check("full 모드 text == heading + items", b["text"].startswith(b["heading"]) and b["items"] in b["text"])
    check("full 모드가 heading 모드보다 길다", len(b["text"]) > len(a["text"]))
    total_h = sum(len(e["text"]) for e in heading_mode.values())
    total_f = sum(len(e["text"]) for e in full_mode.values())
    check("전체 노출 텍스트가 늘어남", total_f > total_h, f"{total_h} -> {total_f}")


def test_determinism() -> None:
    print("[fetch_ecfr] 결정론성")
    import json
    a = json.dumps(fe.finalize(fe.parse_supplement(FIXTURE.encode("utf-8")), "full"),
                   ensure_ascii=False, sort_keys=True)
    b = json.dumps(fe.finalize(fe.parse_supplement(FIXTURE.encode("utf-8")), "full"),
                   ensure_ascii=False, sort_keys=True)
    check("같은 입력 -> 같은 출력", hashlib.sha256(a.encode()).hexdigest()
          == hashlib.sha256(b.encode()).hexdigest())
    codes = [e["code"] for e in fe.finalize(fe.parse_supplement(FIXTURE.encode("utf-8")), "full")]
    check("문서 등장 순서 보존",
          codes == ["ECCN-0A501", "ECCN-3A090", "ECCN-5A001", "ECCN-6E003",
                    "ECCN-8D001", "ECCN-9D604", "ECCN-9A007"], str(codes))


def test_sources_table() -> None:
    print("[fetch_sources] 출처 표 무결성")
    ids = [s["id"] for s in fs.SOURCES]
    check("id 중복 없음", len(ids) == len(set(ids)))
    required = {"id", "local", "url", "sha256", "bytes", "fetchable", "removal_target",
                "rights_holder", "license_basis", "redistributable", "corpus_entries", "note"}
    for s in fs.SOURCES:
        missing = required - set(s)
        check(f"{s['id']} 필수 키 완비", not missing, str(missing))
        check(f"{s['id']} sha256 형식", len(s["sha256"]) == 64 and all(c in "0123456789abcdef" for c in s["sha256"]))
        check(f"{s['id']} redistributable 값", s["redistributable"] in ("yes", "no", "unknown"))
        if s["fetchable"]:
            check(f"{s['id']} fetchable이면 URL 필수", bool(s["url"]))
    check("재배포 가능은 eCFR 산출물뿐",
          [s["id"] for s in fs.SOURCES if s["redistributable"] == "yes"] == ["ecfr_supp1_json"])
    check("제거 대상 5건", sum(1 for s in fs.SOURCES if s["removal_target"]) == 5)


def test_sources_verify_matches_disk() -> None:
    print("[fetch_sources] 로컬 파일 해시 일치 (파일이 있을 때만)")
    checked = 0
    for s in fs.SOURCES:
        path = ROOT / s["local"]
        if not path.exists():
            print(f"  skip {s['id']} (파일 없음 - 제거되었을 수 있음)")
            continue
        digest = fs.sha256_file(path)
        check(f"{s['id']} SHA-256 일치", digest == s["sha256"], f"{digest[:16]} != {s['sha256'][:16]}")
        checked += 1
    print(f"  ({checked}개 파일 검증)")


def main() -> int:
    test_entry_detection()
    test_no_false_heading_from_crossreference()
    test_items_recovery()
    test_section_canonicalization()
    test_text_field_modes()
    test_determinism()
    test_sources_table()
    test_sources_verify_matches_disk()
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
