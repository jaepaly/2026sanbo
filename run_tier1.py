#!/usr/bin/env python3
"""Run both MiniLM-only experiments with one encoder and bundle the result.

PAPER section 7 limitation 6 says the symmetric ablation (4.6) and the
disclosure frontier (4.5) were run on a single encoder, so their generalisation
across models is unverified -- and 4.5 carries the operating recommendation. This
closes that by running both on a second and third encoder.

One command per person, one file back:

    python run_tier1.py bge-m3
    -> output/tier1/tier1_bge-m3.json

Then verify and send it:

    python validate_tier1.py output/tier1/tier1_bge-m3.json

Both experiments are re-run rather than reusing cached embeddings because the
ablation perturbs the queries and the frontier uses a different index mode; there
is nothing shared to cache. BM25 does not use the encoder at all, so its rows must
come out identical for every person -- that is what validate_tier1 checks, and it
is why a returned file can be trusted without trusting the machine it came from.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output" / "tier1"

MODELS = {
    "MiniLM": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "e5-base": "intfloat/multilingual-e5-base",
    "bge-m3": "BAAI/bge-m3",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model_key", choices=sorted(MODELS))
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    # 두 실험 모듈은 import 시점에 SANBO_MODEL_KEY 를 읽어 모델과 출력 경로를 정한다.
    os.environ["SANBO_MODEL_KEY"] = args.model_key
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    print(f"모델: {args.model_key} = {MODELS[args.model_key]}")
    print("두 실험을 차례로 돌립니다. 중간에 끊어도 안전합니다(부분 결과를 쓰지 않음).\n")

    import experiment_symmetric_ablation as abl
    import experiment_disclosure_frontier as front

    if abl.MODEL_KEY != args.model_key or front.MODEL_KEY != args.model_key:
        print(f"오류: 모듈이 다른 모델 키를 잡았습니다 "
              f"(ablation={abl.MODEL_KEY}, frontier={front.MODEL_KEY})", file=sys.stderr)
        return 2

    print("[1/2] 대칭 ablation ...", flush=True)
    abl.main()
    print("\n[2/2] disclosure frontier ...", flush=True)
    front.main()

    bundle = {
        "tier1_format": 1,
        "model_key": args.model_key,
        "model_name": MODELS[args.model_key],
        "symmetric_ablation": json.loads(abl.JSON_PATH.read_text(encoding="utf-8")),
        "disclosure_frontier": json.loads(front.JSON_PATH.read_text(encoding="utf-8")),
        "source_files": [abl.JSON_PATH.name, front.JSON_PATH.name],
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    path = args.out_dir / f"tier1_{args.model_key}.json"
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nwrote {path}")
    print(f"\n다음: python validate_tier1.py {path.relative_to(ROOT)}")
    print("검증이 '모든 검증 통과'로 끝나면 이 파일 하나만 보내면 됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
