#!/usr/bin/env python3
"""Flag equivalent labels that no longer exist in the active corpus.

`data/equivalent_labels.json` maps each validated gold ECCN to counterpart codes
in the other control regimes. Those counterparts are Wassenaar/SCOMET codes, and
the corpus parser fix renamed or merged some of them -- `ECCN-2D001`'s counterpart
`2.D.1`, for instance, exists in v1 but not v2.

A dangling counterpart must not be silently dropped (it would quietly shrink the
equivalent-label recall metric) and must not be auto-repaired either (guessing a
substitute is inventing a label mapping). So this marks it explicitly and lists
prefix-matched candidates for a human to confirm.

    python repair_equivalent_labels.py --check    # report only
    python repair_equivalent_labels.py            # annotate the file

Outputs: data/equivalent_labels.json (annotated), output/equivalent_labels_repair.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "data" / "corpus" / "combined.json"
MAP_PATH = ROOT / "data" / "equivalent_labels.json"
REPORT = ROOT / "output" / "equivalent_labels_repair.md"


def candidates(code: str, present: set[str]) -> list[str]:
    """Codes that could be the successor: longest shared dotted prefix."""
    parts = code.split(".")
    out: list[str] = []
    for cut in range(len(parts), 0, -1):
        prefix = ".".join(parts[:cut])
        hits = sorted(c for c in present
                      if c == prefix or c.startswith(prefix + "."))
        hits = [h for h in hits if h != code]
        if hits:
            out = hits[:8]
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    present = {e["code"] for e in corpus}
    payload = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    mappings = payload["mappings"]

    dangling, restored, total_eq = [], [], 0
    for m in mappings:
        for eq in m.get("equivalents", []):
            total_eq += 1
            code = eq["code"]
            absent = code not in present
            was_flagged = bool(eq.get("absent_from_active_corpus"))
            if absent:
                cands = candidates(code, present)
                eq["absent_from_active_corpus"] = True
                eq["absent_note"] = (
                    "활성 코퍼스에 존재하지 않는 코드다. 코퍼스 파서 교정으로 코드가 "
                    "병합·개칭되었을 수 있다. R@10_equiv 계산에서 제외되며, 후보를 "
                    "사람이 확인해 교체할 때까지 자동 대체하지 않는다.")
                eq["successor_candidates"] = cands
                dangling.append({"eccn": m["eccn"], "code": code,
                                 "regime": eq.get("regime"),
                                 "relation": eq.get("relation"),
                                 "candidates": cands})
            elif was_flagged:
                # a previous run flagged it but it is back (e.g. after --revert)
                eq.pop("absent_from_active_corpus", None)
                eq.pop("absent_note", None)
                eq.pop("successor_candidates", None)
                restored.append({"eccn": m["eccn"], "code": code})

    payload.setdefault("meta", {})["equivalent_label_integrity"] = {
        "active_corpus_entries": len(corpus),
        "total_equivalents": total_eq,
        "dangling": len(dangling),
        "restored_this_run": len(restored),
        "policy": "존재하지 않는 등가 코드는 명시적으로 표시하고 R@10_equiv에서 제외한다. "
                  "자동 대체는 하지 않는다(라벨 매핑을 발명하는 것이므로).",
    }

    lines = ["# 등가 라벨 정합성 점검", "",
             f"활성 코퍼스 {len(corpus)}건 / 등가 코드 총 {total_eq}개 / "
             f"존재하지 않는 것 **{len(dangling)}개**", ""]
    if dangling:
        lines += ["| 정답 ECCN | 사라진 등가 코드 | 레짐 | 관계 | 후보 (사람 확인 필요) |",
                  "|---|---|---|---|---|"]
        for d in dangling:
            lines.append(f"| {d['eccn']} | `{d['code']}` | {d['regime']} | {d['relation']} | "
                         f"{', '.join(f'`{c}`' for c in d['candidates']) or '없음'} |")
        lines += ["", "> 후보는 점 구분 접두가 가장 길게 일치하는 코드다. **자동 채택하지 "
                  "않는다** — 등가 여부는 양쪽 원문을 읽어야 판정된다. 확인 후 "
                  "`data/equivalent_labels.json`의 해당 항목을 직접 수정하고 "
                  "`evidence` 인용을 갱신하십시오.", ""]
    else:
        lines += ["모든 등가 코드가 활성 코퍼스에 존재한다.", ""]
    if restored:
        lines += ["## 이번 실행에서 표시가 해제된 코드", "",
                  *[f"- {r['eccn']} → `{r['code']}`" for r in restored], ""]

    if args.check:
        print("\n".join(lines))
        print("--check 모드: 파일을 변경하지 않았습니다.")
        return 1 if dangling else 0

    MAP_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {MAP_PATH.name}, {REPORT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
