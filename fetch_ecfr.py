#!/usr/bin/env python3
"""eCFR 15 CFR Part 774 Supplement No. 1 (Commerce Control List) 취득·파싱 스크립트.

배경
----
코퍼스의 약 35%(637/1797 entries)가 미국 EAR CCL(eCFR 15 CFR Part 774 Supp. No. 1)에서
나왔지만, 지금까지 저장소에는 파싱 결과물(`data/corpus/ecfr_supp1.json`)만 있고
**취득·파싱 코드가 없었다.** 즉 코퍼스 3분의 1의 재현 경로가 코드로 남아 있지 않았다.
이 스크립트가 그 경로를 복원한다.

또한 기존 `ecfr_supp1.json`은 각 ECCN의 **표제(heading) 한 줄만** 담고 있어
637건 중 **351건**(대소문자 무시, 실측)이 "... (see List of Items Controlled)." 처럼
본문이 다른 곳에 있다고 가리키기만 하는 껍데기였다(그중 315건은 그 문구로 끝난다).
전체 텍스트 총량도 105,613자에 그쳤다. eCFR 원문에서 'List of Items Controlled'
하위 단락(Items / Related Controls / Related Definitions / Notes / 표)까지
재귀 수집하는 것이 그 문제의 근본 해결 경로이므로, 이 스크립트는
표제와 본문을 **분리해서 함께** 저장한다.

사용법
------
    # 1) 온라인 취득 + 파싱 (표제만 text에 담는 하위호환 모드)
    python fetch_ecfr.py --out data/corpus/ecfr_supp1_refetched.json

    # 2) 표제 + Items 본문을 text에 담는 정정 모드 (351건 껍데기 문제 해결)
    python fetch_ecfr.py --text-field full --out data/corpus/ecfr_supp1_full.json

    # 3) 원문 XML을 남겨두고 오프라인 재파싱 (네트워크 불필요, 결정론적)
    python fetch_ecfr.py --save-xml data/raw/ecfr_supp1.xml --out ...
    python fetch_ecfr.py --xml data/raw/ecfr_supp1.xml --out ...

주의
----
- 기본 동작은 **기존 파일을 덮어쓰지 않는다.** 이미 존재하면 `--force`가 필요하다.
- eCFR 저작물은 17 U.S.C. §105에 따라 미국 연방정부 저작물로서 저작권 보호 대상이
  아니다(퍼블릭 도메인). 상세 근거는 `data/SOURCES.md` 참조.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 무작위성을 쓰지 않지만 산출물 감사를 위해 seed를 명시적으로 기록한다.
SEED = 20260730

API_BASE = "https://www.ecfr.gov/api/versioner/v1"
TITLE = 15
CHAPTER = "VII"
SUBCHAPTER = "C"
PART = "774"
APPENDIX = "Supplement No. 1 to Part 774"

# 사람이 읽는 정본 URL (인용용). API URL과 별개로 SOURCES.md에 함께 기록한다.
HUMAN_URL = (
    "https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/"
    "part-774/appendix-Supplement%20No.%201%20to%20Part%20774"
)

USER_AGENT = "sanbo-export-control-research/1.0 (+reproducibility script)"

# ECCN 코드: 카테고리 숫자 1자리 + 제품군 문자 1자리 + 3자리 숫자 (+ 접미 문자)
ECCN_RE = re.compile(r"^([0-9])([A-EY])([0-9]{3})([A-Za-z]?)\b")

# 'List of Items Controlled' 등 절(section) 표제는 <FP-1><E T="0x">...</E></FP-1> 형태
SECTION_LIST_OF_ITEMS = "List of Items Controlled"

# 절 안의 하위 필드는 <FP-1><I>Related Controls:</I> ... 형태
# 원문에 콜론이 빠진 사례(9D604의 `<I>Items</I>`)가 있어 콜론을 선택으로 둔다.
SUBFIELD_RE = re.compile(r"^([A-Z][A-Za-z /()\"'’.-]{2,60}?):?\s*$")

# 'List of Items Controlled' 절에만 나타나는 하위 필드.
# 이 세 개가 보이면 직전 절 표시가 무엇이든 현재 절을 LOIC로 교정한다.
# (1D002처럼 eCFR 원문 자체가 절 표제 순서를 잘못 놓은 사례가 있다.)
LOIC_SUBFIELDS = ("Items", "Related Controls", "Related Definitions")

# 콜론 없이 등장해도 하위 필드로 인정할 화이트리스트.
COLONLESS_SUBFIELDS = set(LOIC_SUBFIELDS)


# ---------------------------------------------------------------------------
# 취득
# ---------------------------------------------------------------------------


class FetchError(RuntimeError):
    """네트워크/HTTP 실패를 호출자에게 명확히 보고하기 위한 예외."""


def _http_get(url: str, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - 네트워크 의존
        raise FetchError(f"HTTP {exc.code} {exc.reason} for {url}") from exc
    except Exception as exc:  # pragma: no cover - 네트워크 의존
        raise FetchError(f"{type(exc).__name__}: {exc} for {url}") from exc


def latest_title_date(timeout: int = 60) -> str:
    """title 15의 최신 반영일(up_to_date_as_of가 아니라 latest_issue_date)을 돌려준다.

    latest_issue_date를 쓰는 이유: versioner full 엔드포인트는 '해당 날짜의 본문'을
    요구하므로, 발행이 없는 날짜를 넣으면 이전 판이 나와 재현이 흐려진다.
    """
    raw = _http_get(f"{API_BASE}/titles.json", timeout=timeout)
    data = json.loads(raw.decode("utf-8"))
    for entry in data.get("titles", []):
        if entry.get("number") == TITLE:
            date = entry.get("latest_issue_date") or entry.get("up_to_date_as_of")
            if not date:
                raise FetchError("titles.json에 title 15 날짜 정보가 없다")
            return str(date)
    raise FetchError("titles.json에서 title 15를 찾지 못했다")


def appendix_present(date: str, timeout: int = 300) -> bool:
    """structure 엔드포인트로 해당 날짜에 Supp. No. 1이 존재하는지 확인."""
    raw = _http_get(f"{API_BASE}/structure/{date}/title-{TITLE}.json", timeout=timeout)
    data = json.loads(raw.decode("utf-8"))
    found = False

    def walk(node: dict) -> None:
        nonlocal found
        if node.get("type") == "appendix" and str(node.get("identifier", "")) == APPENDIX:
            found = True
        for child in node.get("children") or []:
            walk(child)

    walk(data)
    return found


def appendix_xml_url(date: str) -> str:
    query = urllib.parse.urlencode(
        {
            "chapter": CHAPTER,
            "subchapter": SUBCHAPTER,
            "part": PART,
            "appendix": APPENDIX,
        }
    )
    return f"{API_BASE}/full/{date}/title-{TITLE}.xml?{query}"


def fetch_appendix_xml(date: str, timeout: int = 300) -> tuple[bytes, str]:
    url = appendix_xml_url(date)
    return _http_get(url, timeout=timeout), url


# ---------------------------------------------------------------------------
# 텍스트 렌더링
# ---------------------------------------------------------------------------


def _norm(text: str) -> str:
    """공백 정규화. 원문 문자(따옴표 등)는 훼손하지 않는다."""
    text = re.sub(r"[ \s]+", " ", text or "")
    return text.strip()


def _render_table(el: ET.Element) -> str:
    """GPO 표를 'cell | cell' 행 목록으로 평문화한다."""
    rows: list[str] = []
    for tr in el.iter("TR"):
        cells = [_norm("".join(td.itertext())) for td in list(tr) if td.tag in ("TD", "TH")]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    return " ;; ".join(rows)


def render_node(el: ET.Element) -> str:
    """DIV9 직계 자식 노드 하나를 사람이 읽는 평문 한 조각으로 만든다."""
    if el.tag in ("DIV",) or el.find(".//TABLE") is not None:
        table = _render_table(el)
        if table:
            return table
    if el.tag == "NOTE":
        # NOTE는 <HED>표제</HED><P>본문</P> 구조. 표제와 본문을 순서대로 이어붙인다.
        parts = [_norm(el.text or "")]
        for child in el:
            parts.append(_norm("".join(child.itertext())))
            parts.append(_norm(child.tail or ""))
        return _norm(" ".join(p for p in parts if p))
    return _norm("".join(el.itertext()))


def section_label(el: ET.Element) -> str | None:
    """<FP-1><E T="0x">License Requirements</E></FP-1> 같은 절 표제를 뽑는다.

    자식이 하나뿐이고 그 밖의 잔여 텍스트가 없을 때만 절 표제로 인정한다.
    (본문 중간의 강조 <E>/<I>를 절 표제로 오인하지 않기 위함)

    eCFR 원문에는 절 표제를 <E>가 아니라 <I>로 감싼 사례가 섞여 있다
    (예: 0E001, 1B117의 `<FP-1><I>List of Items Controlled</I></FP-1>`).
    <I>는 하위 필드 표기('Items:', 'Related Controls:')와도 겹치므로,
    <I>일 때는 정규화 결과가 알려진 절 이름일 때만 절 표제로 받는다.
    """
    if el.tag not in ("FP-1", "FP-2", "FP"):
        return None
    children = list(el)
    if len(children) != 1 or children[0].tag not in ("E", "I"):
        return None
    leftover = _norm((el.text or "") + (children[0].tail or ""))
    if leftover:
        return None
    label = _norm("".join(children[0].itertext()))
    if not label:
        return None
    if children[0].tag == "I" and canon_section(label) not in CANONICAL_SECTIONS:
        return None
    return label


def subfield_label(el: ET.Element) -> tuple[str, str] | None:
    """<FP-1><I>Items:</I> 본문...</FP-1> → ("Items", "본문...")"""
    children = list(el)
    if not children or children[0].tag != "I":
        return None
    if _norm(el.text or ""):
        return None
    key_raw = _norm("".join(children[0].itertext()))
    m = SUBFIELD_RE.match(key_raw)
    if not m:
        return None
    key = m.group(1).strip()
    if not key_raw.rstrip().endswith(":") and key not in COLONLESS_SUBFIELDS:
        return None
    rest = _norm("".join(children[0].tail or "") + "".join(
        "".join(c.itertext()) + (c.tail or "") for c in children[1:]
    ))
    return key, rest


def eccn_heading(el: ET.Element) -> tuple[str, str] | None:
    """ECCN 항목 시작 노드인지 판정하고 (코드, 표제본문)을 돌려준다.

    표준형: <FP-2><B>0A501 Firearms ... (see List of Items controlled).</B></FP-2>

    eCFR 원문에는 태그가 흔들리는 사례가 있다. 2026-07-23 판본에서 8D001만
    <FP-1><B>8D001 ...</B></FP-1> 로 표기되어 있고, 기존 `ecfr_supp1.json`은
    이 항목을 놓쳤다(637건). FP-1/FP도 후보로 받되 다음 조건을 모두 요구해
    본문 중 강조용 <B>를 표제로 오인하지 않게 한다.
      (1) 첫 자식이 <B>
      (2) <B> 앞에 선행 텍스트가 없음
      (3) <B> 자체의 텍스트가 ECCN 코드로 시작
    2026-07-23 판본에서 이 규칙의 후보는 정확히 638건, 코드 중복 0건이다.
    """
    if el.tag not in ("FP-2", "FP-1", "FP"):
        return None
    children = list(el)
    if not children or children[0].tag != "B":
        return None
    if _norm(el.text or ""):
        return None
    btext = _norm("".join(children[0].itertext()))
    m = ECCN_RE.match(btext)
    if not m:
        return None
    code = "".join(m.groups())
    full = _norm("".join(el.itertext()))
    body = _norm(full[len(code):]) if full.startswith(code) else _norm(full)
    return code, body


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------

CATEGORY_RE = re.compile(r"^Category\s+([0-9])\s*[—\-–]\s*(.*)$")
GROUP_RE = re.compile(r"^([A-E])\.\s+(.*)$")

# HD1/HD2/HD3 중 '항목 경계'로 봐야 하는 구조적 구분선.
#   Part 1—Telecommunications / I. Cryptographic ... / Annex to Category 1
STRUCTURAL_DIVIDER_RE = re.compile(
    r"^(?:Part\s+[0-9]+\s*[—–-]|(?:I{1,3}|IV|VI{0,3}|IX|XI{0,3})\.\s|Annex\b)"
)


def canon_section(label: str) -> str:
    """절 표제 표기 흔들림을 하나로 모은다.

    eCFR 원문에는 'List Based License Exceptions (See Part 740 for a Description of
    All License Exceptions)'가 대소문자만 다른 형태로 18가지 등장한다. 정규화하지
    않으면 sections 딕셔너리 키가 갈라져 후속 분석이 조용히 틀어진다.
    """
    lab = (label or "").strip().rstrip(":").strip()
    low = lab.lower()
    if low.startswith("list of items controlled"):
        return SECTION_LIST_OF_ITEMS
    if low.startswith("license requirements"):
        return "License Requirements"
    if low.startswith("list based license exceptions") or low == "license exceptions":
        return "List Based License Exceptions"
    if low.startswith("special conditions for st"):
        return "Special Conditions for STA"
    if low.startswith("reporting requirements"):
        return "Reporting Requirements"
    return lab


CANONICAL_SECTIONS = {
    SECTION_LIST_OF_ITEMS,
    "License Requirements",
    "List Based License Exceptions",
    "Special Conditions for STA",
    "Reporting Requirements",
}


def parse_supplement(xml_bytes: bytes) -> list[dict]:
    """Supp. No. 1 XML → ECCN 항목 리스트 (문서 등장 순서 유지)."""
    root = ET.fromstring(xml_bytes)

    entries: list[dict] = []
    current: dict | None = None
    section: str | None = None
    subfield: str | None = None
    in_items = False

    category_no = ""
    category_title = ""
    group_letter = ""
    group_title = ""

    def flush() -> None:
        nonlocal current
        if current is not None:
            entries.append(current)
            current = None

    for el in root:
        if el.tag in ("HEAD", "XREF", "CITA", "EDNOTE", "img"):
            continue

        if el.tag in ("HD1", "HD2", "HD3"):
            label = _norm("".join(el.itertext()))
            cat = CATEGORY_RE.match(label)
            if cat:
                flush()
                category_no, category_title = cat.group(1), cat.group(2).strip()
                group_letter, group_title = "", ""
                section = subfield = None
                in_items = False
                continue
            grp = GROUP_RE.match(label)
            if grp:
                flush()
                group_letter, group_title = grp.group(1), grp.group(2).strip()
                section = subfield = None
                in_items = False
                continue
            if STRUCTURAL_DIVIDER_RE.match(label):
                flush()
                section = subfield = None
                in_items = False
                continue
            canon = canon_section(label)
            if canon in CANONICAL_SECTIONS and current is not None:
                # 3A090처럼 절 표제를 <FP-1><E>가 아니라 <HD1>로 쓴 사례.
                # 경계로 오인하면 항목 본문 전체가 유실된다.
                section = canon
                subfield = None
                in_items = False
                current["sections"].setdefault(section, "")
                continue
            if current is not None and section is not None:
                # 6D003/6E003의 'Acoustics', 'Cameras' 같은 항목 내부 소제목.
                # 경계로 오인하면 해당 항목이 표제만 남는다.
                current["sections"][section] = _norm(
                    current["sections"].get(section, "") + " " + label
                )
                if section == SECTION_LIST_OF_ITEMS:
                    current["loic_body"] = _norm(current.get("loic_body", "") + " " + label)
                if subfield is not None:
                    key = (section, subfield)
                    current["subfields"][key] = _norm(
                        current["subfields"].get(key, "") + " " + label
                    )
                continue
            flush()
            section = subfield = None
            in_items = False
            continue

        head = eccn_heading(el)
        if head is not None:
            flush()
            code, body = head
            current = {
                "code": f"ECCN-{code}",
                "source": "ecfr_part774",
                "category": code[0],
                "category_title": category_title,
                "product_group": group_letter or code[1],
                "product_group_title": group_title,
                "heading": body,
                "sections": {},
                "subfields": {},
                "loic_body": "",
            }
            section = None
            subfield = None
            in_items = False
            continue

        if current is None:
            # ECCN 항목 밖(카테고리 서문, EAR99 안내 등)은 버린다.
            continue

        lab = section_label(el)
        if lab is not None:
            section = canon_section(lab)
            subfield = None
            in_items = False
            current["sections"].setdefault(section, "")
            continue

        sub = subfield_label(el)
        if sub is not None:
            subfield, rest = sub
            if subfield in LOIC_SUBFIELDS:
                # 이 세 하위 필드는 LOIC 절 전용이므로 절 표시를 교정한다.
                section = SECTION_LIST_OF_ITEMS
                current["sections"].setdefault(section, "")
            key = (section or "", subfield)
            current["subfields"].setdefault(key, "")
            if rest:
                current["subfields"][key] = _norm(current["subfields"][key] + " " + rest)
            if section:
                current["sections"][section] = _norm(
                    current["sections"].get(section, "") + " " + f"{subfield}: {rest}"
                )
            # 'Items:' 이후의 후속 <P>/<NOTE> 블록만 본문으로 이어붙인다.
            # (Related Controls: 뒤에 오는 블록까지 붙이면 5A001처럼
            #  Items 마커가 없는 항목에서 related_controls가 오염된다.)
            in_items = section == SECTION_LIST_OF_ITEMS and subfield == "Items"
            if section == SECTION_LIST_OF_ITEMS:
                current["loic_body"] = _norm(current.get("loic_body", "") + " " + rest) \
                    if subfield not in ("Related Controls", "Related Definitions") \
                    else current.get("loic_body", "")
            continue

        chunk = render_node(el)
        if not chunk:
            continue
        if section:
            current["sections"][section] = _norm(current["sections"].get(section, "") + " " + chunk)
        else:
            current["heading"] = _norm(current["heading"] + " " + chunk)
        if section == SECTION_LIST_OF_ITEMS:
            # Items 마커가 없는 항목(5A001 등)을 위한 LOIC 본문 누적기.
            # Related Controls/Definitions 줄 자체는 위에서 제외했다.
            current["loic_body"] = _norm(current.get("loic_body", "") + " " + chunk)
        if in_items:
            key = (SECTION_LIST_OF_ITEMS, "Items")
            current["subfields"][key] = _norm(current["subfields"].get(key, "") + " " + chunk)

    flush()

    # 하위 필드를 사람이 쓰기 쉬운 평평한 키로 정리
    out: list[dict] = []
    for e in entries:
        subs = e.pop("subfields")
        items = _norm(subs.get((SECTION_LIST_OF_ITEMS, "Items"), ""))
        related_controls = _norm(subs.get((SECTION_LIST_OF_ITEMS, "Related Controls"), ""))
        related_defs = _norm(subs.get((SECTION_LIST_OF_ITEMS, "Related Definitions"), ""))
        reason = _norm(subs.get(("License Requirements", "Reason for Control"), ""))

        loic = _norm(e["sections"].get(SECTION_LIST_OF_ITEMS, ""))
        loic_body = _norm(e.get("loic_body", ""))
        # 'Items:' 마커가 아예 없는 항목(5A001 등)은 LOIC 절에서
        # Related Controls / Related Definitions를 뺀 본문을 Items로 대체한다.
        items_effective = items or loic_body
        items_source = "items_marker" if items else ("loic_body_fallback" if loic_body else "none")
        full = _norm(" ".join(x for x in (e["heading"], items_effective) if x))

        rec = {
            "code": e["code"],
            "source": e["source"],
            "category": e["category"],
            "category_title": e["category_title"],
            "product_group": e["product_group"],
            "product_group_title": e["product_group_title"],
            "heading": e["heading"],
            "items": items_effective,
            "items_source": items_source,
            "related_controls": related_controls,
            "related_definitions": related_defs,
            "reason_for_control": reason,
            "list_of_items_controlled": loic,
            "sections": {k: _norm(v) for k, v in e["sections"].items()},
            "n_chars_heading": len(e["heading"]),
            "n_chars_items": len(items_effective),
            "n_chars_full": len(full),
            "heading_only": not items_effective,
            "_full_text": full,
        }
        out.append(rec)
    return out


def finalize(entries: list[dict], text_field: str) -> list[dict]:
    """`text` 키를 정한다.

    - heading: 기존 `data/corpus/ecfr_supp1.json`과 동일한 의미(표제만).
               build_corpus_clean.py의 기존 동작을 그대로 재현한다.
    - full   : 표제 + Items 본문. 표제뿐인 351건 문제를 해소하는 정정 모드.
    """
    result: list[dict] = []
    for e in entries:
        rec = dict(e)
        full = rec.pop("_full_text")
        rec["text"] = rec["heading"] if text_field == "heading" else full
        result.append(rec)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", default=None, help="eCFR 판본 날짜 YYYY-MM-DD (기본: title 15 최신 발행일)")
    p.add_argument("--xml", default=None, help="이미 저장한 XML을 파싱(네트워크 불필요)")
    p.add_argument("--save-xml", default=None, help="취득한 원문 XML을 이 경로에 저장")
    p.add_argument("--out", default="data/corpus/ecfr_supp1_refetched.json", help="파싱 결과 JSON 경로")
    p.add_argument(
        "--manifest",
        default="output/ecfr_fetch_manifest.json",
        help="env_meta/seed/sha256/카운트를 담는 감사용 매니페스트 경로",
    )
    p.add_argument("--text-field", choices=("heading", "full"), default="heading",
                   help="`text` 키에 담을 내용 (기본 heading = 기존 파일과 하위호환)")
    p.add_argument("--sort", choices=("document", "code"), default="document",
                   help="출력 정렬 (기본 document = 원문 등장 순서)")
    p.add_argument("--force", action="store_true", help="기존 출력 파일 덮어쓰기 허용")
    p.add_argument("--skip-structure-check", action="store_true", help="structure 엔드포인트 확인 생략")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 카운트만 보고")
    p.add_argument("--light-env", action="store_true",
                   help="env_meta 기록 시 torch/sentence-transformers import를 건너뛴다"
                        " (이 파싱은 두 라이브러리와 무관하고, import에 수 분이 걸리는 환경이 있다)")
    return p


def _collect_env_meta(light: bool) -> dict:
    """환경 기록. light=True면 무거운 ML 라이브러리 import를 피한다."""
    import platform
    base = {"python": platform.python_version(), "platform": platform.platform()}
    if light:
        try:
            import numpy as _np
            base["numpy"] = _np.__version__
        except Exception:
            base["numpy"] = None
        base["torch"] = "not_probed (--light-env)"
        base["sentence_transformers"] = "not_probed (--light-env)"
        return base
    try:
        from retrieval_core import env_meta  # 저장소 공용 환경 기록
        return env_meta()
    except Exception:  # pragma: no cover
        base["note"] = "retrieval_core.env_meta import 실패 - 축약 기록"
        return base


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (ROOT / p)


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    out_path = _resolve(args.out)
    if out_path.exists() and not args.force and not args.dry_run:
        print(f"[FAIL] 출력 파일이 이미 존재한다: {out_path}\n"
              f"       덮어쓰려면 --force, 확인만 하려면 --dry-run 을 쓰라.", file=sys.stderr)
        return 2

    t0 = time.time()
    date = args.date
    source_url = None
    fetched_from = None

    if args.xml:
        xml_path = _resolve(args.xml)
        if not xml_path.exists():
            print(f"[FAIL] --xml 경로가 없다: {xml_path}", file=sys.stderr)
            return 2
        xml_bytes = xml_path.read_bytes()
        fetched_from = f"local:{xml_path}"
        print(f"[ok] 로컬 XML 파싱: {xml_path} ({len(xml_bytes)}B)")
    else:
        try:
            if date is None:
                date = latest_title_date(timeout=min(args.timeout, 60))
                print(f"[ok] title 15 최신 발행일 = {date}")
            if not args.skip_structure_check:
                if not appendix_present(date, timeout=args.timeout):
                    print(f"[FAIL] {date} 판본에 '{APPENDIX}'가 없다", file=sys.stderr)
                    return 3
                print(f"[ok] structure 확인: '{APPENDIX}' 존재")
            xml_bytes, source_url = fetch_appendix_xml(date, timeout=args.timeout)
            fetched_from = source_url
            print(f"[ok] XML 취득: {len(xml_bytes)}B ({time.time() - t0:.1f}s)")
        except FetchError as exc:
            print(f"[FAIL] eCFR 취득 실패 (네트워크 차단/차단정책 가능): {exc}", file=sys.stderr)
            print("       오프라인 환경이면 원문 XML을 별도로 받아 --xml 로 파싱하라.", file=sys.stderr)
            return 4

    xml_sha = hashlib.sha256(xml_bytes).hexdigest()

    if args.save_xml and not args.dry_run:
        xml_out = _resolve(args.save_xml)
        xml_out.parent.mkdir(parents=True, exist_ok=True)
        xml_out.write_bytes(xml_bytes)
        print(f"[ok] 원문 XML 저장: {xml_out}")

    try:
        parsed = parse_supplement(xml_bytes)
    except ET.ParseError as exc:
        print(f"[FAIL] XML 파싱 실패: {exc}", file=sys.stderr)
        return 5

    entries = finalize(parsed, args.text_field)
    if args.sort == "code":
        entries = sorted(entries, key=lambda e: e["code"])

    n = len(entries)
    n_heading_only = sum(1 for e in entries if e["heading_only"])
    chars_heading = sum(e["n_chars_heading"] for e in entries)
    chars_full = sum(e["n_chars_full"] for e in entries)
    by_cat: dict[str, int] = {}
    for e in entries:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1

    print(f"[result] entries={n} heading_only={n_heading_only} "
          f"chars(heading)={chars_heading} chars(heading+items)={chars_full}")
    print(f"[result] by_category={dict(sorted(by_cat.items()))}")

    if args.dry_run:
        print("[dry-run] 파일을 쓰지 않았다.")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    out_sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    print(f"[ok] 결과 저장: {out_path} (sha256={out_sha})")

    meta = _collect_env_meta(args.light_env)

    manifest = {
        "generated_by": "fetch_ecfr.py",
        "seed": SEED,
        "randomness_used": "none (deterministic parse)",
        "env_meta": meta,
        "ecfr_date": date,
        "api_url": source_url,
        "fetched_from": fetched_from,
        "human_citation_url": HUMAN_URL,
        "xml_sha256": xml_sha,
        "xml_bytes": len(xml_bytes),
        "out_path": str(out_path.relative_to(ROOT)) if str(out_path).startswith(str(ROOT)) else str(out_path),
        "out_sha256": out_sha,
        "text_field": args.text_field,
        "sort": args.sort,
        "counts": {
            "entries": n,
            "heading_only": n_heading_only,
            "chars_heading_total": chars_heading,
            "chars_heading_plus_items_total": chars_full,
            "by_category": dict(sorted(by_cat.items())),
        },
        "license_basis": "17 U.S.C. §105 (US federal government work, not copyrightable)",
        "elapsed_sec": round(time.time() - t0, 2),
    }
    man_path = _resolve(args.manifest)
    man_path.parent.mkdir(parents=True, exist_ok=True)
    man_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 매니페스트 저장: {man_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
