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

SHARD_DIR = suite.OUT_DIR / "shards"


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

    # BM25 is encoder-independent: every shard must agree exactly.
    keys = list(per_model)
    ref_key = keys[0]
    mismatches = []
    for imode in suite.INDEX_MODES:
        ref = per_model[ref_key]["hits"][imode]["BM25"]
        for k in keys[1:]:
            other = per_model[k]["hits"][imode]["BM25"]
            if other != ref:
                n = sum(1 for x, y in zip(other, ref) if x != y)
                mismatches.append(f"{imode}: {k} vs {ref_key} — {n}개 질의 불일치")
    if mismatches:
        print("\nBM25 벡터 불일치 (인코더와 무관하므로 같아야 함):", file=sys.stderr)
        for m in mismatches:
            print("  -", m, file=sys.stderr)
        if not args.allow_bm25_mismatch:
            print("\n병합을 중단합니다. 샤드가 서로 다른 코퍼스/질의셋/랭킹 규칙에서 나왔습니다.",
                  file=sys.stderr)
            return 1
        print("\n--allow-bm25-mismatch 지정됨 — 강행합니다.", file=sys.stderr)

    corpus = json.loads(suite.CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(suite.QUERIES_PATH.read_text(encoding="utf-8"))["queries"]
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
