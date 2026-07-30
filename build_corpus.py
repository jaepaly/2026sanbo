#!/usr/bin/env python3
"""Wassenaar / India SCOMET PDF를 통제목록 코퍼스 JSON으로 파싱.

이 모듈은 두 가지 파서 세대를 **모두** 제공한다.

* ``parse_wassenaar`` / ``parse_scomet``  — 레거시(v1). 동작을 한 글자도 바꾸지 않는다.
  ``data/corpus/combined.json`` 과 논문의 기존 수치를 재현하기 위해 보존한다.
* ``parse_wassenaar_v2`` / ``parse_scomet_v2`` — M7 결함 교정판.
  ``data/corpus/combined_v2.json`` 생성에만 쓰인다.

v2에서 고친 결함(자세한 실측치는 ``docs/corpus_parsing_fixes.md``):

1. **페이지 경계 절단** — v1은 페이지 루프 끝에서 ``entries.append(current); current=None``
   을 실행했다. 다음 페이지로 이어지는 본문 행은 ``current`` 가 ``None`` 이라
   ``if current:`` 분기에 걸리지 못하고 **조용히 버려졌다**. v2는 페이지 경계에서
   flush하지 않고 이어붙이며, 대신 (a) 러닝 헤더/푸터를 명시적으로 제거하고
   (b) DUAL-USE LIST 섹션 밖의 페이지에서는 누적을 중단해 오염을 막는다.
2. **번호목록을 가짜 항목으로 오인** — "2. In the form of ..." 가 코드 ``2.I.n`` 으로
   매칭되었다. v2는 정규식 매칭 후 코드를 정규 문법으로 검증하고, 마지막 한 토큰만
   잘라내면 유효해지는 경우(예: ``3.A.2.d.4.A`` → ``3.A.2.d.4`` + 본문 "A Single ...")
   에만 복구하고, 그 외에는 항목 시작이 아니라 **연속 행**으로 처리한다.
3. **스텁·푸터 혼입** — 'Not used since ...' / '[Reserved]' 는 삭제하지 않고
   ``text_completeness="stub"`` 으로 표시한다. 페이지 푸터는 두 변형
   ("- 5 - 15-01-2026", "15-01-2026 - 5 -") 을 모두 제거한다. v1은 후자를
   ``skip_tail`` 정규식이 놓쳐 본문에 섞어 넣었다.
4. **본문의 ``.*``** — 정규식 잔재가 **아니다**. 원문 각주 표식(asterisk)이다.
   (Wassenaar 130쪽 ``2.d.*``, 157쪽 ``... see the Munitions List.*``, 그리고
   각주 본문 ``* The Russian Federation and Ukraine view this list as ...``)
   v2는 각주 본문 행을 제거하고 문말 각주 표식 ``*`` 를 떼며
   ``footnote_marker_stripped`` 플래그를 남긴다.

SCOMET 추가 교정: 원문이 좌측에 코드 열을 둔 표이며 같은 코드의 하위 문단
("6A001 a. ...", "6A001 b. ...")이 별도 행으로 반복된다. v1은 매 행을 새 항목으로
만들었고 중복 제거 단계에서 첫/최장 하나만 남아 하위 문단이 소실됐다. v2는
직전 항목과 코드가 같으면 연속 행으로 합친다.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR = DATA_DIR / "corpus"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 페이지 텍스트 추출 (선택적 캐시)
# ---------------------------------------------------------------------------
def extract_pages(path: Path) -> list[str]:
    """PDF의 페이지별 텍스트를 리스트로 반환.

    ``SANBO_PAGE_CACHE`` 환경변수에 디렉터리를 지정하면 페이지 텍스트를 캐시해
    반복 파싱 비용을 줄인다(레포 밖 경로 권장). 캐시는 파싱 결과에 영향을 주지 않는다.
    """
    cache_dir = os.environ.get("SANBO_PAGE_CACHE")
    cache_file = None
    if cache_dir:
        cache_file = Path(cache_dir) / f"pages_{path.stem}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))
    import pdfplumber  # 지연 임포트: 캐시 적중 시 pdfplumber 없이도 동작

    with pdfplumber.open(path) as r:
        pages = [(p.extract_text() or "") for p in r.pages]
    if cache_file is not None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")
    return pages


# ---------------------------------------------------------------------------
# 공통 정규식
# ---------------------------------------------------------------------------
# Wassenaar 항목 코드 문법 (build_corpus_clean.CODE_PATTERNS 와 동일)
WASSENAAR_CODE_RE = re.compile(
    r"^[0-9]\.[A-E](?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?$"
)
SCOMET_CODE_RE = re.compile(r"^[0-9][A-Z][0-9]{3}[a-z]?$")

WASS_ENTRY_RE = re.compile(
    r"^(?:\s*)(\d+)\s*\.\s*([A-Z])\s*\.\s*(\d+)?\s*\.?\s*([A-Za-z])?\s*\.\s*(\d+)?\s*\.?\s*([A-Za-z])?\.?\s+(.+)$"
)
WASS_ENTRY_SHORT_RE = re.compile(
    r"^(?:\s*)(\d+)\s*\.\s*([A-Z])(?:\s*\.\s*(\d+)?)?\s*\.?\s*([A-Za-z])?\.?\s+(.+)$"
)
SCOMET_ENTRY_RE = re.compile(r"^(\d)([A-Z])(\d{3})([a-z]?)\.?\s+(.+)$")

# v2 전용 Wassenaar 항목 시작 정규식.
#
# 레거시 정규식의 두 구멍을 막는다.
#  (a) 코드 성분 뒤의 마침표를 optional(``\.?``)로 둬서 "2. In the form of ..." 를
#      2.I.n 으로, "3. An ..." 을 3.A.n 으로 매칭했다 → 성분마다 마침표를 필수로 한다.
#  (b) 마침표 뒤 공백을 요구하지 않아 줄바꿈된 상호참조 행("3.A.1.a.10. and 3.A.1.a.12., ...",
#      "5.D.2.c.3.a.;")을 새 항목의 시작으로 오인했다 → 원문이 항목 코드를 띄어 쓴
#      형태("3. A. 1. b. 4.")로 인쇄한다는 사실을 이용해 마침표 뒤 공백을 필수로 한다.
#      (실측: 이 조건으로 걸러지는 17건은 전부 상호참조 연속 행이었고,
#       잃는 1차 항목은 없다 — 해당 하위항목 본문은 상위 항목 본문 안에 그대로 남는다.)
WASS_ENTRY_V2_RE = re.compile(
    r"^(\d)\s*\.\s+([A-E])\s*\.\s+"
    r"(?:(\d+)\s*\.\s+)?"
    r"(?:([a-z])\s*\.\s+)?"
    r"(?:(\d+)\s*\.\s+)?"
    r"(?:([a-z])\s*\.\s+)?"
    r"(?:(\d+)\s*\.\s+)?"
    r"(\S.*)$"
)
# 카테고리 표제행("1. A. SYSTEMS, EQUIPMENT AND COMPONENTS")도 위 정규식이 흡수한다.

# 여러 페이지에 걸친 항목을 감사 대상으로 표시하는 임계값
MANY_PAGES_THRESHOLD = 3

# 문장 종결부호 판정 (미완 항목 탐지용)
TERMINATOR_RE = re.compile(r"[.;:)\]”’\"']\s*$")

# 스텁 텍스트
STUB_TEXT_RE = re.compile(
    r"^\s*(?:not used since\b.*|\[?\(?\s*reserved\s*\)?\]?\.?|deleted\.?)\s*$", re.I
)
# 카테고리 표제(예: 1.A "SYSTEMS, EQUIPMENT AND COMPONENTS")
CATEGORY_CODE_RE = re.compile(r"^[0-9]\.[A-E]$")

# ---- Wassenaar 페이지 러닝 헤더/푸터 ----
WASS_RULE_RE = re.compile(r"^_+$")
WASS_FOOTER_RE = re.compile(
    r"^(?:-\s*\d{1,3}\s*-\s*\d{2}-\d{2}-\d{4}"       # "- 5 - 15-01-2026"
    r"|\d{2}-\d{2}-\d{4}\s*-\s*\d{1,3}\s*-"          # "15-01-2026 - 5 -"
    r"|WA-LIST\b.*"                                   # "WA-LIST (25) 1 Corr."
    r")\s*$"
)
WASS_SECTION_HEADER_RE = re.compile(
    r"^(?:DUAL-USE LIST|MUNITIONS LIST|DEFINITIONS(?:\s|$)|Acronyms and Abbreviations"
    r"|Statements of Understanding|Sensitive List|Very Sensitive List"
    r"|TABLE OF CONTENTS|PUBLIC DOCUMENTS"
    # "TABLE - DEPOSITION TECHNIQUES[ - NOTES | - TECHNICAL NOTE | - STATEMENT ...]" 는
    # 2.E.3.f 표가 걸친 16쪽에 매쪽 반복되는 러닝 서브헤더다.
    r"|TABLE\s*-\s*DEPOSITION TECHNIQUES)"
)
# 카테고리 부속서 시작. 이후 내용은 항목 코드가 없는 목록이므로 누적을 끊는다.
# (예: Category 1 의 'ANNEX / LIST - "EXPLOSIVES"' 23-24쪽. 끊지 않으면 직전 항목
#  1.E.2.g 가 134자에서 5,092자로 부풀어 오른다.)
WASS_BLOCK_BOUNDARY_RE = re.compile(r"^ANNEX(\s|$)")
# 각주 본문 행 ("* The Russian Federation and Ukraine view this list as a reference ...")
WASS_FOOTNOTE_BODY_RE = re.compile(r"^\*(\s|$)")
# 문말 각주 표식: "2.d.*" / "... Munitions List.*"
FOOTNOTE_MARKER_RE = re.compile(r"(?<=[.\w])\*\s*$")

# ---- SCOMET 페이지 러닝 헤더 ----
SCOMET_HEADER_RE = re.compile(r"^(?:Appendix\s*3\s*[–—-]\s*SCOMET List|APPENDIX-3)\s*$", re.I)
# 표 안의 카테고리 표제행("0A2 Special Fissionable Material", "8A3 ELECTRONICS (...)").
# 코드 자릿수가 3자리가 아니라(0A2) 항목 정규식에 걸리지 않아, v1에서는 직전 항목 본문
# 끝에 그대로 붙었다. 뒤 문구가 대문자로 시작할 때만 표제로 본다
# ("8B1 or 8C." / "8D2 and 8E2." 같은 문장 중간 연속 행을 잘못 버리지 않기 위함).
SCOMET_CATEGORY_HEADING_RE = re.compile(r"^\d[A-Z]\d\s+[A-Z(\"']")
SCOMET_ANNEX_HEADER_RE = re.compile(r"^ANNEXURE\s*[–—-]", re.I)
SCOMET_COVER_HEADER_RE = re.compile(r"^Annexure to Notification\b", re.I)


def _page_running_header(page_text: str) -> str:
    """페이지의 첫 유의미 행(러닝 헤더)을 반환."""
    for line in page_text.splitlines():
        line = line.strip()
        if not line or WASS_RULE_RE.match(line):
            continue
        return line
    return ""


# ===========================================================================
# 레거시(v1) 파서 — 동작 변경 금지. combined.json 재현용.
# ===========================================================================
def parse_wassenaar(path: Path):
    """레거시 v1 Wassenaar 파서. 결함 포함. 감사·재현 목적으로만 유지."""
    pages = extract_pages(Path(path))
    entries = []
    current = None
    entry_re = WASS_ENTRY_RE
    entry_re_short = WASS_ENTRY_SHORT_RE
    skip_prefixes = (
        "Wassenaar Arrangement",
        "PUBLIC DOCUMENTS",
        "WA-LIST",
        "Defence",
        " nanotechnology",
        "The following",
        "Items",
        "_",
        "-",
    )
    skip_tail = re.compile(r"\d+\s*-\s*\d+\s*-\s*\d+$")
    for i, text in enumerate(pages):
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if any(line.startswith(p) for p in skip_prefixes):
                continue
            if skip_tail.match(line):
                if current and current["text"]:
                    entries.append(current)
                    current = None
                continue
            m = entry_re.match(line)
            if not m:
                m = entry_re_short.match(line)
            if m:
                if current and current["text"]:
                    entries.append(current)
                raw = m.groups()
                code = ".".join(str(t) for t in raw[:-1] if t is not None)
                current = {
                    "code": code,
                    "text": raw[-1].strip(),
                    "source": "wassenaar_2025",
                    "page": i + 1,
                }
                continue
            if current:
                current["text"] += " " + line
        # [결함 1] 페이지 경계 flush — 다음 페이지 연속 행이 유실되는 원인
        if current and current["text"]:
            entries.append(current)
            current = None
    seen, out = set(), []
    for e in entries:
        k = e["code"].strip()
        if k not in seen and len(e["text"]) >= 10:
            seen.add(k)
            out.append(e)
    return out


def parse_scomet(path: Path):
    """레거시 v1 SCOMET 파서. 결함 포함. 감사·재현 목적으로만 유지."""
    pages = extract_pages(Path(path))
    entries = []
    current = None
    entry_re = SCOMET_ENTRY_RE
    skip = {"Appendix 3", "SCOMET List", "Technical Note", "National equivalents", "Item", "Notification"}
    for i, text in enumerate(pages):
        for line in text.splitlines():
            line = line.strip()
            if not line or line in skip or any(line.startswith(s) for s in skip):
                continue
            m = entry_re.match(line)
            if m:
                if current and current["text"]:
                    entries.append(current)
                code = "".join(m.group(j) for j in range(1, 5))
                current = {
                    "code": code,
                    "text": m.group(5).strip(),
                    "source": "india_scomet_2024",
                    "page": i + 1,
                }
            elif current and line:
                current["text"] += " " + line
        # [결함 1] 페이지 경계 flush
        if current and current["text"]:
            entries.append(current)
            current = None
    seen, out = set(), []
    for e in entries:
        k = e["code"].strip()
        if k not in seen and len(e["text"]) >= 10:
            seen.add(k)
            out.append(e)
    return out


# ===========================================================================
# v2 파서 — M7 교정판
# ===========================================================================
def repair_wassenaar_code(parts: list[str], desc: str) -> tuple[str | None, str, bool]:
    """정규식이 뽑은 코드 토큰을 검증/복구.

    반환: (code 또는 None, desc, repaired)

    * 그대로 유효하면 통과.
    * 마지막 한 토큰만 잘라 유효해지고 잔여 토큰이 1글자이며 결과 코드가
      3토큰 이상이면 복구하고, 잘라낸 토큰을 본문 앞에 되돌린다.
      (예: "3. A. 2. d. 4. A Single Sideband ..." → 3.A.2.d.4 / "A Single Sideband ...")
    * 그 외에는 항목 시작이 아니라 번호목록/문장으로 판단해 None을 반환한다.
    """
    code = ".".join(parts)
    if WASSENAAR_CODE_RE.match(code):
        return code, desc, False
    if len(parts) >= 4:
        trimmed = parts[:-1]
        tail = parts[-1]
        cand = ".".join(trimmed)
        if len(tail) == 1 and WASSENAAR_CODE_RE.match(cand):
            return cand, (tail + " " + desc).strip(), True
    return None, desc, False


def _wassenaar_clean_line(line: str) -> tuple[str | None, bool]:
    """Wassenaar 페이지 행 정리. 반환 (행 또는 None=버림, 각주표식_제거여부)."""
    line = line.strip()
    if not line:
        return None, False
    if WASS_RULE_RE.match(line):
        return None, False
    if WASS_FOOTER_RE.match(line):
        return None, False
    if WASS_SECTION_HEADER_RE.match(line):
        return None, False
    if WASS_FOOTNOTE_BODY_RE.match(line):
        return None, False
    stripped = FOOTNOTE_MARKER_RE.sub("", line)
    return (stripped.strip() or None), stripped != line


def parse_wassenaar_v2(path: Path) -> list[dict]:
    """교정판 Wassenaar 파서."""
    pages = extract_pages(Path(path))
    entries: list[dict] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current and current["text"]:
            entries.append(current)
        current = None

    for i, text in enumerate(pages):
        page_no = i + 1
        header = _page_running_header(text)
        # DUAL-USE LIST 섹션 밖(전문·목차·MUNITIONS LIST·정의·부속서)에서는 누적 중단.
        # v1은 이 구분이 없어 ML/정의 페이지 본문이 가짜 dual-use 항목으로 새어들었다.
        if not header.startswith("DUAL-USE LIST"):
            flush()
            continue
        for raw_line in text.splitlines():
            if WASS_FOOTNOTE_BODY_RE.match(raw_line.strip()):
                # 각주 블록은 항상 페이지 하단(푸터 바로 위)에 있다. 본문이 아니므로
                # 여기서부터 페이지 끝까지 버린다. v1은 각주 둘째 줄부터를 본문으로
                # 흡수했다(예: 9.A.2 끝에 "of dual-use goods which could contribute ...").
                break
            if WASS_BLOCK_BOUNDARY_RE.match(raw_line.strip()):
                flush()
                continue
            line, marker_stripped = _wassenaar_clean_line(raw_line)
            if line is None:
                continue
            m = WASS_ENTRY_V2_RE.match(line)
            code, desc, repaired = None, line, False
            if m:
                groups = m.groups()
                parts = [str(t) for t in groups[:-1] if t is not None]
                code, desc, repaired = repair_wassenaar_code(parts, groups[-1].strip())
            if code is not None:
                flush()
                current = {
                    "code": code,
                    "text": desc,
                    "source": "wassenaar_2025",
                    "page": page_no,
                    "pages": [page_no],
                    "parse_flags": ["code_repaired"] if repaired else [],
                }
                if marker_stripped:
                    current["parse_flags"].append("footnote_marker_stripped")
                continue
            if current is None:
                continue  # 항목 시작 전의 일반 서술(카테고리 총칙 등)
            current["text"] += " " + line
            if page_no not in current["pages"]:
                current["pages"].append(page_no)
                if "page_continuation" not in current["parse_flags"]:
                    current["parse_flags"].append("page_continuation")
            if marker_stripped and "footnote_marker_stripped" not in current["parse_flags"]:
                current["parse_flags"].append("footnote_marker_stripped")
    flush()
    return _finalize(entries, min_len=10)


def parse_scomet_v2(path: Path) -> list[dict]:
    """교정판 SCOMET 파서."""
    pages = extract_pages(Path(path))
    entries: list[dict] = []
    current: dict | None = None
    # v1과 동일한 스킵 집합을 유지해 이번 교정의 효과만 분리 측정한다.
    skip = {"Appendix 3", "SCOMET List", "Technical Note", "National equivalents", "Item", "Notification"}
    in_list = False

    def flush() -> None:
        nonlocal current
        if current and current["text"]:
            entries.append(current)
        current = None

    for i, text in enumerate(pages):
        page_no = i + 1
        header = _page_running_header(text)
        if SCOMET_COVER_HEADER_RE.match(header):
            flush()
            continue
        if SCOMET_ANNEX_HEADER_RE.match(header):
            # 목록 본문이 끝나고 부속서가 시작 → 이후는 항목이 아니다.
            flush()
            in_list = False
            continue
        if SCOMET_HEADER_RE.match(header):
            in_list = True
        if not in_list:
            flush()
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if SCOMET_HEADER_RE.match(line):
                continue
            if line in skip or any(line.startswith(s) for s in skip):
                continue
            if SCOMET_CATEGORY_HEADING_RE.match(line) and not SCOMET_ENTRY_RE.match(line):
                flush()
                continue
            m = SCOMET_ENTRY_RE.match(line)
            if m:
                code = "".join(m.group(j) for j in range(1, 5))
                desc = m.group(5).strip()
                if current is not None and current["code"] == code:
                    # 표의 코드 열이 하위 문단마다 반복된다 → 같은 항목의 연속 행
                    current["text"] += " " + desc
                    if "table_row_merged" not in current["parse_flags"]:
                        current["parse_flags"].append("table_row_merged")
                    if page_no not in current["pages"]:
                        current["pages"].append(page_no)
                        if "page_continuation" not in current["parse_flags"]:
                            current["parse_flags"].append("page_continuation")
                    continue
                flush()
                current = {
                    "code": code,
                    "text": desc,
                    "source": "india_scomet_2024",
                    "page": page_no,
                    "pages": [page_no],
                    "parse_flags": [],
                }
                continue
            if current is None:
                continue
            current["text"] += " " + line
            if page_no not in current["pages"]:
                current["pages"].append(page_no)
                if "page_continuation" not in current["parse_flags"]:
                    current["parse_flags"].append("page_continuation")
    flush()
    return _finalize(entries, min_len=10)


def classify_completeness(code: str, text: str) -> str:
    """항목 본문의 완성도 등급."""
    t = (text or "").strip()
    if not t or STUB_TEXT_RE.match(t):
        return "stub"
    if CATEGORY_CODE_RE.match(code or ""):
        return "heading_only"
    return "full"


def _finalize(entries: list[dict], min_len: int) -> list[dict]:
    """같은 코드가 여러 번 나오면 최장 본문을 남기고, 완성도/플래그를 확정.

    v1은 '처음 등장한 것'을 남겼다(정보 손실이 큼). v2는 최장 본문을 남기고
    버린 개수를 ``duplicate_occurrences`` 로 기록한다.
    """
    best: dict[str, dict] = {}
    dup_count: dict[str, int] = {}
    for e in entries:
        code = e["code"].strip()
        e["code"] = code
        text = re.sub(r"\s+", " ", e["text"]).strip()
        e["text"] = text
        if len(text) < min_len and classify_completeness(code, text) != "stub":
            continue
        prev = best.get(code)
        if prev is None:
            best[code] = e
            dup_count[code] = 0
        else:
            dup_count[code] += 1
            if len(text) > len(prev["text"]):
                e["parse_flags"] = sorted(set(e["parse_flags"]) | set(prev["parse_flags"]))
                best[code] = e
            else:
                prev["parse_flags"] = sorted(set(prev["parse_flags"]) | set(e["parse_flags"]))
    out = []
    for code, e in best.items():
        flags = set(e.get("parse_flags", []))
        if dup_count.get(code):
            flags.add("duplicate_occurrences")
        if not TERMINATOR_RE.search(e["text"]):
            flags.add("unterminated_text")
        if len(e.get("pages") or []) > MANY_PAGES_THRESHOLD:
            # 원문 표/부속 기술주석이 여러 쪽에 걸친 경우. 정상일 수 있으나 감사 대상.
            flags.add("spans_many_pages")
        e["parse_flags"] = sorted(flags)
        e["text_completeness"] = classify_completeness(code, e["text"])
        e["duplicate_occurrences"] = dup_count.get(code, 0)
        out.append(e)
    return out


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Wassenaar/SCOMET PDF 파싱")
    ap.add_argument("--v2", action="store_true", help="교정판 파서로 *_v2.json 생성")
    args = ap.parse_args()

    if args.v2:
        was = parse_wassenaar_v2(DATA_DIR / "wassenaar_2025.pdf")
        (OUT_DIR / "wassenaar_v2.json").write_text(
            json.dumps(was, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        sc = parse_scomet_v2(DATA_DIR / "india_scomet_2024_official.pdf")
        (OUT_DIR / "india_scomet_v2.json").write_text(
            json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[v2] Wassenaar: {len(was)} | SCOMET: {len(sc)} | Total: {len(was)+len(sc)}")
    else:
        was = parse_wassenaar(DATA_DIR / "wassenaar_2025.pdf")
        (OUT_DIR / "wassenaar.json").write_text(
            json.dumps(was, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        sc = parse_scomet(DATA_DIR / "india_scomet_2024_official.pdf")
        (OUT_DIR / "india_scomet.json").write_text(
            json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[v1] Wassenaar: {len(was)} | SCOMET: {len(sc)} | Total: {len(was)+len(sc)}")
