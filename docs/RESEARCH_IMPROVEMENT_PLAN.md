# 연구 개선 계획 (Research Improvement Plan)

> 대상: 본 저장소에서 작업하는 모든 에이전트/연구자
> 목적: 산업보안논문경진대회 제출을 위한 연구 완성도 제고
> 최종 갱신: 2026-06-26
> 이 문서는 "무엇을, 왜, 어떻게" 고쳐야 하는지를 우선순위와 함께 정리한 작업 지시서다.

---

## 0. 한 줄 요약

현재 연구는 **정직성과 평가 인프라는 좋으나, 헤드라인 성능 수치(합성 R@10 0.9792)가 자기참조(self-retrieval) 설정에서 나온 과대평가**라는 치명적 약점이 있다. 동시에 **외부 평가의 정답 라벨이 검증되지 않은 추정값**이라 R@10=0도 깨끗한 결론이 아니다. 우선순위는 (1) 평가 설계의 타당도 확보 → (2) 실제 baseline 강화 → (3) 논문 서사 재구성 순이다.

---

## 1. 현재 상태 스냅샷

### 1.1 구축된 것 (자산)
- 공개 통제목록 3종 정화 코퍼스 1,797개 (`data/corpus/combined.json`): Wassenaar 2025(585), India SCOMET 2024(575), US eCFR CCL(637)
- 코드 누출 없는 합성 설명형 쿼리 780개 (`generate_queries.py`, `data/queries.json`)
- BM25 투명 baseline + 노출량 proxy + 통계검정(paired permutation) (`run_experiments.py`)
- 4개 노출 조건: `full_text` / `minimal_text` / `minimal_no_code` / `route_only`
- 상담형 모사 외부 질의셋 30개 + 평가 파이프라인 (`evaluate_external_queries.py`, `output/external_eval.*`)
- 한국 법제 연계 문서 (`docs/korean_regulatory_framework.md`)

### 1.2 핵심 수치 (현재)
| 평가셋 | 조건 | R@10 | 비고 |
|---|---|---:|---|
| 합성 780 | minimal_text | 0.9792 | **자기참조 재검색 — 과대평가** |
| 합성 780 | full_text | 0.9968 | 동일 한계 |
| 외부 30 | 전 조건 | 0.0000 | **추정 라벨 기준, 13/30 코드충돌** |

---

## 2. 문제 진단 (우선순위 순)

### P0 — 타당도를 위협하는 치명적 문제

**P0-1. 합성 쿼리 self-derivation (과대평가의 근원)**
`generate_queries.py`는 각 코퍼스 항목 *자기 본문*에서 코드만 빼 쿼리를 만들고, 검색 대상 문서(`minimal_text`)는 *같은 항목 본문의 첫 문장*이다. 쿼리와 정답이 near-duplicate라서 BM25가 0.97을 내는 것은 후보 발견이 아니라 자기 텍스트 재검색이다.
→ 0.9792를 "성능"으로 논문 전면에 내세우면 심사에서 무너진다.

**P0-2. 외부 정답 라벨이 검증 안 된 추정값**
`external_consultation_queries.json`의 `candidate_labels`는 연구자 추정값(`label_confidence: low` 다수)이고, `label_basis`에 의미 불일치가 자백되어 있다(예: 티타늄을 알루미늄 항목에, MRI를 거리가 먼 3A에). 30개 중 **13개가 코드 정규화 충돌**(`2B001`이 SCOMET 생물작용제와 eCFR 공작기계 양쪽 존재)을 가진다.
→ R@10=0은 "BM25 한계"와 "라벨 불확실성"이 혼입된 수치다. 둘을 분리하지 못하면 결론이 약하다.

### P1 — 결과의 깊이/일반화를 막는 문제

**P1-1. 한국어 cross-lingual 미지원**
코퍼스가 100% 영어(한글 포함 항목 0개)인데 질의의 절반이 한국어다. 한국어 16개 중 14개 zero-score는 당연한 결과이며 별도 기여로 분리해야 한다.

**P1-2. baseline이 BM25 단일**
Dense/하이브리드/reranker 비교가 없어 "최소노출 trade-off가 retriever에 얼마나 의존적인가"를 보여주지 못한다.

**P1-3. 노출량 proxy가 문자 수**
영업비밀 민감도와 동일하지 않다. proxy 타당성 논증 또는 가중치 개선 필요.

### P2 — 완성도/신뢰도 보강

- 코퍼스 파싱 표본 수작업 검수(현재 정규식 기반, 미검증)
- 전문가(관세사/수출통제 실무자) 라벨 검수
- 통계검정의 효과크기·신뢰구간 보고
- 재현성: 시드/환경/버전 고정 문서화

---

## 3. 개선 작업 지시 (에이전트용 구체 태스크)

> 각 태스크는 독립 실행 가능하도록 입력/출력/수용기준을 명시한다.

### TASK A (P0) — 정직한 합성 평가셋 재구성: paraphrase split

> **진행 상황 (2026-06-26)**: 1차 완료. `experiment_paraphrase_gap.py`로 자기참조 의존성을
> 정량화했다(쿼리-정답 평균 Jaccard 0.485; 변별토큰 5개 제거 시 minimal_text R@10
> 0.9792→0.7596, 10개 제거 시 0.4407). 산출물: `output/paraphrase_gap.{json,md}`.
> **남은 일**: 아래 A1~A3로 *생성형* 패러프레이즈 평가셋(`data/queries_paraphrased.json`)을
> 별도 구축해 "교정된 헤드라인 R@k"를 확보. 현재 실험은 ablation(증거)이고, A1~A3는 대체 평가셋이다.

**문제**: 쿼리=정답 본문. **목표**: 쿼리를 정답 본문과 어휘적으로 분리.

- 입력: `data/corpus/combined.json`
- 방법(택1 또는 병행):
  - (A1) **Held-out 어휘 분리**: 쿼리 생성 시 정답 항목 본문의 토큰을 일정 비율(예: 50%) 이상 제거/치환하고, 동의어·상위어로 패러프레이즈. 쿼리-정답 자카드 유사도 상한(예: 0.3)을 강제.
  - (A2) **LLM 패러프레이즈**: 정답 본문을 "제품/기술 설명 상담 문장"으로 재서술하되, 통제번호·원문 구절 직접 인용 금지. 생성 후 자카드/코사인으로 leakage 필터.
  - (A3) **교차 출처 평가**: 정답은 한 통제체계(예: Wassenaar) 항목인데, 코퍼스 인덱스는 다른 체계(eCFR) 표현으로 매칭하도록 구성 → 실제 cross-list 후보검색 모사.
- 출력: `data/queries_paraphrased.json` + leakage 리포트(`data/queries_paraphrased_report.json`: 자카드 분포, 제거 토큰 비율)
- 수용기준: 쿼리-정답 평균 자카드 < 0.3, 코드 누출 0건. 이 평가셋에서 다시 R@k 측정 → **이 수치가 진짜 헤드라인이 된다.**

### TASK B (P0) — 검증된 정답을 가진 외부 평가셋 v2

> **진행 상황 (2026-06-26)**: 1차 완료(TASK C 포함). `build_validated_queries.py`로
> `data/external_consultation_queries_validated.json` 생성: 라벨을 eCFR full code로
> 핀 고정(충돌 0), eCFR 텍스트가 항목을 명확히 기술하는 13개만 검증 라벨 부여, 나머지
> 17개는 사유와 함께 metrics 제외. `evaluate_validated_queries.py`로 exact 매칭 재평가:
> BM25 R@10=0(영어 포함), hybrid(α=0.5) 0.2308, 한국어 0→0.20. 라벨 노이즈 제거로
> hybrid가 0.10→0.23으로 약 2배. 산출물: `output/validated_eval.{json,md}`.
> **남은 일**: 전문가(관세사/수출통제 실무자) 검수로 라벨을 법적 수준으로 승격, 표본 확대,
> eCFR 외 통제체계까지 단일출처 정답 확장.

**문제**: 추정 라벨 + 코드 충돌. **목표**: 단일 통제체계로 한정한 신뢰 가능한 정답.

- 방법:
  - (B1) **단일 출처 고정**: 정답을 eCFR ECCN으로만 한정. `normalize_code` 충돌을 없애기 위해 정답을 원본 코드(`ECCN-XXXX`)로 저장하고 비교도 출처 일치까지 검사(아래 TASK C).
  - (B2) **라벨 근거 강화**: 각 질의에 BIS Interactive CCL 또는 공식 결정문 링크를 근거로 첨부. `label_confidence: low`는 제거하거나 high로 끌어올리기 전까지 평가에서 제외 플래그.
  - (B3) **규모 확대**: 가능하면 50~100개로. 단 "검증된 30개"가 "추정된 100개"보다 낫다.
- 출력: `data/external_consultation_queries_v2.json`
- 수용기준: 코드 충돌 0건, 모든 정답에 1차 근거 링크, `label_confidence` 전부 medium 이상.

### TASK C (P0/버그) — 출처 인지 코드 매칭

> **진행 상황 (2026-06-26)**: 완료(TASK B에 통합). 검증셋은 라벨을 full eCFR code로 저장하고
> `evaluate_validated_queries.py`가 exact code equality로 매칭하므로 정규화 충돌이 원천적으로
>발생하지 않는다. 기존 `evaluate_external_queries.py`의 충돌 감사(`has_code_collision`)는 진단용으로 유지.

**문제**: `normalize_code`가 `ECCN-2B001`과 SCOMET `2B001`을 동일시. **목표**: 충돌 무력화.

- 위치: `evaluate_external_queries.py`
- 방법: 정답 라벨에 `source_system`을 필수화하고, 매칭을 `(normalized_code, source)` 쌍으로 수행. 또는 비교 자체를 원본 코드 문자열 기준으로.
- 수용기준: `candidate_label_collision_count`가 평가 로직에서 0이 되거나, 충돌 질의가 명시적으로 제외/표기됨.
- 참고: 충돌 진단 인프라는 이미 추가됨(`has_code_collision`, `candidate_label_collision_count`). 이를 평가 매칭까지 반영하면 됨.

### TASK D (P1) — 한국어 cross-lingual 트랙 분리

- 방법(택1):
  - (D1) `query_en` 번역 필드를 모든 한국어 질의에 추가하고 EN/KO 평가를 별도 보고.
  - (D2) 도메인 한영 동의어 사전(`data/domain_synonyms.json`) 구축 후 쿼리 확장.
  - (D3) 다국어 임베딩(예: bge-m3, 이미 v6.2에서 0.83 언급됨) 기반 dense retrieval로 KO 트랙만 별도 비교.
- 출력: `output/crosslingual_eval.json` + EN-only vs KO-원문 vs KO-번역 비교표.
- 수용기준: "코퍼스가 영어라 한국어가 0점"이라는 당연한 결과를, "번역/임베딩으로 KO가 X→Y로 회복"이라는 정량 기여로 전환.

### TASK E (P1) — retriever 비교 트랙

> **진행 상황 (2026-06-26)**: 1차 완료. `experiment_retriever_compare.py`(합성 어휘격차)와
> `experiment_external_retriever.py`(외부 상담셋) 추가. 발견:
> (1) 자기참조 합성셋에서는 BM25가 모든 어휘격차 레벨에서 dense 우위 → 합성 benchmark는
>     retriever 비교에 부적합. (2) 합성 "한국어" 쿼리가 영어 본문이라 언어 분리가 가짜임을 발견.
> (3) 외부 상담셋에서 BM25 R@10=0인데 hybrid(α=0.5) 0.10, 한국어 0→0.0625로 회복 →
>     다국어 dense의 cross-lingual 가치 입증. 산출물: `output/retriever_compare.{json,md}`,
>     `output/external_retriever.{json,md}`. **남은 일**: LLM reranker(Ollama) 추가는 선택,
>     검증된 라벨셋(TASK B) 확보 후 절대 R@10 재측정.

- 방법: 동일 평가셋(TASK A/B 산출물)에서 BM25 vs dense(bge-m3/e5) vs 하이브리드(BM25+dense, RRF) vs +LLM reranker 비교. 각 조건에서 노출량@10 동시 측정.
- 출력: `output/retriever_comparison.json` + 노출량-R@10 frontier 그래프.
- 핵심 질문: **"최소노출 trade-off 곡선이 retriever를 바꾸면 어떻게 이동하는가."** 이게 논문의 두 번째 축이 될 수 있다.
- 주의: 외부 LLM/임베딩 API 호출은 연구의 "정보최소화" 주제와 충돌하므로, **로컬 모델 사용**과 "인덱싱은 로컬, 쿼리시 외부 호출 없음"을 명시.

### TASK F (P2) — proxy/검수/재현성

- 노출량 proxy: 문자 수 외에 (1) 토큰 수, (2) 고유명사·수치 사양 수(민감도 가중) 버전 추가.
- 코퍼스 검수: 출처별 30개씩 90개 표본 수작업 검수 리포트(`docs/corpus_audit.md`), 파싱 오류율 보고.
- 재현성: `requirements.txt` 버전 핀, 시드 고정 확인, 실행 1커맨드 스크립트.

---

## 4. 평가 프로토콜 권고

1. **두 평가셋을 항상 분리 보고**: (a) 합성-paraphrase(타당도 확보된 헤드라인), (b) 외부-검증(stress test). self-derivation 합성셋의 0.97은 부록으로 강등하고 "왜 과대평가인지" 설명과 함께만 제시.
2. **metric 확장**: R@k 외 MRR, nDCG@k, 그리고 노출량 대비 성능(efficiency frontier)을 주력 지표로.
3. **통계**: 효과크기와 신뢰구간 동반. permutation p값만으로 부족.
4. **negative result를 강점으로**: "self-synthetic→독립 paraphrase 일반화 격차"는 그 자체로 논문 기여. 숨기지 말고 정량화.

---

## 5. 논문 서사 재구성 제안

기존 서사("최소노출로 66% 줄여도 R@10 유지")는 self-derivation 때문에 위태롭다. 더 방어 가능하고 학술적으로 강한 대안 서사:

> **"외부 AI에 기술정보를 노출하는 전략물자 사전검토에서, 정보최소화의 효과는 평가 설계와 retriever 선택에 강하게 의존한다."**
> - 기여 1: 최소노출 평가 프레임워크 + 노출량-성능 frontier 정식화
> - 기여 2: 자기참조 합성평가의 과대평가 위험을 정량 폭로(0.97→독립셋 붕괴)하고, paraphrase/cross-list 평가로 교정
> - 기여 3: 한국 법제(대외무역법·전략물자수출입고시·산업기술보호법·국가핵심기술)와 연계한 보수적 워크플로우 설계 — 판정이 아닌 사전검토 보조로 한정

이 서사는 "성능 자랑"이 아니라 "방법론적 엄밀성 + 보안 도메인 정합성"으로 승부하므로, baseline이 약해도 평가받을 수 있다.

---

## 6. 절대 하지 말 것 (회귀 방지)

- 합성 R@10 0.97을 무수식 헤드라인으로 쓰기
- 외부 R@10=0을 "BM25 현장 성능 0"으로 단정하기
- 추정 라벨을 "정답"으로 호칭하기
- "AI가 전략물자 판정/자가판정 대체" 류 주장 (도메인상 금지)
- 외부 API 호출을 쓰면서 "정보최소화"를 주장하기

---

## 7. 권장 실행 순서

```
TASK C (버그/소) → TASK A (P0, 헤드라인 교정) → TASK B (P0, 외부셋 신뢰화)
   → TASK E (P1, retriever 축) → TASK D (P1, KO 트랙) → TASK F (P2, 보강)
   → 논문 서사 재작성(5장)
```

각 TASK 완료 시 `output/`에 산출물과 리포트를 남기고, README/PAPER의 해당 수치를 갱신할 것.
