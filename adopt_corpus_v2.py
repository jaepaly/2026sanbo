#!/usr/bin/env python3
"""Swap the active corpus to combined_v2.json, reversibly and auditably.

Telling teammates to `cp combined_v2.json combined.json` destroys the version
every published number was computed from, with no record of when or by whom. This
does the same swap but keeps v1 recoverable, records SHA-256 of both sides, and
refuses to run twice by accident.

    python adopt_corpus_v2.py --check     # what would change, touch nothing
    python adopt_corpus_v2.py             # perform the swap
    python adopt_corpus_v2.py --revert    # go back to v1

After swapping you MUST regenerate. See docs/TEAM_WORKFLOW.md "코퍼스 v2 채택 매뉴얼".
The synthetic query set is derived from corpus text, so it is invalid until
`generate_queries.py` re-runs; `verify_claims.py` will fail loudly until the
whole chain is redone, which is the intended behaviour.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "data" / "corpus"
ACTIVE = CORPUS_DIR / "combined.json"
V2 = CORPUS_DIR / "combined_v2.json"
BACKUP = CORPUS_DIR / "combined_v1_superseded.json"
MANIFEST = CORPUS_DIR / "corpus_version_manifest.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def describe(path: Path) -> dict:
    entries = json.loads(path.read_text(encoding="utf-8"))
    by_src: dict[str, dict] = {}
    for e in entries:
        s = by_src.setdefault(e["source"], {"n": 0, "chars": 0})
        s["n"] += 1
        s["chars"] += len(e.get("text", ""))
    return {"path": path.name, "sha256": sha256(path), "total": len(entries),
            "by_source": by_src}


def current_version() -> str:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8")).get("active", "v1")
    return "v1"


def show(a: dict, b: dict) -> None:
    print(f"\n{'소스':<22}{'현재':>10}{'교체후':>10}{'문자 현재':>14}{'문자 교체후':>14}")
    for s in sorted(set(a["by_source"]) | set(b["by_source"])):
        x = a["by_source"].get(s, {"n": 0, "chars": 0})
        y = b["by_source"].get(s, {"n": 0, "chars": 0})
        print(f"{s:<22}{x['n']:>10}{y['n']:>10}{x['chars']:>14,}{y['chars']:>14,}")
    print(f"{'합계':<22}{a['total']:>10}{b['total']:>10}")
    print(f"\nsha256 현재  {a['sha256'][:16]}...")
    print(f"sha256 교체후 {b['sha256'][:16]}...")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="변경 내용만 출력, 파일 미변경")
    g.add_argument("--revert", action="store_true", help="v1으로 되돌린다")
    args = ap.parse_args()

    active = current_version()

    if args.revert:
        if active != "v2":
            print(f"현재 활성 코퍼스가 {active} 이므로 되돌릴 것이 없습니다.", file=sys.stderr)
            return 1
        if not BACKUP.exists():
            print(f"오류: 백업 {BACKUP.name} 이 없습니다. 되돌릴 수 없습니다.", file=sys.stderr)
            return 2
        shutil.copy2(BACKUP, ACTIVE)
        MANIFEST.write_text(json.dumps(
            {"active": "v1", "note": "adopt_corpus_v2.py --revert 로 복원",
             "v1": describe(ACTIVE)}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"v1으로 복원했습니다. 이제 재생성 체인을 다시 돌려야 합니다"
              f"(docs/TEAM_WORKFLOW.md '코퍼스 v2 채택 매뉴얼' 참조).")
        return 0

    if not V2.exists():
        print(f"오류: {V2.name} 이 없습니다. 먼저 실행하세요:\n"
              f"  python build_corpus_clean.py --v2", file=sys.stderr)
        return 2

    cur = describe(ACTIVE)
    new = describe(V2)

    if active == "v2":
        print("이미 v2가 활성 상태입니다.")
        if cur["sha256"] != new["sha256"]:
            print("경고: 활성 코퍼스와 combined_v2.json 의 해시가 다릅니다. "
                  "누군가 활성 파일을 직접 수정했을 수 있습니다.", file=sys.stderr)
            show(cur, new)
            return 1
        return 0

    show(cur, new)

    if args.check:
        print("\n--check 모드: 파일을 변경하지 않았습니다.")
        print("\n교체 후 반드시 재생성해야 하는 것:")
        print("  1) 합성 질의셋 — 코퍼스 본문에서 파생되므로 교체 즉시 무효")
        print("  2) 합성셋 실험 (주장 1) 및 ablation")
        print("  3) 검증셋 3모델 통합 실행 — recall 은 불변이나 노출량@10 이 크게 이동")
        print("  4) 통계·그림·claim registry")
        return 0

    if BACKUP.exists() and sha256(BACKUP) != cur["sha256"]:
        print(f"오류: 백업 {BACKUP.name} 이 이미 있고 현재 활성 코퍼스와 다릅니다. "
              f"덮어쓰지 않습니다. 수동으로 확인하세요.", file=sys.stderr)
        return 2

    shutil.copy2(ACTIVE, BACKUP)
    shutil.copy2(V2, ACTIVE)
    MANIFEST.write_text(json.dumps({
        "active": "v2",
        "note": "adopt_corpus_v2.py 로 교체. 되돌리려면 --revert.",
        "v1_superseded": {**cur, "path": BACKUP.name},
        "v2_active": new,
        "regeneration_required": [
            "python generate_queries.py",
            "python run_experiments.py",
            "python experiment_paraphrase_gap.py",
            "python run_model_shard.py <MiniLM|e5-base|bge-m3>  (모델별, 분담 가능)",
            "python merge_shards.py",
            "python report_exposure_decomposition.py",
            "python experiment_stats.py",
            "python make_figures.py",
            "python verify_claims.py",
        ],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n교체 완료. v1은 {BACKUP.name} 으로 보존했습니다.")
    print(f"기록: {MANIFEST.name}")
    print("\n중요: 지금 저장소의 산출물은 전부 v1 기준이라 코퍼스와 불일치합니다.")
    print("docs/TEAM_WORKFLOW.md '코퍼스 v2 채택 매뉴얼'의 재생성 체인을 반드시 완주하세요.")
    print("verify_claims.py 가 통과할 때까지는 논문에 수치를 옮기지 마십시오.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
