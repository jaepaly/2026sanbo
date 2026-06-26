# 논문 초안 메모 — 전략물자 AI 사전 트리아지

## 권장 제목

기술정보 최소노출과 전략물자 후보검색 성능의 상충관계: 공개 통제목록 기반 설명형 쿼리 실험

## 초록 초안

외부 인공지능 또는 검색 서비스를 활용해 전략물자 통제목록 후보를 탐색할 때, 기업은 기술사양과 제품 설명을 외부 시스템에 전송해야 하는 부담을 가진다. 본 연구는 법적 판정이 아닌 사전 후보검색 단계에서, 반환·처리되는 통제목록 정보량을 줄이면서 후보검색 성능을 얼마나 유지할 수 있는지 실험적으로 분석한다. Wassenaar Arrangement 2025, India SCOMET 2024, U.S. eCFR Commerce Control List의 공개 통제목록을 정화하여 1,797개 항목의 코퍼스를 구축하고, 정답 통제번호가 포함되지 않는 설명형 합성 쿼리 780개를 생성하였다. BM25 기준선 실험 결과, `minimal_text` 조건은 `full_text` 대비 평균 노출량@10을 약 66.4% 감소시키면서 Recall@10 0.9792를 유지했다. 다만 이 합성 쿼리는 코퍼스 항목 자기 본문에서 파생되어 정답 문서와 near-duplicate 관계이므로, 이 절대수치는 자기참조 재검색에 가깝고 후보 발견 능력으로 직접 일반화되지 않는다. 

추가로, 본 연구는 상담형 모사 질의셋(`data/external_consultation_queries.json`) 30개를 `evaluate_external_queries.py`로 평가하였다. synthetic benchmark에서는 minimal_text가 R@10 0.9792를 보였으나, 상담형 모사 질의셋에서는 R@10=0이 나왔다. 이는 BM25-only baseline이 어휘 불일치·도메인 설명 격차에서 구조적으로 약하다는 한계를 명확히 보여준다. 본 연구의 기여는 최종 성능 시스템이 아니라 최소정보노출 평가 프레임워크와 baseline 구축이다. 외부 질의 결과는 개선 필요성을 보여주는 stress test다. 한국 대외무역법·전략물자 수출입고시·산업기술보호법·국가핵심기술 제도와 연계하여, 최소정보노출형 사전검토 workflow를 제안한다. 다만, 본 시스템이 실제 현장 검증을 완료한 것은 아니다.

## 연구질문

1. 정답 통제번호를 쿼리에 포함하지 않는 설명형 쿼리에서도 공개 통제목록 후보검색이 가능한가?
2. 반환 정보량을 `full_text`에서 `minimal_text`로 줄이면 Recall@k와 평균 노출량은 어떻게 변하는가?
3. 법제·업무흐름 힌트만 제공하는 `route_only` 조건은 후보검색에 충분한가?
4. 검색 결과는 어떤 표현 정책을 따라야 법적 판정 오해를 줄일 수 있는가?
5. 상담형 모사 질의셋에서 minimal_text 조건의 후보검색 성능은 어떤 패턴을 보이는가?

## 실험 설계

### 코퍼스

| 소스 | 항목 수 | 성격 |
|---|---:|---|
| Wassenaar Arrangement 2025 | 585 | 국제 이중용도·군용물자 통제목록 |
| India SCOMET 2024 | 575 | 인도 SCOMET 공개 통제목록 |
| U.S. eCFR CCL | 637 | 미국 EAR Commerce Control List |

### 비교 조건

| 조건 | 색인·반환 정보 | 목적 |
|---|---|---|
| `full_text` | 통제번호 + 원문 설명 전체 | 상한 기준선 |
| `minimal_text` | 통제번호 + 첫 핵심 설명 | 정보 최소화 후보 |
| `minimal_no_code` | 첫 핵심 설명, 통제번호 제외 | 코드 노출까지 줄인 조건 |
| `route_only` | 통제체계·업무흐름 힌트 | 극단적 저노출 음성 대조군 |

### 외부 모사 질의셋
- `data/external_consultation_queries.json`: 상담형 모사 질의셋 30개 (KO 16, EN 14). 각 질의별 연구자가 예비로 부여한 `candidate_labels` (정답 아님).
- `docs/case_analysis.md`: 실제 코드 산출 결과를 바탕으로 한 사례 분석 5개
- `output/external_eval.json`, `output/external_eval.md`: 평가 결과

### 외부 모사 질의셋 결과
`evaluate_external_queries.py`로 실제 평가한 결과, 모든 조건에서 R@10=0이 나왔다.

| 조건 | R@1 | R@5 | R@10 | 영어 R@10 | 한국어 R@10 | zero-score 수 | 라벨충돌 질의수 |
|---|---:|---:|---:|---:|---:|---:|---:|
| minimal_text | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 14 | 13 |
| minimal_no_code | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 14 | 13 |
| full_text | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 12 | 13 |

주의: 이 R@10=0은 연구자가 예비 부여한(검증되지 않은) `candidate_labels` 기준이며, 30개 중 13개 질의는 코드 정규화 충돌을 가진다. 따라서 "BM25의 현장 성능=0"이 아니라 "불확실한 후보 라벨 기준 비수렴"으로 읽어야 한다.

세부 분석: `docs/case_analysis.md` 참조.

## BM25-only baseline로 충분한 이유

본 연구는 BM25-only sparse retrieval을 기준선으로 사용한다. 이 선택은 다음과 같은 이유로 방어 가능하다:

1. **투명성**: BM25는 사전학습된 임베딩이나 블랙박스 LLM reranker를 포함하지 않는다. 모든 점수는 용어 출현 빈도와 문서 길이 정규화로 계산된다. 심사위원이 코드와 수식을 직접 확인할 수 있다.
2. **현실적인 보안 요구**: 외부 AI 서비스에 기술정보를 전송하는 시나리오에서, 가장 안전한 설계는 "외부 모델 호출 자체를 최소화"하는 것이다. BM25-only는 인덱싱은 사전에 로컬에서 수행하고, 쿼리 단계에서도 외부 추론 API를 호출하지 않는다.
3. **성능-보안 트레이드오프 명확화**: 합성 benchmark에서 66% 감소한 노출량에 비해 R@10은 약 1.8%p만 감소했다. 이 수치는 "최소노출이 성능을 크게 해치지 않는다"는 정량적 근거를 제공한다. 다만 상담형 모사 질의셋에서 R@10=0이 나온 점은, 이 수치가 모든 실제 질의에 직접 일반화될 수 없음을 보여준다.
4. **확장 가능성**: 본 baseline이 안정화된 후에 Dense retrieval이나 reranker를 부가 실험으로 추가할 수 있으나, 이는 연구 질문(정보최소화)의 핵심을 흐리지 않아야 한다. 후속 연구로 분리하는 방식을 권장한다.

다만, 사례 분석(ext-003, ext-005)에서 확인된 바와 같이, BM25-only는 어휘 불일치·도메인 설명 격차에서 한계가 있다. 이를 보완하기 위해서는 (1) 동의어·유의어 확장, (2) domain-specific synonym dictionary, (3) Dense retrieval을 2nd stage rerank로 제한적 도입 등의 확장이 가능하다.

## 해석

`minimal_text`와 `minimal_no_code`는 `full_text`보다 R@10이 낮지만, 감소 폭은 약 1.6~1.8%p 수준이다. 반면 평균 노출량@10은 약 66~67% 감소한다. 따라서 사전 트리아지 단계에서는 원문 전체를 반환하기보다 핵심 설명 중심 후보목록을 먼저 제공하고, 사용자가 공식 판정 절차로 이동하도록 설계하는 편이 안전하다.

`route_only`는 성능이 낮다. 이는 법제 안내만으로는 기술적 후보검색을 대체할 수 없음을 보여준다. 따라서 법제 라우팅은 검색 대체물이 아니라 검색 결과에 붙는 보수적 안내 레이어로 다루어야 한다.

### 합성 benchmark 절대수치의 한계 (중요)

합성 쿼리(`generate_queries.py`)는 각 코퍼스 항목 **자기 자신의 본문**에서 통제번호만 제거해 템플릿에 감싼 것이고, 검색 대상 문서(`minimal_text`)는 **같은 항목 본문의 첫 문장**이다. 즉 쿼리와 정답 문서가 동일 원문에서 파생된 near-duplicate 관계이므로, R@10 0.9792는 "후보 발견" 능력이라기보다 **자기참조 재검색(self-retrieval)** 성능에 가깝다. 따라서 본 연구의 핵심 기여는 절대 성능 수치가 아니라 (1) 노출량-성능 trade-off 곡선의 형태와 (2) 합성 평가와 독립 패러프레이즈 평가 사이의 일반화 격차(generalization gap)다. 상담형 모사 질의셋에서 R@10이 무너진 것은 이 격차의 직접 증거다.

## 한국 법제도와의 연결

본 연구의 minimal_text 후보검색 워크플로우는 다음 한국 법제 체계와 연결된다:
- 대외무역법 제18조(전략물자 수출 제한) 및 전략물자 수출입고시(신고 절차)
- 산업기술보호법(해외 기술 유출 방지)
- 국가핵심기술 제도(해외 이전 승인)

워크플로우는 다음을 전제로 한다:
1. 본 시스템은 사전 후보검색 보조로만 사용된다.
2. 최종 판정은 YesTrade 자가판정 또는 전문판정, 관세사 검토, 산업통상자원부 승인 절차를 따른다.
3. 기술자료(도면, 특허, 소스코드)가 함께 이전되는 경우, 산업기술보호법상 별도 검토가 필요하다.

상세 workflow: `docs/korean_regulatory_framework.md`

## 절대 쓰면 안 되는 주장

- AI가 전략물자 해당/비해당을 판정한다.
- 본 시스템이 YesTrade 자가판정 또는 전문판정을 대신하거나 보조하는 기능을 제공하지 않는다.
- 법제 라우팅 정확도가 검증되었다.
- 상담형 모사 질의셋을 넘어 실제 기업·관세사 질의까지 일반화가 확인되었다.
- 국가핵심기술 해당 여부를 자동 판단한다.
- BM25 baseline이 "실제 현장에서 충분하다"고 단정한다. 상담형 모사 질의셋 결과에서 calibration이 필요함을 항상 언급해야 한다.

## 검증된 참고문헌·근거 링크

- [Wassenaar Arrangement Control Lists](https://www.wassenaar.org/control-lists/)
- [Wassenaar Arrangement 2025 PDF](https://www.wassenaar.org/app/uploads/2025/12/List-of-Dual-Use-Goods-and-Technologies-and-ML-2025.pdf)
- [DGFT Updated SCOMET List 2024 PDF](https://content.dgft.gov.in/Website/UPDATED%20SCOMET%20List%202024%20as%20on%2002.09.2024.pdf)
- [eCFR 15 CFR Part 774 Supplement No. 1](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-774/appendix-Supplement%20No.%201%20to%20Part%20774)
- [BIS Interactive Commerce Control List](https://www.bis.gov/regulations/ear/interactive-commerce-control-list)
- [YesTrade 제도개요](https://www.yestrade.go.kr/system-guidance)
- [YesTrade 온라인 자가판정 한계](https://www.yestrade.go.kr/judgements/self/intro)
- [전략물자수출입고시](https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000270104&chrClsCd=010201)
- [국가핵심기술 제도](https://kaits.or.kr/web/content.do?menu_cd=000067)
- [Ryu, Won & Kim, Intelligent Decision Support System for Nuclear Export Control: A BERT-Based Approach](https://www.tandfonline.com/doi/full/10.1080/00295450.2025.2556617)
- [Nelson, Improving Strategic Trade Detection and Classification Through Machine Learning](https://mag.wcoomd.org/magazine/wco-news-94/strategic-trade-detection-machine-learning/)

## 다음 보강 과제

1. 상담형 모사 질의셋`(`data/external_consultation_queries.json`)의 라벨 정확성 검증 및 불일치 코드 파싱 오류 수정 (예: 2B001이 bio agent로 파싱된 문제)
2. 한국어 질의 대응: 영어 번역 필드(`query_en`) 추가 또는 도메인 동의어 사전(`domain_synonyms.json`) 구축
3. 통제목록 파싱 결과 표본 100개 수작업 검수
4. Dense retrieval 추가 실험 (후속 연구)
5. 전문가 2인 이상 후보 적합성 평가 (별도 연구)
6. 노출량 proxy를 문자 수에서 민감도 가중치 기반으로 확장
