#!/usr/bin/env python3
"""Verify a teammate's model shard in one command before merging it.

    python validate_shard.py output/shards/shard_bge-m3.json

Exit 0 means the shard is safe to merge. The strongest check is structural
rather than statistical: BM25 does not use the dense encoder at all, so the BM25
hit vectors in every shard must be byte-identical. If a teammate ran against a
different corpus revision, a different query file, an older ranking rule, or
edited the numbers, the BM25 vectors diverge and this catches it -- without
needing to trust anything about their machine.

When no reference shard exists yet, BM25 is recomputed locally instead (cheap:
no encoder involved).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import experiment_validated_suite as suite
import retrieval_core as rc

FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        FAIL.append(name)


def local_bm25_hits(corpus, queries, imode) -> list[int]:
    """BM25-only hit@10 -- no encoder, so this is fast and fully reproducible."""
    docs = [rc.index_text(e, imode) for e in corpus]
    codes = [e["code"] for e in corpus]
    index = rc.BM25(docs)
    out = []
    for q in queries:
        scores = index.scores(q["query"])
        top10 = rc.retrieve(scores, 10)          # [] when there is no signal
        labels = set(q["validated_labels"])
        out.append(int(any(codes[i] in labels for i in top10)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("shard", type=Path)
    ap.add_argument("--reference", type=Path, default=None,
                    help="another shard to cross-check BM25 vectors against")
    args = ap.parse_args()

    if not args.shard.exists():
        print(f"error: {args.shard} not found", file=sys.stderr)
        return 2
    shard = json.loads(args.shard.read_text(encoding="utf-8"))
    corpus = json.loads(suite.CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(suite.QUERIES_PATH.read_text(encoding="utf-8"))["queries"]

    print(f"검증 대상: {args.shard}")
    print(f"모델: {shard.get('model_key')} = {shard.get('model_name')}")
    print(f"revision: {shard.get('revision')}\n")

    print("[구조]")
    check("shard_format == 1", shard.get("shard_format") == 1)
    check("model_key 가 알려진 인코더", shard.get("model_key") in suite.DENSE_MODELS,
          str(shard.get("model_key")))
    check("seed 일치", shard.get("seed") == suite.SEED,
          f"{shard.get('seed')} vs {suite.SEED}")
    check("index_modes 일치", shard.get("index_modes") == suite.INDEX_MODES)
    check("alphas 일치", shard.get("alphas") == suite.ALPHAS)
    check("env 기록됨", bool(shard.get("env", {}).get("numpy")))
    check("모델 revision 기록됨", bool(shard.get("revision")),
          "없으면 재현 불가 — huggingface_hub 설치 후 재실행 권장")

    print("\n[데이터 일치]")
    check("corpus_size 일치", shard.get("corpus_size") == len(corpus),
          f"{shard.get('corpus_size')} vs {len(corpus)}")
    check("query_ids 일치", shard.get("query_ids") == [q["id"] for q in queries])
    check("langs 일치", shard.get("langs") == [q["lang"] for q in queries])

    print("\n[벡터 형태]")
    for imode in suite.INDEX_MODES:
        h = shard.get("hits", {}).get(imode, {})
        names = {suite.alpha_name(a) for a in suite.ALPHAS}
        check(f"{imode}: retriever 키 완비", set(h) == names,
              str(sorted(set(names) - set(h))) if set(h) != names else "")
        lens = {k: len(v) for k, v in h.items()}
        check(f"{imode}: 길이 모두 {len(queries)}",
              all(v == len(queries) for v in lens.values()), str(sorted(set(lens.values()))))
        check(f"{imode}: 값이 0/1", all(set(v) <= {0, 1} for v in h.values()))
        check(f"{imode}: exposure@10 기록",
              set(shard.get("exposure_at10", {}).get(imode, {}))
              >= {f"return={r}" for r in suite.RETURN_MODES})

    print("\n[BM25 교차검증 — 인코더와 무관하므로 반드시 일치해야 함]")
    ref = None
    if args.reference and args.reference.exists():
        ref = json.loads(args.reference.read_text(encoding="utf-8"))
        src = f"reference {args.reference.name}"
    else:
        others = sorted(p for p in args.shard.parent.glob("shard_*.json")
                        if p != args.shard)
        if others:
            ref = json.loads(others[0].read_text(encoding="utf-8"))
            src = f"기존 샤드 {others[0].name}"
    if ref:
        for imode in suite.INDEX_MODES:
            a = shard["hits"][imode]["BM25"]
            b = ref["hits"][imode]["BM25"]
            check(f"{imode}: BM25 벡터가 {src} 와 동일", a == b,
                  f"{sum(1 for x, y in zip(a, b) if x != y)}개 불일치" if a != b else "")
    else:
        print("  (비교할 다른 샤드 없음 — BM25를 로컬에서 재계산해 대조)")
        for imode in suite.INDEX_MODES:
            expect = local_bm25_hits(corpus, queries, imode)
            got = shard["hits"][imode]["BM25"]
            check(f"{imode}: BM25 벡터가 로컬 재계산과 동일", got == expect,
                  f"{sum(1 for x, y in zip(got, expect) if x != y)}개 불일치"
                  if got != expect else "")

    print("\n[정합성]")
    for imode in suite.INDEX_MODES:
        d = shard.get("diagnostics", {}).get(imode, {})
        n_ns = d.get("bm25_no_signal_queries")
        bm = shard["hits"][imode]["BM25"]
        check(f"{imode}: 무신호 질의({n_ns})가 BM25 미적중과 모순 없음",
              n_ns is not None and sum(bm) <= len(queries) - n_ns,
              f"BM25 적중 {sum(bm)}, 무신호 {n_ns}")
        same = d.get("hybrid_top10_identical_to_dense", {}).get(
            suite.alpha_name(suite.PRIMARY_ALPHA))
        check(f"{imode}: hybrid≡dense 건수({same}) >= 무신호 건수({n_ns})",
              same is not None and n_ns is not None and same >= n_ns,
              "BM25 점수가 전부 0이면 α<1 랭킹은 dense와 동일해야 한다")

    print()
    if FAIL:
        print(f"{len(FAIL)}건 실패 — 병합하지 마십시오:")
        for f in FAIL:
            print("  -", f)
        return 1
    print("모든 검증 통과 — merge_shards.py 로 병합 가능합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
