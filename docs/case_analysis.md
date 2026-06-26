# 외부 모사 질의 평가 사례 분석

이 문서는 `output/external_eval.json`의 실제 산출만 근거로 작성했다. 수동 보정 표, 생략 부호, 추정 순위는 넣지 않았다.

## 1. 목적

`data/external_consultation_queries.json` 30개는 합성 benchmark와 별도로 만든 **상담형 모사 질의셋**이다. 목적은 BM25-only baseline이 실제 상담형 문장에 가까운 질의에서도 후보 라벨을 회수하는지 확인하는 것이 아니라, 어디서 실패하는지 드러내는 stress test를 제공하는 데 있다.

## 2. 평가 방법

- 코퍼스: `data/corpus/combined.json` 1,797개 항목
- 질의셋: `data/external_consultation_queries.json` 30개
- 스크립트: `evaluate_external_queries.py`
- 출력: `output/external_eval.json`, `output/external_eval.md`
- 비교 기준: 질의별 `candidate_labels`를 코드 정규화 후 top-10 결과와 비교
- 조건: `minimal_text`, `minimal_no_code`, `full_text`
- query field: 원문 `query`

## 3. 전체 결과

| 조건 | R@1 | R@5 | R@10 | 영어 R@10 | 한국어 R@10 | zero-score 수 | candidate label 존재 수 | 라벨충돌 질의수 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| minimal_text | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 14 | 30 | 13 |
| minimal_no_code | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 14 | 30 | 13 |
| full_text | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 12 | 30 | 13 |

관찰:

1. 세 조건 모두 R@10=0이다.
2. `minimal_text`와 `minimal_no_code`에서는 14개 질의가 `max_score=0`이다.
3. `full_text`는 zero-score를 12개로 줄였지만, 여전히 candidate label hit를 만들지 못했다.
4. `external_eval.json` 기준으로 30개 질의 모두 normalize된 candidate label 문자열은 코퍼스 안에 존재한다. 다만 **30개 중 13개 질의는 코드 정규화 충돌**(예: `2B001`이 SCOMET 생물작용제와 eCFR 공작기계 양쪽에 존재)을 가진다. 즉 "존재"가 곧 "의도한 통제체계의 항목과 일치"를 뜻하지는 않는다. 따라서 이번 실패는 **후보 회수 실패**이면서 동시에 **후보 라벨 자체의 불확실성**이 함께 작용한 결과로 보아야 하며, R@10=0을 "BM25의 현장 성능=0"으로 단정해서는 안 된다.

## 4. 실패 패턴 요약

### 4.1 한국어 질의 실패

`minimal_text` 기준 failure breakdown은 다음과 같다.

- `korean_query_no_match`: 14
- `candidate_label_not_in_top10`: 16

한국어 질의 16개 중 14개는 `max_score=0`이다. 나머지 2개(`ext-016`, `ext-024`)는 일부 영문/숫자 토큰 때문에 점수가 0은 아니지만, candidate label은 top-10에 들어오지 못했다. 따라서 한국어 질의는 단순히 "조금 약하다"가 아니라, 현재 BM25 baseline에서 **회수 실패가 구조적**이라고 보는 편이 맞다.

### 4.2 영어 질의 실패

영어 질의 14개는 `minimal_text`에서 모두 `max_score>0`이다. 즉 BM25가 무관한 문서를 아무 점수 없이 반환한 것이 아니라, **어휘 중첩이 있는 다른 항목들에 점수를 주었지만 candidate label까지 연결하지 못한 것**이다.

### 4.3 full_text도 해결책이 아니었다

`full_text`는 `minimal_text`보다 문서 정보량이 많아서 zero-score 수가 14 → 12로 줄었지만, 최종 R@10은 여전히 0.0000이다. 반환 텍스트를 늘리는 것만으로는 상담형 모사 질의셋의 실패를 고치지 못했다.

## 5. 대표 사례 5개

아래 순위와 점수는 모두 `output/external_eval.json`의 `results.minimal_text.per_query`에서 그대로 옮겼다.

### 사례 1 — 한국어 질의 완전 zero-score (`ext-001`)

- query: 리튬이온 배터리 양극재 제조에 쓰이는 화학물질을 인도에 수출하려 합니다. 관련 통제항목이 있는지 확인 부탁드립니다.
- candidate_labels: `1C350`, `1C991`
- max_score: `0.0`
- failure_type: `korean_query_no_match`

| 순위 | code | score |
|---|---|---:|
| 1 | ECCN-0A002 | 0.0000 |
| 2 | ECCN-0A501 | 0.0000 |
| 3 | ECCN-0A502 | 0.0000 |
| 4 | ECCN-0A503 | 0.0000 |
| 5 | ECCN-0A504 | 0.0000 |

해석: 한국어 질의가 영어 중심 코퍼스와 거의 어휘 매칭을 만들지 못한 전형적 사례다.

### 사례 2 — 한국어 질의인데 점수는 생겼지만 hit는 실패 (`ext-016`)

- query: 3D 프린터용 특수 금분소재를 프랑스에 공급합니다. 군용 부품 제조 가능성이 있다고 합니다.
- candidate_labels: `1C002`, `1C003`
- max_score: `8.1833`
- failure_type: `candidate_label_not_in_top10`

| 순위 | code | score |
|---|---|---:|
| 1 | 9.D.4.a | 8.1833 |
| 2 | 8D904 | 5.8431 |
| 3 | 9.D.4 | 5.6415 |
| 4 | 9.E.3.f.3 | 0.0000 |
| 5 | 9.E.3.f.2 | 0.0000 |

해석: 일부 토큰이 우연히 점수를 만들었어도 candidate label 회수로 이어지지 않았다. 한국어 질의 실패를 단순 zero-score 문제로만 볼 수 없다는 근거다.

### 사례 3 — CNC 질의의 영어 실패 (`ext-003`)

- query: We are exporting a CNC machining center with 5-axis simultaneous control capability. Which ECCN categories might apply?
- candidate_labels: `2B001`, `2B002`
- max_score: `12.4296`
- failure_type: `candidate_label_not_in_top10`

| 순위 | code | score |
|---|---|---:|
| 1 | 4A002 | 12.4296 |
| 2 | ECCN-2B201 | 10.5208 |
| 3 | 2.B.1.b | 10.3133 |
| 4 | 8B209 | 9.9496 |
| 5 | 4.D | 9.8313 |

해석: 질의는 기계가공 맥락을 충분히 담고 있지만, candidate label인 `2B001`/`2B002`는 top-10에 들어오지 않았다. 영어 질의라도 BM25 어휘 매칭만으로는 기대한 라벨에 수렴하지 않는다는 점을 보여준다.

### 사례 4 — 제어 소프트웨어 질의의 영어 실패 (`ext-013`)

- query: We are exporting software that controls vibration test equipment for satellite components. Is the software itself controlled?
- candidate_labels: `2D001`, `2D002`
- max_score: `19.3708`
- failure_type: `candidate_label_not_in_top10`

| 순위 | code | score |
|---|---|---:|
| 1 | 5A204 | 19.3708 |
| 2 | 4A006 | 15.7182 |
| 3 | ECCN-4D993 | 14.4706 |
| 4 | ECCN-1D390 | 13.7767 |
| 5 | ECCN-9B990 | 13.6419 |

해석: score 자체는 높지만 target candidate label과는 다른 계열 문서들이 상위에 온다. 이는 "영어면 된다"가 아니라, 문장형 질의에서 BM25가 다른 어휘 중첩에 쉽게 끌린다는 점을 보여준다.

### 사례 5 — 반도체 화학 전구체 질의의 영어 실패 (`ext-027`)

- query: Chemical precursor materials for semiconductor photoresist are being sent to a distributor in Taiwan. Are these dual-use controlled?
- candidate_labels: `1C350`, `1C991`
- max_score: `19.5862`
- failure_type: `candidate_label_not_in_top10`

| 순위 | code | score |
|---|---|---:|
| 1 | 8C112 | 19.5862 |
| 2 | 1.C.12 | 16.2424 |
| 3 | ECCN-7B103 | 14.9700 |
| 4 | ECCN-9A103 | 14.3716 |
| 5 | ECCN-9E102 | 14.2347 |

해석: 반도체/화학/dual-use 같은 일반 토큰은 여러 후보를 자극하지만, candidate label을 회수하는 데 필요한 정합성은 만들지 못했다.

## 6. 결론

이 상담형 모사 질의셋에서는 세 조건 모두 R@10=0.0000이다. 따라서 합성 benchmark에서 보인 높은 R@10을 그대로 현장형 질의 성능으로 일반화하면 안 된다.

이 결과가 보여주는 것은 다음 세 가지다.

1. 현재 BM25-only baseline은 한국어 상담형 질의에 구조적으로 약하다(코퍼스가 100% 영어라 한국어 질의는 어휘 매칭이 원천적으로 불가능).
2. 영어 상담형 질의도 non-zero score와 candidate hit는 전혀 다른 문제다.
3. `full_text`처럼 더 많은 문서를 반환해도 candidate label 회수 실패가 해결되지 않는다.
4. 단, R@10=0은 BM25의 한계와 **후보 라벨 자체의 불확실성**(30개 중 13개 코드 충돌, 다수 `label_confidence: low`)이 혼입된 수치다. 깨끗한 결론을 위해서는 검증된 단일 통제체계 정답셋이 필요하다(7장 참조).

## 7. 개선 방향

- 한국어 질의용 번역 보조 조건 또는 한영 도메인 동의어 사전 분리 평가
- candidate label 수준의 회수를 높이기 위한 query expansion 실험
- BM25를 유지하되 2단계 rerank 또는 domain synonym 보강을 후속 실험으로 분리
- 상담형 모사 질의셋은 계속 stress test로 유지하고, 합성 benchmark와 섞어서 해석하지 않기
