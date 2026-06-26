# 외부 모사 질의 평가 결과

- 질의셋: `data/external_consultation_queries.json`
- 평가 기준: researcher-assigned `candidate_labels`와 정규화된 코드 비교
- query field: 원문 query 사용
- 파일 입출력: UTF-8

> 주의: `candidate_labels`는 연구자가 예비로 부여한 후보값이며 검증된 정답이 아니다.
> 따라서 R@10=0은 "BM25의 현장 성능이 0"이 아니라 "불확실한 후보 라벨 기준으로
> 어휘 매칭이 수렴하지 않는다"로 해석해야 한다. 코드 정규화 충돌(`candidate_label_collision_count`)이
> 있는 질의는 라벨이 의도와 다른 통제체계 항목을 가리킬 수 있다.

## 요약표

| 조건 | R@1 | R@5 | R@10 | 영어 R@10 | 한국어 R@10 | zero-score 수 | 라벨충돌 질의수 |
|---|---:|---:|---:|---:|---:|---:|---:|
| minimal_text | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 14 | 13 |
| minimal_no_code | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 14 | 13 |
| full_text | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 12 | 13 |

## failure type 분포

### minimal_text
- candidate_label_not_in_top10: 16
- korean_query_no_match: 14

### minimal_no_code
- candidate_label_not_in_top10: 16
- korean_query_no_match: 14

### full_text
- candidate_label_not_in_top10: 18
- korean_query_no_match: 12

## 대표 실패 사례 5개 (minimal_text 기준)

- **ext-027** [en] max_score=19.5862, hit@10=0, failure_type=candidate_label_not_in_top10
  - query: Chemical precursor materials for semiconductor photoresist are being sent to a distributor in Taiwan. Are these dual-use controlled?
  - candidate_labels: ['1C350', '1C991']
  - top10: ['8C112', '1.C.12', 'ECCN-7B103', 'ECCN-9A103', 'ECCN-9E102']
  - top5_scores: [19.5862, 16.2424, 14.97, 14.3716, 14.2347]

- **ext-013** [en] max_score=19.3708, hit@10=0, failure_type=candidate_label_not_in_top10
  - query: We are exporting software that controls vibration test equipment for satellite components. Is the software itself controlled?
  - candidate_labels: ['2D001', '2D002']
  - top10: ['5A204', '4A006', 'ECCN-4D993', 'ECCN-1D390', 'ECCN-9B990']
  - top5_scores: [19.3708, 15.7182, 14.4706, 13.7767, 13.6419]

- **ext-015** [en] max_score=18.9964, hit@10=0, failure_type=candidate_label_not_in_top10
  - query: A research institute in Singapore wants to buy our high-speed oscilloscope with bandwidth over 1 GHz. Which controls may apply?
  - candidate_labels: ['3A001', '3A002']
  - top10: ['8.E.2.a', '5.E.1.d.1', '5.E.1.d.2', '3.A.1.b.2.e', '3.A.1.b.4.b']
  - top5_scores: [18.9964, 15.8273, 15.5185, 15.4801, 15.1047]

- **ext-009** [en] max_score=18.1592, hit@10=0, failure_type=candidate_label_not_in_top10
  - query: A foreign collaborator requested our advanced FPGA firmware for image processing. Is this likely subject to export control?
  - candidate_labels: ['3D001', '5D002']
  - top10: ['ECCN-0A521', 'ECCN-0B521', 'ECCN-0D521', 'ECCN-0C521', 'ECCN-0E521']
  - top5_scores: [18.1592, 18.1592, 18.1592, 18.1592, 18.1592]

- **ext-005** [en] max_score=17.4795, hit@10=0, failure_type=candidate_label_not_in_top10
  - query: Cryptographic software source code will be transferred to a foreign subsidiary for internal development. Does export control apply?
  - candidate_labels: ['5D002', '5D991']
  - top10: ['6A008', '7.D.4.a', '5.A.2.e', '6.A.3.b', '8D704']
  - top5_scores: [17.4795, 14.3385, 13.9355, 13.3173, 12.3489]
