#!/usr/bin/env python3
"""Build control corpus from Wassenaar + India SCOMET PDFs into clean JSON."""
import json, re, os
from pathlib import Path
import pdfplumber

DATA_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR = DATA_DIR / "corpus"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_wassenaar(path: Path):
    r = pdfplumber.open(path)
    entries = []
    current = None
    entry_re = re.compile(
        r"^(?:\s*)(\d+)\s*\.\s*([A-Z])\s*\.\s*(\d+)?\s*\.?\s*([A-Za-z])?\s*\.\s*(\d+)?\s*\.?\s*([A-Za-z])?\.?\s+(.+)$"
    )
    entry_re_short = re.compile(
        r"^(?:\s*)(\d+)\s*\.\s*([A-Z])(?:\s*\.\s*(\d+)?)?\s*\.?\s*([A-Za-z])?\.?\s+(.+)$"
    )
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
    for i, page in enumerate(r.pages):
        text = page.extract_text() or ""
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
                # rebuild code
                raw = m.groups()
                code_parts = []
                for token in raw[:-1]:
                    if token is not None:
                        code_parts.append(str(token))
                code = ".".join(code_parts)
                # strip trailing sentence-starting conjunctives that leaked from previous entry
                desc = raw[-1].strip()
                current = {
                    "code": code,
                    "text": desc,
                    "source": "wassenaar_2025",
                    "page": i + 1,
                }
                continue
            if current:
                current["text"] += " " + line
        if current and current["text"]:
            entries.append(current)
            current = None
    r.close()
    seen, out = set(), []
    for e in entries:
        k = e["code"].strip()
        if k not in seen and len(e["text"]) >= 10:
            seen.add(k)
            out.append(e)
    return out


def parse_scomet(path: Path):
    r = pdfplumber.open(path)
    entries = []
    current = None
    entry_re = re.compile(r"^(\d)([A-Z])(\d{3})([a-z]?)\.?\s+(.+)$")
    skip = {"Appendix 3", "SCOMET List", "Technical Note", "National equivalents", "Item", "Notification"}
    for i, page in enumerate(r.pages):
        text = page.extract_text() or ""
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
        if current and current["text"]:
            entries.append(current)
            current = None
    r.close()
    seen, out = set(), []
    for e in entries:
        k = e["code"].strip()
        if k not in seen and len(e["text"]) >= 10:
            seen.add(k)
            out.append(e)
    return out


if __name__ == "__main__":
    was = parse_wassenaar(DATA_DIR / "wassenaar_2025.pdf")
    (OUT_DIR / "wassenaar.json").write_text(
        json.dumps(was, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sc = parse_scomet(DATA_DIR / "india_scomet_2024_official.pdf")
    (OUT_DIR / "india_scomet.json").write_text(
        json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Wassenaar: {len(was)} | SCOMET: {len(sc)} | Total: {len(was)+len(sc)}")
