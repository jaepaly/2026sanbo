#!/usr/bin/env python3
"""제3자 원본 자료 취득·검증 스크립트 (재배포 대신 재취득).

목적
----
이 저장소는 지금까지 제3자 저작물(외국 정부·국제기구 발간물, 정부 포털 HTML)을
`data/` 아래에 **원본 그대로 재배포**하고 있었고, 그 취득 경로가 코드로 남아 있지
않았다. 이 스크립트는 두 문제를 함께 해소한다.

  1) 재배포 대신 **재취득**: 저장소에서 원본 파일을 제거해도 이 스크립트로
     동일 바이트를 다시 받아올 수 있다(SHA-256으로 확인).
  2) **취득 경로 코드화**: 어떤 URL에서 무엇을 받아 어떤 해시가 나와야 하는지를
     실행 가능한 형태로 고정한다.

법적 근거·재배포 가능성 판단은 `data/SOURCES.md`에 정리했다. 이 스크립트의
`SOURCES` 표는 그 문서와 같은 사실을 기계가 읽을 수 있게 옮긴 것이다.

사용법
------
    python fetch_sources.py verify              # 로컬 파일 SHA-256 검증 (네트워크 불필요)
    python fetch_sources.py check-remote        # URL 도달성 + 원격 SHA-256 확인
    python fetch_sources.py fetch --dest-dir X  # 원본 재취득 (기본은 덮어쓰지 않음)
    python fetch_sources.py list                # 출처 표 출력

네트워크가 막힌 환경에서도 무엇이 왜 실패했는지 항목별로 보고하고 0이 아닌
종료 코드를 돌려준다(조용히 성공한 척하지 않는다).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 무작위성을 쓰지 않지만 산출물 감사를 위해 seed를 명시적으로 기록한다.
SEED = 20260730

USER_AGENT = "Mozilla/5.0 (compatible; sanbo-export-control-research/1.0)"

# 접근 확인 일자 (이 표의 URL/해시를 실제로 확인한 날짜)
ACCESS_DATE = "2026-07-30"


# ---------------------------------------------------------------------------
# 출처 표
# ---------------------------------------------------------------------------
# fetchable=False 인 항목은 자동 재취득이 불가능하다(JS 렌더링 셸, 정확한 URL 미확인 등).
# removal_target=True 인 항목은 저장소에서 제거해야 하는 제3자 저작물이다.
#   * 실제 삭제와 git 히스토리 정리는 팀장이 결정한다. 이 스크립트는 삭제하지 않는다.

SOURCES: list[dict] = [
    {
        "id": "wassenaar_2025_corr_pdf",
        "local": "data/wassenaar_2025.pdf",
        "url": (
            "https://www.wassenaar.org/app/uploads/2026/01/"
            "List-of-Dual-Use-Goods-and-Technologies-and-ML-2025-Corr.pdf"
        ),
        "sha256": "1a92a954dc51211f6f39a8780525248d0338bc116a23f80164e2aa6541be43fb",
        "bytes": 1366353,
        "fetchable": True,
        "removal_target": True,
        "rights_holder": "Wassenaar Arrangement Secretariat",
        "license_basis": "확인 필요 (사무국 발간물, 명시적 재배포 허가 문구 미확인)",
        "redistributable": "no",
        "corpus_entries": 585,
        "note": (
            "판본은 '2025 Corr.'(2026-01-15 생성, 243쪽). "
            "build_corpus_clean.py의 SOURCE_META에 적힌 URL(/2025/12/...-ML-2025.pdf)은 "
            "정정 전 '2025' 판(2025-12-05 생성, 242쪽, sha256 2a6b2af7...)을 가리키므로 "
            "로컬 파일과 다르다. 코퍼스를 만든 실제 원본은 이 항목의 URL이다."
        ),
        "sha256_verified_remote": True,
    },
    {
        "id": "india_scomet_2024_pdf",
        "local": "data/india_scomet_2024_official.pdf",
        "url": (
            "https://content.dgft.gov.in/Website/"
            "UPDATED%20SCOMET%20List%202024%20as%20on%2002.09.2024.pdf"
        ),
        "sha256": "4e26322b3f05bea962b7451e66db967dc1ad8ed8816254e663dde80cc410681f",
        "bytes": 3812663,
        "fetchable": True,
        "removal_target": True,
        "rights_holder": "Directorate General of Foreign Trade (DGFT), Government of India",
        "license_basis": "확인 필요 (인도 정부 저작물, GODL-India 적용 여부 미확인)",
        "redistributable": "no",
        "corpus_entries": 575,
        "note": "원격 SHA-256이 로컬과 정확히 일치한다(2026-07-30 확인). 재취득으로 완전 대체 가능.",
        "sha256_verified_remote": True,
    },
    {
        "id": "ecfr_supp1_json",
        "local": "data/corpus/ecfr_supp1.json",
        "url": None,  # fetch_ecfr.py가 eCFR 공식 API로 취득·파싱한다
        "sha256": "e3df05c369a9431a5b9755f75e1528a9b65cc67254f50d5992f5c182560f29f9",
        "bytes": 175321,
        "fetchable": False,
        "delegate": "fetch_ecfr.py",
        "fetch_hint": "`python fetch_ecfr.py --text-field full` 로 재생성",
        "removal_target": False,
        "rights_holder": "U.S. Government (Bureau of Industry and Security / GPO)",
        "license_basis": "17 U.S.C. §105 (연방정부 저작물, 저작권 보호 대상 아님)",
        "redistributable": "yes",
        "corpus_entries": 637,
        "note": (
            "이 파일은 원본이 아니라 파싱 산출물이다. 재현은 "
            "`python fetch_ecfr.py --text-field full` 로 한다. "
            "주의: data/corpus/corpus_quality_report.json에 기록된 해시는 "
            "c15d80cd131e7f0e0ee23fc8af3f729e5683b17b908c3bd927a7392aa7c43f04 이지만 "
            "현재 파일(및 HEAD 커밋본)의 해시는 e3df05c3... 이다. 즉 품질보고서가 "
            "입력 파일에 대해 stale 하다 -- 코퍼스 담당자 확인 필요."
        ),
        "sha256_verified_remote": False,
    },
    {
        "id": "law_korea_html",
        "local": "data/law_korea.html",
        "url": "https://www.law.go.kr/행정규칙/전략물자수출입고시",
        "sha256": "ffbaac38e6f1d77ea60967b29c1740e945ed4613151c14b4d9d6b1e95418e717",
        "bytes": 77374,
        "fetchable": False,
        "removal_target": True,
        "rights_holder": "국가법령정보센터 (법제처) / 고시 본문은 산업통상부",
        "license_basis": (
            "고시 본문은 저작권법 제7조 제1호(법령)·제2호(고시)로 보호 대상 제외. "
            "다만 국가법령정보센터 **페이지 HTML 자체**(레이아웃·스크립트)는 제7조 적용 대상이 아니다."
        ),
        "redistributable": "no",
        "corpus_entries": 0,
        "note": (
            "파일명과 달리 내용은 '전략물자수출입고시' 페이지의 JS 셸이다. "
            "텍스트 추출 결과 조문 0건('전략물자' 3회, '수출허가' 0회, '판정' 0회). "
            "메타: 산업통상부고시 제2025-37호, 시행 2025-12-31. "
            "코드에서 참조하는 곳이 없다(grep 결과 0건). "
            "JS 렌더링이므로 URL 취득만으로는 동일 바이트 재현 불가 -- 자동 재취득 미지원. "
            "정확한 스크레이프 URL(admRulSeq 파라미터) 확인 필요."
        ),
        "fetch_hint": "JS 렌더링 셸이라 URL 취득만으로 동일 바이트 재현 불가 (data/SOURCES.md 참조)",
        "sha256_verified_remote": False,
    },
    {
        "id": "yestrade_post_html",
        "local": "data/yestrade_post.html",
        "url": "https://www.yestrade.go.kr/",
        "sha256": "fad6fade8971cc5d0b52de0349d16ab2e0d58d2e6d406d3bdb71de3077d16390",
        "bytes": 21700,
        "fetchable": False,
        "removal_target": True,
        "rights_holder": "MINISTRY OF TRADE, INDUSTRY (YesTrade 포털)",
        "license_basis": "확인 필요 (footer에 'Copyright (C) MINISTRY OF TRADE, INDUSTRY. All Rights Reserved.' 명시)",
        "redistributable": "no",
        "corpus_entries": 0,
        "note": (
            "제목 '동향자료 > 상세보기 | YESTRADE'. 코드에서 참조하는 곳이 없다(grep 0건). "
            "정확한 게시글 URL 확인 필요 -- 파일 내부에 canonical/og:url이 없다."
        ),
        "fetch_hint": "정확한 게시글 URL 미확인 (data/SOURCES.md 참조)",
        "sha256_verified_remote": False,
    },
    {
        "id": "wassenaar_2025_zip",
        "local": "data/wassenaar_2025.zip",
        "url": None,
        "sha256": "6f06d4655f79da5feac66e1edee1a6a4b6d2e568314fd44a68c27f67efb6331b",
        "bytes": 59256,
        "fetchable": False,
        "removal_target": True,
        "rights_holder": "Wassenaar Arrangement Secretariat (웹사이트 오류 페이지)",
        "license_basis": "해당 없음 (통제목록 내용이 전혀 없음)",
        "redistributable": "no",
        "corpus_entries": 0,
        "note": (
            "확장자 위장. 첫 바이트가 '\\n<!doctype html>'이고 <title>은 "
            "'Page not found - The Wassenaar Arrangement'. 즉 zip이 아니라 404 오류 페이지다. "
            "통제목록 데이터가 0건이므로 코퍼스에 기여한 바 없고 코드 참조도 0건. "
            "재취득 대상이 아니라 **단순 삭제 대상**."
        ),
        "fetch_hint": "404 오류 페이지 -- 재취득 대상 아님, 삭제 대상",
        "sha256_verified_remote": False,
    },
]

# 참고용: build_corpus_clean.py가 기록한 URL이 실제로 가리키는 다른 파일
KNOWN_URL_MISMATCH = {
    "recorded_in": "build_corpus_clean.py SOURCE_META['wassenaar_2025']['source_url']",
    "recorded_url": (
        "https://www.wassenaar.org/app/uploads/2025/12/"
        "List-of-Dual-Use-Goods-and-Technologies-and-ML-2025.pdf"
    ),
    "resolves_to_sha256": "2a6b2af7299523e6940fcda3dfa80263cdf58f0ac093d312f78c63db6ec1200f",
    "resolves_to_bytes": 1361602,
    "resolves_to_edition": "2025 (정정 전, 242쪽, CreationDate 2025-12-05)",
    "local_file_edition": "2025 Corr. (243쪽, CreationDate 2026-01-15)",
    "verdict": "URL과 로컬 파일이 다른 판본이다. SOURCE_META의 URL을 정정해야 한다(담당: 코퍼스 소유자).",
}


# ---------------------------------------------------------------------------
# 도우미
# ---------------------------------------------------------------------------


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def http_get(url: str, timeout: int = 300) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _collect_env_meta(light: bool) -> dict:
    """환경 기록. light=True면 무거운 ML 라이브러리 import를 피한다."""
    import platform
    base = {"python": platform.python_version(), "platform": platform.platform()}
    if light:
        try:
            import numpy as _np
            base["numpy"] = _np.__version__
        except Exception:
            base["numpy"] = None
        base["torch"] = "not_probed (--light-env)"
        base["sentence_transformers"] = "not_probed (--light-env)"
        return base
    try:
        from retrieval_core import env_meta
        return env_meta()
    except Exception:
        base["note"] = "retrieval_core.env_meta import 실패 - 축약 기록"
        return base


def _resolve(p: str | Path) -> Path:
    q = Path(p)
    return q if q.is_absolute() else (ROOT / q)


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------


def cmd_list() -> tuple[int, list[dict]]:
    rows = []
    for s in SOURCES:
        rows.append(
            {
                "id": s["id"],
                "local": s["local"],
                "url": s["url"],
                "fetchable": s["fetchable"],
                "removal_target": s["removal_target"],
                "redistributable": s["redistributable"],
                "corpus_entries": s["corpus_entries"],
                "license_basis": s["license_basis"],
            }
        )
        print(
            f"{s['id']:<28} entries={s['corpus_entries']:<5} "
            f"fetch={'Y' if s['fetchable'] else 'N'} "
            f"remove={'Y' if s['removal_target'] else 'N'} "
            f"redist={s['redistributable']:<4} {s['local']}"
        )
    return 0, rows


def cmd_verify() -> tuple[int, list[dict]]:
    """로컬 파일의 SHA-256을 표와 비교한다. 네트워크 불필요."""
    results = []
    bad = 0
    for s in SOURCES:
        path = _resolve(s["local"])
        if not path.exists():
            status = "missing"
            actual = None
            size = None
        else:
            actual = sha256_file(path)
            size = path.stat().st_size
            status = "ok" if actual == s["sha256"] else "sha256_mismatch"
        if status != "ok":
            bad += 1
        results.append(
            {
                "id": s["id"],
                "local": s["local"],
                "status": status,
                "expected_sha256": s["sha256"],
                "actual_sha256": actual,
                "expected_bytes": s["bytes"],
                "actual_bytes": size,
            }
        )
        mark = "ok  " if status == "ok" else "FAIL"
        print(f"[{mark}] {s['id']:<28} {status:<16} {s['local']}")
    print(f"verify: {len(SOURCES) - bad}/{len(SOURCES)} ok")
    return (0 if bad == 0 else 1), results


def cmd_check_remote(timeout: int = 300) -> tuple[int, list[dict]]:
    """URL 도달성과 원격 SHA-256을 확인한다. 네트워크 필요."""
    results = []
    bad = 0
    for s in SOURCES:
        if not s["fetchable"] or not s["url"]:
            hint = s.get("fetch_hint") or "자동 취득 경로 미확인"
            results.append({"id": s["id"], "status": "not_fetchable", "reason": hint})
            print(f"[skip] {s['id']:<28} 자동 취득 미지원 -- {hint}")
            continue
        try:
            blob = http_get(s["url"], timeout=timeout)
        except urllib.error.HTTPError as exc:
            bad += 1
            results.append({"id": s["id"], "status": "http_error", "code": exc.code, "reason": str(exc.reason)})
            print(f"[FAIL] {s['id']:<28} HTTP {exc.code} {exc.reason}")
            continue
        except Exception as exc:
            bad += 1
            results.append({"id": s["id"], "status": "network_unreachable", "reason": f"{type(exc).__name__}: {exc}"})
            print(f"[FAIL] {s['id']:<28} 네트워크 실패 {type(exc).__name__}: {exc}")
            continue
        digest = hashlib.sha256(blob).hexdigest()
        match = digest == s["sha256"]
        if not match:
            bad += 1
        results.append(
            {
                "id": s["id"],
                "status": "sha256_match" if match else "sha256_drift",
                "remote_sha256": digest,
                "remote_bytes": len(blob),
                "expected_sha256": s["sha256"],
            }
        )
        print(f"[{'ok  ' if match else 'DRIFT'}] {s['id']:<28} remote={digest[:16]}... bytes={len(blob)}")
    return (0 if bad == 0 else 2), results


def cmd_fetch(dest_dir: Path | None, force: bool, timeout: int = 300) -> tuple[int, list[dict]]:
    """원본을 URL에서 다시 받아온다.

    dest_dir가 None이면 표의 `local` 경로(저장소 안)에 쓴다. 기존 파일이 있으면
    --force 없이는 건드리지 않는다.
    """
    results = []
    bad = 0
    for s in SOURCES:
        if not s["fetchable"] or not s["url"]:
            hint = s.get("fetch_hint") or "자동 취득 경로 미확인 (data/SOURCES.md 참조)"
            results.append({"id": s["id"], "status": "skipped_not_fetchable", "reason": hint})
            print(f"[skip] {s['id']:<28} 자동 취득 미지원 -- {hint}")
            continue

        if dest_dir is None:
            out = _resolve(s["local"])
        else:
            out = _resolve(dest_dir) / Path(s["local"]).name

        if out.exists() and not force:
            results.append({"id": s["id"], "status": "exists_skipped", "path": str(out)})
            print(f"[skip] {s['id']:<28} 이미 존재 (덮어쓰려면 --force): {out}")
            continue

        try:
            blob = http_get(s["url"], timeout=timeout)
        except Exception as exc:
            bad += 1
            results.append({"id": s["id"], "status": "fetch_failed", "reason": f"{type(exc).__name__}: {exc}"})
            print(f"[FAIL] {s['id']:<28} 취득 실패 {type(exc).__name__}: {exc}")
            continue

        digest = hashlib.sha256(blob).hexdigest()
        if digest != s["sha256"]:
            bad += 1
            results.append(
                {
                    "id": s["id"],
                    "status": "sha256_drift_not_written",
                    "remote_sha256": digest,
                    "expected_sha256": s["sha256"],
                    "remote_bytes": len(blob),
                }
            )
            print(f"[FAIL] {s['id']:<28} 해시 불일치 -> 쓰지 않음. remote={digest}")
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
        results.append({"id": s["id"], "status": "written", "path": str(out), "sha256": digest, "bytes": len(blob)})
        print(f"[ok  ] {s['id']:<28} 저장 {out} ({len(blob)}B)")
    return (0 if bad == 0 else 3), results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("verify", "check-remote", "fetch", "list"), nargs="?", default="verify")
    p.add_argument("--dest-dir", default=None, help="fetch: 저장소 대신 이 디렉터리에 받는다")
    p.add_argument("--force", action="store_true", help="fetch: 기존 파일 덮어쓰기 허용")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--report", default="output/source_manifest.json", help="감사용 JSON 보고서 경로")
    p.add_argument("--no-report", action="store_true", help="보고서를 쓰지 않는다")
    p.add_argument("--light-env", action="store_true",
                   help="env_meta 기록 시 torch/sentence-transformers import를 건너뛴다")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    t0 = time.time()

    if args.command == "list":
        code, results = cmd_list()
    elif args.command == "verify":
        code, results = cmd_verify()
    elif args.command == "check-remote":
        code, results = cmd_check_remote(timeout=args.timeout)
    else:
        dest = Path(args.dest_dir) if args.dest_dir else None
        code, results = cmd_fetch(dest, args.force, timeout=args.timeout)

    if not args.no_report:
        meta = _collect_env_meta(args.light_env)
        report = {
            "generated_by": "fetch_sources.py",
            "command": args.command,
            "seed": SEED,
            "randomness_used": "none (deterministic)",
            "env_meta": meta,
            "access_date": ACCESS_DATE,
            "exit_code": code,
            "results": results,
            "sources": SOURCES,
            "known_url_mismatch": KNOWN_URL_MISMATCH,
            "removal_targets": [s["id"] for s in SOURCES if s["removal_target"]],
            "elapsed_sec": round(time.time() - t0, 2),
            "notes": [
                "이 스크립트는 어떤 파일도 삭제하지 않는다. 제거 결정과 git 히스토리 정리는 팀장 사안이다.",
                "법적 판단이 '확인 필요'로 남은 항목은 data/SOURCES.md의 확인 경로를 따르라.",
            ],
        }
        rp = _resolve(args.report)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] 보고서 저장: {rp}")

    if code != 0:
        print(f"[exit {code}] 위 실패 항목을 확인하라.", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
