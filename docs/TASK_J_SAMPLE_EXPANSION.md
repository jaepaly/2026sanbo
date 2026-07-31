# TASK J — 검증셋 표본 확대 (n=71 → 151)

> 담당: 팀원 2인 분담 / 스펙 작성: 2026-07-31 / 기준 커밋: `85a42d0`
> 선행 읽기: `docs/HANDOFF.md`, `PAPER.md` §4.5·4.8, `docs/RESEARCH_IMPROVEMENT_PLAN.md` TASK G

---

## 0. 왜 이걸 하는가

PAPER 4.8이 한계 6을 닫으면서 **새 문제**를 드러냈다. 질의 노출 사다리의 **운용 권고 등급이 인코더에 따라 갈린다.**

| 인코더 | L1 등가 입증 | L2 판정 | 권고 |
|---|---|---|---|
| MiniLM | 예 (TOST p_max 0.0063) | 검정력 부족 | L2 |
| e5-base | 예 (p_max 0.0054) | 검정력 부족 | L2 |
| bge-m3 | **아니오** (p_max 0.402) | **손실 징후** (−0.0704 > δ=0.05) | **L1** |

그래서 논문은 보수적으로 L1을 권고한다. 이 분기가 **진짜 모델 차이인지, 아니면 n=71의 잡음인지**가 현재 가장 큰 미해결 질문이다. 표본을 늘리면 답이 나온다.

부수적으로, 대칭 ablation에서 e5-base가 최대 압력 level 3에서 유의성을 잃는 것(+0.0845, p=0.109, 8승 2패)도 검정력 문제일 가능성이 있다.

---

## 1. ⚠ 먼저 알아야 할 한계 — 완전 해결은 불가능하다

정직하게 못 박는다. **이 확장으로 L2 등가를 δ=0.05에서 입증할 수는 없다.**

- L2 등가 입증에 필요한 표본: **n ≈ 1,102** (`output/disclosure_frontier.json` → `required_n_for_delta_0.05`)
- 현재 코퍼스에서 새 질의를 만들 수 있는 eCFR 항목: **257개**
  (eCFR 637 − 이미 정답으로 쓴 70 = 567, 그중 표제 스텁이 아니라 설명 가능한 것이 257)
- 따라서 **이론적 최대 n = 71 + 257 = 328**. 1,102에 한참 못 미친다.

즉 **δ=0.05에서의 L2 등가 입증은 이 코퍼스로 구조적으로 도달 불가**다. 그것을 목표로 삼지 마라. (참고: δ=0.1로 완화하면 L2는 이미 등가다. 마진 완화는 사전지정 위반이므로 사후에 하지 않는다.)

### 그럼 +80은 무엇을 사는가

1. **모델 분기의 정체 규명** — bge-m3의 L2 손실 징후(−0.0704)가 n=151에서도 유지되면 진짜 모델 차이이고, 사라지면 n=71의 잡음이었다는 뜻이다. **어느 쪽이든 논문이 쓸 수 있는 답이다.**
2. **검정력 회복** — 표준오차가 대략 √(151/71) ≈ 1.46배 줄어 CI가 좁아진다. e5-base ablation level 3의 비유의(p=0.109)가 유의로 바뀌는지 확인된다.
3. **라벨 결함 희석** — 현재 정답이 전부 표제 스텁인 질의가 42/71(59.2%)이다. 새 질의는 **비스텁 항목에서만** 만들므로 이 비율이 내려간다.

---

## 2. 배정

미사용 eCFR 항목 257개(비스텁)를 카테고리로 나눈다. **서로 겹치지 않게** 각자 40개.

| 담당 | 배정 구간 | 목표 |
|---|---|---:|
| 팀원 1 (이예찬) | eCFR 카테고리 **0·1·2·8** (`0xxx`,`1xxx`,`2xxx`,`8xxx`) 중 **미사용·비스텁** 항목 | 40 |
| 팀원 2 (장승우) | eCFR 카테고리 **3·4·5·6·7·9** (`3xxx`~`9xxx`) 중 **미사용·비스텁** 항목 | 40 |

TASK G와 같은 분할이라 그때 안 쓴 항목이 그대로 남아 있다. 자기 구간에서 다음 조건을 만족하는 항목만 고른다.

- `source == "ecfr_part774"`
- 그 코드가 `data/validated_queries_expanded.json`의 어떤 `validated_labels`에도 없을 것 (미사용)
- 본문에 `(see List of Items Controlled)` 계열 문구가 **없을 것** (비스텁 — 기술 파라미터가 코퍼스에 실제로 있어야 한다)
- 본문 150자 이상 권장

확인 명령:

```bash
python - <<'PY'
import json, re
c = json.load(open('data/corpus/combined.json', encoding='utf-8'))
q = json.load(open('data/validated_queries_expanded.json', encoding='utf-8'))['queries']
used = {lbl for x in q for lbl in x['validated_labels']}
STUB = re.compile(r'\(\s*see\s+(?:the\s+)?list\s+of\s+items\s+cont(?:r)?ol', re.I)
MY = ('ECCN-0', 'ECCN-1', 'ECCN-2', 'ECCN-8')      # ← 자기 구간으로 바꿀 것
pool = [e for e in c
        if e['source'] == 'ecfr_part774'
        and e['code'] not in used
        and not STUB.search(e.get('text') or '')
        and e['code'].startswith(MY)
        and len(e.get('text') or '') >= 150]
print(len(pool), '개 사용 가능')
for e in pool[:5]:
    print(' ', e['code'], e['text'][:90].replace('\n', ' '))
PY
```

---

## 3. 만들 것 — 질의 1개당 사다리 5단계

TASK G와 다른 점: **질의 하나마다 L0~L4 다섯 버전을 다 써야 한다.** 사다리(4.5)가 미해결 질문의 무대이기 때문이다. 40개 질의 = 200개 문장.

| 등급 | 무엇을 지우나 |
|---|---|
| **L0** | 원문 그대로. 실제 상담처럼 정량 사양치·제품명·목적지·최종사용자·용도·자사 정체성·거래 형태를 자연스럽게 포함 |
| **L1** | L0 − **정량 사양치** (수치+단위, 정밀도·공차·성능 등급 표현 전부) |
| **L2** | L1 − **고유명칭** (제품·모델·공정·상표·특정 재료/기술 고유명) + 규제 조문 인용 문구 |
| **L3** | L2 − **최종사용자·목적지·용도·자사 정체성·거래 형태** → 기능·물리 원리만 남김 |
| **L4** | 카테고리 키워드만 (2~5 단어) |

기존 71개의 실제 사다리 예시가 `data/disclosure_ladder.json`에 전문으로 있다. **반드시 몇 개 읽고 같은 톤·같은 삭제 기준으로 쓸 것.**

### 스키마 (`data/validated_queries_slice_j_<이름>.json`)

```json
{"queries": [
  {
    "id": "j-<이름>-001",
    "lang": "ko",
    "query": "<L0 원문>",
    "context": "국가/용도 요약",
    "validated_labels": ["ECCN-XXXX"],
    "label_confidence": "high",
    "label_basis_corpus_text": "해당 eCFR 텍스트 근거",
    "ladder": {
      "L0": "<L0 원문 = query 와 동일>",
      "L1": "<정량 사양치 제거>",
      "L2": "<+ 고유명칭 제거>",
      "L3": "<+ 사용자·목적지·용도·정체성·거래 제거, 기능만>",
      "L4": "<카테고리 키워드 2~5 단어>"
    }
  }
]}
```

---

## 4. ⚠ 자기참조를 만들지 마라 (가장 중요)

이 프로젝트에서 두 번 데인 함정이다.

1. **코퍼스 v3 반증**(HANDOFF §6): 검증 질의는 "그 당시 코퍼스에 있던 표제를 읽고" 역생성됐다. 나중에 본문을 채우자 질의가 본 적 없는 텍스트라 매칭에 기여하지 못했다.
2. **L3 교란 판정**(PAPER 4.5): 상위 등급 재작성이 질의를 기능 서술만 남기는데 그게 통제목록 원문의 문체라, 질의가 정답 문서 쪽으로 표류해 회수율이 유지됐다. **그래서 L3는 운용 근거에서 배제됐다.**

따라서:

- **항목 원문의 표현을 베끼지 마라.** 그 품목을 아는 실무자가 자기 말로 묻듯이 써라.
- 특히 **L3를 쓸 때** 통제목록 문체("...으로 specially designed된...")로 수렴시키지 마라. 기능을 남기되 **일상적 기술 어휘**로 써라.
- 통제번호와 그 변형을 질의에 절대 넣지 마라.

---

## 5. 제출 전 필수 검증

```bash
python validate_query_slice.py data/validated_queries_slice_j_<이름>.json
```

**exit 0 (모든 게이트 통과)** 이어야 한다. 게이트: 라벨이 정확한 eCFR 코드 / 코드누출 0 / 어휘 Jaccard < 0.30 / **의미 게이트(제3 인코더)** / 한국어 비율 ≥ 0.40 / 정답 코드 재사용 없음.

실패하면 해당 질의를 고쳐 다시 통과시킨다. **통과하지 못한 파일은 보내지 마라.**

---

## 6. 수용 기준

- 질의 40개 이상, 각 질의에 L0~L4 다섯 버전 전부
- 한국어 비율 ≥ 0.40
- 정답 코드가 기존 71개 및 상대 슬라이스와 겹치지 않음
- 정답이 **비스텁** eCFR 항목
- `validate_query_slice.py` exit 0
- `docs/RESULT_REPORT_TEMPLATE.md` 양식 리포트 동봉

---

## 7. 팀장이 받은 뒤 (재실행 순서)

HANDOFF §7 ①의 코퍼스 변경 순서에 준한다. 질의셋이 바뀌므로 사다리·감사·평가를 전부 다시 돌린다.

```
슬라이스 검증 → 병합(n=151) → build_disclosure_ladder.py
→ audit_ladder_selfreference.py      (새 L3가 또 교란인지 반드시 재판정)
→ audit_label_quality.py audit
→ experiment_disclosure_frontier.py
→ run_tier1.py <각 모델> → validate_tier1.py → report_tier1_crossmodel.py
→ merge_shards.py 계열 재실행 → report_exposure_decomposition.py
→ experiment_label_sensitivity.py
→ make_figures.py → experiment_stats.py → verify_claims.py
```

**핵심 확인 질문**: n=151에서 bge-m3의 L2 판정이 여전히 "손실 징후"인가? 유지되면 모델 차이가 실재하는 것이고, 사라지면 n=71의 검정력 부족이었다는 뜻이다. 어느 쪽이든 PAPER 4.8과 운용 권고를 그 결과로 갱신한다.

---

## 8. 에이전트 프롬프트 (복붙용)

```
이 저장소(2026sanbo)는 전략물자 사전 트리아지 정보최소화 연구다. 먼저 docs/HANDOFF.md,
docs/TASK_J_SAMPLE_EXPANSION.md, PAPER.md 4.5·4.8절을 읽어 맥락과 가드레일을 파악하라.
그다음 TASK J를 수행한다.

- 내 배정 구간은 <배정구간>이다. data/corpus/combined.json 에서 source=ecfr_part774 이고,
  data/validated_queries_expanded.json 의 어떤 validated_labels 에도 없고(미사용),
  본문에 "(see List of Items Controlled)" 계열 문구가 없는(비스텁) 항목 중 내 구간에서
  40개를 고른다. 스펙 2절의 확인 명령을 그대로 쓰면 된다.
- 각 항목마다 그 항목을 묘사하는 상담형 질의를 쓰고, 스펙 3절 표에 따라 L0~L4 다섯
  버전을 모두 작성한다. data/disclosure_ladder.json 의 기존 예시를 반드시 몇 개 읽고
  같은 톤·같은 삭제 기준을 따른다.
- 자기참조 금지(스펙 4절): 항목 원문 표현을 베끼지 말고, 특히 L3를 통제목록 문체로
  수렴시키지 마라. 통제번호와 그 변형을 질의에 넣지 마라. 한국어 40% 이상.
- data/validated_queries_slice_j_<이름>.json 에 스펙 3절 스키마대로 저장한다.
- 제출 전 반드시 `python validate_query_slice.py data/validated_queries_slice_j_<이름>.json`
  을 실행해 exit 0 을 확인하라. 실패한 질의는 고쳐서 다시 통과시켜라.

금지: 라벨을 "법적 정답"으로 호칭, "AI가 전략물자 판정" 류 주장, 항목 원문 베껴쓰기.
마지막으로 docs/RESULT_REPORT_TEMPLATE.md 양식으로 report_task_j_<이름>.md 를 채우고,
슬라이스 JSON 과 검증 통과 출력을 함께 제출하면 된다고 안내하라.
```
