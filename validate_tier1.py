#!/usr/bin/env python3
"""Verify a Tier-1 bundle before merging it, without trusting the machine it came from.

    python validate_tier1.py output/tier1/tier1_bge-m3.json

Same anchor as `validate_shard.py`: BM25 never touches the dense encoder, so its
hit vectors must be identical no matter who ran it or on what. Here that check is
stronger than for shards, because the ablation perturbs the queries and the
frontier rewrites them by disclosure level -- BM25 rows still have to match
exactly at every level, which pins the corpus, the query set, the substitution
dictionary, the disclosure ladder, and the ranking rule all at once.

When no other bundle exists to compare against, BM25 is recomputed locally from
the corpus on disk. That needs no encoder and takes seconds, so a first bundle is
verified just as strictly as a later one.

Exit 0 means the bundle is safe to merge.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "data" / "corpus" / "combined.json"
LADDER = ROOT / "data" / "disclosure_ladder.json"
SUBS = ROOT / "data" / "hypernym_substitutions.json"

FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAIL.append(name)


def bm25_hits(corpus, queries, labels, imode) -> list[int]:
    docs = [rc.index_text(e, imode) for e in corpus]
    codes = [e["code"] for e in corpus]
    index = rc.BM25(docs)
    out = []
    for q, L in zip(queries, labels):
        top10 = rc.retrieve(index.scores(q), 10)
        out.append(int(any(codes[i] in L for i in top10)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--reference", type=Path, default=None)
    args = ap.parse_args()

    if not args.bundle.exists():
        print(f"error: {args.bundle} not found", file=sys.stderr)
        return 2
    b = json.loads(args.bundle.read_text(encoding="utf-8"))
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    ladder = json.loads(LADDER.read_text(encoding="utf-8"))["queries"]

    print(f"검증 대상: {args.bundle}")
    print(f"모델: {b.get('model_key')} = {b.get('model_name')}\n")

    print("[구조]")
    check("tier1_format == 1", b.get("tier1_format") == 1)
    abl = b.get("symmetric_ablation") or {}
    fr = b.get("disclosure_frontier") or {}
    check("두 실험 결과가 모두 있다", bool(abl) and bool(fr))
    if not (abl and fr):
        print("\n구조가 깨져 병합할 수 없습니다.")
        return 1
    check("ablation env 기록", bool((abl.get("env") or {}).get("numpy")))
    check("frontier env 기록", bool((fr.get("env") or {}).get("numpy")))
    check("두 실험의 모델이 일치",
          (abl.get("env") or {}).get("dense_model", b["model_name"]) == b["model_name"]
          or b["model_name"] in json.dumps(abl.get("env", {})),
          "env 에 dense_model 이 없으면 통과로 둔다")

    print("\n[데이터 일치]")
    check("질의 수 71", len(ladder) == 71, str(len(ladder)))
    check("ablation query_ids 가 사다리와 동일",
          abl.get("query_ids") == [q["id"] for q in ladder])
    check("치환 사전 존재", SUBS.exists())

    print("\n[BM25 교차검증 — 인코더와 무관하므로 반드시 일치]")
    ref = None
    if args.reference and args.reference.exists():
        ref = json.loads(args.reference.read_text(encoding="utf-8"))
        src = args.reference.name
    else:
        others = sorted(p for p in args.bundle.parent.glob("tier1_*.json")
                        if p != args.bundle)
        if others:
            ref = json.loads(others[0].read_text(encoding="utf-8"))
            src = others[0].name

    # frontier: 등급별 BM25 는 로컬 재계산과 대조 가능
    fr_hits = fr.get("hit_vectors") or {}
    labels = [set(q["validated_labels"]) for q in ladder]
    for lv in ("L0", "L1", "L2", "L3", "L4"):
        got = (fr_hits.get(lv) or {}).get("BM25")
        if got is None:
            check(f"frontier {lv}: BM25 벡터 존재", False)
            continue
        qs = [q["levels"][lv]["query"] for q in ladder]
        expect = bm25_hits(corpus, qs, labels, fr.get("prespecification", {})
                           .get("index_mode", "minimal_text"))
        n_diff = sum(1 for x, y in zip(got, expect) if x != y)
        check(f"frontier {lv}: BM25 가 로컬 재계산과 동일", got == expect,
              f"{n_diff}개 불일치 (샤드 {sum(got)} vs 재계산 {sum(expect)})" if n_diff else "")

    # ablation 도 로컬 재계산으로 대조한다. 동료 번들과만 비교하면 **비교 상대가 없을 때
    # 검사가 통째로 건너뛰어지고**, 그 틈으로 낡은 코퍼스에서 계산된 기준본이 통과한다.
    # 실제로 그 사고가 났다: v1 코퍼스로 만든 MiniLM ablation 이 기준본으로 커밋됐고,
    # 두 번째 번들이 들어와서야 드러났다. substitution_log 가 등급별 치환 질의 전문을
    # 담고 있으므로 인코더 없이 BM25 를 그대로 재계산할 수 있다.
    log = abl.get("substitution_log") or {}
    abl_hits = abl.get("hit_vectors") or {}
    qids = abl.get("query_ids") or [q["id"] for q in ladder]
    if not log:
        check("ablation: substitution_log 존재(로컬 재계산에 필요)", False)
    else:
        for imode in ("full_text", "minimal_text"):
            for lv in ("0", "1", "2", "3"):
                got = ((abl_hits.get(imode) or {}).get(lv) or {}).get("BM25")
                if got is None:
                    check(f"ablation {imode} L{lv}: BM25 벡터 존재", False)
                    continue
                qs, ls = [], []
                for qid, lab in zip(qids, labels):
                    node = (log.get(qid) or {}).get(lv)
                    if node is None:
                        qs = []
                        break
                    qs.append(node["text"])
                    ls.append(lab)
                if not qs:
                    check(f"ablation {imode} L{lv}: substitution_log 완전성", False,
                          "일부 질의의 등급 텍스트 누락")
                    continue
                expect = bm25_hits(corpus, qs, ls, imode)
                n_diff = sum(1 for x, y in zip(got, expect) if x != y)
                check(f"ablation {imode} L{lv}: BM25 가 로컬 재계산과 동일",
                      got == expect,
                      f"{n_diff}개 불일치 (번들 {sum(got)} vs 재계산 {sum(expect)}) — "
                      f"다른 코퍼스에서 계산된 번들입니다" if n_diff else "")
    if ref:
        abl_ref = (ref.get("symmetric_ablation") or {}).get("hit_vectors") or {}
        for imode in ("full_text", "minimal_text"):
            a = (abl_hits.get(imode) or {})
            r = (abl_ref.get(imode) or {})
            keys = sorted(set(a) & set(r))
            bad = [k for k in keys if isinstance(a[k], dict) and "BM25" in a[k]
                   and a[k]["BM25"] != r[k].get("BM25")]
            check(f"ablation: BM25 가 {src} 와 동일 ({imode})", not bad, str(bad[:4]))

    print("\n[정합성]")
    hl = abl.get("headline") or {}
    rbl = hl.get("recall_by_level") or {}
    bm = rbl.get("BM25") or {}
    if bm:
        lv = sorted(bm, key=lambda k: int(k))
        vals = [bm[k] for k in lv]
        check("ablation: 치환할수록 BM25 R@10 단조 감소",
              all(a >= b - 1e-9 for a, b in zip(vals, vals[1:])), str(vals))
    ko = (rbl.get("BM25") and (hl.get("recall_by_level_ko") or {}).get("BM25")) or {}
    if ko:
        check("ablation: 한국어 BM25 는 전 level 0.0000 (코퍼스가 100% 영어)",
              all(abs(v) < 1e-9 for v in ko.values()), str(ko))
    tiers = fr.get("evidence_tiers") or {}
    prim = tiers.get("hybrid_0.5") or {}
    if prim:
        check("frontier: 권고 등급이 산출됨", bool(prim.get("recommended_level")),
              str(prim.get("recommended_level")))
        check("frontier: 자기참조 교란 등급이 권고에서 제외됨",
              prim.get("recommended_level") not in
              (prim.get("confounded_by_selfreference") or []),
              f"권고 {prim.get('recommended_level')}, 교란 {prim.get('confounded_by_selfreference')}")

    print()
    if FAIL:
        print(f"{len(FAIL)}건 실패 — 병합하지 마십시오:")
        for f in FAIL:
            print("  -", f)
        return 1
    print("모든 검증 통과 — 이 파일을 보내면 됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
