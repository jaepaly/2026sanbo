#!/usr/bin/env python3
"""질의 측 노출 등급 사다리(L0~L4) 생성기.

배경 (docs/threat_model.md 참조)
    기존 실험은 노출량을 "시스템이 되돌려 주는 공개 통제목록의 문자 수"로 정의했다.
    Wassenaar/eCFR/SCOMET은 전부 공개문서이므로 그것을 덜 반환하는 것은 기업
    영업비밀 보호와 무관하다. 보호자산이 실제로 신뢰경계를 넘는 지점은 **질의 본문**
    (아웃바운드)이다. 이 스크립트는 검증셋 71개 질의를 L0(원문)~L4(카테고리 키워드)
    5단계로 재작성하고, 각 등급에 남아 있는 민감 필드를 카테고리 단위로 계량한다.

측정 단위
    문자 수가 아니라 **사전 정의 카테고리**와 그 카테고리에 귀속된 토큰 수를 센다.
    ("정밀도 ±0.5 µm"는 11자, "본 장비는 산업용입니다"는 13자인데 민감도는 비교가
    안 된다. 문자 수는 민감도의 대리변수가 못 된다.)

자동 / 수동의 분리
    자동: 수치·단위 정규식, 성능등급 표현 사전, 국가·지역 사전, 고유명칭 사전,
          최종사용자/용도/자사정체성/거래형태 사전 → 토큰 태깅, 등급 간 차분으로
          `removed` 목록 자동 생성, 단조성·라벨동일성·언어보존·통제번호누출 검증.
    수동: 질의 재작성 문장 자체(L1~L4)와 사전에 담기지 않는 제거 항목의 주석
          (MANUAL_REMOVALS). 재작성은 사람 판단이 필요하고 자동화 대상이 아니다.

사전(lexicon)의 성격
    개방형 정규식(수치)과 **닫힌 어휘목록**의 조합이다. 어휘목록은 71개 L0 질의에
    실제로 등장한 민감 표현을 열거해 만들었으므로 감사 가능하고, 다른 코퍼스로
    일반화하려면 목록을 확장해야 한다(한계로 명시).

출력: data/disclosure_ladder.json
실행: python build_disclosure_ladder.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import retrieval_core as rc  # noqa: E402

DATA_DIR = ROOT / "data"
SRC_PATH = DATA_DIR / "validated_queries_expanded.json"
OUT_PATH = DATA_DIR / "disclosure_ladder.json"

SEED = 20260626          # 이 스크립트에는 무작위성이 없다. 재현성 기록용.
LEVELS = ["L0", "L1", "L2", "L3", "L4"]

# --------------------------------------------------------------------------
# 1. 민감 필드 카테고리 사전 (코드에 박아 넣은 정의)
# --------------------------------------------------------------------------

CATEGORY_DEFS = {
    "quantitative_spec": {
        "ko": "수치+단위, 정밀도·공차·성능 등급 표현",
        "counted": True,
        "tier": 1,
    },
    "product_identifier": {
        "ko": "제품명·모델명·공정명·상표·특정 기술/재료 고유명칭",
        "counted": True,
        "tier": 2,
    },
    "destination": {
        "ko": "목적지 국가·지역(불특정 '해외/foreign' 포함)",
        "counted": True,
        "tier": 3,
    },
    "end_user": {
        "ko": "수요기관의 유형·성격(대학·연구소·팹리스·방산업체 등)",
        "counted": True,
        "tier": 3,
    },
    "end_use": {
        "ko": "용도·응용 맥락(군용·미사일·잠수함·원자력·감시 등)",
        "counted": True,
        "tier": 3,
    },
    "supplier_identity": {
        "ko": "질의자 자신의 업종·사업자 정체성",
        "counted": True,
        "tier": 3,
    },
    "transaction_intent": {
        "ko": "구체적 거래 형태·단계(샘플·시제품·입찰·견적·납품 예정)",
        "counted": True,
        "tier": 3,
    },
    "function": {
        "ko": "기능·물리적 원리(잔존 최소 정보, 계수 제외)",
        "counted": False,
        "tier": 4,
    },
    "item_category": {
        "ko": "품목 대분류 키워드(잔존 최소 정보, 계수 제외)",
        "counted": False,
        "tier": 5,
    },
}

COUNTED = [k for k, v in CATEGORY_DEFS.items() if v["counted"]]

LEVEL_DEFS = {
    "L0": "원문 그대로(기존 검증셋 질의)",
    "L1": "L0 − 정량 사양치: 수치·단위·정밀도·공차·성능 등급 표현 전부 삭제",
    "L2": "L1 − 고유명칭(제품·모델·공정·상표·특정 재료/기술명) + 규제 조문 인용 문구 삭제",
    "L3": "L2 − 최종사용자·목적지·용도·자사 정체성·거래 형태 삭제 → 기능·물리적 원리만",
    "L4": "카테고리 키워드만(2~5 단어)",
}

# --------------------------------------------------------------------------
# 2. 자동 추출기 — 수치·단위 정규식
# --------------------------------------------------------------------------

# 단위는 "숫자에 인접할 때만" 정량 사양으로 센다. 단위어 단독(예: '밀리미터파')은
# 대역 이름이므로 product_identifier로 처리된다.
UNIT_ALTS = [
    "밀리미터", "센티미터", "킬로미터", "나노미터", "마이크로미터", "미터",
    "밀리초", "킬로볼트", "볼트", "킬로와트", "와트", "기가헤르츠", "메가헤르츠",
    "헤르츠", "킬로그램", "그램", "톤", "퍼센트", "차원", "축", "비트", "도", "초",
    "ghz", "mhz", "khz", "hz", "kw", "mw", "kv", "ma", "db", "mm", "cm", "km",
    "nm", "um", "ms", "kg", "bits", "bit", "axes", "axis", "w", "v", "a", "s",
    "g", "t", "c", "k", "m",
]
UNIT_ALTS.sort(key=len, reverse=True)
NUM_UNIT_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:" + "|".join(re.escape(u) for u in UNIT_ALTS) + r")?",
    re.I,
)

# 수치가 없는 정량 사양 표현(성능 등급). 사전 기반이므로 열거한다.
GRADE_TERMS = [
    "고정밀", "초정밀", "정밀측정", "정밀도", "정밀하게", "정밀", "고속", "고온",
    "고압", "고전압", "높은 전압", "고출력", "고부식성", "초내열", "저소음", "경량",
    "대구경", "미세공정", "최첨단", "특수", "고점도", "심해", "원거리", "분해능",
    "공차", "등급이 높아", "매우 높은", "매우 작은", "장거리", "다중", "소형",
    "무거운", "사거리가 긴", "사거리",
    "high-precision", "high precision", "high-speed", "high speed",
    "high-current", "high current", "high-voltage", "high voltage",
    "low-noise", "low noise", "lightweight", "deep-sea", "deep sea",
    "very high", "very short", "high birefringence", "total dose",
    "bandwidth", "beat length", "resolution", "tolerance", "ultra",
]

# --------------------------------------------------------------------------
# 3. 자동 추출기 — 카테고리별 닫힌 어휘목록
#    ASCII 항목은 단어경계 매칭, 한국어 항목은 부분문자열 매칭(교착어 조사 대응).
#    우선순위는 아래 딕셔너리 순서이며, 매칭된 문자 구간은 소비되어 중복 계수되지 않는다.
# --------------------------------------------------------------------------

TERMS: dict[str, list[str]] = {
    "quantitative_spec": list(GRADE_TERMS),
    "product_identifier": [
        "자이로스코프", "도플러", "밀리미터파", "게이트올어라운드", "전자 설계 자동화",
        "타이타늄", "실리콘", "세라믹", "탄소섬유", "질량 분석", "소나", "식각",
        "마이크로컴퓨터", "프린터", "적층형", "스핀들", "용융", "완성 단계",
        "가변 주파수",
        "CNC", "machining center", "oscilloscope", "GaAs", "MMIC", "gallium",
        "nitride", "carbide", "arsenide", "silicon", "lie-detection",
        "lie detection", "stress-analysis", "stress analysis", "polygraph",
        "glass-lined", "glass-microsphere", "glass microsphere", "microsphere",
        "pre-impregnated", "impregnated", "carbon fiber", "carbon fibre",
        "carbon", "lithography", "positioning table", "skid", "tow",
    ],
    "destination": [
        "베트남", "독일", "프랑스", "싱가포르", "일본", "말레이시아", "중국", "대만",
        "인도 제조사", "인도 합작법인", "브라질", "중동", "남미", "아랍에미리트",
        "우크라이나", "터키", "이탈리아", "스웨덴", "캐나다", "노르웨이", "호주",
        "아프리카", "동남아", "해외", "외국",
        "NATO", "Singapore", "Taiwan", "Israel", "Brazil", "India", "Malaysia",
        "Spain", "United Kingdom", "Finland", "Denmark", "Chilean", "Qatar",
        "Europe", "Middle East", "overseas", "abroad", "foreign",
    ],
    "end_use": [
        "군용", "군사", "방산", "미사일", "어뢰", "잠수함", "무인 비행체", "무인기",
        "드론", "로켓", "해군", "항공기", "항공용", "항공 플랫폼", "항공우주",
        "위성", "인권", "감시", "폭발물", "교도소", "광산", "야외 작전",
        "원자력", "핵연료", "방사성", "총기", "사냥용", "경찰용", "경호업체용",
        "개인 보호용", "비군사용", "화학 누출 현장 대응용", "해저 조사용",
        "해저 관측용", "민간 복구 프로젝트", "민간 연구 목적", "실험 소모품",
        "missile", "submarine", "rocket", "munitions", "military", "defense",
        "defence", "naval", "aerospace", "satellite", "surveillance",
        "security screening", "nuclear", "propulsion", "petroleum", "pipeline",
        "pesticide", "oceanography", "power electronics", "hazardous samples",
        "shielded laboratory", "academic testing", "internal development",
        "research collaboration",
    ],
    "supplier_identity": [
        "제조사가", "업체가", "회사가", "개발사가", "납품사가", "조선소가",
        "장비사가", "부품사가", "연구소가", "업체는", "당사", "국내",
        "시위 대응 장비", "보안검색 장비", "교정시설 장비", "방탄복", "해양로봇",
        "our company", "our product", "our software", "we make", "we supply",
        "we sell", "we provide", "we license", "we are exporting",
        "we are shipping", "we have", "producer is", "distributor plans",
        "integrator will", "builder is", "supplier is", "vendor will",
        "facility plans", "export team", "export group", "compliance needs",
        "the company wants", "the team wants",
    ],
    "end_user": [
        "대학", "연구소", "연구기관", "파운드리", "팹리스", "협력사", "공장",
        "유통사", "조달청", "고객", "파트너", "합작법인", "방산업체", "데이터센터",
        "조선소", "공항 운영사", "에너지 회사", "측량 회사", "항공 회사",
        "항공부품사", "항공우주 기관", "플랜트 업체", "컨소시엄", "공공기관",
        "구조물 업체", "업체에", "업체에게", "제조사에",
        "university", "research institute", "research lab", "institute",
        "customer", "client", "buyer", "vendor", "subsidiary", "partner",
        "firm", "project", "facility",
    ],
    "transaction_intent": [
        "공급 예정", "공급하려", "공급할", "공급합니다", "공급하기", "납품하려고",
        "납품하려", "납품할", "보내려", "수출하려", "수출 전", "제공하려", "제공할",
        "판매하려", "이전하려", "기증하려", "설치하려", "인도하려", "샘플",
        "시제품", "테스트용", "입찰", "견적", "요청했습니다",
        "are exporting", "will export", "plans to export", "plans to send",
        "is sending", "is quoting", "wants to buy", "want to ship",
        "requested", "requesting", "will provide", "releasing samples",
        "before contracting", "before procurement", "before delivery",
        "sending the proposal",
    ],
}


def _compile(term: str) -> re.Pattern:
    """ASCII 항목은 단어경계, 한국어 항목은 부분문자열."""
    if term.isascii():
        return re.compile(r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b", re.I)
    return re.compile(re.escape(term).replace(r"\ ", r"\s+"))


# 긴 항목을 먼저 시도해야 'silicon carbide'가 'silicon'으로 쪼개지지 않는다.
COMPILED: list[tuple[str, str, re.Pattern]] = []
for _cat in TERMS:
    for _t in sorted(TERMS[_cat], key=len, reverse=True):
        COMPILED.append((_cat, _t, _compile(_t)))


def annotate(text: str) -> list[dict]:
    """질의문에서 민감 필드 스팬을 추출한다. 구간은 한 번만 소비된다."""
    text = text or ""
    taken = [False] * len(text)
    spans: list[dict] = []

    def claim(start: int, end: int) -> bool:
        if any(taken[start:end]):
            return False
        for i in range(start, end):
            taken[i] = True
        return True

    # (1) 수치+단위: 개방형 정규식
    for m in NUM_UNIT_RE.finditer(text):
        surface = m.group(0).strip()
        if not surface:
            continue
        if claim(m.start(), m.start() + len(m.group(0).rstrip())):
            spans.append({"category": "quantitative_spec", "term": "<numeric>",
                          "surface": surface, "start": m.start()})

    # (2) 닫힌 어휘목록: 카테고리 우선순위 → 항목 길이 내림차순
    for cat, term, pat in COMPILED:
        for m in pat.finditer(text):
            if claim(m.start(), m.end()):
                spans.append({"category": cat, "term": term,
                              "surface": m.group(0), "start": m.start()})

    spans.sort(key=lambda s: s["start"])
    return spans


def measure(text: str) -> dict:
    """등급별 노출 계량치."""
    spans = annotate(text)
    per_cat = Counter()
    per_cat_tokens = Counter()
    for s in spans:
        per_cat[s["category"]] += 1
        per_cat_tokens[s["category"]] += max(1, len(rc.tokenize(s["surface"])))
    counted_fields = sorted(c for c in per_cat if c in COUNTED)
    return {
        "spans": spans,
        "counted_sensitive_fields": counted_fields,
        "sensitive_token_count": sum(per_cat_tokens[c] for c in counted_fields),
        "sensitive_span_count": sum(per_cat[c] for c in counted_fields),
        "tokens_by_category": {c: per_cat_tokens[c] for c in sorted(per_cat)},
        "token_count": len(rc.tokenize(text)),
        "char_count": len(text),
    }


# --------------------------------------------------------------------------
# 4. 사람이 재작성한 L1~L4 (L0은 원본 JSON에서 그대로 읽는다)
#    - 언어는 원문과 동일하게 유지(ko 45 / en 26)
#    - L1~L3은 상담형 문장, L4는 2~5 단어 키워드
#    - 통제목록 원문 문언을 새로 베껴 넣지 않는다(자기참조 악화 금지)
# --------------------------------------------------------------------------

LADDER: dict[str, dict[str, str]] = {
    "ext-002": {
        "L1": "반도체 식각 공정용 플라즈마 발생장비를 베트남 업체에 공급 예정입니다. 해당 장비의 통제 분류를 알고 싶습니다.",
        "L2": "반도체 공정용 플라즈마 발생장비를 베트남 업체에 공급 예정입니다. 해당 장비의 통제 분류를 알고 싶습니다.",
        "L3": "반도체 소재를 가공하기 위해 플라즈마를 발생시키는 장비의 통제 분류를 알고 싶습니다.",
        "L4": "반도체 공정 장비",
    },
    "ext-003": {
        "L1": "We are exporting a CNC machining center with simultaneous multi-axis contouring control. Which ECCN categories might apply?",
        "L2": "We are exporting an automatically controlled machine that cuts metal parts while moving several axes at the same time. Which export control categories might apply?",
        "L3": "We would like the control classification for a machine that shapes metal parts by moving a cutting tool along several axes under automatic control.",
        "L4": "metal cutting machine tool",
    },
    "ext-004": {
        "L1": "드론용 자이로스코프 모듈을 해외 대학에 샘플로 제공할 예정입니다. 군용 가능성이 있는지 확인 필요합니다.",
        "L2": "무인 비행체용 회전 각속도 센서 모듈을 해외 대학에 샘플로 제공할 예정입니다. 군용 가능성이 있는지 확인 필요합니다.",
        "L3": "회전 각속도를 감지하는 관성 센서 모듈의 통제 분류를 알고 싶습니다.",
        "L4": "관성 센서 모듈",
    },
    "ext-005": {
        "L1": "Cryptographic software source code will be transferred to a foreign subsidiary for internal development. Does export control apply?",
        "L2": "Cryptographic software source code will be transferred to a foreign subsidiary for internal development. Does export control apply?",
        "L3": "We would like to know whether source code that implements data encryption falls under export control.",
        "L4": "encryption software source code",
    },
    "ext-006": {
        "L1": "항공기용 타이타늄 합금 판재를 독일 항공부품사에 수출하려 합니다. 관심 대상일 수 있다고 들어 통제 분류를 확인하고 싶습니다.",
        "L2": "항공기용 금속 합금 판재를 독일 항공부품사에 수출하려 합니다. 관심 대상일 수 있다고 들어 통제 분류를 확인하고 싶습니다.",
        "L3": "금속 합금 판재 형태의 소재에 대한 통제 분류를 확인하고 싶습니다.",
        "L4": "금속 합금 판재 소재",
    },
    "ext-007": {
        "L1": "We are shipping test equipment for underwater acoustic communication systems. This could be used for submarine applications. Please advise.",
        "L2": "We are shipping test equipment for underwater acoustic communication systems. This could be used for submarine applications. Please advise.",
        "L3": "We would like the control classification for equipment used to test systems that send sound through water.",
        "L4": "underwater acoustic equipment",
    },
    "ext-013": {
        "L1": "We are exporting software that controls vibration test equipment for satellite components. Is the software itself controlled?",
        "L2": "We are exporting software that controls vibration test equipment for satellite components. Is the software itself controlled?",
        "L3": "We would like the control classification for software that operates equipment used to apply mechanical vibration during testing.",
        "L4": "test equipment control software",
    },
    "ext-015": {
        "L1": "A research institute in Singapore wants to buy our oscilloscope. Which controls may apply?",
        "L2": "A research institute in Singapore wants to buy our instrument that digitises and displays fast electrical waveforms. Which controls may apply?",
        "L3": "We would like the control classification for an instrument that samples and displays electrical waveforms as they change over time.",
        "L4": "electronic test instrument",
    },
    "ext-016": {
        "L1": "적층형 프린터용 금속 분말 소재를 프랑스에 공급합니다. 군용 부품 제조 가능성이 있다고 합니다.",
        "L2": "층을 쌓아 부품을 만드는 장비에 넣는 금속 분말 소재를 프랑스에 공급합니다. 군용 부품 제조 가능성이 있다고 합니다.",
        "L3": "금속 분말 형태의 소재에 대한 통제 분류를 확인하고 싶습니다.",
        "L4": "금속 분말 소재",
    },
    "ext-017": {
        "L1": "We are shipping radar components with GaAs MMIC technology to a NATO partner country. What should we check first?",
        "L2": "We are shipping radar components based on compound-semiconductor microwave integrated circuits to a NATO partner country. What should we check first?",
        "L3": "We would like the control classification for microwave integrated circuits made on a compound semiconductor substrate.",
        "L4": "microwave integrated circuits",
    },
    "ext-023": {
        "L1": "An overseas university requested encryption chips for a research collaboration. We need to understand if any licenses are required.",
        "L2": "An overseas university requested encryption chips for a research collaboration. We need to understand if any licenses are required.",
        "L3": "We need to understand whether integrated circuits that perform data encryption are subject to licensing.",
        "L4": "encryption hardware components",
    },
    "ext-028": {
        "L1": "어뢰 유도제어 부품(소나/음향 신호 처리)을 NATO 회원국에 수출하려 합니다. 군용입니다.",
        "L2": "어뢰 유도제어 부품(수중 음향 신호 처리)을 NATO 회원국에 수출하려 합니다. 군용입니다.",
        "L3": "물속에서 음향 신호를 받아 처리하는 부품의 통제 분류를 알고 싶습니다.",
        "L4": "수중 음향 부품",
    },
    "ext-029": {
        "L1": "We have a customer in Israel requesting an angular positioning table used in semiconductor lithography. Is this an ECCN-controlled item?",
        "L2": "We have a customer in Israel requesting a rotary stage that sets a workpiece to a commanded angle inside semiconductor production equipment. Is this a controlled item?",
        "L3": "We would like the control classification for a rotary stage that positions a workpiece at a commanded angle.",
        "L4": "rotary positioning stage",
    },
    "g-seungwoo-001": {
        "L1": "밀폐 용기 안에서 절연성 액체를 전자 부품에 직접 뿌려 작동 온도를 유지시키는 냉각 장치를 베트남 데이터센터에 납품하려 합니다. 수출 통제 대상인지 확인이 필요합니다.",
        "L2": "밀폐 용기 안에서 절연성 액체를 전자 부품에 직접 뿌려 작동 온도를 유지시키는 냉각 장치를 베트남 데이터센터에 납품하려 합니다. 수출 통제 대상인지 확인이 필요합니다.",
        "L3": "밀폐 용기 안에서 절연성 액체를 전자 부품에 직접 뿌려 작동 온도를 유지하는 냉각 장치의 통제 분류를 알고 싶습니다.",
        "L4": "전자 부품 액체 냉각 장치",
    },
    "g-seungwoo-002": {
        "L1": "모터 구동용으로 쓰이는 가변 주파수 변환 장치를 인도 제조사에 공급할 예정입니다. 원자력 규제 대상은 아닌데 일반 수출 통제에 걸리는지 궁금합니다.",
        "L2": "모터 구동용으로 쓰이는 출력 주파수를 조절하는 전력 변환 장치를 인도 제조사에 공급할 예정입니다. 수출 통제에 걸리는지 궁금합니다.",
        "L3": "모터 회전 속도를 조절하기 위해 출력 주파수를 바꾸는 전력 변환 장치의 통제 분류를 알고 싶습니다.",
        "L4": "주파수 변환 전력 장치",
    },
    "g-seungwoo-003": {
        "L1": "We are exporting a direct-current power feed unit to a research lab in Taiwan. It is not under nuclear regulatory scope. Could you tell me the classification?",
        "L2": "We are exporting a unit that supplies direct-current electrical power to a load, to a research lab in Taiwan. Could you tell me the classification?",
        "L3": "We would like the classification for a unit that supplies direct-current electrical power to a load.",
        "L4": "direct current power supply",
    },
    "g-seungwoo-004": {
        "L1": "직류 전원 장치를 독일 연구소에 보내려 합니다. 원자력 관련 품목은 아니라고 들었는데 통제 분류를 알고 싶습니다.",
        "L2": "직류 형태로 전기를 공급하는 전원 장치를 독일 연구소에 보내려 합니다. 통제 분류를 알고 싶습니다.",
        "L3": "직류 형태로 전기를 내보내는 전원 장치의 통제 분류를 알고 싶습니다.",
        "L4": "직류 전원 장치",
    },
    "g-seungwoo-005": {
        "L1": "이온을 측정하는 질량 분석 장비를 일본 대학에 수출하려 합니다. 통제 품목인지 검토 부탁드립니다.",
        "L2": "이온을 질량에 따라 분리해 측정하는 장비를 일본 대학에 수출하려 합니다. 통제 품목인지 검토 부탁드립니다.",
        "L3": "이온을 질량에 따라 분리해 측정하는 분석 장비의 통제 분류를 알고 싶습니다.",
        "L4": "이온 질량 측정 장비",
    },
    "g-seungwoo-006": {
        "L1": "Our company makes lie-detection instruments and stress-analysis devices for security screening. We want to ship them to a client in Brazil. What is the export category?",
        "L2": "Our company makes instruments that infer deception from a person's physiological signals, used in security screening. We want to ship them to a client in Brazil. What is the export category?",
        "L3": "We would like the export category for instruments that record a person's physiological responses in order to infer deception.",
        "L4": "physiological deception detection instrument",
    },
    "g-seungwoo-007": {
        "L1": "완성 단계의 반도체 소자를 검사하고 시험하기 위해 특별히 만든 장비를 말레이시아 공장에 공급하려 합니다. 분류 확인이 필요합니다.",
        "L2": "반도체 소자를 검사하고 시험하기 위해 특별히 만든 장비를 말레이시아 공장에 공급하려 합니다. 분류 확인이 필요합니다.",
        "L3": "반도체 소자의 전기적 특성을 검사하고 시험하는 장비의 통제 분류를 알고 싶습니다.",
        "L4": "반도체 검사 시험 장비",
    },
    "g-seungwoo-008": {
        "L1": "집적회로 생산을 가능하게 하는 반도체 제조 장비를 중국 협력사에 보내려 합니다. 통제 대상인지 매우 궁금합니다.",
        "L2": "집적회로 생산을 가능하게 하는 반도체 제조 장비를 중국 협력사에 보내려 합니다. 통제 대상인지 매우 궁금합니다.",
        "L3": "집적회로를 만드는 데 쓰는 제조 장비의 통제 분류를 알고 싶습니다.",
        "L4": "반도체 제조 장비",
    },
    "g-seungwoo-009": {
        "L1": "We supply wafer substrates layered with gallium nitride and silicon carbide films for power electronics. A customer in Singapore requested them. Which control code applies?",
        "L2": "We supply wafer substrates carrying deposited compound-semiconductor films for power electronics. A customer in Singapore requested them. Which control code applies?",
        "L3": "We would like the control code for wafer substrates that carry a deposited semiconductor film layer.",
        "L4": "coated semiconductor wafer substrate",
    },
    "g-seungwoo-010": {
        "L1": "전자기 펄스나 정전기 충격이 발생해도 마이크로컴퓨터가 곧바로 정상 동작을 회복하게 만드는 소프트웨어를 해외 방산업체에 제공하려 합니다. 통제 여부를 알고 싶습니다.",
        "L2": "전자기 펄스나 정전기 충격이 발생해도 제어용 컴퓨터가 곧바로 정상 동작을 회복하게 만드는 소프트웨어를 해외 방산업체에 제공하려 합니다. 통제 여부를 알고 싶습니다.",
        "L3": "전기적 충격 이후 컴퓨터가 스스로 정상 동작을 회복하도록 하는 소프트웨어의 통제 분류를 알고 싶습니다.",
        "L4": "컴퓨터 자동 복구 소프트웨어",
    },
    "g-seungwoo-011": {
        "L1": "게이트올어라운드 트랜지스터 구조의 집적회로를 설계하기 위한 전자 설계 자동화 소프트웨어를 대만 팹리스에 공급하려 합니다. 분류 검토가 필요합니다.",
        "L2": "채널을 여러 면에서 감싸는 구조의 트랜지스터로 집적회로를 설계하는 데 쓰는 설계용 소프트웨어를 대만 팹리스에 공급하려 합니다. 분류 검토가 필요합니다.",
        "L3": "집적회로를 설계하는 데 쓰는 소프트웨어의 통제 분류를 알고 싶습니다.",
        "L4": "집적회로 설계 소프트웨어",
    },
    "g-seungwoo-012": {
        "L1": "We license design know-how for building processor cores with advanced arithmetic units. A firm in India wants the package. What classification is this?",
        "L2": "We license design know-how for building processor cores that carry out arithmetic operations in hardware. A firm in India wants the package. What classification is this?",
        "L3": "We would like the classification for design know-how used to build a microprocessor core.",
        "L4": "microprocessor design technology",
    },
    "g-seungwoo-013": {
        "L1": "실리콘 웨이퍼를 절삭하고 연마하는 데 필요한 공정 기술을 외국 파운드리에 이전하려 합니다. 통제 대상인지 확인 부탁드립니다.",
        "L2": "반도체 웨이퍼를 절삭하고 연마하는 데 필요한 기술을 외국 파운드리에 이전하려 합니다. 통제 대상인지 확인 부탁드립니다.",
        "L3": "반도체 웨이퍼 표면을 깎고 매끄럽게 다듬는 기술의 통제 분류를 알고 싶습니다.",
        "L4": "웨이퍼 가공 기술",
    },
    "g-seungwoo-014": {
        "L1": "We have analog and digital computing units modified for use in missile platforms. A defense partner abroad requested them. Could you confirm the export control code?",
        "L2": "We have analog and digital computing units modified for use in missile platforms. A defense partner abroad requested them. Could you confirm the export control code?",
        "L3": "We would like the export control code for analog and digital computing units built for a severe operating environment.",
        "L4": "ruggedised analog digital computer",
    },
    "g-seungwoo-015": {
        "L1": "실시간 처리 장비를 위해 소스 코드를 자동으로 생성해 주는 운영체제 소프트웨어를 해외 업체에 납품할 예정입니다. 통제 분류를 알고 싶습니다.",
        "L2": "실시간 처리 장비를 위해 소스 코드를 자동으로 생성해 주는 운영체제 소프트웨어를 해외 업체에 납품할 예정입니다. 통제 분류를 알고 싶습니다.",
        "L3": "실시간 처리 장비용 소스 코드를 자동으로 만들어 주는 소프트웨어의 통제 분류를 알고 싶습니다.",
        "L4": "소스 코드 자동 생성 소프트웨어",
    },
    "g-seungwoo-016": {
        "L1": "무인 비행체에 쓰도록 설계된 원격 측정 및 원격 제어 장비를 외국 항공우주 기관에 보내려 합니다. 분류 확인이 필요합니다.",
        "L2": "무인 비행체에 쓰도록 설계된 원격 측정 및 원격 제어 장비를 외국 항공우주 기관에 보내려 합니다. 분류 확인이 필요합니다.",
        "L3": "원격으로 측정값을 받고 명령을 전달하는 장비의 통제 분류를 알고 싶습니다.",
        "L4": "원격 측정 제어 장비",
    },
    "g-seungwoo-017": {
        "L1": "We make devices that can covertly capture wire and electronic communications. A buyer in the Middle East is interested. What is the proper export classification?",
        "L2": "We make devices that can covertly capture wire and electronic communications. A buyer in the Middle East is interested. What is the proper export classification?",
        "L3": "We would like the export classification for devices that intercept communications signals without the parties being aware.",
        "L4": "communications interception device",
    },
    "g-seungwoo-019": {
        "L1": "물속에서 전기장을 감지하는 센서와 자기장 측정 장비를 외국 해양연구소에 수출하려 합니다. 군용 가능성도 있어 분류 확인이 필요합니다.",
        "L2": "물속에서 전기장을 감지하는 센서와 자기장 측정 장비를 외국 해양연구소에 수출하려 합니다. 군용 가능성도 있어 분류 확인이 필요합니다.",
        "L3": "전기장과 자기장을 감지하고 측정하는 센서 장비의 통제 분류를 알고 싶습니다.",
        "L4": "자기장 감지 센서",
    },
    "g-seungwoo-020": {
        "L1": "Our product is a sensor hardened against nuclear radiation effects, usable on missile platforms. A foreign client asked about it. Which ECCN?",
        "L2": "Our product is a sensor hardened against nuclear radiation effects, usable on missile platforms. A foreign client asked about it. Which classification applies?",
        "L3": "We would like the classification for a detector component built to keep working after exposure to ionising radiation.",
        "L4": "radiation hardened sensor",
    },
    "g-seungwoo-021": {
        "L1": "공중이나 해상에서 중력 값을 측정하는 장비를 외국 측량 회사에 공급하려 합니다. 통제 대상인지 알고 싶습니다.",
        "L2": "공중이나 해상에서 중력 값을 측정하는 장비를 외국 측량 회사에 공급하려 합니다. 통제 대상인지 알고 싶습니다.",
        "L3": "중력의 크기와 변화를 재는 장비의 통제 분류를 알고 싶습니다.",
        "L4": "중력 측정 장비",
    },
    "g-seungwoo-022": {
        "L1": "물속 물체를 탐지하고 위치를 파악하는 해양 음향 장비를 동남아 조선소에 납품할 예정입니다. 분류 검토가 필요합니다.",
        "L2": "물속 물체를 탐지하고 위치를 파악하는 해양 음향 장비를 동남아 조선소에 납품할 예정입니다. 분류 검토가 필요합니다.",
        "L3": "소리를 이용해 물속 물체를 탐지하고 위치를 파악하는 장비의 통제 분류를 알고 싶습니다.",
        "L4": "수중 음향 탐지 장비",
    },
    "g-seungwoo-023": {
        "L1": "We sell optical sensing fiber that is structurally modified so that the two polarisation modes travel differently. A customer in Europe wants it. What classification applies?",
        "L2": "We sell optical sensing fiber that is structurally modified so that the two polarisation modes travel differently. A customer in Europe wants it. What classification applies?",
        "L3": "We would like the classification for optical fibre whose structure is modified so that light of different polarisations propagates differently.",
        "L4": "polarisation sensing optical fibre",
    },
    "g-seungwoo-024": {
        "L1": "카메라와 영상 장치의 성능을 끌어올리거나 제한을 풀어주는 소프트웨어를 해외 연구기관에 제공하려 합니다. 통제 여부를 확인하고 싶습니다.",
        "L2": "카메라와 영상 장치의 성능을 끌어올리거나 제한을 풀어주는 소프트웨어를 해외 연구기관에 제공하려 합니다. 통제 여부를 확인하고 싶습니다.",
        "L3": "영상 장치의 성능 제한을 해제하거나 향상시키는 소프트웨어의 통제 분류를 알고 싶습니다.",
        "L4": "카메라 성능 향상 소프트웨어",
    },
    "g-seungwoo-025": {
        "L1": "도플러 속도계를 방위 기준과 결합한 수중 음향 항법 시스템을 외국 해군 협력사에 수출하려 합니다. 분류 확인 부탁드립니다.",
        "L2": "주파수 변화로 속도를 재는 장치를 방위 기준과 결합한 수중 음향 항법 시스템을 외국 해군 협력사에 수출하려 합니다. 분류 확인 부탁드립니다.",
        "L3": "소리의 주파수 변화로 속도를 재고 방위 기준과 결합해 위치를 계산하는 수중 항법 장치의 통제 분류를 알고 싶습니다.",
        "L4": "수중 음향 항법 장치",
    },
    "g-seungwoo-026": {
        "L1": "Our device determines orientation by automatically tracking stars or satellites, used for navigation. A foreign aerospace firm requested a sample. Which control code?",
        "L2": "Our device determines orientation by automatically tracking stars or satellites, used for navigation. A foreign aerospace firm requested a sample. Which control code?",
        "L3": "We would like the control code for a device that finds its own orientation by automatically tracking celestial objects.",
        "L4": "star tracking attitude sensor",
    },
    "g-seungwoo-027": {
        "L1": "특정 전자기 발생원의 방위를 알아내는 수동형 방향 탐지 센서를 외국 업체에 보내려 합니다. 미사일 용도 가능성이 있어 분류 확인이 필요합니다.",
        "L2": "특정 전자기 발생원의 방위를 알아내는 수동형 방향 탐지 센서를 외국 업체에 보내려 합니다. 미사일 용도 가능성이 있어 분류 확인이 필요합니다.",
        "L3": "스스로 신호를 내지 않고 전자기 신호가 오는 방향을 알아내는 센서의 통제 분류를 알고 싶습니다.",
        "L4": "수동형 방향 탐지 센서",
    },
    "g-seungwoo-028": {
        "L1": "We provide know-how needed to operate and maintain military acoustic and radar gear that falls outside standard munitions lists. A partner abroad asked. What ECCN is this?",
        "L2": "We provide know-how needed to operate and maintain acoustic and radar equipment for military users. A partner abroad asked. What is the classification?",
        "L3": "We would like the classification for technical know-how used to operate and maintain acoustic and electromagnetic sensing equipment.",
        "L4": "acoustic sensor maintenance technology",
    },
    "g-seungwoo-029": {
        "L1": "로켓이나 무인기의 레이더 반사 면적을 측정하기 위해 특별히 만든 시스템을 외국 항공 회사에 공급하려 합니다. 통제 여부가 궁금합니다.",
        "L2": "로켓이나 무인기의 레이더 반사 면적을 측정하기 위해 특별히 만든 시스템을 외국 항공 회사에 공급하려 합니다. 통제 여부가 궁금합니다.",
        "L3": "물체가 되돌려 보내는 전파의 양을 측정하는 시스템의 통제 분류를 알고 싶습니다.",
        "L4": "전파 반사 측정 시스템",
    },
    "g-seungwoo-030": {
        "L1": "Our software boosts the performance of frequency converters and generators. A buyer overseas requested it. Which export classification fits?",
        "L2": "Our software boosts the performance of frequency converters and generators. A buyer overseas requested it. Which export classification fits?",
        "L3": "We would like the export classification for software that raises the achievable performance of frequency conversion equipment.",
        "L4": "frequency converter enhancement software",
    },
    "g-yechan-001": {
        "L1": "국내 총기 액세서리 업체가 사냥용 조준경 모듈과 교체용 렌즈 하우징을 캐나다 유통사에 보내려 합니다. 군용 장비는 아니라고 하나 공개 통제목록 후보를 사전에 확인하고 싶습니다.",
        "L2": "국내 총기 액세서리 업체가 사냥용 조준경 모듈과 교체용 렌즈 하우징을 캐나다 유통사에 보내려 합니다. 군용 장비는 아니라고 하나 공개 통제목록 후보를 사전에 확인하고 싶습니다.",
        "L3": "광학 조준 장치와 교체용 렌즈 하우징 부품의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "광학 조준 장치 부품",
    },
    "g-yechan-002": {
        "L1": "시위 대응 장비 제조사가 차량 탑재형 살수 장비를 중동 지역 공공기관에 납품하려고 합니다. 군사 장비가 아니라는 설명만으로 충분한지 후보 항목 검토가 필요합니다.",
        "L2": "시위 대응 장비 제조사가 차량 탑재형 살수 장비를 중동 지역 공공기관에 납품하려고 합니다. 군사 장비가 아니라는 설명만으로 충분한지 후보 항목 검토가 필요합니다.",
        "L3": "차량에 실어 물을 세게 뿌리는 장비의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "차량 탑재 살수 장비",
    },
    "g-yechan-003": {
        "L1": "방호장비 회사가 경찰용 헬멧과 투명 보호판을 남미 조달청 입찰에 공급하려 합니다. 일반 안전장비와 구분되는 통제목록 후보가 있는지 사전 확인이 필요합니다.",
        "L2": "방호장비 회사가 경찰용 헬멧과 투명 보호판을 남미 조달청 입찰에 공급하려 합니다. 일반 안전장비와 구분되는 통제목록 후보가 있는지 사전 확인이 필요합니다.",
        "L3": "머리를 보호하는 헬멧과 얼굴을 가리는 투명 보호판의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "방호 헬멧 보호판",
    },
    "g-yechan-004": {
        "L1": "교정시설 장비 납품사가 해외 교도소에 전자식 구속 벨트와 고정 의자 부품을 공급하려 합니다. 인권 민감 품목이라 수출 전 후보 분류를 확인하고 싶습니다.",
        "L2": "교정시설 장비 납품사가 해외 교도소에 전자식 구속 벨트와 고정 의자 부품을 공급하려 합니다. 인권 민감 품목이라 수출 전 후보 분류를 확인하고 싶습니다.",
        "L3": "사람의 움직임을 물리적으로 제한하는 장치와 그 부품의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "인체 구속 장치 부품",
    },
    "g-yechan-005": {
        "L1": "항공 부품사가 탄소섬유 적층 패널을 프랑스 위성 구조물 업체에 샘플로 보내려 합니다. 단순 복합재인지 통제목록 후보가 될 수 있는지 검토 요청입니다.",
        "L2": "항공 부품사가 섬유 강화 적층 패널을 프랑스 위성 구조물 업체에 샘플로 보내려 합니다. 단순 복합재인지 통제목록 후보가 될 수 있는지 검토 요청입니다.",
        "L3": "섬유로 보강한 층 구조 복합재 패널의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "복합재 적층 패널",
    },
    "g-yechan-006": {
        "L1": "연구소가 화학 누출 현장 대응용 휴대형 탐지기와 보호 장구 세트를 싱가포르 파트너에게 이전하려 합니다. 비군사용 안전 장비지만 후보 항목 확인이 필요합니다.",
        "L2": "연구소가 화학 누출 현장 대응용 휴대형 탐지기와 보호 장구 세트를 싱가포르 파트너에게 이전하려 합니다. 비군사용 안전 장비지만 후보 항목 확인이 필요합니다.",
        "L3": "유해 화학물질을 감지하는 휴대형 탐지기와 인체 보호 장구의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "화학물질 탐지 보호 장비",
    },
    "g-yechan-007": {
        "L1": "방탄복 제조사가 경호업체용 방호 조끼와 세라믹 삽입판을 아랍에미리트에 판매하려 합니다. 개인 보호용이라고 하지만 사전 후보검색이 필요합니다.",
        "L2": "방탄복 제조사가 경호업체용 방호 조끼와 단단한 삽입판을 아랍에미리트에 판매하려 합니다. 개인 보호용이라고 하지만 사전 후보검색이 필요합니다.",
        "L3": "총탄을 막는 몸통 방호 조끼와 그 삽입판의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "몸통 방호 조끼",
    },
    "g-yechan-008": {
        "L1": "로봇 장비 업체가 의심 물체 제거용 원격 작업 플랫폼을 우크라이나 민간 복구 프로젝트에 기증하려 합니다. 폭발물 처리 가능성이 있어 후보 항목을 확인하고 싶습니다.",
        "L2": "로봇 장비 업체가 의심 물체 제거용 원격 작업 플랫폼을 우크라이나 민간 복구 프로젝트에 기증하려 합니다. 폭발물 처리 가능성이 있어 후보 항목을 확인하고 싶습니다.",
        "L3": "사람이 접근하지 않고 원격으로 위험 물체를 다루는 작업 장비의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "원격 위험물 처리 장비",
    },
    "g-yechan-009": {
        "L1": "드론 개발사가 레이더와 열 신호를 낮추는 외장 코팅 시제품을 터키 협력사에 테스트용으로 보내려 합니다. 항공 플랫폼 적용 가능성이 있어 통제목록 후보를 봐야 합니다.",
        "L2": "드론 개발사가 레이더와 열 신호를 낮추는 외장 코팅 시제품을 터키 협력사에 테스트용으로 보내려 합니다. 항공 플랫폼 적용 가능성이 있어 통제목록 후보를 봐야 합니다.",
        "L3": "물체가 되돌려 보내는 전파와 방출하는 열을 줄이는 표면 코팅 재료의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "전파 열 저감 코팅",
    },
    "g-yechan-010": {
        "L1": "복합재 설비 회사가 항공기용 적층 부품 생산라인의 자동 검사 장비를 이탈리아 공장에 설치하려 합니다. 제작 장비 자체가 통제목록 후보인지 문의합니다.",
        "L2": "복합재 설비 회사가 항공기용 적층 부품 생산라인의 자동 검사 장비를 이탈리아 공장에 설치하려 합니다. 제작 장비 자체가 통제목록 후보인지 문의합니다.",
        "L3": "섬유 복합재 부품을 만드는 생산 설비와 그 검사 장비의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "복합재 제조 설비",
    },
    "g-yechan-011": {
        "L1": "금속 소재 업체가 합금 분말 제조용 분무 설비를 인도 합작법인에 이전하려 합니다. 일반 분말 장비인지 통제목록 후보인지 사전 확인을 요청합니다.",
        "L2": "금속 소재 업체가 합금 분말 제조용 분무 설비를 인도 합작법인에 이전하려 합니다. 일반 분말 장비인지 통제목록 후보인지 사전 확인을 요청합니다.",
        "L3": "녹인 금속을 미세한 방울로 흩뿌려 합금 분말을 만드는 설비의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "금속 분말 제조 설비",
    },
    "g-yechan-012": {
        "L1": "화학 장비 회사가 추진제 원료를 균질하게 섞는 산업용 혼합기를 브라질 로켓 연구기관에 납품하려 합니다. 연구용 장비라며 후보검색을 요청했습니다.",
        "L2": "화학 장비 회사가 추진제 원료를 균질하게 섞는 산업용 혼합기를 브라질 로켓 연구기관에 납품하려 합니다. 연구용 장비라며 후보검색을 요청했습니다.",
        "L3": "여러 원료를 고르게 섞는 산업용 혼합 장치의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "산업용 원료 혼합 장치",
    },
    "g-yechan-013": {
        "L1": "A carbon fiber producer is quoting continuous reinforcement tow and pre-impregnated sheets for a satellite structure vendor in Spain. The export team wants candidate categories before releasing samples.",
        "L2": "A fibre producer is quoting continuous reinforcement strands and resin-coated sheet material for a satellite structure vendor in Spain. The export team wants candidate categories before releasing samples.",
        "L3": "We would like candidate control categories for continuous reinforcement fibre strands and resin-coated sheet material.",
        "L4": "reinforcement fibre material",
    },
    "g-yechan-014": {
        "L1": "A chemical distributor plans to send solid rocket ingredient chemicals to a university propulsion lab in the United Kingdom. The customer says it is for academic testing, but the supplier needs a candidate-code review.",
        "L2": "A chemical distributor plans to send solid rocket ingredient chemicals to a university propulsion lab in the United Kingdom. The customer says it is for academic testing, but the supplier needs a candidate-code review.",
        "L3": "We would like candidate control codes for chemical ingredients used to make solid propellant.",
        "L4": "solid propellant ingredient chemicals",
    },
    "g-yechan-015": {
        "L1": "베어링 업체가 스핀들용 베어링 조립품을 독일 공작기계 제조사에 공급하려 합니다. 일반 산업재로만 보기 어려워 수출 전 후보 항목 확인을 요청했습니다.",
        "L2": "베어링 업체가 회전하는 축을 지지하는 베어링 조립품을 독일 공작기계 제조사에 공급하려 합니다. 일반 산업재로만 보기 어려워 수출 전 후보 항목 확인을 요청했습니다.",
        "L3": "회전하는 축을 지지하는 구름 베어링 조립품의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "구름 베어링 조립품",
    },
    "g-yechan-016": {
        "L1": "세라믹 부품 회사가 방사성 금속 용융 실험에 쓰는 도가니를 캐나다 원자력 연구기관에 보내려 합니다. 실험 소모품이지만 후보검색이 필요합니다.",
        "L2": "부품 회사가 방사성 금속을 녹이는 데 쓰는 도가니를 캐나다 원자력 연구기관에 보내려 합니다. 실험 소모품이지만 후보검색이 필요합니다.",
        "L3": "금속을 녹일 때 쓰는 내열 도가니의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "금속 용해 도가니",
    },
    "g-yechan-017": {
        "L1": "밸브 제조사가 부식성 핵연료 공정 라인에 들어가는 차단 밸브를 일본 플랜트 업체에 납품하려 합니다. 재질과 용도 때문에 사전 검토가 필요합니다.",
        "L2": "밸브 제조사가 부식성 핵연료 공정 라인에 들어가는 차단 밸브를 일본 플랜트 업체에 납품하려 합니다. 재질과 용도 때문에 사전 검토가 필요합니다.",
        "L3": "유체 흐름을 막는 차단 밸브의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "유체 차단 밸브",
    },
    "g-yechan-018": {
        "L1": "보안검색 장비 업체가 의복 안 물체를 확인하는 밀리미터파 스캐너를 공항 운영사에 판매하려 합니다. 감시 장비 성격이 있어 후보 항목을 확인합니다.",
        "L2": "보안검색 장비 업체가 전파를 이용해 의복 안 물체를 확인하는 스캐너를 공항 운영사에 판매하려 합니다. 감시 장비 성격이 있어 후보 항목을 확인합니다.",
        "L3": "옷 속에 숨긴 물체를 몸에 닿지 않고 확인하는 검색 장비의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "인체 검색 스캐너",
    },
    "g-yechan-019": {
        "L1": "발전기 업체가 이동식 전원 장치를 아프리카 광산 현장에 공급하려 합니다. 민수 장비지만 야외 작전 지원에 전용될 수 있어 사전 후보검색을 요청합니다.",
        "L2": "발전기 업체가 이동식 전원 장치를 아프리카 광산 현장에 공급하려 합니다. 민수 장비지만 야외 작전 지원에 전용될 수 있어 사전 후보검색을 요청합니다.",
        "L3": "옮겨 쓸 수 있는 발전 및 전원 공급 장치의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "이동식 발전 장치",
    },
    "g-yechan-021": {
        "L1": "소재 공정 장비사가 열과 압력으로 항공용 분말 부품을 치밀화하는 프레스를 스웨덴 연구소에 납품하려 합니다. 장비 사양이 민감해 후보 항목 확인이 필요합니다.",
        "L2": "소재 공정 장비사가 열과 압력으로 항공용 분말 부품을 치밀화하는 프레스를 스웨덴 연구소에 납품하려 합니다. 장비 사양이 민감해 후보 항목 확인이 필요합니다.",
        "L3": "분말 소재에 열과 압력을 함께 가해 치밀한 부품으로 만드는 프레스 장비의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "열간 가압 프레스 장비",
    },
    "g-yechan-022": {
        "L1": "측정 장비 회사가 항공기 엔진 부품 검사에 쓰는 좌표 측정 시스템을 이탈리아 고객에게 공급하려 합니다. 사전 검토가 필요합니다.",
        "L2": "측정 장비 회사가 항공기 엔진 부품 검사에 쓰는 좌표 측정 시스템을 이탈리아 고객에게 공급하려 합니다. 사전 검토가 필요합니다.",
        "L3": "물체 표면의 좌표를 재어 형상을 검사하는 측정 시스템의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "좌표 측정 시스템",
    },
    "g-yechan-023": {
        "L1": "An automation integrator will export a sensor-guided industrial arm for handling hazardous samples inside a shielded laboratory in Finland. The buyer asks for a pre-triage category before procurement.",
        "L2": "An automation integrator will export a sensor-guided industrial arm for handling hazardous samples inside a shielded laboratory in Finland. The buyer asks for a pre-triage category before procurement.",
        "L3": "We would like a candidate control category for a sensor-guided industrial manipulator arm.",
        "L4": "industrial robot manipulator",
    },
    "g-yechan-024": {
        "L1": "A chemical plant builder is quoting glass-lined reactors, corrosion-resistant heat exchangers, and process skid modules for a pesticide precursor facility in Malaysia. Compliance needs a controlled-list candidate before sending the proposal.",
        "L2": "A chemical plant builder is quoting reactors with a chemically inert lining, corrosion-resistant heat exchangers, and pre-assembled process modules for a pesticide precursor facility in Malaysia. Compliance needs a candidate entry before sending the proposal.",
        "L3": "We would like candidate control entries for chemical reaction vessels and heat exchangers built to resist corrosive fluids.",
        "L4": "corrosion resistant chemical equipment",
    },
    "g-yechan-025": {
        "L1": "해양로봇 업체가 케이블 점검용 무인 잠수 조사정과 해상 회수용 선박을 노르웨이 에너지 회사에 판매하려 합니다. 해양 장비 후보 항목을 확인해야 합니다.",
        "L2": "해양로봇 업체가 케이블 점검용 무인 잠수 조사정과 해상 회수용 선박을 노르웨이 에너지 회사에 판매하려 합니다. 해양 장비 후보 항목을 확인해야 합니다.",
        "L3": "사람이 타지 않고 물속에서 움직이는 잠수 조사 장비의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "무인 잠수 장비",
    },
    "g-yechan-026": {
        "L1": "선박 장비 회사가 수중 위치추적 모듈과 추진 부품을 싱가포르 해양 연구기관에 공급하려 합니다. 해저 조사용이지만 공개 목록 후보 확인이 필요합니다.",
        "L2": "선박 장비 회사가 수중 위치추적 모듈과 추진 부품을 싱가포르 해양 연구기관에 공급하려 합니다. 해저 조사용이지만 공개 목록 후보 확인이 필요합니다.",
        "L3": "물속에서 위치를 파악하는 모듈과 수중 추진 부품의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "수중 항해 추진 부품",
    },
    "g-yechan-027": {
        "L1": "조선소가 해저 관측용 잠수정을 호주 대학 컨소시엄에 인도하려 합니다. 민간 연구 목적이지만 잠수 선박 계열 후보 항목을 먼저 확인하려 합니다.",
        "L2": "조선소가 해저 관측용 잠수정을 호주 대학 컨소시엄에 인도하려 합니다. 민간 연구 목적이지만 잠수 선박 계열 후보 항목을 먼저 확인하려 합니다.",
        "L3": "사람이 탑승해 물속에서 운항하는 잠수정의 통제목록 후보를 확인하고 싶습니다.",
        "L4": "유인 잠수정",
    },
    "g-yechan-028": {
        "L1": "A ship model testing facility plans to export a hydrodynamic test channel for measuring propeller signatures to a university in Denmark. The team wants a retrieval label before contracting.",
        "L2": "A ship model testing facility plans to export a hydrodynamic test channel for measuring propeller signatures to a university in Denmark. The team wants a retrieval label before contracting.",
        "L3": "We would like a candidate control category for a water channel used to test how a propeller behaves in flowing water.",
        "L4": "hydrodynamic test channel",
    },
    "g-yechan-029": {
        "L1": "A buoyancy material supplier is sending glass-microsphere foam blocks for underwater instrument housings to a Chilean oceanography project. The export group needs pre-triage because the blocks are designed for underwater deployment.",
        "L2": "A buoyancy material supplier is sending rigid foam blocks that stay buoyant underwater, for instrument housings, to a Chilean oceanography project. The export group needs pre-triage.",
        "L3": "We would like a candidate control entry for rigid foam material that provides buoyancy underwater.",
        "L4": "buoyancy foam material",
    },
    "g-yechan-030": {
        "L1": "An offshore software vendor will provide a control program for an unmanned subsea inspection vehicle used in petroleum pipeline surveys in Qatar. The company wants a category candidate before delivery.",
        "L2": "An offshore software vendor will provide a control program for an unmanned subsea inspection vehicle used in petroleum pipeline surveys in Qatar. The company wants a category candidate before delivery.",
        "L3": "We would like a candidate category for software that controls an unmanned underwater inspection vehicle.",
        "L4": "subsea vehicle control software",
    },
}

# 사전(lexicon)에 담기지 않는 제거 항목 — 사람 판단이 필요한 부분만 주석으로 남긴다.
# 형식: (query_id, level) -> [설명, ...]
MANUAL_REMOVALS: dict[tuple[str, str], list[str]] = {
    ("g-seungwoo-002", "L2"): ["self_reference: '원자력 규제 대상은 아닌데' (통제목록 원문의 NRC 예외조항 인용)"],
    ("g-seungwoo-003", "L2"): ["self_reference: 'It is not under nuclear regulatory scope.' (NRC 예외조항 인용)"],
    ("g-seungwoo-004", "L2"): ["self_reference: '원자력 관련 품목은 아니라고 들었는데' (NRC 예외조항 인용)"],
    ("g-seungwoo-028", "L2"): [
        "self_reference: 'falls outside standard munitions lists' (규제 목록 문언 인용)",
        "regulatory_term: 'What ECCN is this?' -> 'What is the classification?'",
    ],
    ("ext-003", "L2"): ["regulatory_term: 'ECCN' -> 'export control'"],
    ("ext-029", "L2"): ["regulatory_term: 'ECCN-controlled' -> 'controlled'"],
    ("g-seungwoo-020", "L2"): ["regulatory_term: 'Which ECCN?' -> 'Which classification applies?'"],
}


# --------------------------------------------------------------------------
# 5. 조립 + 검증
# --------------------------------------------------------------------------

# 각 등급이 남기도록 설계된 잔존 서술 필드(계수 제외). L4는 기능 표현이 남는지를
# 소형 사전으로 자동 판정한다.
FUNCTION_WORDS = [
    "측정", "감지", "탐지", "냉각", "방호", "검색", "구속", "혼합", "변환", "제어",
    "설계", "복구", "항법", "가공", "제조", "생성", "향상", "차단", "발전", "가압",
    "저감", "조준", "보호", "추진", "잠수", "반사", "분말",
    "measurement", "measuring", "sensing", "detection", "cooling", "control",
    "design", "interception", "enhancement", "maintenance", "tracking",
    "cutting", "encryption", "hardened", "buoyancy", "manipulator", "test",
]


def residual_fields(level: str, text: str) -> list[str]:
    """계수 대상이 아닌 잔존 서술 필드(function / item_category)."""
    out = ["item_category"]
    if level != "L4":
        out.append("function")
    elif any(w.lower() in text.lower() for w in FUNCTION_WORDS):
        out.append("function")
    return sorted(out)


def diff_removed(prev_spans: list[dict], cur_spans: list[dict]) -> list[str]:
    """등급 간 차분으로 '이 등급에서 제거한 항목'을 자동 도출한다."""
    prev = Counter((s["category"], s["surface"].strip()) for s in prev_spans)
    cur = Counter((s["category"], s["surface"].strip()) for s in cur_spans)
    gone = prev - cur
    return [f"{cat}: {surf}" for (cat, surf), n in sorted(gone.items()) for _ in range(n)]


def label_variants(code: str) -> set[str]:
    return {v.lower() for v in {
        code, code.replace("ECCN-", ""), code.replace("ECCN-", "").replace(".", " "),
        code.replace("-", " "),
    } if v}


def leak_hits(text: str, labels: list[str]) -> list[str]:
    """통제번호 누출: 정답 코드 문자열 직접 포함 + 일반 통제번호 정규식."""
    hits = []
    low = (text or "").lower()
    for code in labels:
        for v in label_variants(code):
            if v in low:
                hits.append(f"label:{code}")
                break
    m = rc.CONTROL_CODE_RE.search(text or "")
    if m:
        hits.append(f"control_code_re:{m.group(0)}")
    return hits


def main() -> int:
    src = json.loads(SRC_PATH.read_text(encoding="utf-8"))
    queries = src["queries"]

    missing = [q["id"] for q in queries if q["id"] not in LADDER]
    extra = [k for k in LADDER if k not in {q["id"] for q in queries}]
    if missing or extra:
        print(f"FAIL 재작성 누락 {len(missing)}건 {missing[:5]} / 잉여 {extra}")
        return 1

    problems: list[str] = []
    entries: list[dict] = []

    for q in queries:
        qid = q["id"]
        texts = {"L0": q["query"], **LADDER[qid]}
        levels: dict[str, dict] = {}
        prev_spans: list[dict] = []
        for lv in LEVELS:
            text = texts[lv]
            m = measure(text)
            fields = sorted(set(m["counted_sensitive_fields"]) | set(residual_fields(lv, text)))
            removed = [] if lv == "L0" else diff_removed(prev_spans, m["spans"])
            removed += MANUAL_REMOVALS.get((qid, lv), [])
            levels[lv] = {
                "query": text,
                "sensitive_fields_disclosed": fields,
                "counted_sensitive_fields": m["counted_sensitive_fields"],
                "sensitive_field_count": len(m["counted_sensitive_fields"]),
                "sensitive_token_count": m["sensitive_token_count"],
                "sensitive_span_count": m["sensitive_span_count"],
                "tokens_by_category": m["tokens_by_category"],
                "token_count": m["token_count"],
                "char_count": m["char_count"],
                "removed": removed,
                "detected_spans": [
                    {"category": s["category"], "surface": s["surface"].strip()}
                    for s in m["spans"]
                ],
            }
            prev_spans = m["spans"]

        # --- 항목별 검증 -------------------------------------------------
        counts = [levels[lv]["sensitive_token_count"] for lv in LEVELS]
        if any(b > a for a, b in zip(counts, counts[1:])):
            problems.append(f"{qid}: sensitive_token_count 비단조 {counts}")
        fcounts = [levels[lv]["sensitive_field_count"] for lv in LEVELS]
        if any(b > a for a, b in zip(fcounts, fcounts[1:])):
            problems.append(f"{qid}: sensitive_field_count 비단조 {fcounts}")
        for lv in LEVELS[1:]:
            if re.search(r"\d", levels[lv]["query"]):
                problems.append(f"{qid}/{lv}: L1 이상에 숫자가 남아 있다")
        if levels["L3"]["sensitive_token_count"] != 0:
            problems.append(
                f"{qid}/L3: 계수 민감토큰 잔존 {levels['L3']['counted_sensitive_fields']} "
                f"{[s for s in levels['L3']['detected_spans']]}")
        if levels["L4"]["sensitive_token_count"] != 0:
            problems.append(f"{qid}/L4: 계수 민감토큰 잔존 {levels['L4']['detected_spans']}")
        nw = len(levels["L4"]["query"].split())
        if not (2 <= nw <= 5):
            problems.append(f"{qid}/L4: 단어 수 {nw} (2~5 요구)")
        for lv in LEVELS:
            hits = leak_hits(levels[lv]["query"], q["validated_labels"])
            if hits:
                problems.append(f"{qid}/{lv}: 통제번호 누출 {hits}")

        entries.append({
            "id": qid,
            "lang": q["lang"],
            "origin": q["origin"],
            "validated_labels": q["validated_labels"],
            "levels": levels,
        })

    # --- 전체 요약 --------------------------------------------------------
    lang_counts = dict(Counter(e["lang"] for e in entries))
    per_level = {}
    for lv in LEVELS:
        st = [e["levels"][lv]["sensitive_token_count"] for e in entries]
        fc = [e["levels"][lv]["sensitive_field_count"] for e in entries]
        tk = [e["levels"][lv]["token_count"] for e in entries]
        ch = [e["levels"][lv]["char_count"] for e in entries]
        field_freq = Counter()
        for e in entries:
            field_freq.update(e["levels"][lv]["counted_sensitive_fields"])
        per_level[lv] = {
            "definition": LEVEL_DEFS[lv],
            "mean_sensitive_token_count": round(sum(st) / len(st), 3),
            "mean_sensitive_field_count": round(sum(fc) / len(fc), 3),
            "mean_token_count": round(sum(tk) / len(tk), 3),
            "mean_char_count": round(sum(ch) / len(ch), 2),
            "queries_with_zero_sensitive_tokens": sum(1 for x in st if x == 0),
            "field_frequency": dict(sorted(field_freq.items())),
            "distinct_queries": len({e["levels"][lv]["query"] for e in entries}),
            "identical_to_previous_level": (
                None if lv == "L0" else
                sum(1 for e in entries
                    if e["levels"][lv]["query"] == e["levels"][LEVELS[LEVELS.index(lv) - 1]]["query"])
            ),
        }

    payload = {
        "meta": {
            "purpose": "질의 측(아웃바운드) 노출 등급 사다리. 반환 텍스트가 아니라 "
                       "기업이 외부로 보내는 질의 본문에 남은 민감 필드를 계량한다.",
            "threat_model": "docs/threat_model.md",
            "source": str(SRC_PATH.relative_to(ROOT)).replace("\\", "/"),
            "n_queries": len(entries),
            "language_distribution": lang_counts,
            "origin_distribution": dict(Counter(e["origin"] for e in entries)),
            "levels": LEVEL_DEFS,
            "category_definitions": CATEGORY_DEFS,
            "counted_categories": COUNTED,
            "measurement_note": "문자 수는 민감도의 대리변수가 아니므로 카테고리와 "
                                "카테고리에 귀속된 토큰 수로 센다. function/item_category는 "
                                "잔존 최소 정보이므로 계수에서 제외한다.",
            "automation_split": {
                "automatic": ["수치·단위 정규식", "성능등급 사전", "국가·지역 사전",
                              "고유명칭 사전", "최종사용자/용도/자사정체성/거래형태 사전",
                              "등급 간 차분으로 removed 자동 생성", "단조성·라벨·언어·누출 검증"],
                "manual": ["L1~L4 질의 재작성 문장", "MANUAL_REMOVALS 주석(규제 조문 인용 제거 등)"],
            },
            "limitations": [
                "어휘목록은 71개 L0 질의에 등장한 표현을 열거한 닫힌 사전이다. 다른 "
                "코퍼스로 일반화하려면 확장이 필요하다.",
                "supplier_identity와 end_user의 구분은 한국어 조사(…가/…에)와 영어 정형구에 "
                "의존하므로 일부 항목의 카테고리 라벨이 뒤바뀔 수 있다. 계수 총합은 영향받지 않는다.",
                "재식별 위험(기능 서술만으로 기업·제품이 추정될 가능성)은 측정하지 않았다. 확인 필요.",
            ],
            "seed": SEED,
            "env": rc.env_meta({"seed": SEED}),
        },
        "per_level_summary": per_level,
        "validation": {
            "problems": problems,
            "passed": not problems,
            "checks": [
                "sensitive_token_count / sensitive_field_count 등급 간 단조 비증가",
                "L1 이상에 숫자 없음",
                "L3·L4의 계수 민감토큰 0",
                "L4 단어 수 2~5",
                "모든 등급에서 통제번호 누출 0 (정답코드 문자열 + CONTROL_CODE_RE)",
                "라벨·언어는 등급 간 불변(단일 엔트리에 1회 저장)",
            ],
        },
        "queries": entries,
    }

    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"n={len(entries)}  lang={lang_counts}")
    for lv in LEVELS:
        p = per_level[lv]
        print(f"  {lv}: 민감토큰 {p['mean_sensitive_token_count']:6.3f}  "
              f"필드수 {p['mean_sensitive_field_count']:5.3f}  "
              f"토큰 {p['mean_token_count']:6.2f}  문자 {p['mean_char_count']:6.1f}  "
              f"L0대비동일 {p['identical_to_previous_level']}")
    if problems:
        print(f"\n{len(problems)} PROBLEM(S)")
        for p in problems[:40]:
            print("  -", p)
        return 1
    print(f"\nOK -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
