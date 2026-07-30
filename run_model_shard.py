#!/usr/bin/env python3
"""Run ONE dense encoder and write a shard a teammate can hand back.

Encoding 1,797 documents x 3 index modes with bge-m3 takes about an hour on a
CPU and under two minutes on any CUDA GPU, so it is the one part of this study
worth handing to whoever has the better machine. Nothing here requires judgement:
the seed is fixed, ranking is deterministic, and `validate_shard.py` verifies a
returned shard in one command.

    python run_model_shard.py bge-m3
    -> output/shards/shard_bge-m3.json

Send that one file back. The team lead runs `merge_shards.py`.

BM25 does not depend on the encoder, so every shard must contain byte-identical
BM25 hit vectors. `validate_shard.py` checks exactly that, which is why a shard
computed on a different machine cannot silently disagree about the corpus, the
query set, or the ranking rule.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import experiment_validated_suite as suite

SHARD_DIR = suite.OUT_DIR / "shards"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model_key", choices=sorted(suite.DENSE_MODELS),
                    help="which encoder to run")
    ap.add_argument("--out-dir", type=Path, default=SHARD_DIR)
    args = ap.parse_args()

    corpus = json.loads(suite.CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(suite.QUERIES_PATH.read_text(encoding="utf-8"))["queries"]

    print(f"corpus {len(corpus)} entries / queries {len(queries)}")
    print(f"model  {args.model_key} = {suite.DENSE_MODELS[args.model_key]}")
    print("index modes:", ", ".join(suite.INDEX_MODES))
    print("encoding (this is the slow part) ...", flush=True)

    shard = suite.run_model(args.model_key, corpus, queries)
    shard["shard_format"] = 1
    shard["index_modes"] = suite.INDEX_MODES
    shard["alphas"] = suite.ALPHAS
    shard["seed"] = suite.SEED

    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"shard_{args.model_key}.json"
    path.write_text(json.dumps(shard, ensure_ascii=False, indent=2), encoding="utf-8")

    bm25 = shard["hits"]["minimal_text"]["BM25"]
    hyb = shard["hits"]["minimal_text"][suite.alpha_name(suite.PRIMARY_ALPHA)]
    print(f"\nwrote {path}")
    print(f"sanity: BM25 R@10 {sum(bm25)}/{len(bm25)}, "
          f"hybrid R@10 {sum(hyb)}/{len(hyb)} (minimal_text)")
    print(f"revision: {shard['revision']}")
    print(f"\n다음: python validate_shard.py {path}  로 검증한 뒤 이 파일 하나만 보내면 됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
