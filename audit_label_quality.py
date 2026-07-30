#!/usr/bin/env python3
"""정답셋(ground-truth) 오염 감사 및 등가 라벨 교정 — M8.

검증셋 n=71의 라벨 품질에는 서로 독립적인 여섯 가지 결함이 있다. 이 스크립트는
그 여섯 가지를 **실측으로 재현**하고, 교정된 라벨 공간(등가 라벨 허용)에서
R@10 을 다시 계산한다.

감사 항목
---------
D1  eCFR 표제 스텁
    eCFR 항목 상당수가 "... as follows (see List of Items Controlled)." 라는
    표제만 갖고 있고 실제 기술 파라미터(직경·주파수·정확도 등)는 코퍼스에
    존재하지 않는다. 예: ext-015 는 "oscilloscope ... over 1 GHz" 를 묻지만
    정답 문서 ECCN-3A002 본문에는 oscilloscope 도 GHz 도 없다. 이런 질의는
    원리상 어떤 검색기로도 어휘적으로 맞출 수 없다.

D2  타 규제체계 쌍둥이
    코퍼스는 eCFR(637) + Wassenaar(585) + SCOMET(575) 이지만 채점은 eCFR
    exact code 일치다. Wassenaar/SCOMET 쌍둥이 문서는 원문이 사실상 같은데도
    전부 miss 로 집계된다.

D3  부정확한 2차 라벨
    hit 판정이 any-label 적중이므로, 질의와 무관한 2차 라벨이 붙어 있으면
    난이도가 인위적으로 낮아진다(ext-005, ext-023).

D4  질의-라벨 규제체계 모순
    ext-028 은 "군용입니다"라고 명시하는데 정답은 민군겸용 CCL 항목이다.

D5  코드 재사용
    '1질의 1항목' 원칙 위반. 같은 ECCN 이 두 질의의 정답으로 쓰였다.

D6  도달 불가 라벨 공간
    정답이 eCFR full code 로만 정의되어 코퍼스의 non-eCFR 항목은 원리상
    정답이 될 수 없다.

교정
----
`data/equivalent_labels.json` 은 각 정답 ECCN 의 Wassenaar/SCOMET 등가 코드를
담는다. 후보는 기계적으로 생성하지만(구조적 코드 대응 + 원문 Jaccard),
**파일에 들어간 모든 쌍은 사람이 양쪽 원문을 읽고 확인한 것만**이다.
확인하지 않은/등가가 아닌 후보는 REJECTED_CANDIDATES 에 이유와 함께 남긴다.

사용법
------
    python audit_label_quality.py audit        # D1~D6 실측 + 품목명 누락 경고 (모델 불필요)
    python audit_label_quality.py candidates   # 기계 후보 재생성(사람 검토용)
    python audit_label_quality.py emit         # data/equivalent_labels.json, *_v2.json 생성
    python audit_label_quality.py recall       # R@10_equiv before/after (MiniLM 1개 모델)
    python audit_label_quality.py all          # 위 전부 (recall 포함)

`recall` 은 SANBO 스모크 수준이다: 단일 인코더(MiniLM), index_mode=full_text,
alpha=0.5 — `experiment_validated_suite.py` 의 primary 설정과 동일하므로
before 값이 그 스크립트의 hybrid_0.5/full_text 값과 일치해야 한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_V1_PATH = DATA_DIR / "validated_queries_expanded.json"
QUERIES_V2_PATH = DATA_DIR / "validated_queries_expanded_v2.json"
EQUIV_PATH = DATA_DIR / "equivalent_labels.json"
SLICE_PATHS = [
    DATA_DIR / "external_consultation_queries_validated.json",
    DATA_DIR / "validated_queries_slice_yechan.json",
    DATA_DIR / "validated_queries_slice_seungwoo.json",
]

SEED = 20260626
PRIMARY_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
PRIMARY_ALPHA = 0.5          # validated_suite.py 의 primary alpha
PRIMARY_INDEX_MODE = "full_text"
TOP_K = 10

# eCFR 항목이 "표제 스텁"인지 판정하는 패턴. 표제 뒤에 실제 파라미터가 오지 않고
# 별도 문서인 "List of Items Controlled" 로 넘겨버리는 형태.
STUB_RE = re.compile(r"\(\s*see\s+(?:the\s+)?list\s+of\s+items\s+cont(?:r)?ol", re.I)
SHORT_TEXT_CHARS = 150       # 사실상 표제 한 줄인 길이 상한

# 정답 코드 ↔ 국제 레짐 코드의 구조적 대응 규칙.
#   Wassenaar : ECCN {cat}{type}0{nn}  ->  "{cat}.{type}.{n}"
#   SCOMET    : ECCN {cat}{type}0{nn}  ->  "8{type}{cat}{nn}"
# 규칙은 Wassenaar 유래 core list(세 번째 자리가 0)에만 유효하다. 미국 단독
# 통제(9xx)·MTCR(1xx)·NSG(2xx) 계열에 적용하면 서로 다른 ECCN 이 같은 SCOMET
# 코드로 붕괴하므로(1A001 과 1A101 이 모두 8A101) 아래에서 명시적으로 배제한다.
CORE_ECCN_RE = re.compile(r"^ECCN-(\d)([A-EY])0(\d{2})$")

# ---------------------------------------------------------------------------
# 사람이 양쪽 원문을 읽고 확인한 등가 관계
# ---------------------------------------------------------------------------
# relation:
#   equivalent : 양쪽이 같은 통제 항목을 같은 범위로 기술한다.
#   broader    : 상대 항목이 정답 항목을 포함하지만 더 넓다(상위 노드).
# confidence:
#   high   : 표제가 사실상 동일하고 하위 파라미터도 일치한다.
#   medium : 표제는 일치하나 범위가 다르거나, eCFR 쪽이 표제 스텁이라
#            코퍼스 내부에서는 표제 수준까지만 확인 가능하다.
VERIFIED_STRUCTURAL: dict[str, dict] = {
    "ECCN-1A002": {"relation": "equivalent", "confidence": "high"},
    "ECCN-1A004": {"relation": "equivalent", "confidence": "high"},
    "ECCN-1A005": {"relation": "equivalent", "confidence": "high"},
    "ECCN-1A006": {"relation": "equivalent", "confidence": "high"},
    "ECCN-1B001": {"relation": "equivalent", "confidence": "medium",
                   "note": "eCFR 은 'production or inspection', 국제 레짐은 'production' 만. "
                           "eCFR 쪽이 검사장비까지 포함해 약간 넓다."},
    "ECCN-1B002": {"relation": "equivalent", "confidence": "high"},
    "ECCN-1C002": {"relation": "equivalent", "confidence": "high"},
    "ECCN-1C010": {"relation": "equivalent", "confidence": "high"},
    "ECCN-2A001": {"relation": "equivalent", "confidence": "high"},
    "ECCN-2B001": {"relation": "equivalent", "confidence": "high"},
    "ECCN-2B004": {"relation": "equivalent", "confidence": "high"},
    "ECCN-2B006": {"relation": "equivalent", "confidence": "high"},
    "ECCN-2B007": {"relation": "equivalent", "confidence": "high"},
    "ECCN-2D001": {"relation": "equivalent", "confidence": "high",
                   "note": "제외참조까지 대응한다: 2D001↔2D002, 2.D.1↔2.D.2, 8D201↔8D202."},
    "ECCN-3A001": {"relation": "equivalent", "confidence": "high"},
    "ECCN-3A002": {"relation": "equivalent", "confidence": "high"},
    "ECCN-3A003": {"relation": "equivalent", "confidence": "high",
                   "note": "따옴표 스타일만 다르고 문장이 동일하다."},
    "ECCN-3B001": {"relation": "equivalent", "confidence": "high"},
    "ECCN-3B002": {"relation": "equivalent", "confidence": "medium",
                   "note": "eCFR 은 'Test or inspection ... testing or inspecting', "
                           "국제 레짐은 'Test ... testing' 만."},
    "ECCN-3C006": {"relation": "equivalent", "confidence": "high",
                   "note": "제외참조 3C001↔3.C.1↔8C301, 기판참조 3C005↔3.C.5↔8C305 까지 대응."},
    "ECCN-3D005": {"relation": "equivalent", "confidence": "high",
                   "note": "문장이 동일하다."},
    "ECCN-3D006": {"relation": "equivalent", "confidence": "high"},
    "ECCN-3E002": {"relation": "equivalent", "confidence": "high",
                   "note": "제외참조 3E001↔3.E.1↔8E301 까지 대응."},
    "ECCN-3E004": {"relation": "equivalent", "confidence": "high",
                   "note": "문장이 동일하다(SFQR 20 nm, 26x8 mm, edge exclusion 2 mm)."},
    "ECCN-5A002": {"relation": "equivalent", "confidence": "high"},
    "ECCN-5D002": {"relation": "equivalent", "confidence": "high"},
    "ECCN-6A001": {"relation": "equivalent", "confidence": "high"},
    "ECCN-6A006": {"relation": "equivalent", "confidence": "high"},
    "ECCN-7A002": {"relation": "equivalent", "confidence": "high"},
    "ECCN-7A008": {"relation": "equivalent", "confidence": "high",
                   "note": "문장이 동일하다(CEP 3% of distance travelled)."},
    "ECCN-8A001": {"relation": "equivalent", "confidence": "high"},
    "ECCN-8A002": {"relation": "equivalent", "confidence": "high",
                   "note": "eCFR 은 'parts and components', 국제 레짐은 'components'."},
    "ECCN-8B001": {"relation": "equivalent", "confidence": "high",
                   "note": "문장이 동일하다(100 dB, 0~500 Hz water tunnel)."},
    "ECCN-8C001": {"relation": "equivalent", "confidence": "high"},
}

# 구조 규칙이 닿지 않는(=Wassenaar core 가 아닌) 정답 코드에 대해, 원문 Jaccard
# 상위 후보를 사람이 읽고 확인한 것만 수록한다.
VERIFIED_EXTRA: dict[str, list[dict]] = {
    "ECCN-1A101": [
        {"code": "3A501", "relation": "broader", "confidence": "medium",
         "note": "SCOMET 3A501.b 가 'Devices ... for reduced observables' 로 1A101 과 동일. "
                 "다만 3A501.a 는 재료(=ECCN 1C101)까지 포함해 상위 노드."},
    ],
    "ECCN-1B117": [
        {"code": "3B014", "relation": "broader", "confidence": "medium",
         "note": "SCOMET 3B014.a 가 batch mixer(=1B117), 3B014.b 가 continuous mixer(=1B118). "
                 "eCFR 은 두 항목으로 쪼개져 있어 SCOMET 쪽이 상위 노드."},
    ],
    "ECCN-2A225": [
        {"code": "4A008", "relation": "equivalent", "confidence": "high",
         "note": "표제 문장이 동일하고 SCOMET 쪽에 150~8000 cm3, 내화물 목록까지 그대로 있다."},
    ],
    "ECCN-2A226": [
        {"code": "4A013", "relation": "equivalent", "confidence": "high",
         "note": "표제 문장 동일. SCOMET 쪽이 nominal size 5 mm / bellows seal / "
                 "60% 초과 니켈 라이닝 파라미터를 그대로 갖고 있다."},
    ],
    "ECCN-3A225": [
        {"code": "4A011", "relation": "equivalent", "confidence": "high",
         "note": "표제 동일(variable/fixed frequency motor drive). 양쪽 모두 원자력 규제기관 "
                 "관할분을 제외한다(eCFR: NRC 10 CFR 110, SCOMET: Prescribed Equipment 0B)."},
    ],
    "ECCN-3A226": [
        {"code": "4A015", "relation": "equivalent", "confidence": "high",
         "note": "표제 동일. SCOMET 쪽에 100 V / 500 A / 8시간 / 0.1% 파라미터가 그대로 있다."},
    ],
    "ECCN-3A227": [
        {"code": "4A016", "relation": "equivalent", "confidence": "high",
         "note": "표제 동일. SCOMET 쪽에 20 kV / 1 A / 8시간 / 0.1% 파라미터가 그대로 있다."},
    ],
    "ECCN-3A233": [
        {"code": "4A024", "relation": "equivalent", "confidence": "high",
         "note": "표제 문장 동일(230 u 이상, 분해능 2 parts in 230, ion sources therefor)."},
    ],
    "ECCN-6A102": [
        {"code": "5C012", "relation": "broader", "confidence": "medium",
         "note": "SCOMET 5C012 표제가 'Detectors ... against nuclear effects (EMP, X-rays, "
                 "combined blast and thermal effects)' 로 6A102 와 같은 항목. 다만 하위에 "
                 "radiation hardened microcircuit(=3A101) 과 ADC 까지 묶여 있어 상위 노드."},
    ],
    "ECCN-6A107": [
        {"code": "6.A.7", "relation": "broader", "confidence": "medium",
         "note": "Wassenaar 6.A.7 은 지상용(a.)까지 포함하는 상위 노드. eCFR 은 지상용을 "
                 "6A007, 항공/해상용을 6A107 로 분리한다."},
        {"code": "8A607", "relation": "broader", "confidence": "medium",
         "note": "6.A.7 과 같은 이유로 상위 노드. 항공/해상 gravimeter 와 gravity "
                 "gradiometer(c.)를 포함한다."},
    ],
    "ECCN-6B108": [
        {"code": "5A218", "relation": "equivalent", "confidence": "high",
         "note": "표제 문장이 사실상 동일: radar cross section measurement systems usable for "
                 "rocket systems / UAV / cruise missiles and their subsystems."},
    ],
    "ECCN-7A104": [
        {"code": "5C003", "relation": "broader", "confidence": "medium",
         "note": "SCOMET 5C003 이 'Compasses (including gyro-astro compasses), gyroscopes, "
                 "accelerometers and inertial equipment' 로 gyro-astro compass 를 명시하지만 "
                 "관성장비 전체를 묶은 상위 노드."},
    ],
}

# 기계 후보로 올라왔지만 원문을 읽고 **등가가 아니라고 판단해 제외**한 것들.
# 감사 추적용으로 이유를 남긴다.
REJECTED_CANDIDATES: list[dict] = [
    {"eccn": "ECCN-0A977", "candidate": "4.A.5 / 8A405", "jaccard_minimal_text": 0.391,
     "reason": "water cannon(폭동진압) vs intrusion software. 'systems, equipment and "
               "components ... specially designed or modified for' 라는 상용구만 겹친다."},
    {"eccn": "ECCN-0A979", "candidate": "9.A.11 / 8A911", "jaccard_minimal_text": 0.235,
     "reason": "police helmet/shield vs ramjet engine. 상용구 일치."},
    {"eccn": "ECCN-3B994", "candidate": "3.B.1 / 8B301", "jaccard_minimal_text": 0.414,
     "reason": "3B994 는 advanced-node IC 용 미국 단독통제 신설항목이다. 3.B.1(=3B001)과 "
               "품목군은 겹치지만 통제기준이 다르므로 등가가 아니다."},
    {"eccn": "ECCN-5A101", "candidate": "5A217", "jaccard_minimal_text": 0.429,
     "reason": "5A101 은 미사일용 telemetering/telecontrol 장비, SCOMET 5A217 은 발사·지상지원 "
               "설비. 코퍼스에 telemetry 대응 항목은 5C005(encrypted telemetry)뿐이며 이 역시 "
               "범위가 다르다."},
    {"eccn": "ECCN-5D991", "candidate": "8D501 / 8D101 / 8D401", "jaccard_minimal_text": 0.484,
     "reason": "'software specially designed or modified for the development, production or "
               "use of equipment specified by X' 라는 소프트웨어 상용구만 겹친다. 대상 장비가 "
               "다르다. (5D991 자체는 미국 단독통제 항목으로 국제 대응이 없다.)"},
    {"eccn": "ECCN-6E619", "candidate": "6A022", "jaccard_minimal_text": 0.400,
     "reason": "6E619 는 600 시리즈(군용) 기술, SCOMET 6A022 는 Munitions List Category 6 "
               "기술 전체. 항목 대응이 아니라 범주 대응이다."},
    {"eccn": "ECCN-8A620", "candidate": "8.A.1 / 8A801", "jaccard_minimal_text": 0.208,
     "reason": "8A620 은 600 시리즈(군용) 잠수정, 8.A.1 은 민군겸용 잠수정(=ECCN 8A001). "
               "규제체계 계층이 다르다."},
    {"eccn": "ECCN-8D999", "candidate": "9.D.5", "jaccard_minimal_text": 0.400,
     "reason": "후보 문서 '9.D.5' 자체가 코퍼스 파싱 잔해('Software specially designed or "
               "modified for the operation of items specified in' 에서 끊김)다. 등가 판단 불가."},
    {"eccn": "ECCN-2B350", "candidate": "(없음)", "jaccard_minimal_text": 0.258,
     "reason": "화학무기 관련 제조설비(Australia Group)에 대응하는 항목이 이 코퍼스의 "
               "Wassenaar/SCOMET 발췌분에 없다."},
    {"eccn": "ECCN-1C111", "candidate": "(없음)", "jaccard_minimal_text": 0.267,
     "reason": "미사일 추진제(MTCR Item 4) 대응 항목이 코퍼스 발췌분에 없다. "
               "상위 후보는 전부 소프트웨어 상용구 일치."},
    {"eccn": "ECCN-4A101", "candidate": "(없음)", "jaccard_minimal_text": 0.314,
     "reason": "미사일용 아날로그/디지털 계산기 대응 항목이 코퍼스 발췌분에 없다."},
    {"eccn": "ECCN-3D202", "candidate": "(없음)", "jaccard_minimal_text": 0.269,
     "reason": "SCOMET 4A011 의 N.B.2 가 대응 소프트웨어를 'Item 4C' 로 넘기지만 해당 4C 항목이 "
               "코퍼스 발췌분에 없다. 확인 필요."},
    {"eccn": "ECCN-6D201", "candidate": "(없음)", "jaccard_minimal_text": 0.267,
     "reason": "SCOMET 4B004 의 N.B. 가 대응 소프트웨어를 'Item 4C' 로 넘기지만 해당 4C 항목이 "
               "코퍼스 발췌분에 없다. 확인 필요."},
    {"eccn": "미국 단독통제 9xx 계열", "candidate": "(없음)", "jaccard_minimal_text": None,
     "reason": "0A504·0A982·2A984·2A994·3A981·4D993·5A980·5A991·6A991·6C992 는 정의상 "
               "다자 레짐 대응 코드가 없다(EAR 단독 통제)."},
]

# ---------------------------------------------------------------------------
# 질의별 라벨 결함 (D3, D4, D5)
# ---------------------------------------------------------------------------
# 제거할 2차 라벨: 질의 품목과 실제로 다른 항목을 가리키는 군더더기 라벨.
DROP_LABELS: dict[str, list[dict]] = {
    "ext-005": [
        {"code": "ECCN-5D991", "issue": "imprecise_secondary_label",
         "reason": "질의는 암호 소프트웨어 소스코드다. 5D991 본문은 '5A991·5B991 장비용 "
                   "소프트웨어 및 dynamic adaptive routing software' 로 암호와 무관하다. "
                   "any-label 적중 채점에서 난이도를 인위적으로 낮춘다."},
    ],
    "ext-023": [
        {"code": "ECCN-5A991", "issue": "imprecise_secondary_label",
         "reason": "질의는 암호 칩이다. 5A991 본문은 'Telecommunication equipment, not "
                   "controlled by 5A001' 로 암호기능과 무관하다."},
    ],
}

# 질의-라벨 규제체계 모순 (D4)
REGIME_CONTRADICTION: dict[str, dict] = {
    "ext-028": {
        "issue": "regime_contradiction_military_vs_dual_use",
        "reason": "질의가 '군용입니다'라고 명시하는데 정답 ECCN-6A001 은 민군겸용 CCL "
                  "음향 항목이다. 군용 어뢰 유도제어 부품은 USML/600 시리즈 소관이므로 "
                  "질의와 라벨의 규제체계가 어긋난다.",
        "excluded_from_metrics": True,
        # 모순 문장만 제거한 교정 질의. 원문은 query_original 로 보존한다.
        "query_corrected": "어뢰 유도제어 부품(소나/음향 신호 처리)을 NATO 회원국에 수출하려 합니다.",
    },
}

# ---------------------------------------------------------------------------
# 품목명 누락 경고에 쓰는 일반어 목록 (영어 질의)
# ---------------------------------------------------------------------------
GENERIC_EN = {
    # 문법어
    "a", "an", "and", "any", "are", "as", "at", "be", "before", "but", "by", "can",
    "could", "do", "does", "for", "from", "has", "have", "if", "in", "into", "is",
    "it", "its", "may", "might", "of", "on", "or", "our", "out", "should", "that",
    "the", "their", "them", "there", "they", "this", "to", "under", "up", "us",
    "used", "using", "want", "wants", "was", "we", "what", "when", "which", "will",
    "with", "would", "you", "your", "not", "also", "before", "after", "own",
    # 수출상담 상용구 (질의 대부분에 공통으로 나타나므로 품목명이 아니다)
    "advise", "apply", "applies", "buy", "buyer", "candidate", "category",
    "categories", "check", "class", "classification", "client", "company",
    "confirm", "consult", "consultation", "control", "controlled", "controls",
    "country", "customer", "delivery", "eccn", "export", "exporting", "firm",
    "know", "license", "licenses", "licence", "list", "need", "needs", "partner",
    "plans", "please", "product", "proper", "provide", "quoting", "regulation",
    "regulations", "request", "requested", "requests", "requires", "required",
    "sample", "sell", "send", "sending", "ship", "shipping", "status", "supply",
    "team", "tell", "understand", "vendor", "wish", "abroad", "overseas",
    "foreign", "internal", "external", "item", "items", "unit", "units",
    "equipment", "system", "systems", "device", "devices", "component",
    "components", "module", "modules", "gear", "instrument", "instruments",
    "specified", "specific", "very", "high", "low", "level", "levels", "make",
    "makes", "made", "uses", "usable", "use", "based", "given", "same", "other",
    "possible", "capability", "capable", "customer", "buyers", "lab", "laboratory",
    "institute", "university", "research", "project", "facility", "plant",
    "producer", "distributor", "supplier", "integrator", "builder", "offshore",
    "domestic", "grade", "type", "kind", "first", "still", "already",
    "about", "because", "itself", "requesting", "inside", "outside", "long",
    "fit", "fits", "determine", "determines", "maintain", "maintaining",
    "building", "retrieval", "group", "compliance", "boost", "boosts",
    "quote", "quotes", "deliver", "delivered", "prior", "ahead", "standard",
    "standards", "confirmation", "advise", "interested", "proper", "sample",
    "samples", "package", "know-how", "program",
}
# 국가/지역명 (품목명이 아님)
COUNTRY_EN = {
    "singapore", "taiwan", "brazil", "india", "israel", "europe", "spain",
    "denmark", "finland", "chilean", "chile", "qatar", "nato", "vietnam",
    "germany", "france", "canada", "korea", "japan", "china", "kingdom",
    "united", "middle", "east", "petroleum",
}
MIN_TERM_LEN = 4
TERM_COVERAGE_WARN = 0.25    # 핵심어 중 정답 본문에 등장하는 비율이 이 밑이면 경고
# '변별력 있는' 품목어의 기준: 코퍼스 전체에서 이 문서 수 이하로만 등장하는 토큰.
# 코퍼스에는 있는데 정답 문서에는 없다면, 그 질의는 정답 문서를 어휘적으로
# 지목할 근거가 없다는 뜻이다(ext-015 의 'oscilloscope' 가 전형).
DISCRIMINATIVE_DF_MAX = 20


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_corpus() -> list[dict]:
    return load_json(CORPUS_PATH)


def load_queries_v1() -> list[dict]:
    return load_json(QUERIES_V1_PATH)["queries"]


def jaccard(a: set[str], b: set[str]) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def token_sets(corpus: list[dict], mode: str) -> dict[str, set[str]]:
    return {e["code"]: set(rc.tokenize(rc.index_text(e, mode))) for e in corpus}


def is_stub(entry: dict) -> bool:
    """표제만 있고 기술 파라미터가 본문에 없는 항목인가."""
    return bool(STUB_RE.search(entry.get("text") or ""))


def structural_counterparts(eccn: str, by_code: dict[str, dict]) -> list[tuple[str, str]]:
    """Wassenaar/SCOMET 구조 대응 코드 후보. core list(0nn) 에만 적용한다."""
    m = CORE_ECCN_RE.match(eccn)
    if not m:
        return []
    cat, typ, nn = m.groups()
    out = []
    wa = f"{cat}.{typ}.{int(nn)}"
    sc = f"8{typ}{cat}{nn}"
    for cand, src in ((wa, "wassenaar_2025"), (sc, "india_scomet_2024")):
        entry = by_code.get(cand)
        if entry is not None and entry.get("source") == src:
            out.append((cand, src))
    return out


# ---------------------------------------------------------------------------
# D1 ~ D6 실측
# ---------------------------------------------------------------------------


def audit_stub_text(corpus: list[dict], queries: list[dict]) -> dict:
    """D1: eCFR 표제 스텁 실측."""
    by_code = {e["code"]: e for e in corpus}
    ecfr = [e for e in corpus if e.get("source") == "ecfr_part774"]
    stub_entries = [e for e in ecfr if is_stub(e)]
    short_entries = [e for e in ecfr if len(e.get("text") or "") < SHORT_TEXT_CHARS]

    gold_codes = sorted({c for q in queries for c in q["validated_labels"]})
    gold_stub = [c for c in gold_codes if c in by_code and is_stub(by_code[c])]

    q_all_stub, q_any_stub = [], []
    for q in queries:
        labels = [c for c in q["validated_labels"] if c in by_code]
        if not labels:
            continue
        flags = [is_stub(by_code[c]) for c in labels]
        if all(flags):
            q_all_stub.append(q["id"])
        if any(flags):
            q_any_stub.append(q["id"])

    return {
        "ecfr_entries": len(ecfr),
        "stub_entries": len(stub_entries),
        "stub_share": round(len(stub_entries) / len(ecfr), 4) if ecfr else 0.0,
        "entries_under_%d_chars" % SHORT_TEXT_CHARS: len(short_entries),
        "short_share": round(len(short_entries) / len(ecfr), 4) if ecfr else 0.0,
        "distinct_gold_codes": len(gold_codes),
        "gold_codes_that_are_stubs": len(gold_stub),
        "gold_stub_share": round(len(gold_stub) / len(gold_codes), 4) if gold_codes else 0.0,
        "queries_all_gold_labels_stub": len(q_all_stub),
        "queries_any_gold_label_stub": len(q_any_stub),
        "queries_all_gold_labels_stub_share": round(len(q_all_stub) / len(queries), 4),
        "example": {
            "query_id": "ext-015",
            "gold": "ECCN-3A002",
            "gold_text": by_code.get("ECCN-3A002", {}).get("text", ""),
            "note": "질의는 'oscilloscope ... bandwidth over 1 GHz' 인데 정답 본문에 "
                    "oscilloscope/GHz 가 모두 없다.",
        },
        "stub_gold_codes": gold_stub,
    }


def audit_cross_regime_twins(corpus: list[dict], queries: list[dict]) -> dict:
    """D2: 타 규제체계 쌍둥이 실측.

    임계값과 '몇 번째 라벨까지 보는지'가 결과를 바꾸므로 둘 다 보고한다.
    first_label_only 는 `validate_query_slice.py` 가 갖고 있던 버그(첫 라벨만
    검사)를 그대로 재현한 값이다.
    """
    by_code = {e["code"]: e for e in corpus}
    non_ecfr = [e for e in corpus if e.get("source") != "ecfr_part774"]
    out: dict = {"definition": "Jaccard over tokens of index_text(entry, 'minimal_text')"}

    for mode in ("minimal_text", "full_text"):
        T = token_sets(corpus, mode)
        for label_pick in ("all_labels", "first_label_only"):
            counts = {"0.30": 0, "0.40": 0}
            worst: list[tuple[float, str, str, str, str]] = []
            for q in queries:
                labels = q["validated_labels"]
                if label_pick == "first_label_only":
                    labels = labels[:1]
                best = (0.0, "", "", "")
                for lbl in labels:
                    if lbl not in T:
                        continue
                    for e in non_ecfr:
                        j = jaccard(T[lbl], T[e["code"]])
                        if j > best[0]:
                            best = (j, lbl, e["code"], e.get("source", ""))
                if best[0] >= 0.30:
                    counts["0.30"] += 1
                if best[0] >= 0.40:
                    counts["0.40"] += 1
                worst.append((best[0], q["id"], best[1], best[2], best[3]))
            worst.sort(reverse=True)
            out[f"{mode}|{label_pick}"] = {
                "queries_with_twin_j_ge_0.30": counts["0.30"],
                "queries_with_twin_j_ge_0.40": counts["0.40"],
                "n": len(queries),
                "top10": [
                    {"query_id": qid, "gold": g, "twin": t, "regime": s,
                     "jaccard": round(j, 3)}
                    for j, qid, g, t, s in worst[:10]
                ],
            }
    out["note"] = (
        "minimal_text|first_label_only 이 감사 착수 시점에 보고된 정의다"
        "(J>=0.40 29건, J>=0.30 48건). all_labels 로 고치면 각각 30건, 49건이 되며 "
        "차이는 ext-005/ext-023 의 2차 라벨에서 나온다."
    )
    return out


def audit_label_issues(queries: list[dict], by_code: dict[str, dict]) -> dict:
    """D3, D4: 부정확한 2차 라벨과 규제체계 모순."""
    rows = []
    for qid, drops in DROP_LABELS.items():
        q = next((x for x in queries if x["id"] == qid), None)
        for d in drops:
            rows.append({
                "query_id": qid,
                "query": q["query"] if q else None,
                "dropped_label": d["code"],
                "dropped_label_text": by_code.get(d["code"], {}).get("text", ""),
                "kept_labels": [c for c in (q["validated_labels"] if q else [])
                                if c != d["code"]],
                "issue": d["issue"],
                "reason": d["reason"],
            })
    contradictions = []
    for qid, info in REGIME_CONTRADICTION.items():
        q = next((x for x in queries if x["id"] == qid), None)
        contradictions.append({
            "query_id": qid,
            "query": q["query"] if q else None,
            "gold": q["validated_labels"] if q else [],
            "gold_text": [by_code.get(c, {}).get("text", "")
                          for c in (q["validated_labels"] if q else [])],
            **{k: v for k, v in info.items()},
        })
    return {
        "imprecise_secondary_labels": rows,
        "imprecise_secondary_label_count": len(rows),
        "regime_contradictions": contradictions,
        "regime_contradiction_count": len(contradictions),
    }


def audit_duplicate_codes(queries: list[dict]) -> dict:
    """D5: 같은 ECCN 이 두 질의 이상의 정답으로 재사용된 경우."""
    used: dict[str, list[str]] = {}
    for q in queries:
        for c in q["validated_labels"]:
            used.setdefault(c, []).append(q["id"])
    dups = {c: ids for c, ids in used.items() if len(ids) > 1}
    return {
        "label_occurrences": sum(len(v) for v in used.values()),
        "distinct_labels": len(used),
        "reused_codes": {c: ids for c, ids in sorted(dups.items())},
        "reused_code_count": len(dups),
        "queries_involved": sorted({i for ids in dups.values() for i in ids}),
        "one_query_one_item_satisfied": not dups,
    }


def audit_label_space(corpus: list[dict]) -> dict:
    """D6: 라벨 공간이 eCFR full code 로 한정되어 생기는 도달 불가 문서."""
    ecfr = [e for e in corpus if e.get("source") == "ecfr_part774"]
    unreachable = len(corpus) - len(ecfr)
    per_source: dict[str, int] = {}
    for e in corpus:
        per_source[e.get("source", "?")] = per_source.get(e.get("source", "?"), 0) + 1
    return {
        "corpus_size": len(corpus),
        "labelable_entries": len(ecfr),
        "unreachable_entries": unreachable,
        "unreachable_share": round(unreachable / len(corpus), 4) if corpus else 0.0,
        "per_source": per_source,
    }


# ---------------------------------------------------------------------------
# 핵심 품목명 누락 경고
# ---------------------------------------------------------------------------


def _norm(tok: str) -> str:
    """아주 단순한 복수형 정규화(검색기가 아니라 경고용이므로 이 정도로 충분).

    -ss/-us/-is/-os 로 끝나는 단어는 복수형이 아니므로 건드리지 않는다
    (그러지 않으면 simultaneous -> simultaneou 같은 잔해가 생긴다).
    """
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if (len(tok) > 3 and tok.endswith("s")
            and tok[-2:] not in ("ss", "us", "is", "os")):
        return tok[:-1]
    return tok


def item_terms(query: str, lang: str) -> list[str]:
    """질의에서 '품목을 가리키는' 후보 어휘를 뽑는다.

    한국어 질의는 100% 영어 코퍼스에 대해 어휘적 존재 여부가 정의되지 않으므로,
    질의 안의 라틴문자/숫자 토큰(예: MMIC, GHz, 3D)만 검사 대상으로 삼는다.
    """
    toks = rc.tokenize(query)
    if lang == "en":
        return sorted({_norm(t) for t in toks
                       if len(t) >= MIN_TERM_LEN
                       and not t.isdigit()
                       and t not in GENERIC_EN
                       and t not in COUNTRY_EN})
    latin = [t for t in toks if re.fullmatch(r"[a-z0-9]+", t) and not t.isdigit()]
    return sorted({_norm(t) for t in latin if len(t) >= 2 and t not in GENERIC_EN})


def corpus_document_frequency(corpus: list[dict]) -> dict[str, int]:
    df: dict[str, int] = {}
    for e in corpus:
        for t in {_norm(x) for x in rc.tokenize(e.get("text") or "")}:
            df[t] = df.get(t, 0) + 1
    return df


def audit_item_term_coverage(queries: list[dict], by_code: dict[str, dict],
                             df: dict[str, int] | None = None) -> dict:
    """정답 본문에 질의 핵심 품목명이 없으면 경고한다."""
    rows = []
    for q in queries:
        gold_text = " ".join(by_code.get(c, {}).get("text", "") for c in q["validated_labels"])
        gold_toks = {_norm(t) for t in rc.tokenize(gold_text)}
        terms = item_terms(q["query"], q["lang"])
        present = [t for t in terms if t in gold_toks]
        missing = [t for t in terms if t not in gold_toks]
        coverage = len(present) / len(terms) if terms else None
        checkable = bool(terms)
        warn = checkable and (coverage is not None and coverage < TERM_COVERAGE_WARN)
        # 코퍼스에는 존재하지만 정답 문서에는 없는 변별력 있는 품목어
        discriminative_missing = []
        if df is not None:
            discriminative_missing = [
                t for t in missing if 1 <= df.get(t, 0) <= DISCRIMINATIVE_DF_MAX
            ]
        rows.append({
            "query_id": q["id"],
            "lang": q["lang"],
            "checkable": checkable,
            "reason_not_checkable": None if checkable else (
                "한국어 질의에 라틴문자 품목 토큰이 없어 영어 코퍼스와 어휘 비교가 불가"
            ),
            "n_terms": len(terms),
            "coverage": None if coverage is None else round(coverage, 3),
            "present": present,
            "missing": missing,
            "warn_item_name_absent": warn,
            "discriminative_terms_missing_from_gold_text": discriminative_missing,
            "warn_discriminative_term_absent": bool(discriminative_missing),
            "gold_is_stub": all(is_stub(by_code[c]) for c in q["validated_labels"]
                                if c in by_code) if q["validated_labels"] else None,
        })
    warned = [r for r in rows if r["warn_item_name_absent"]]
    disc = [r for r in rows if r["warn_discriminative_term_absent"]]
    checkable = [r for r in rows if r["checkable"]]
    return {
        "coverage_threshold": TERM_COVERAGE_WARN,
        "discriminative_df_max": DISCRIMINATIVE_DF_MAX,
        "n": len(rows),
        "checkable": len(checkable),
        "not_checkable": len(rows) - len(checkable),
        "warnings_low_coverage": len(warned),
        "warned_query_ids_low_coverage": [r["query_id"] for r in warned],
        "warnings_discriminative_term_absent": len(disc),
        "warned_query_ids_discriminative": [
            {"query_id": r["query_id"],
             "terms": r["discriminative_terms_missing_from_gold_text"]} for r in disc],
        "mean_coverage_checkable": round(
            float(np.mean([r["coverage"] for r in checkable])), 4) if checkable else None,
        "per_query": rows,
    }


# ---------------------------------------------------------------------------
# 등가 라벨 사전
# ---------------------------------------------------------------------------


def machine_candidates(corpus: list[dict], queries: list[dict],
                       top_n: int = 3) -> list[dict]:
    """사람 검토용 기계 후보 생성 (구조 대응 + 원문 Jaccard 상위)."""
    by_code = {e["code"]: e for e in corpus}
    non_ecfr = [e for e in corpus if e.get("source") != "ecfr_part774"]
    T = token_sets(corpus, "minimal_text")
    gold = sorted({c for q in queries for c in q["validated_labels"]})
    out = []
    for g in gold:
        struct = structural_counterparts(g, by_code)
        sims = sorted(
            ((jaccard(T[g], T[e["code"]]), e["code"], e.get("source", ""))
             for e in non_ecfr), reverse=True)[:top_n]
        out.append({
            "eccn": g,
            "eccn_text": by_code[g]["text"] if g in by_code else None,
            "structural": [{"code": c, "regime": s,
                            "jaccard_minimal_text": round(jaccard(T[g], T[c]), 3)}
                           for c, s in struct],
            "text_similarity_top": [{"code": c, "regime": s, "jaccard_minimal_text": round(j, 3),
                                     "text": by_code[c]["text"][:400]}
                                    for j, c, s in sims],
        })
    return out


def build_equivalent_labels(corpus: list[dict], queries: list[dict]) -> dict:
    """검증 완료된 등가 라벨 사전을 만든다 (data/equivalent_labels.json)."""
    by_code = {e["code"]: e for e in corpus}
    T_min = token_sets(corpus, "minimal_text")
    T_full = token_sets(corpus, "full_text")
    gold = sorted({c for q in queries for c in q["validated_labels"]})

    mappings = []
    for g in gold:
        equivalents = []
        meta = VERIFIED_STRUCTURAL.get(g)
        if meta:
            for cand, regime in structural_counterparts(g, by_code):
                equivalents.append({
                    "code": cand,
                    "regime": regime,
                    "relation": meta["relation"],
                    "confidence": meta["confidence"],
                    "candidate_source": "structural_code_rule+text_jaccard",
                    "jaccard_minimal_text": round(jaccard(T_min[g], T_min[cand]), 3),
                    "jaccard_full_text": round(jaccard(T_full[g], T_full[cand]), 3),
                    "evidence": {
                        "eccn_quote": by_code[g]["text"][:400],
                        "counterpart_quote": by_code[cand]["text"][:400],
                    },
                    "note": meta.get("note"),
                    "verified_by": "human read of both source texts",
                })
        for extra in VERIFIED_EXTRA.get(g, []):
            cand = extra["code"]
            if cand not in by_code:
                continue
            equivalents.append({
                "code": cand,
                "regime": by_code[cand].get("source"),
                "relation": extra["relation"],
                "confidence": extra["confidence"],
                "candidate_source": "text_jaccard_top3",
                "jaccard_minimal_text": round(jaccard(T_min[g], T_min[cand]), 3),
                "jaccard_full_text": round(jaccard(T_full[g], T_full[cand]), 3),
                "evidence": {
                    "eccn_quote": by_code[g]["text"][:400],
                    "counterpart_quote": by_code[cand]["text"][:400],
                },
                "note": extra.get("note"),
                "verified_by": "human read of both source texts",
            })
        if equivalents:
            mappings.append({"eccn": g, "eccn_is_stub": is_stub(by_code[g]),
                             "equivalents": equivalents})

    n_pairs = sum(len(m["equivalents"]) for m in mappings)
    n_eq = sum(1 for m in mappings for e in m["equivalents"]
               if e["relation"] == "equivalent")
    return {
        "meta": {
            "purpose": "정답 ECCN 의 Wassenaar/SCOMET 등가 코드. R@10_equiv 채점에 쓴다.",
            "generated_by": "audit_label_quality.py emit",
            "seed": SEED,
            "env": rc.env_meta(),
            "corpus": str(CORPUS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "queries": str(QUERIES_V1_PATH.relative_to(ROOT)).replace("\\", "/"),
            "candidate_generation": {
                "structural_code_rule": {
                    "wassenaar": "ECCN-{cat}{type}0{nn} -> '{cat}.{type}.{int(nn)}'",
                    "scomet": "ECCN-{cat}{type}0{nn} -> '8{type}{cat}{nn}'",
                    "restriction": "세 번째 자리가 0 인 Wassenaar core list 항목에만 적용. "
                                   "MTCR(1xx)/NSG(2xx)/미국단독(9xx) 계열에 적용하면 서로 다른 "
                                   "ECCN 이 동일 SCOMET 코드로 붕괴한다(1A001, 1A101 -> 8A101).",
                },
                "text_similarity": "Jaccard over tokens of index_text(entry, 'minimal_text')",
            },
            "verification_protocol": (
                "기계 후보를 생성한 뒤 양쪽 원문을 사람이 읽고, 같은 통제 항목을 기술하는 "
                "경우에만 수록했다. 등가가 아닌 후보는 rejected_candidates 에 이유와 함께 남긴다."
            ),
            "relation_semantics": {
                "equivalent": "같은 통제 항목을 같은 범위로 기술",
                "broader": "상대 항목이 정답 항목을 포함하지만 더 넓다(상위 노드)",
            },
            "counts": {
                "distinct_gold_codes": len(gold),
                "gold_codes_with_equivalents": len(mappings),
                "gold_codes_without_equivalents": len(gold) - len(mappings),
                "total_pairs": n_pairs,
                "pairs_relation_equivalent": n_eq,
                "pairs_relation_broader": n_pairs - n_eq,
            },
        },
        "mappings": mappings,
        "rejected_candidates": REJECTED_CANDIDATES,
    }


def equiv_index(equiv_doc: dict, *, allow_broader: bool,
                min_confidence: str = "medium") -> dict[str, set[str]]:
    """등가 사전을 {정답코드: {허용코드...}} 로 펼친다."""
    order = {"low": 0, "medium": 1, "high": 2}
    floor = order.get(min_confidence, 1)
    out: dict[str, set[str]] = {}
    for m in equiv_doc["mappings"]:
        keep = set()
        for e in m["equivalents"]:
            if order.get(e["confidence"], 0) < floor:
                continue
            if e["relation"] == "broader" and not allow_broader:
                continue
            keep.add(e["code"])
        if keep:
            out[m["eccn"]] = keep
    return out


# ---------------------------------------------------------------------------
# v2 질의셋
# ---------------------------------------------------------------------------


def build_queries_v2(corpus: list[dict], queries: list[dict], equiv_doc: dict) -> dict:
    """기존 71개를 유지하면서 라벨 품질 필드를 붙인 v2 를 만든다."""
    by_code = {e["code"]: e for e in corpus}
    src: dict[str, dict] = {}
    for p in SLICE_PATHS:
        if not p.exists():
            continue
        d = load_json(p)
        for q in (d["queries"] if isinstance(d, dict) else d):
            src[q["id"]] = q

    dup = audit_duplicate_codes(queries)["reused_codes"]
    eq_all = equiv_index(equiv_doc, allow_broader=True)
    eq_strict = equiv_index(equiv_doc, allow_broader=False)
    df = corpus_document_frequency(corpus)
    coverage = {r["query_id"]: r for r in
                audit_item_term_coverage(queries, by_code, df)["per_query"]}

    out_queries = []
    for q in queries:
        qid = q["id"]
        original = list(q["validated_labels"])
        dropped = DROP_LABELS.get(qid, [])
        kept = [c for c in original if c not in {d["code"] for d in dropped}]

        issues: list[str] = []
        if dropped:
            issues.append("imprecise_secondary_label")
        contra = REGIME_CONTRADICTION.get(qid)
        if contra:
            issues.append(contra["issue"])
        if any(c in dup for c in kept):
            issues.append("duplicate_gold_code")
        stub_flags = [is_stub(by_code[c]) for c in kept if c in by_code]
        if stub_flags and all(stub_flags):
            issues.append("gold_text_is_heading_stub")

        equiv_strict = sorted({x for c in kept for x in eq_strict.get(c, set())})
        equiv_incl = sorted({x for c in kept for x in eq_all.get(c, set())})

        rec: dict = {
            "id": qid,
            "lang": q["lang"],
            "query": q["query"],
            # v1 병합 과정에서 사라져 스키마 검증이 71건 전부 실패하던 필드를 복원한다.
            "context": src.get(qid, {}).get("context", ""),
            "validated_labels": kept,
            "primary_label": kept[0] if kept else None,
            "origin": q.get("origin"),
            "label_confidence": src.get(qid, {}).get("label_confidence"),
            "label_basis_corpus_text": src.get(qid, {}).get("label_basis_corpus_text", ""),
            "equivalent_labels": equiv_incl,
            "equivalent_labels_strict": equiv_strict,
            "label_issues": issues,
            "text_completeness": {
                "gold_text_chars": [len(by_code.get(c, {}).get("text", "")) for c in kept],
                "gold_is_heading_stub": [is_stub(by_code[c]) for c in kept if c in by_code],
                "item_term_coverage": coverage.get(qid, {}).get("coverage"),
                "item_terms_missing_from_gold_text": coverage.get(qid, {}).get("missing", []),
                "item_term_check_applicable": coverage.get(qid, {}).get("checkable"),
                "warn_item_name_absent": coverage.get(qid, {}).get("warn_item_name_absent"),
                "discriminative_terms_missing_from_gold_text":
                    coverage.get(qid, {}).get("discriminative_terms_missing_from_gold_text", []),
                "warn_discriminative_term_absent":
                    coverage.get(qid, {}).get("warn_discriminative_term_absent"),
            },
            "excluded_from_metrics": bool(contra and contra.get("excluded_from_metrics")),
        }
        if original != kept:
            rec["validated_labels_v1"] = original
            rec["removed_labels"] = dropped
        if qid in dup or any(c in dup for c in kept):
            rec["duplicate_with"] = sorted(
                {i for c in kept for i in dup.get(c, []) if i != qid})
        if contra:
            rec["query_original"] = q["query"]
            rec["query_corrected"] = contra["query_corrected"]
            rec["exclusion_reason"] = contra["reason"]
        out_queries.append(rec)

    n_excluded = sum(1 for r in out_queries if r["excluded_from_metrics"])
    return {
        "meta": {
            "version": 2,
            "supersedes": "data/validated_queries_expanded.json",
            "generated_by": "audit_label_quality.py emit",
            "seed": SEED,
            "env": rc.env_meta(),
            "n": len(out_queries),
            "n_excluded_from_metrics": n_excluded,
            "n_evaluable": len(out_queries) - n_excluded,
            "label_nature": "corpus-text-grounded category labels (exact eCFR codes); "
                            "not legal or expert determinations",
            "changes_vs_v1": [
                "context / label_confidence / label_basis_corpus_text 복원 "
                "(v1 병합에서 누락되어 스키마 검증이 71건 전부 실패했다)",
                "ext-005 의 ECCN-5D991, ext-023 의 ECCN-5A991 을 부정확한 2차 라벨로 제거 "
                "(제거 전 값은 validated_labels_v1 에 보존)",
                "ext-028 은 질의('군용입니다')와 라벨(민군겸용 6A001)의 규제체계가 모순되어 "
                "excluded_from_metrics=true. 원문은 query_original, 교정문은 query_corrected.",
                "primary_label 로 단일 정답을 지정 ('1질의 1항목' 원칙)",
                "equivalent_labels / equivalent_labels_strict 추가 (data/equivalent_labels.json 유래)",
                "text_completeness, label_issues, duplicate_with 추가",
            ],
            "scoring_note": (
                "R@10 은 validated_labels 로, R@10_equiv 는 "
                "validated_labels ∪ equivalent_labels 로 채점한다. 두 값을 반드시 함께 보고할 것."
            ),
        },
        "queries": out_queries,
    }


# ---------------------------------------------------------------------------
# R@10_equiv
# ---------------------------------------------------------------------------


def top10_indices(corpus: list[dict], queries: list[dict], *,
                  index_mode: str = PRIMARY_INDEX_MODE,
                  alpha: float = PRIMARY_ALPHA,
                  model_name: str = PRIMARY_MODEL,
                  k: int = TOP_K) -> tuple[list[list[int]], dict]:
    """validated_suite 의 primary 설정과 동일한 파이프라인으로 top-k 를 구한다."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)
    docs = [rc.index_text(e, index_mode) for e in corpus]
    index = rc.BM25(docs)
    doc_emb = model.encode(docs, batch_size=32, normalize_embeddings=True,
                           show_progress_bar=False).astype(np.float32)
    q_emb = model.encode([q["query"] for q in queries], batch_size=32,
                         normalize_embeddings=True,
                         show_progress_bar=False).astype(np.float32)
    tops, no_signal = [], 0
    for qi, q in enumerate(queries):
        raw = index.scores(q["query"])
        if not rc.has_signal(raw):
            no_signal += 1
        bm = rc.minmax(raw)
        dn = rc.minmax(doc_emb @ q_emb[qi])
        # rank_indices: 내림차순 + 인덱스 오름차순 동점처리 (np.argsort(-s) 금지)
        tops.append(list(rc.rank_indices(rc.blend(bm, dn, alpha))[:k]))
    return tops, {"model": model_name, "index_mode": index_mode, "alpha": alpha,
                  "k": k, "bm25_no_signal_queries": no_signal}


def score_hits(corpus: list[dict], queries: list[dict], tops: list[list[int]],
               label_fn) -> list[int]:
    codes = [e["code"] for e in corpus]
    hits = []
    for q, top in zip(queries, tops):
        allowed = label_fn(q)
        hits.append(int(any(codes[i] in allowed for i in top)))
    return hits


def recall_at10_equiv(corpus: list[dict], queries_v1: list[dict],
                      queries_v2: list[dict], equiv_doc: dict, **kw) -> dict:
    """R@10 (before) 와 R@10_equiv (after) 를 같은 랭킹 위에서 비교한다.

    랭킹은 라벨과 무관하므로 top-10 을 한 번만 계산하고 채점 규칙만 바꾼다.
    """
    tops, diag = top10_indices(corpus, queries_v1, **kw)
    langs = [q["lang"] for q in queries_v1]
    v2_by_id = {q["id"]: q for q in queries_v2}
    eq_strict = equiv_index(equiv_doc, allow_broader=False)
    eq_all = equiv_index(equiv_doc, allow_broader=True)

    def gold_v1(q):
        return set(q["validated_labels"])

    def gold_v2(q):
        return set(v2_by_id[q["id"]]["validated_labels"])

    def gold_v2_strict(q):
        g = gold_v2(q)
        return g | {x for c in g for x in eq_strict.get(c, set())}

    def gold_v2_incl(q):
        g = gold_v2(q)
        return g | {x for c in g for x in eq_all.get(c, set())}

    def gold_v1_incl(q):
        g = gold_v1(q)
        return g | {x for c in g for x in eq_all.get(c, set())}

    variants = {
        "before_v1_labels": gold_v1,
        "before_v2_labels": gold_v2,
        "after_v1_labels_equiv_inclusive": gold_v1_incl,
        "after_v2_labels_equiv_strict": gold_v2_strict,
        "after_v2_labels_equiv_inclusive": gold_v2_incl,
    }

    excluded = {q["id"] for q in queries_v2 if q.get("excluded_from_metrics")}
    keep = [i for i, q in enumerate(queries_v1) if q["id"] not in excluded]

    out: dict = {"diagnostics": diag, "seed": SEED, "env": rc.env_meta(),
                 "excluded_from_metrics": sorted(excluded)}
    hit_vectors: dict[str, list[int]] = {}
    for name, fn in variants.items():
        hits = score_hits(corpus, queries_v1, tops, fn)
        hit_vectors[name] = hits
        ko = [h for h, lg in zip(hits, langs) if lg == "ko"]
        en = [h for h, lg in zip(hits, langs) if lg == "en"]
        sub = [hits[i] for i in keep]
        sub_ko = [hits[i] for i in keep if langs[i] == "ko"]
        sub_en = [hits[i] for i in keep if langs[i] == "en"]
        out[name] = {
            "all_71": rc.rate_with_ci(hits),
            "all_71_ko": rc.rate_with_ci(ko),
            "all_71_en": rc.rate_with_ci(en),
            "evaluable_%d" % len(keep): rc.rate_with_ci(sub),
            "evaluable_ko": rc.rate_with_ci(sub_ko),
            "evaluable_en": rc.rate_with_ci(sub_en),
        }

    base = hit_vectors["before_v1_labels"]
    contrasts = {}
    for name in ("before_v2_labels", "after_v1_labels_equiv_inclusive",
                 "after_v2_labels_equiv_strict", "after_v2_labels_equiv_inclusive"):
        a = hit_vectors[name]
        diffs = [x - y for x, y in zip(a, base)]
        contrasts[f"{name}_vs_before_v1_labels"] = {
            "paired_bootstrap": rc.paired_bootstrap_ci(diffs, seed=SEED),
            "mcnemar": rc.exact_mcnemar(a, base),
        }
    # 쌍둥이가 '실제로' 얼마나 방해하는지: top-10 안에 등가 문서가 들어온 질의 수.
    # 구조적으로 쌍둥이가 존재하는 질의 수(D2)와 이 값은 다르다.
    codes = [e["code"] for e in corpus]
    eq_seen_and_gold_missed, eq_seen_total = [], []
    base_hits = hit_vectors["before_v1_labels"]
    for qi, q in enumerate(queries_v1):
        allowed_eq = {x for c in gold_v2(q) for x in eq_all.get(c, set())}
        seen = [codes[i] for i in tops[qi] if codes[i] in allowed_eq]
        if seen:
            eq_seen_total.append({"query_id": q["id"], "equivalents_in_top10": seen})
            if not base_hits[qi]:
                eq_seen_and_gold_missed.append(q["id"])
    out["equivalent_in_top10"] = {
        "queries_with_equivalent_in_top10": len(eq_seen_total),
        "queries_where_only_the_equivalent_was_retrieved": eq_seen_and_gold_missed,
        "detail": eq_seen_total,
    }

    out["contrasts_vs_before"] = contrasts
    out["hit_vectors"] = hit_vectors
    out["top10_codes"] = {q["id"]: [codes[i] for i in tops[qi]]
                          for qi, q in enumerate(queries_v1)}
    out["query_ids"] = [q["id"] for q in queries_v1]
    out["newly_hit_query_ids"] = {
        name: [queries_v1[i]["id"] for i in range(len(base))
               if hit_vectors[name][i] > base[i]]
        for name in contrasts_keys(contrasts)
    }
    out["newly_missed_query_ids"] = {
        name: [queries_v1[i]["id"] for i in range(len(base))
               if hit_vectors[name][i] < base[i]]
        for name in contrasts_keys(contrasts)
    }
    return out


def contrasts_keys(contrasts: dict) -> list[str]:
    return [k.replace("_vs_before_v1_labels", "") for k in contrasts]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_audit(args) -> dict:
    corpus = load_corpus()
    queries = load_queries_v1()
    by_code = {e["code"]: e for e in corpus}
    return {
        "meta": {"seed": SEED, "env": rc.env_meta(), "n_queries": len(queries),
                 "corpus_size": len(corpus)},
        "D1_ecfr_heading_stub": audit_stub_text(corpus, queries),
        "D2_cross_regime_twins": audit_cross_regime_twins(corpus, queries),
        "D3_D4_label_issues": audit_label_issues(queries, by_code),
        "D5_code_reuse": audit_duplicate_codes(queries),
        "D6_label_space": audit_label_space(corpus),
        "item_term_coverage": audit_item_term_coverage(
            queries, by_code, corpus_document_frequency(corpus)),
    }


def cmd_candidates(args) -> list[dict]:
    return machine_candidates(load_corpus(), load_queries_v1())


def cmd_emit(args) -> dict:
    corpus = load_corpus()
    queries = load_queries_v1()
    equiv = build_equivalent_labels(corpus, queries)
    EQUIV_PATH.write_text(json.dumps(equiv, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    v2 = build_queries_v2(corpus, queries, equiv)
    QUERIES_V2_PATH.write_text(json.dumps(v2, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    return {"wrote": [str(EQUIV_PATH), str(QUERIES_V2_PATH)],
            "equiv_counts": equiv["meta"]["counts"],
            "v2_meta": {k: v for k, v in v2["meta"].items() if k != "env"}}


def cmd_recall(args) -> dict:
    corpus = load_corpus()
    queries = load_queries_v1()
    if not EQUIV_PATH.exists() or not QUERIES_V2_PATH.exists():
        raise SystemExit("먼저 `python audit_label_quality.py emit` 을 실행하라.")
    equiv = load_json(EQUIV_PATH)
    v2 = load_json(QUERIES_V2_PATH)["queries"]
    return recall_at10_equiv(corpus, queries, v2, equiv)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["audit", "candidates", "emit", "recall", "all"])
    ap.add_argument("--out", type=Path, default=None,
                    help="결과 JSON 을 파일로 저장 (기본: stdout)")
    args = ap.parse_args()

    if args.command == "all":
        result = {"audit": cmd_audit(args), "emit": cmd_emit(args),
                  "recall": cmd_recall(args)}
    else:
        result = {"audit": cmd_audit, "candidates": cmd_candidates,
                  "emit": cmd_emit, "recall": cmd_recall}[args.command](args)

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
