# 라벨 교란 민감도 — 전문가 검수의 대체 증거

정답 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 **전문가 검증을 받지 않았다.**
논문의 헤드라인은 모두 *같은 라벨을 고정 기준점으로 둔 질의별 짝지음 비교*라서
라벨의 법적 정확성은 대비에서 상쇄되지만, 라벨 결함이 *어떤 질의를 남기느냐*를
통해 결론을 흔들 수는 있다. 그래서 `docs/label_audit.md`가 지목한 결함별로
해당 질의를 제거한 부분집합에서 결론이 유지되는지 확인한다.

- 색인 모드: `minimal_text` / 모델: MiniLM, bge-m3, e5-base
- 방법: `validated_suite.json`의 질의별 `hit_vectors`를 마스킹해 **정확히 재계산**
  (모델 재실행 없음, 근사 아님).

## 변형별 표본

| 변형 | 설명 | 제거 | n | 영어 | 한국어 |
|---|---|---:|---:|---:|---:|
| `V0_baseline` | 전체 질의 (기준) | 0 | 151 | 42 | 109 |
| `V1_no_stub_gold` | 정답이 전부 표제 스텁인 질의 제거 (D1) | 42 | 109 | 27 | 82 |
| `V2_no_label_defect` | 부정확 2차 라벨·규제체계 모순 제거 (D3/D4) | 3 | 148 | 40 | 108 |
| `V3_unique_gold_code` | 정답 코드 재사용 질의 제거 (D5) | 3 | 148 | 41 | 107 |
| `V4_strict` | V1 ∩ V2 ∩ V3 (가장 보수적) | 42 | 109 | 27 | 82 |
| `V5_no_semantic_flag` | 의미 게이트(LaBSE τ=0.44) 초과 질의 제거 (자기참조 의심) | 14 | 137 | 39 | 98 |
| `V6_strict_plus_semantic` | V4 + 의미 게이트 초과 제거 (최대 보수) | 54 | 97 | 24 | 73 |

## dense − BM25 (주 결론): 모든 변형에서 유의한가

| 변형 | 모델 | BM25 | dense | 평균차 | 승/패 | exact p | 유의 |
|---|---|---:|---:|---:|---:|---:|---|
| `V0_baseline` | MiniLM | 0.1523 | 0.4503 | +0.2980 | 53/8 | 2.99e-09 | **예** |
| `V0_baseline` | bge-m3 | 0.1523 | 0.5695 | +0.4172 | 65/2 | 3.09e-17 | **예** |
| `V0_baseline` | e5-base | 0.1523 | 0.4768 | +0.3245 | 54/5 | 1.91e-11 | **예** |
| `V1_no_stub_gold` | MiniLM | 0.1835 | 0.4495 | +0.2661 | 37/8 | 1.54e-05 | **예** |
| `V1_no_stub_gold` | bge-m3 | 0.1835 | 0.6147 | +0.4312 | 49/2 | 1.18e-12 | **예** |
| `V1_no_stub_gold` | e5-base | 0.1835 | 0.5413 | +0.3578 | 44/5 | 7.60e-09 | **예** |
| `V2_no_label_defect` | MiniLM | 0.1554 | 0.4595 | +0.3041 | 53/8 | 2.99e-09 | **예** |
| `V2_no_label_defect` | bge-m3 | 0.1554 | 0.5811 | +0.4257 | 65/2 | 3.09e-17 | **예** |
| `V2_no_label_defect` | e5-base | 0.1554 | 0.4865 | +0.3311 | 54/5 | 1.91e-11 | **예** |
| `V3_unique_gold_code` | MiniLM | 0.1554 | 0.4595 | +0.3041 | 53/8 | 2.99e-09 | **예** |
| `V3_unique_gold_code` | bge-m3 | 0.1554 | 0.5743 | +0.4189 | 64/2 | 6.00e-17 | **예** |
| `V3_unique_gold_code` | e5-base | 0.1554 | 0.4865 | +0.3311 | 54/5 | 1.91e-11 | **예** |
| `V4_strict` | MiniLM | 0.1835 | 0.4495 | +0.2661 | 37/8 | 1.54e-05 | **예** |
| `V4_strict` | bge-m3 | 0.1835 | 0.6147 | +0.4312 | 49/2 | 1.18e-12 | **예** |
| `V4_strict` | e5-base | 0.1835 | 0.5413 | +0.3578 | 44/5 | 7.60e-09 | **예** |
| `V5_no_semantic_flag` | MiniLM | 0.1460 | 0.4088 | +0.2628 | 44/8 | 4.04e-07 | **예** |
| `V5_no_semantic_flag` | bge-m3 | 0.1460 | 0.5401 | +0.3942 | 56/2 | 1.19e-14 | **예** |
| `V5_no_semantic_flag` | e5-base | 0.1460 | 0.4307 | +0.2847 | 44/5 | 7.60e-09 | **예** |
| `V6_strict_plus_semantic` | MiniLM | 0.1753 | 0.4021 | +0.2268 | 30/8 | 4.72e-04 | **예** |
| `V6_strict_plus_semantic` | bge-m3 | 0.1753 | 0.5876 | +0.4124 | 42/2 | 1.13e-10 | **예** |
| `V6_strict_plus_semantic` | e5-base | 0.1753 | 0.4948 | +0.3196 | 36/5 | 7.84e-07 | **예** |

## hybrid − dense: 어느 변형에서도 유의하지 않은가

| 변형 | 모델 | 평균차 | exact p | 유의 |
|---|---|---:|---:|---|
| `V0_baseline` | MiniLM | +0.0596 | 0.0117 | 예 |
| `V0_baseline` | bge-m3 | -0.0199 | 0.453 | 아니오 |
| `V0_baseline` | e5-base | +0.0132 | 0.774 | 아니오 |
| `V1_no_stub_gold` | MiniLM | +0.0734 | 0.00781 | 예 |
| `V1_no_stub_gold` | bge-m3 | -0.0183 | 0.688 | 아니오 |
| `V1_no_stub_gold` | e5-base | +0.0092 | 1 | 아니오 |
| `V2_no_label_defect` | MiniLM | +0.0608 | 0.0117 | 예 |
| `V2_no_label_defect` | bge-m3 | -0.0203 | 0.453 | 아니오 |
| `V2_no_label_defect` | e5-base | +0.0135 | 0.774 | 아니오 |
| `V3_unique_gold_code` | MiniLM | +0.0608 | 0.0117 | 예 |
| `V3_unique_gold_code` | bge-m3 | -0.0135 | 0.688 | 아니오 |
| `V3_unique_gold_code` | e5-base | +0.0135 | 0.774 | 아니오 |
| `V4_strict` | MiniLM | +0.0734 | 0.00781 | 예 |
| `V4_strict` | bge-m3 | -0.0183 | 0.688 | 아니오 |
| `V4_strict` | e5-base | +0.0092 | 1 | 아니오 |
| `V5_no_semantic_flag` | MiniLM | +0.0657 | 0.0117 | 예 |
| `V5_no_semantic_flag` | bge-m3 | -0.0219 | 0.453 | 아니오 |
| `V5_no_semantic_flag` | e5-base | +0.0146 | 0.774 | 아니오 |
| `V6_strict_plus_semantic` | MiniLM | +0.0825 | 0.00781 | 예 |
| `V6_strict_plus_semantic` | bge-m3 | -0.0206 | 0.688 | 아니오 |
| `V6_strict_plus_semantic` | e5-base | +0.0103 | 1 | 아니오 |

## 한국어 (구조적 실패의 라벨 비의존성)

| 변형 | 모델 | BM25 한국어 | dense 한국어 |
|---|---|---:|---:|
| `V0_baseline` | MiniLM | 0.0275 | 0.4771 |
| `V0_baseline` | bge-m3 | 0.0275 | 0.5780 |
| `V0_baseline` | e5-base | 0.0275 | 0.4679 |
| `V1_no_stub_gold` | MiniLM | 0.0366 | 0.4634 |
| `V1_no_stub_gold` | bge-m3 | 0.0366 | 0.5976 |
| `V1_no_stub_gold` | e5-base | 0.0366 | 0.5122 |
| `V2_no_label_defect` | MiniLM | 0.0278 | 0.4815 |
| `V2_no_label_defect` | bge-m3 | 0.0278 | 0.5833 |
| `V2_no_label_defect` | e5-base | 0.0278 | 0.4722 |
| `V3_unique_gold_code` | MiniLM | 0.0280 | 0.4860 |
| `V3_unique_gold_code` | bge-m3 | 0.0280 | 0.5888 |
| `V3_unique_gold_code` | e5-base | 0.0280 | 0.4766 |
| `V4_strict` | MiniLM | 0.0366 | 0.4634 |
| `V4_strict` | bge-m3 | 0.0366 | 0.5976 |
| `V4_strict` | e5-base | 0.0366 | 0.5122 |
| `V5_no_semantic_flag` | MiniLM | 0.0306 | 0.4388 |
| `V5_no_semantic_flag` | bge-m3 | 0.0306 | 0.5510 |
| `V5_no_semantic_flag` | e5-base | 0.0306 | 0.4184 |
| `V6_strict_plus_semantic` | MiniLM | 0.0411 | 0.4247 |
| `V6_strict_plus_semantic` | bge-m3 | 0.0411 | 0.5753 |
| `V6_strict_plus_semantic` | e5-base | 0.0411 | 0.4658 |

## 결론

- dense−BM25가 **모든 변형 × 모든 모델에서 유의**한가: **예**
- hybrid−dense가 **어느 변형에서도 유의하지 않은가**: **아니오**
- 즉 라벨 결함(표제 스텁·부정확 2차 라벨·규제체계 모순·코드 재사용)이 있는 질의를
  모두 제거해도 **주 결론(dense−BM25 우위)** 은 뒤집히지 않는다. 라벨 결함이 그
  결론을 만들어낸 것이 아니다.
- 위의 hybrid−dense 항목은 **보정 전** 기준이다. n=151 실측에서는 MiniLM 이 5개 변형
  전부에서 보정 전 유의(p 0.0078~0.0117)라 이 항목이 '아니오'가 된다. 그러나 5변형 ×
  3모델 = 15개 조합 가족에 Holm 보정을 적용하면 유의한 조합은 0개이므로,
  '하이브리드가 dense 보다 낫다'는 여전히 성립하지 않는다. n=71 판에서는 보정 전
  기준으로도 0개였다. 보정 결과는 `label_sensitivity.json` 의
  `holm_across_15_combinations` 에 있다.
- 다만 이것은 **라벨 강건성**의 증거이지 **라벨 정확성**의 증거가 아니다. 절대 성능
  수치(예: 이 색인 모드의 주 지표 R@10 0.5099 — MiniLM, hybrid α=0.5, n=151. n=71
  판의 0.5775 는 옛 값이다)를 '법적으로 옳은 ECCN을 찾는 비율'로 해석하려면 여전히
  전문가 검증이 필요하며, 본 연구는 그 해석을 하지 않는다.
