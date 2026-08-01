# [SUPERSEDED] 확장 검증셋 평가 (TASK I)

> ⚠ 평가 결과는 `output/validated_suite.json`(experiment_validated_suite.py)으로
> 대체되었다. 이 스크립트의 존속 이유는 `data/validated_queries_expanded.json` 병합이다.

- 표본: **n=151** (영어 42, 한국어 109) — 원본 검증 13 + TASK G 슬라이스 병합
- 매칭: exact full eCFR code (충돌 0) / 노출 minimal_text / Dense sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- 라벨: 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).

## R@10 by retriever

| retriever | 전체 R@10 | 영어 R@10 | 한국어 R@10 |
|---|---:|---:|---:|
| BM25 (1.0) | 0.1523 | 0.4762 | 0.0275 |
| hybrid (0.7) | 0.4702 | 0.5000 | 0.4587 |
| hybrid (0.5) | 0.5099 | 0.5476 | 0.4954 |
| hybrid (0.3) | 0.5099 | 0.5476 | 0.4954 |
| Dense (0.0) | 0.4503 | 0.3810 | 0.4771 |

## 핵심 비교 (exact McNemar primary + paired bootstrap 보조)

| 비교 | 평균차 | bootstrap 95% CI | 승/패/무 | exact p (양측) |
|---|---:|---|---:|---:|
| hybrid_0.5_vs_bm25 | +0.3576 | [0.2848, 0.4371] | 54/0/97 | 1.11e-16 |
| dense_vs_bm25 | +0.2980 | [0.2119, 0.3841] | 53/8/90 | 2.99e-09 |
| hybrid_0.7_vs_bm25 | +0.3179 | [0.2450, 0.3907] | 48/0/103 | 7.11e-15 |

> 소표본에서 percentile bootstrap CI가 0을 포함하는 것은 이산 경계 인공물일 수
> 있으므로 primary는 exact McNemar다(`docs/statistics.md` §5).

## 해석

- n=13 → n=151로 확대. 핵심 질문: hybrid>BM25 / 한국어 회복의 95% CI가 0을 벗어났는가.
- 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 법적·전문가 판정이 아니다.
