#!/usr/bin/env python3
"""저장소 전역 불변식 검사 (통합 검증자).

개별 담당자의 테스트는 각자 소유한 파일만 본다. 이 파일은 **저장소 전체**를 훑어
담당 경계에서 새는 결함을 잡는다.

검사 항목
1. 실행 코드에 `np.argsort(-...)` 가 남아 있지 않다.
   - 주석/독스트링의 언급은 정정 이력 기록이므로 허용한다. AST 로 실제 호출만 본다.
   - 이 패턴은 동점의 순서를 정렬 구현에 맡기므로, BM25 점수 벡터가 전부 0인 질의
     (검증셋 71개 중 44개)에서 '상위 10건'이 코퍼스 앞머리 10행이 된다.
2. 모든 .py 가 컴파일된다(문법 오류 없음).
3. tests/ 아래 모든 테스트 파일이 실제로 존재하고 컴파일된다.
4. 저장소가 만든 산출물 JSON 중 '정정 후'로 표시된 것들은 env + seed 를 기록한다.

실행: PYTHONIOENCODING=utf-8 python tests/test_repo_invariants.py
"""

from __future__ import annotations

import ast
import json
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        FAILURES.append(f"{name}: {detail}")


def py_files() -> list[Path]:
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in p.parts or ".venv" in p.parts:
            continue
        out.append(p)
    return out


class ArgsortNegVisitor(ast.NodeVisitor):
    """`argsort(-X)` 형태의 실제 호출만 수집한다."""

    def __init__(self) -> None:
        self.hits: list[int] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else "")
        if name == "argsort" and node.args:
            first = node.args[0]
            if isinstance(first, ast.UnaryOp) and isinstance(first.op, ast.USub):
                self.hits.append(node.lineno)
        self.generic_visit(node)


def test_no_argsort_neg() -> None:
    print("[1] 실행 코드에 np.argsort(-...) 호출이 없다")
    offenders: list[str] = []
    for p in py_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            offenders.append(f"{p.relative_to(ROOT)} (파싱 실패: {exc})")
            continue
        v = ArgsortNegVisitor()
        v.visit(tree)
        for line in v.hits:
            offenders.append(f"{p.relative_to(ROOT)}:{line}")
    check("argsort(-X) 호출 0건", not offenders, "; ".join(offenders))


def test_all_compile() -> None:
    print("[2] 모든 .py 가 컴파일된다")
    bad: list[str] = []
    for p in py_files():
        try:
            py_compile.compile(str(p), doraise=True, quiet=1)
        except py_compile.PyCompileError as exc:
            bad.append(f"{p.relative_to(ROOT)}: {exc.msg}")
    check(f"{len(py_files())}개 파일 컴파일", not bad, "; ".join(bad))


EXPECTED_TESTS = [
    "test_retrieval_core.py",
    "test_corpus.py",
    "test_label_audit.py",
    "test_disclosure_ladder.py",
    "test_selfreference.py",
    "test_fetch_sources.py",
    "test_m9_m14_fixes.py",
]


def test_test_files_present() -> None:
    print("[3] 담당자별 테스트 파일이 모두 존재한다")
    for name in EXPECTED_TESTS:
        check(f"tests/{name} 존재", (ROOT / "tests" / name).is_file())


# 정정 작업으로 새로 만들었거나 재생성한 산출물. 여기에 있는 파일은 env + seed 를
# 반드시 기록해야 한다(규칙 5). 재실행되지 않은 정정 전 산출물은 의도적으로 뺐다.
CORRECTED_ARTIFACTS = [
    "output/disclosure_frontier.json",
    "output/selfreference_audit.json",
    "output/symmetric_ablation.json",
    "output/stats_summary.json",
    "output/paraphrase_gap.json",
    "output/retriever_compare.json",
    "output/external_retriever.json",
    "output/experiment_logs.json",
    "output/exposure_decomposition.json",
    "output/source_manifest.json",
    "data/corpus/corpus_quality_report_v2.json",
    "data/disclosure_ladder.json",
    "data/equivalent_labels.json",
]


def _has_key(obj: object, key: str, depth: int = 0) -> bool:
    if depth > 6:
        return False
    if isinstance(obj, dict):
        if key in obj:
            return True
        return any(_has_key(v, key, depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_key(v, key, depth + 1) for v in obj[:50])
    return False


def test_env_and_seed_recorded() -> None:
    print("[4] 정정 후 산출물이 env + seed 를 기록한다")
    for rel in CORRECTED_ARTIFACTS:
        p = ROOT / rel
        if not p.is_file():
            check(f"{rel} 존재", False, "파일 없음")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        has_env = _has_key(d, "env") or _has_key(d, "env_meta")
        has_seed = _has_key(d, "seed") or _has_key(d, "bootstrap_seed")
        check(f"{rel}: env+seed", has_env and has_seed,
              f"env={has_env} seed={has_seed}")


def main() -> int:
    test_no_argsort_neg()
    test_all_compile()
    test_test_files_present()
    test_env_and_seed_recorded()
    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("all repo-invariant checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
