# TASK H — 임베딩 robustness (확장셋 n=71)

- 표본: n=71 (영어 26, 한국어 45) / 노출 minimal_text / 매칭 exact eCFR code
- BM25는 모델 불문 동일. dense 모델만 교체해 hybrid 우위가 유지되는지 확인.

## 모델별 R@10 (전체 / 영어 / 한국어)

| dense 모델 | BM25 | Dense(α0) | hybrid α0.7 | hybrid α0.5 | hybrid α0.3 |
|---|---:|---:|---:|---:|---:|
| paraphrase-multilingual-MiniLM-L12-v2 | 0.169 | 0.549 | 0.549 | 0.578 | 0.578 |
| multilingual-e5-base | 0.169 | 0.422 | 0.422 | 0.437 | 0.451 |
| bge-m3 | 0.169 | 0.563 | 0.563 | 0.563 | 0.578 |

## 한국어 R@10 (BM25 vs 각 dense hybrid α0.5)

| dense 모델 | BM25 KO | hybrid α0.5 KO |
|---|---:|---:|
| paraphrase-multilingual-MiniLM-L12-v2 | 0.022 | 0.600 |
| multilingual-e5-base | 0.022 | 0.400 |
| bge-m3 | 0.022 | 0.622 |

## hybrid(α0.5) vs BM25 — paired bootstrap 95% CI

| dense 모델 | 평균차 | 95% CI | 유의? | wins/losses |
|---|---:|---|---|---:|
| paraphrase-multilingual-MiniLM-L12-v2 | +0.4085 | [0.2958, 0.5211] | **예** | 29/0 |
| multilingual-e5-base | +0.2676 | [0.1549, 0.3803] | **예** | 20/1 |
| bge-m3 | +0.3944 | [0.2817, 0.5070] | **예** | 28/0 |

## 해석

- 핵심: 여러 다국어 임베딩에서 hybrid > BM25 우위와 한국어 회복이 유지되면, 결과가 특정 모델 때문이 아님을 보인다.
- 라벨은 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).
