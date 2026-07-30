#!/usr/bin/env python3
"""Merge per-model shards into the full validated-set analysis. No re-encoding.

    python merge_shards.py
    -> output/validated_suite.json, output/validated_suite.md

Reads every output/shards/shard_*.json, cross-checks them against each other,
and runs the statistics once. Because BM25 does not depend on the encoder, all
shards must agree exactly on the BM25 hit vectors; disagreement means one shard
was produced from a different corpus, query set, or ranking rule, and merging is
refused rather than silently averaging incompatible runs.

Missing encoders are fine -- the analysis simply covers whichever models are
present, and `meta.dense_models` records exactly which those were.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import experiment_validated_suite as suite
import retrieval_core as rc

SHARD_DIR = suite.OUT_DIR / "shards"
VERSION_MANIFEST = suite.DATA_DIR / "corpus" / "corpus_version_manifest.json" \
    if hasattr(suite, "DATA_DIR") else Path("data/corpus/corpus_version_manifest.json")


def ROOT_MANIFEST() -> str | None:
    """Which corpus version is active, for the error message after a swap."""
    try:
        m = json.loads(Path(VERSION_MANIFEST).read_text(encoding="utf-8"))
        return f"{m.get('active')} (sha {m.get('v2_active', m.get('v1', {})).get('sha256', '')[:16]}...)"
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard-dir", type=Path, default=SHARD_DIR)
    ap.add_argument("--primary", default=None,
                    help=f"primary model key (default {suite.PRIMARY_MODEL} if present)")
    ap.add_argument("--allow-bm25-mismatch", action="store_true",
                    help="병합을 강행한다. 진단 목적 외에는 쓰지 마십시오.")
    args = ap.parse_args()

    paths = sorted(args.shard_dir.glob("shard_*.json"))
    if not paths:
        print(f"error: {args.shard_dir} 에 shard_*.json 이 없습니다. "
              f"run_model_shard.py 를 먼저 실행하세요.", file=sys.stderr)
        return 2

    per_model: dict[str, dict] = {}
    for p in paths:
        s = json.loads(p.read_text(encoding="utf-8"))
        key = s.get("model_key")
        if not key:
            print(f"error: {p.name} 에 model_key 가 없습니다", file=sys.stderr)
            return 2
        per_model[key] = s
        print(f"loaded {p.name:<28} {key:<10} revision {s.get('revision')}")

    corpus = json.loads(suite.CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(suite.QUERIES_PATH.read_text(encoding="utf-8"))["queries"]

    # BM25 is encoder-independent, so it is the integrity anchor. Cross-checking
    # shards against each other is not enough: a single stale shard has nothing
    # to disagree with and would merge silently against a corpus it was never
    # computed from -- exactly the situation right after a corpus swap. So every
    # shard is checked against BM25 recomputed from the corpus on disk, which
    # needs no encoder and takes seconds.
    keys = list(per_model)
    mismatches = []
    local_bm25 = {}
    for imode in suite.INDEX_MODES:
        docs = [rc.index_text(e, imode) for e in corpus]
        codes = [e["code"] for e in corpus]
        index = rc.BM25(docs)
        expect = []
        for q in queries:
            top10 = rc.retrieve(index.scores(q["query"]), 10)
            labels = set(q["validated_labels"])
            expect.append(int(any(codes[i] in labels for i in top10)))
        local_bm25[imode] = expect
        for k in keys:
            got = per_model[k]["hits"][imode]["BM25"]
            if got != expect:
                n = sum(1 for x, y in zip(got, expect) if x != y)
                mismatches.append(
                    f"{imode}: {k} 샤드가 현재 코퍼스에서 재계산한 BM25와 {n}개 질의 불일치 "
                    f"(샤드 적중 {sum(got)}, 재계산 {sum(expect)}) — 다른 코퍼스/질의셋에서 "
                    f"계산된 샤드입니다")
    if mismatches:
        print("\nBM25 벡터 불일치 (인코더와 무관하므로 같아야 함):", file=sys.stderr)
        for m in mismatches:
            print("  -", m, file=sys.stderr)
        vm = ROOT_MANIFEST()
        if vm:
            print(f"\n현재 활성 코퍼스: {vm}", file=sys.stderr)
        print("\n병합을 중단합니다. 코퍼스를 교체했다면 output/shards/ 를 비우고 "
              "run_model_shard.py 를 다시 돌려야 합니다.", file=sys.stderr)
        if not args.allow_bm25_mismatch:
            return 1
        print("\n--allow-bm25-mismatch 지정됨 — 강행합니다.", file=sys.stderr)

    for k, s in per_model.items():
        if s.get("query_ids") != [q["id"] for q in queries]:
            print(f"error: {k} 샤드의 query_ids 가 현재 질의셋과 다릅니다", file=sys.stderr)
            return 1

    primary = args.primary or (suite.PRIMARY_MODEL if suite.PRIMARY_MODEL in per_model
                               else sorted(per_model)[0])
    print(f"\nmodels: {', '.join(sorted(per_model))} / primary: {primary}")

    out = suite.analyze(per_model, corpus, queries, primary_model=primary)
    out["meta"]["merged_from_shards"] = [p.name for p in paths]
    out["meta"]["shard_envs"] = {k: s.get("env") for k, s in per_model.items()}
    missing = sorted(set(suite.DENSE_MODELS) - set(per_model))
    if missing:
        out["meta"]["missing_models"] = missing
        print(f"note: 미포함 인코더 {missing} — robustness 주장은 포함된 "
              f"{len(per_model)}개 모델 범위로 한정해 서술할 것")
    suite.write_outputs(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
