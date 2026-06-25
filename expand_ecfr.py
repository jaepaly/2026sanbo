#!/usr/bin/env python3
"""Attempt to expand eCFR Part 774 Supplement 1 corpus from web sources."""
import json, re, os
from pathlib import Path

try:
    import requests
except Exception:
    requests = None

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CORPUS_DIR = DATA_DIR / "corpus"
ECFR_PATH = CORPUS_DIR / "ecfr_supp1.json"
EXPANDED_PATH = CORPUS_DIR / "ecfr_supp1_expanded.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}

def fetch(url: str, **kw):
    if requests is None:
        raise RuntimeError("requests not installed")
    r = requests.get(url, headers=HEADERS, timeout=60, **kw)
    r.raise_for_status()
    return r

# ---- Source A: eCFR API JSON/XML ----
def try_ecfr_api() -> list:
    out = []
    import datetime
    yr = datetime.date.today().year
    candidates = [
        f"https://www.ecfr.gov/api/versioner/v1/full/{yr}-01-01/title-15.xml",
        f"https://www.ecfr.gov/api/versioner/v1/structure/{yr}-01-01/title-15.json",
    ]
    for url in candidates:
        try:
            print(f"[expand_ecfr] trying {url}")
            body = fetch(url)
            ct = body.headers.get("content-type", "")
            if "xml" in ct:
                txt = body.text
                codes = re.findall(r"\b(ECCN[-\s][0-9A-Za-z.]{2,})\b", txt)
                seen = set()
                for c in codes:
                    c = c.replace(" ", "-")
                    if c not in seen:
                        seen.add(c)
                        out.append({"code": c, "text": "", "source": "ecfr_api", "page": 0})
            elif "json" in ct:
                data = body.json()
                # walk structure looking for references to Supplemental 1 entries
                def walk(x):
                    if isinstance(x, dict):
                        for v in x.values():
                            walk(v)
                    elif isinstance(x, list):
                        for item in x:
                            walk(item)
                    elif isinstance(x, str):
                        m = re.search(r"\b(ECCN[-\s][0-9A-Za-z.]{2,})\b", x)
                        if m:
                            c = m.group(1).replace(" ", "-")
                            out.append({"code": c, "text": "", "source": "ecfr_api_struct", "page": 0})
                walk(data)
            if out:
                return out
        except Exception as e:
            print(f"[expand_ecfr] {url} failed: {e}")
    return out

# ---- Source B: Cornell LII HTML ----
def try_cornell_lii() -> list:
    out = []
    urls = [
        "https://www.law.cornell.edu/cfr/text/15/part-774",
        "https://www.law.cornell.edu/cfr/text/15/774",
    ]
    for url in urls:
        try:
            print(f"[expand_ecfr] trying Cornell {url}")
            html = fetch(url).text
            paras = re.findall(r"<p[^>]*>(.*?)</p>", html, flags=re.S)
            seen = set()
            for p in paras:
                p = re.sub(r"<[^>]+>", "", p).strip()
                m = re.search(r"(ECCN[-\s][0-9A-Za-z.]{2,})", p)
                if m and len(p) > 40:
                    c = m.group(1).replace(" ", "-")
                    if c not in seen:
                        seen.add(c)
                        out.append({"code": c, "text": p, "source": "cornell_lii", "page": 0})
            if out:
                return out
        except Exception as e:
            print(f"[expand_ecfr] Cornell failed: {e}")
    return out

# ---- Source C: wassenaar zip-as-html reparse ----
def try_wassenaar_html() -> list:
    path = DATA_DIR / "wassenaar_2025.zip"
    if not path.exists():
        return []
    out = []
    seen = set()
    try:
        html = path.read_text(encoding="utf-8", errors="ignore")
        blocks = re.findall(r"([0-9]\.[A-Z]\.\d+[A-Za-z.]*\s+.*?)(?=\s[0-9]\.[A-Z]\.\d+[A-Za-z.]*\s+|$)", html)
        for b in blocks:
            b = re.sub(r"\s+", " ", b).strip()
            m = re.match(r"([0-9]\.[A-Z]\.\d+[A-Za-z.]*)\s+(.*)", b)
            if m and len(b) > 50:
                c = m.group(1)
                txt = m.group(2)
                if c not in seen:
                    seen.add(c)
                    out.append({"code": c, "text": txt, "source": "wassenaar_html", "page": 0})
    except Exception as e:
        print(f"[expand_ecfr] wassenaar_html failed: {e}")
    return out

# ---- Source D: re-extract from existing PDFs more permissively ----
def reparse_pdfs() -> list:
    out = []
    pdfs = [
        ("wassenaar_2025.pdf", r"^(?:\s*)(\d+)\s*\.\s*([A-Z])\s*\.\s*(\d+)?\s*\.?\s*([A-Za-z])?\s*\.\s*(\d+)?\s*\.?\s*([A-Za-z])?\.?\s+(.+)$", "wassenaar_reparse"),
        ("india_scomet.pdf", r"^(\d)([A-Z])(\d{3})([a-z]?)\.?\s+(.+)$", "scomet_reparse"),
    ]
    for fname, pat, src in pdfs:
        p = DATA_DIR / fname
        if not p.exists():
            continue
        try:
            import pdfplumber
            r = pdfplumber.open(p)
            seen = set()
            for i, page in enumerate(r.pages):
                txt = (page.extract_text() or "")
                for line in txt.splitlines():
                    line = line.strip()
                    if not line or len(line) < 8:
                        continue
                    m = re.match(pat, line)
                    if not m:
                        continue
                    grp = m.groups()
                    # build code from first 4 non-pure-digit-or-empty tokens
                    code_parts = []
                    for t in grp[:4]:
                        if t is None:
                            continue
                        s = str(t)
                        if s.isdigit() and int(s) == 0:
                            continue
                        code_parts.append(s)
                    code = ".".join(code_parts)
                    desc = (grp[4] or "").strip() if len(grp) > 4 else ""
                    if code not in seen and len(desc) > 10:
                        seen.add(code)
                        out.append({"code": code, "text": desc, "source": src, "page": i+1})
            r.close()
        except Exception as e:
            print(f"[expand_ecfr] reparse {fname} failed: {e}")
    return out

def merge_and_dedupe(base: list, new: list) -> list:
    seen = set((e.get("code",""), e.get("source","")) for e in base)
    merged = list(base)
    added = 0
    for e in new:
        if not e.get("code"):
            continue
        key = (e["code"], e.get("source", ""))
        if key not in seen:
            seen.add(key)
            merged.append(e)
            added += 1
    return merged, added

def main():
    print("[expand_ecfr] Loading base eCFR corpus ...")
    base = []
    if ECFR_PATH.exists():
        base = json.loads(ECFR_PATH.read_text(encoding="utf-8"))
    print(f"[expand_ecfr] Base size: {len(base)}")

    candidates = []
    for src in [try_ecfr_api, try_cornell_lii, try_wassenaar_html, reparse_pdfs]:
        candidates += src()

    print(f"[expand_ecfr] Candidates from expansion: {len(candidates)}")
    merged, added = merge_and_dedupe(base, candidates)
    print(f"[expand_ecfr] Added {added} new entries. Total: {len(merged)}")

    EXPANDED_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[expand_ecfr] Saved to {EXPANDED_PATH}")

    comb = CORPUS_DIR / "combined.json"
    if comb.exists():
        all_corpus = json.loads(comb.read_text(encoding="utf-8"))
        others = [x for x in all_corpus if not x.get("code", "").startswith("ECCN-")]
        expanded_e = [x for x in merged if x.get("code", "").startswith("ECCN-")]
        new_combined = others + expanded_e
        comb.write_text(json.dumps(new_combined, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[expand_ecfr] Updated combined.json: {len(new_combined)} total (eCFR={len(expanded_e)})")

if __name__ == "__main__":
    main()
