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

합성 쿼리(`generate_queries.py`)는 각 코퍼스 항목 **자기 자신의 본문**에서 통제번호만 제거해 템플릿에 감싼 것이고, 검색 대상 문서(`minimal_text`)는 **같은 항목 본문의 첫 문장**이다. 즉 쿼리와 정답 문서가 동일 원문에서 파생된 near-duplicate 관계이므로(쿼리-정답 minimal_text 문서 평균 Jaccard 0.485), R@10 0.9792는 "후보 발견" 능력이라기보다 **자기참조 재검색(self-retrieval)** 성능에 가깝다.

이 의존성을 정량화하기 위해, 외부 모델 없이 결정론적으로 각 쿼리가 정답 문서와 공유하는 **고-IDF(변별) 토큰을 N개 제거**하고 R@k를 재측정했다(`experiment_paraphrase_gap.py`). 사용자가 통제목록의 희소 전문어를 인용하지 않고 일반어로 기술하는 상황을 모사한 것이다.

| 제거 변별토큰 수(minimal_text) | R@1 | R@5 | R@10 | 평균 Jaccard |
|---:|---:|---:|---:|---:|
| 0 (기존 헤드라인) | 0.7837 | 0.9583 | 0.9792 | 0.485 |
| 3 | 0.6202 | 0.8397 | 0.8862 | 0.402 |
| 5 | 0.5256 | 0.7099 | 0.7596 | 0.347 |
| 10 | 0.2708 | 0.4006 | 0.4407 | 0.213 |

변별 토큰 5개만 제거해도 R@10이 0.9792 → 0.7596(−22%p), 10개에서 0.4407로 반토막 난다. `minimal_text`(첫 문장만 색인)는 `full_text`보다 훨씬 가파르게 붕괴한다. 따라서 본 연구의 핵심 기여는 절대 성능 수치가 아니라 (1) 노출량-성능 trade-off 곡선의 형태, (2) 합성 평가와 독립 패러프레이즈 평가 사이의 일반화 격차(generalization gap), (3) 그 격차의 어휘 민감도 정량화다. 상담형 모사 질의셋에서 R@10이 무너진 것은 이 격차의 직접 증거다. 상세: `output/paraphrase_gap.md`.

### Retriever 비교: 합성 benchmark는 BM25에 구조적으로 유리하다

BM25 vs Dense(다국어 MiniLM) vs Hybrid를 두 평가셋에서 비교했다(`experiment_retriever_compare.py`, `experiment_external_retriever.py`).

**(가) 자기참조 합성셋**: BM25가 모든 어휘격차 레벨에서 Dense를 앞선다(N=10에서도 BM25 0.4407 > Dense 0.2532). 또한 합성 "한국어" 쿼리는 한국어 지시문에 **영어 기술설명 본문**이 들어 있어 BM25 한국어 R@10이 0.98로 나온다 — 즉 합성셋의 언어 분리는 가짜다. **합성 benchmark는 retriever 비교·cross-lingual 평가에 부적합하다.**

**(나) 외부 상담셋(진짜 패러프레이즈·진짜 한국어)**: BM25는 전 조건 R@10=0(코퍼스 100% 영어 → 한국어 어휘 매칭 불가)인데, 다국어 dense·hybrid가 매칭을 회복한다.

| retriever | 전체 R@10 | 영어 R@10 | 한국어 R@10 |
|---|---:|---:|---:|
| BM25 (α=1.0) | 0.0000 | 0.0000 | 0.0000 |
| **hybrid (α=0.5)** | **0.1000** | 0.1429 | **0.0625** |
| Dense (α=0.0) | 0.0667 | 0.0714 | 0.0625 |

한국어 R@10이 0 → 0.0625로, hybrid 전체가 0 → 0.10으로 회복된다(절대값은 라벨 노이즈로 낮음). 핵심 메시지: **자기참조 합성 평가는 BM25를 과대평가하고 다국어 dense의 cross-lingual 가치를 가린다.** 따라서 정보최소화 효과는 평가설계·retriever 선택에 강하게 의존한다. 상세: `output/retriever_compare.md`, `output/external_retriever.md`.

### 검증 라벨셋: 충돌 제거 후 재평가

원본 외부셋의 라벨 노이즈(13/30 코드충돌 + 의미 불일치)를 제거하기 위해, eCFR 텍스트가 항목을 명확히 기술하는 경우에만 **full code(ECCN-XXXX)로 핀 고정한 검증 라벨**을 부여하고(나머지 17개는 사유와 함께 metrics 제외), exact code 매칭으로 재평가했다(`build_validated_queries.py`, `evaluate_validated_queries.py`). 라벨은 법적 판정이 아니라 코퍼스 텍스트 근거 카테고리 라벨이다(전문가 검증 아님).

| retriever | R@10 | 영어 R@10 | 한국어 R@10 |
|---|---:|---:|---:|
| BM25 (α=1.0) | 0.0000 | 0.0000 | 0.0000 |
| **hybrid (α=0.5)** | **0.2308** | 0.2500 | 0.2000 |
| Dense (α=0.0) | 0.1538 | 0.1250 | 0.2000 |

평가 표본 13개(영어 8, 한국어 5, 소표본). 관찰: (1) **BM25는 정답 라벨이 코퍼스에 존재하고 영어 질의여도 R@10=0** — 상담형 패러프레이즈에서 어휘 매칭이 정답 항목으로 수렴하지 못한다(라벨을 코퍼스 텍스트 기준으로 골라 BM25에 유리했음에도 0). (2) hybrid(α=0.5)가 양 극단을 모두 앞선다. (3) 라벨 노이즈 제거로 hybrid R@10이 0.10 → 0.23으로 약 2배 — 노이즈가 수치를 억눌렀음이 확인된다. 상세: `output/validated_eval.md`.

### 한국어 cross-lingual 트랙 (TASK D)

검증셋의 한국어 평가질의 5개를 사람이 영어로 수동 번역하여(외부 API 미사용), KO-원문 vs KO-번역 vs EN-원문을 BM25/Dense/Hybrid로 비교했다(`experiment_crosslingual_eval.py`).

| track | BM25(α=1.0) | Hybrid(α=0.5) | Dense(α=0.0) | n |
|---|---:|---:|---:|---:|
| KO-원문 | 0.0000 | 0.2000 | 0.2000 | 5 |
| KO-번역 | 0.2000 | 0.2000 | 0.2000 | 5 |
| EN-원문 | 0.0000 | 0.2500 | 0.1250 | 8 |

관찰(경향, 표본 5개): KO-원문에서 BM25=0인데 (a) 영어 번역 시 BM25가 0→0.20, (b) 다국어 dense는 번역 없이도 0.20을 달성한다. 즉 **번역 경로와 다국어 임베딩 경로가 모두 한국어 0점을 비슷하게 회복**시킨다. 한국어 표본이 5개로 매우 작아 절대값이 아니라 경향으로만 해석하며, 표본 확대가 후속 과제다. 상세: `output/crosslingual_eval.md`.

### 통계 보강 및 figure (TASK F)

기존 `output/*.json`만으로 bootstrap 95% CI·효과크기를 산출하고(`experiment_stats.py`, seed 고정, 검증셋은 per-query paired bootstrap), 논문용 그림 4종을 생성했다(`make_figures.py`):

- `output/fig_paraphrase_gap.png` — 어휘격차 N별 R@10 (자기참조 의존성)
- `output/fig_retriever_alpha.png` — 합성셋 alpha별 R@10
- `output/fig_exposure_recall.png` — 노출량-성능 frontier
- `output/fig_validated_retriever.png` — 검증셋 retriever별 R@10(전체/EN/KO)

**통계적 주의(중요)**: 합성셋 비교(minimal vs full, N5 vs N0)는 표본이 624개로 CI가 0을 포함하지 않아 유의하다. 그러나 **검증셋의 hybrid vs BM25 차이는 +0.2308이지만 95% CI가 [0.0, 0.46]으로 0을 포함**한다(n=13). 따라서 검증셋의 retriever 우위는 **통계적으로 입증된 효과가 아니라 경향**으로 서술해야 하며, 표본 확대가 필수다. 상세: `docs/statistics.md`, `output/stats_summary.json`.

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
