#!/usr/bin/env python3
"""
Add realistic trade officer query templates (A-scenario: code given).
These reflect actual questions customs/trade officers ask when they already
know the ECCN code and need to verify details.
"""
import json, random, re
from pathlib import Path
from collections import Counter

random.seed(42)
ROOT = Path(__file__).resolve().parent
corpus_path = ROOT / "data" / "corpus" / "combined.json"
queries_path = ROOT / "data" / "queries.json"

# Realistic trade officer query patterns (A-scenario: code is known)
REAL_TEMPLATES_EN = [
    # Short verification
    "Verify the correct classification for {code}.",
    "Confirm export control status for {code}.",
    "Check licensing requirements for {code}.",
    "Determine if {code} requires a license.",
    "What is the ECCN description for {code}?",
    # Parameter lookup
    "List the technical parameters for {code}.",
    "What are the unit/quantity thresholds in {code}?",
    "Find the controlled features in {code}.",
    # Requirement check
    "Explain the conditions that trigger licensing for {code}.",
    "What end-use restrictions apply to {code}?",
    "Review the controlled activities under {code}.",
    # Comparison/scope
    "How does {code} compare to similar categories?",
    "What items are explicitly excluded from {code}?",
    "What is the scope of 'technology' under {code}?",
    # Case-specific
    "Does this item fall under {code}?",
    "Determine applicable controls: {code}.",
    "Verify the correct ECCN: {code}.",
    "Check the classification decision for {code}.",
    "Confirm the scope of {code}.",
    "Review the export requirements for {code}.",
    # License exception
    "Are there applicable license exceptions for {code}?",
    "Check if {code} is eligible for license exception.",
    "What license exceptions may apply to {code}?",
]

REAL_TEMPLATES_KO = [
    # Short verification
    "{code}의 정확한 분류를 확인하세요.",
    "{code}의 수출통제 상태를 확인하세요.",
    "{code}의 허가 요건을 확인하세요.",
    "{code}에 허가가 필요한지 확인하세요.",
    "{code}의 ECCN 설명을 확인하세요.",
    # Parameter lookup
    "{code}의 기술적 사양을 확인하세요.",
    "{code}의 단위/수량 임계값을 확인하세요.",
    "{code}의 통제 대상 기능을 확인하세요.",
    # Requirement check
    "{code}에서 허가를 트리거하는 조건을 설명하세요.",
    "{code}에 적용되는 최종사용자 제한은?",
    "{code}의 통제 활동을 검토하세요.",
    # Comparison/scope
    "{code}와 유사 카테고리를 비교하세요.",
    "{code}에서 명시적으로 제외된 품목은?",
    "{code}의 기술 범위는 어디까지인가요?",
    # Case-specific
    "이 품목이 {code}에 해당하는지 확인하세요.",
    "적용 통제 결정: {code}.",
    "ECCN 분류 확인: {code}.",
    "{code}의 분류 결정을 검토하세요.",
    "{code}의 범위를 확인하세요.",
    "{code}의 수출 요건을 검토하세요.",
    # License exception
    "{code}에 적용 가능한 허가 예외가 있나요?",
    "{code}가 허가 예외 대상인지 확인하세요.",
    "{code}에 적용될 수 있는 허가 예외는?",
]


def extract_category_prefix(code: str):
    """Extract category prefix like '0A' or '2B'."""
    m = re.match(r'[A-Z]*([0-9][A-Z]{1})', code)
    if m:
        return m.group(1)
    return "controlled"

with corpus_path.open(encoding="utf-8") as f:
    data = json.load(f)

random.shuffle(data)
queries = []
for idx, entry in enumerate(data):
    lang = random.choice(["en", "ko"])
    prefix = extract_category_prefix(entry["code"])
    if lang == "ko":
        tpl = random.choice(REAL_TEMPLATES_KO)
    else:
        tpl = random.choice(REAL_TEMPLATES_EN)
    q = tpl.format(code=entry["code"])
    queries.append({
        "id": f"q{idx:04d}",
        "query": q,
        "answer_code": entry["code"],
        "source": entry.get("source", "unknown"),
        "base_term": prefix,
        "lang": lang,
    })

queries = queries[:500]
random.shuffle(queries)
n = len(queries)
train = queries[: int(n * 0.7)]
val = queries[int(n * 0.7) : int(n * 0.85)]
test = queries[int(n * 0.85) :]

payload = {"train": train, "val": val, "test": test, "total": n}
queries_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Generated {n} realistic trade-officer queries | train={len(train)} val={len(val)} test={len(test)}")
print("Source dist:", dict(Counter(q['source'] for q in queries)))
print("Lang dist:", dict(Counter(q['lang'] for q in queries)))
print('\nSample queries:')
for q in queries[:5]:
    print(f"  [{q['lang']}] {q['query'][:80]}")
    print(f"    answer={q['answer_code']}, source={q['source']}")
