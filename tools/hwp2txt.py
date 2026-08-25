#!/usr/bin/env python3
"""HWP 5.0 본문 텍스트 추출기 (OLE + zlib + 레코드 파싱).

팀원이 HWP 로 쓰는 논문 초안을 검토하려면 본문을 텍스트로 꺼내야 하는데, 이 환경에는
hwp5txt / libreoffice / pandoc 이 없다. 그래서 HWP 5.0 포맷(OLE 복합문서)을 직접 읽는다.

    python tools/hwp2txt.py "논문.hwp" > draft.txt

의존성: olefile (pip install olefile)

주의 — 컨트롤 문자 폭:
    1 wchar : 0, 10, 13, 24~31
    8 wchar : 1~9, 11~12, 14~23
8 wchar 짜리를 1 wchar 로 세면 뒤따르는 16바이트 제어 데이터가 본문 글자로 섞여 나온다
(초판에서 "捤獥汤捯" 같은 쓰레기가 나온 원인). WIDE_CTRL 이 그것을 건너뛴다.
"""
import struct
import sys
import zlib

import olefile

HWPTAG_BEGIN = 0x10
PARA_TEXT = HWPTAG_BEGIN + 51  # 67

WIDE_CTRL = set(range(1, 10)) | {11, 12} | set(range(14, 24))
NEWLINE = chr(10)
TAB = chr(9)


def records(buf):
    i = 0
    while i + 4 <= len(buf):
        (h,) = struct.unpack_from("<I", buf, i)
        i += 4
        tag = h & 0x3FF
        size = (h >> 20) & 0xFFF
        if size == 0xFFF:
            (size,) = struct.unpack_from("<I", buf, i)
            i += 4
        yield tag, buf[i:i + size]
        i += size


def para_text(data):
    out = []
    k, n = 0, len(data)
    while k + 1 < n:
        (c,) = struct.unpack_from("<H", data, k)
        if c in WIDE_CTRL:
            k += 16
            continue
        k += 2
        if c in (10, 13):
            out.append(NEWLINE)
        elif c == 9:
            out.append(TAB)
        elif c < 32:
            continue
        else:
            out.append(chr(c))
    return "".join(out)


def extract(path):
    ole = olefile.OleFileIO(path)
    streams = ["/".join(s) for s in ole.listdir()]
    body = sorted(
        [s for s in streams if s.startswith("BodyText/")],
        key=lambda s: int("".join(ch for ch in s if ch.isdigit()) or 0),
    )
    compressed = True
    if "FileHeader" in streams:
        fh = ole.openstream("FileHeader").read()
        if len(fh) > 36:
            compressed = bool(fh[36] & 0x01)
    chunks = []
    for s in body:
        raw = ole.openstream(s).read()
        try:
            buf = zlib.decompress(raw, -15) if compressed else raw
        except zlib.error:
            try:
                buf = zlib.decompress(raw)
            except zlib.error:
                continue
        for tag, data in records(buf):
            if tag == PARA_TEXT:
                t = para_text(data)
                if t.strip():
                    chunks.append(t)
    ole.close()
    return NEWLINE.join(chunks)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(extract(sys.argv[1]))
