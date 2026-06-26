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
                         and does not quote the answer code.
  3. low_overlap       : Jaccard(query tokens, answer minimal_text tokens) < MAX_JACCARD
                         (removes the self-retrieval artifact; query must be a
                         genuine paraphrase, not the entry's own wording).
  4. schema            : required fields present, lang in {ko, en}.

Slice-level checks: minimum count and Korean ratio.

Usage:
  python validate_query_slice.py data/validated_queries_slice_<name>.json
Exit code 0 = all gates pass; 1 = at least one failure (details printed).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from run_experiments import build_doc_text, tokenize, CONTROL_CODE_RE, has_code_leak

ROOT = Path(__file__).resolve().parent
CORPUS_PATH = ROOT / "data" / "corpus" / "combined.json"

MAX_JACCARD = 0.30
MIN_QUERIES = 25
MIN_KO_RATIO = 0.40
REQUIRED_FIELDS = ["id", "lang", "query", "context", "validated_labels"]


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


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
    ko = en = 0
    for q in queries:
        qid = q.get("id", "<no-id>")

        # schema
        missing = [f for f in REQUIRED_FIELDS if not q.get(f)]
        if missing:
            failures.append(f"{qid}: missing fields {missing}")
            continue
        if q["lang"] not in ("ko", "en"):
            failures.append(f"{qid}: lang must be ko/en, got {q['lang']!r}")
        if q["lang"] == "ko":
            ko += 1
        else:
            en += 1

        labels = q["validated_labels"]
        if not labels:
            failures.append(f"{qid}: empty validated_labels")
            continue

        # gate 1: label exact + eCFR source
        ans_entry = None
        for lbl in labels:
            entry = by_code.get(lbl)
            if entry is None:
                failures.append(f"{qid}: label {lbl!r} is not an exact corpus code")
            elif entry.get("source") != "ecfr_part774":
                failures.append(f"{qid}: label {lbl!r} source={entry.get('source')} (must be ecfr_part774)")
            elif ans_entry is None:
                ans_entry = entry

        # gate 2: no code leak
        for lbl in labels:
            if has_code_leak(q["query"], lbl):
                failures.append(f"{qid}: code leak — query contains code variant of {lbl}")
                break
        else:
            if CONTROL_CODE_RE.search(q["query"]):
                failures.append(f"{qid}: query contains a control-code-shaped token")

        # gate 3: low overlap vs answer doc (self-retrieval guard)
        if ans_entry is not None:
            j = jaccard(tokenize(q["query"]), tokenize(build_doc_text(ans_entry, "minimal_text")))
            if j >= MAX_JACCARD:
                failures.append(f"{qid}: Jaccard {j:.3f} >= {MAX_JACCARD} (too close to entry wording — paraphrase more)")

    n = len(queries)
    ko_ratio = ko / n if n else 0.0
    if n < MIN_QUERIES:
        failures.append(f"slice: only {n} queries (need >= {MIN_QUERIES})")
    if ko_ratio < MIN_KO_RATIO:
        failures.append(f"slice: Korean ratio {ko_ratio:.2f} < {MIN_KO_RATIO} (ko={ko}, en={en})")

    print(json.dumps({
        "slice": slice_path.name,
        "queries": n,
        "ko": ko,
        "en": en,
        "ko_ratio": round(ko_ratio, 3),
        "max_jaccard_allowed": MAX_JACCARD,
        "failures": failures,
        "passed": not failures,
    }, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
