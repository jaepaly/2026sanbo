# 검증셋 통합 평가 (n=71, 영어 26 / 한국어 45)

사전지정: 등가성 마진 δ=0.05, 기본 α=0.5, bootstrap 20000회(seed 20260626). 민감도 δ는 민감도 분석으로만 보고한다.

라벨: 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).

## 1. 진단 — BM25가 애초에 아무 신호도 내지 못하는 질의

| 색인 모드 | BM25 무신호 질의 | 고유 색인문서 | hybrid top-10 = dense top-10 (α=0.5) |
|---|---:|---:|---:|
| full_text | 44/71 | 1783 | 44/71 |
| minimal_text | 44/71 | 1783 | 44/71 |
| minimal_no_code | 44/71 | 1656 | 44/71 |

> 무신호 질의는 어휘 교집합이 0이어서 top-10을 만들 수 없다. 이전 코드는 이 경우
> 코퍼스 배열 앞머리를 결과로 집계했다.

## 2. R@10 (95% CI = Clopper-Pearson)

### e5-base (revision `d128750597153bb5987e10b1c3493a34e5a4502a`)

| 색인 | retriever | 전체 R@10 | 95% CI | 영어 | 한국어 |
|---|---|---:|---|---:|---:|
| full_text | BM25 | 0.1549 | [0.080, 0.260] | 0.4231 | 0.0000 |
| full_text | hybrid_0.7 | 0.5070 | [0.386, 0.628] | 0.5000 | 0.5111 |
| full_text | hybrid_0.5 | 0.5070 | [0.386, 0.628] | 0.5000 | 0.5111 |
| full_text | hybrid_0.3 | 0.5070 | [0.386, 0.628] | 0.5000 | 0.5111 |
| full_text | dense | 0.4789 | [0.359, 0.601] | 0.4231 | 0.5111 |
| minimal_text | BM25 | 0.1549 | [0.080, 0.260] | 0.4231 | 0.0000 |
| minimal_text | hybrid_0.7 | 0.4789 | [0.359, 0.601] | 0.4615 | 0.4889 |
| minimal_text | hybrid_0.5 | 0.4930 | [0.372, 0.614] | 0.5000 | 0.4889 |
| minimal_text | hybrid_0.3 | 0.5070 | [0.386, 0.628] | 0.5385 | 0.4889 |
| minimal_text | dense | 0.4648 | [0.345, 0.587] | 0.4231 | 0.4889 |
| minimal_no_code | BM25 | 0.1549 | [0.080, 0.260] | 0.4231 | 0.0000 |
| minimal_no_code | hybrid_0.7 | 0.4366 | [0.319, 0.559] | 0.4231 | 0.4444 |
| minimal_no_code | hybrid_0.5 | 0.4648 | [0.345, 0.587] | 0.5000 | 0.4444 |
| minimal_no_code | hybrid_0.3 | 0.4789 | [0.359, 0.601] | 0.5385 | 0.4444 |
| minimal_no_code | dense | 0.4507 | [0.332, 0.573] | 0.4615 | 0.4444 |

### MiniLM (revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`)

| 색인 | retriever | 전체 R@10 | 95% CI | 영어 | 한국어 |
|---|---|---:|---|---:|---:|
| full_text | BM25 | 0.1549 | [0.080, 0.260] | 0.4231 | 0.0000 |
| full_text | hybrid_0.7 | 0.5915 | [0.468, 0.707] | 0.5000 | 0.6444 |
| full_text | hybrid_0.5 | 0.6056 | [0.482, 0.720] | 0.5385 | 0.6444 |
| full_text | hybrid_0.3 | 0.6056 | [0.482, 0.720] | 0.5385 | 0.6444 |
| full_text | dense | 0.5915 | [0.468, 0.707] | 0.5000 | 0.6444 |
| minimal_text | BM25 | 0.1549 | [0.080, 0.260] | 0.4231 | 0.0000 |
| minimal_text | hybrid_0.7 | 0.5493 | [0.427, 0.668] | 0.4615 | 0.6000 |
| minimal_text | hybrid_0.5 | 0.5775 | [0.454, 0.694] | 0.5385 | 0.6000 |
| minimal_text | hybrid_0.3 | 0.5775 | [0.454, 0.694] | 0.5385 | 0.6000 |
| minimal_text | dense | 0.5493 | [0.427, 0.668] | 0.4615 | 0.6000 |
| minimal_no_code | BM25 | 0.1549 | [0.080, 0.260] | 0.4231 | 0.0000 |
| minimal_no_code | hybrid_0.7 | 0.4930 | [0.372, 0.614] | 0.4231 | 0.5333 |
| minimal_no_code | hybrid_0.5 | 0.5211 | [0.399, 0.641] | 0.5000 | 0.5333 |
| minimal_no_code | hybrid_0.3 | 0.5352 | [0.413, 0.654] | 0.5385 | 0.5333 |
| minimal_no_code | dense | 0.5070 | [0.386, 0.628] | 0.4615 | 0.5333 |

## 3. 검색기 비교 (paired bootstrap + exact McNemar, Holm 보정)

| 모델 | 색인 | 비교 | 평균차 | 95% CI | 승/패/무 | exact p | Holm p |
|---|---|---|---:|---|---:|---:|---:|
| e5-base | full_text | hybrid_vs_bm25[overall] | +0.3521 | [0.2394, 0.4648] | 26/1/44 | 4.17e-07 | 2.92e-06 |
| e5-base | full_text | dense_vs_bm25[overall] | +0.3239 | [0.1972, 0.4507] | 25/2/44 | 5.65e-06 | 3.39e-05 |
| e5-base | full_text | hybrid_vs_dense[overall] | +0.0282 | [0.0000, 0.0704] | 2/0/69 | 0.5 | 1 |
| e5-base | full_text | hybrid_vs_bm25[en] | +0.0769 | [-0.0769, 0.2308] | 3/1/22 | 0.625 | 1 |
| e5-base | full_text | dense_vs_bm25[en] | +0.0000 | [-0.1538, 0.1538] | 2/2/22 | 1 | 1 |
| e5-base | full_text | hybrid_vs_dense[en] | +0.0769 | [0.0000, 0.1923] | 2/0/24 | 0.5 | 1 |
| e5-base | full_text | hybrid_vs_bm25[ko] | +0.5111 | [0.3556, 0.6444] | 23/0/22 | 2.38e-07 | 2.15e-06 |
| e5-base | full_text | dense_vs_bm25[ko] | +0.5111 | [0.3556, 0.6444] | 23/0/22 | 2.38e-07 | 2.15e-06 |
| e5-base | full_text | hybrid_vs_dense[ko] | +0.0000 | [0.0000, 0.0000] | 0/0/45 | 1 | 1 |
| e5-base | minimal_text | hybrid_vs_bm25[overall] | +0.3380 | [0.2254, 0.4507] | 24/0/47 | 1.19e-07 | 1.07e-06 |
| e5-base | minimal_text | dense_vs_bm25[overall] | +0.3099 | [0.1972, 0.4225] | 23/1/47 | 2.98e-06 | 1.79e-05 |
| e5-base | minimal_text | hybrid_vs_dense[overall] | +0.0282 | [-0.0282, 0.0845] | 3/1/67 | 0.625 | 1 |
| e5-base | minimal_text | hybrid_vs_bm25[en] | +0.0769 | [0.0000, 0.1923] | 2/0/24 | 0.5 | 1 |
| e5-base | minimal_text | dense_vs_bm25[en] | +0.0000 | [-0.1154, 0.1154] | 1/1/24 | 1 | 1 |
| e5-base | minimal_text | hybrid_vs_dense[en] | +0.0769 | [-0.0769, 0.2308] | 3/1/22 | 0.625 | 1 |
| e5-base | minimal_text | hybrid_vs_bm25[ko] | +0.4889 | [0.3333, 0.6444] | 22/0/23 | 4.77e-07 | 3.81e-06 |
| e5-base | minimal_text | dense_vs_bm25[ko] | +0.4889 | [0.3333, 0.6444] | 22/0/23 | 4.77e-07 | 3.81e-06 |
| e5-base | minimal_text | hybrid_vs_dense[ko] | +0.0000 | [0.0000, 0.0000] | 0/0/45 | 1 | 1 |
| e5-base | minimal_no_code | hybrid_vs_bm25[overall] | +0.3099 | [0.2113, 0.4225] | 22/0/49 | 4.77e-07 | 4.29e-06 |
| e5-base | minimal_no_code | dense_vs_bm25[overall] | +0.2958 | [0.1831, 0.4085] | 22/1/48 | 5.72e-06 | 3.43e-05 |
| e5-base | minimal_no_code | hybrid_vs_dense[overall] | +0.0141 | [0.0000, 0.0423] | 1/0/70 | 1 | 1 |
| e5-base | minimal_no_code | hybrid_vs_bm25[en] | +0.0769 | [0.0000, 0.1923] | 2/0/24 | 0.5 | 1 |
| e5-base | minimal_no_code | dense_vs_bm25[en] | +0.0385 | [-0.0769, 0.1538] | 2/1/23 | 1 | 1 |
| e5-base | minimal_no_code | hybrid_vs_dense[en] | +0.0385 | [0.0000, 0.1154] | 1/0/25 | 1 | 1 |
| e5-base | minimal_no_code | hybrid_vs_bm25[ko] | +0.4444 | [0.3111, 0.6000] | 20/0/25 | 1.91e-06 | 1.53e-05 |
| e5-base | minimal_no_code | dense_vs_bm25[ko] | +0.4444 | [0.3111, 0.6000] | 20/0/25 | 1.91e-06 | 1.53e-05 |
| e5-base | minimal_no_code | hybrid_vs_dense[ko] | +0.0000 | [0.0000, 0.0000] | 0/0/45 | 1 | 1 |
| MiniLM | full_text | hybrid_vs_bm25[overall] | +0.4507 | [0.3380, 0.5634] | 32/0/39 | 4.66e-10 | 4.2e-09 |
| MiniLM | full_text | dense_vs_bm25[overall] | +0.4366 | [0.3099, 0.5634] | 32/1/38 | 7.92e-09 | 4.75e-08 |
| MiniLM | full_text | hybrid_vs_dense[overall] | +0.0141 | [0.0000, 0.0423] | 1/0/70 | 1 | 1 |
| MiniLM | full_text | hybrid_vs_bm25[en] | +0.1154 | [0.0000, 0.2692] | 3/0/23 | 0.25 | 1 |
| MiniLM | full_text | dense_vs_bm25[en] | +0.0769 | [-0.0769, 0.2308] | 3/1/22 | 0.625 | 1 |
| MiniLM | full_text | hybrid_vs_dense[en] | +0.0385 | [0.0000, 0.1154] | 1/0/25 | 1 | 1 |
| MiniLM | full_text | hybrid_vs_bm25[ko] | +0.6444 | [0.4889, 0.7778] | 29/0/16 | 3.73e-09 | 2.98e-08 |
| MiniLM | full_text | dense_vs_bm25[ko] | +0.6444 | [0.4889, 0.7778] | 29/0/16 | 3.73e-09 | 2.98e-08 |
| MiniLM | full_text | hybrid_vs_dense[ko] | +0.0000 | [0.0000, 0.0000] | 0/0/45 | 1 | 1 |
| MiniLM | minimal_text | hybrid_vs_bm25[overall] | +0.4225 | [0.3099, 0.5352] | 30/0/41 | 1.86e-09 | 1.68e-08 |
| MiniLM | minimal_text | dense_vs_bm25[overall] | +0.3944 | [0.2676, 0.5070] | 29/1/41 | 5.77e-08 | 3.46e-07 |
| MiniLM | minimal_text | hybrid_vs_dense[overall] | +0.0282 | [-0.0282, 0.0845] | 3/1/67 | 0.625 | 1 |
| MiniLM | minimal_text | hybrid_vs_bm25[en] | +0.1154 | [0.0000, 0.2692] | 3/0/23 | 0.25 | 1 |
| MiniLM | minimal_text | dense_vs_bm25[en] | +0.0385 | [-0.0769, 0.1538] | 2/1/23 | 1 | 1 |
| MiniLM | minimal_text | hybrid_vs_dense[en] | +0.0769 | [-0.0769, 0.2308] | 3/1/22 | 0.625 | 1 |
| MiniLM | minimal_text | hybrid_vs_bm25[ko] | +0.6000 | [0.4444, 0.7333] | 27/0/18 | 1.49e-08 | 1.19e-07 |
| MiniLM | minimal_text | dense_vs_bm25[ko] | +0.6000 | [0.4444, 0.7333] | 27/0/18 | 1.49e-08 | 1.19e-07 |
| MiniLM | minimal_text | hybrid_vs_dense[ko] | +0.0000 | [0.0000, 0.0000] | 0/0/45 | 1 | 1 |
| MiniLM | minimal_no_code | hybrid_vs_bm25[overall] | +0.3662 | [0.2535, 0.4789] | 26/0/45 | 2.98e-08 | 2.68e-07 |
| MiniLM | minimal_no_code | dense_vs_bm25[overall] | +0.3521 | [0.2394, 0.4648] | 25/0/46 | 5.96e-08 | 4.77e-07 |
| MiniLM | minimal_no_code | hybrid_vs_dense[overall] | +0.0141 | [-0.0282, 0.0704] | 2/1/68 | 1 | 1 |
| MiniLM | minimal_no_code | hybrid_vs_bm25[en] | +0.0769 | [0.0000, 0.1923] | 2/0/24 | 0.5 | 1 |
| MiniLM | minimal_no_code | dense_vs_bm25[en] | +0.0385 | [0.0000, 0.1154] | 1/0/25 | 1 | 1 |
| MiniLM | minimal_no_code | hybrid_vs_dense[en] | +0.0385 | [-0.0769, 0.1538] | 2/1/23 | 1 | 1 |
| MiniLM | minimal_no_code | hybrid_vs_bm25[ko] | +0.5333 | [0.3778, 0.6889] | 24/0/21 | 1.19e-07 | 8.35e-07 |
| MiniLM | minimal_no_code | dense_vs_bm25[ko] | +0.5333 | [0.3778, 0.6889] | 24/0/21 | 1.19e-07 | 8.35e-07 |
| MiniLM | minimal_no_code | hybrid_vs_dense[ko] | +0.0000 | [0.0000, 0.0000] | 0/0/45 | 1 | 1 |

> `hybrid_vs_dense`는 기존 산출물에 한 번도 없던 비교다. 한국어에서 BM25 점수가
> 항등 0이면 α<1의 랭킹은 dense와 수학적으로 동일하므로 승/패가 0/0으로 나오는 것이
> 정상이다 — 즉 '하이브리드가 필요하다'가 아니라 'dense 성분이 필요하다'가 데이터가
> 지지하는 진술이다.

## 4. 노출량@10 — 색인 모드 × 반환 모드

| 색인 모드 | 반환=full_text | 반환=minimal_text | 반환=minimal_no_code | 정정 전 정의 |
|---|---|---|---|---|
| full_text | 9730 | 1811 | 1721 | 9640 |
| minimal_text | 6149 | 1857 | 1765 | 1765 |
| minimal_no_code | 6277 | 1764 | 1674 | 1674 |

> 정정 전 정의는 `minimal_text`와 `minimal_no_code`에 동일한 값을 부여했다.
> 대각선이 아닌 칸(예: 색인=minimal_text, 반환=minimal_no_code)은 색인 품질을
> 유지하면서 반환량만 줄이는 조건이며, 기존 설계로는 측정할 수 없었다.

## 5. 정보최소화 등가성 검정 (TOST)

사전지정 마진 δ=0.05. 'CI가 0을 포함' 은 등가성의 근거가 아니다.

| 비교 | 평균차 | 95% CI | 승/패/무 | exact p | δ=0.05 등가? | δ=0.05 필요 n | δ=0.03 필요 n |
|---|---:|---|---:|---:|---|---:|---:|
| minimal_text_vs_full_text[hybrid_0.5] | -0.0282 | [-0.1127, 0.0423] | 3/5/63 | 0.727 | **아니오** | 1473 | 209277 |
| minimal_text_vs_full_text[dense] | -0.0423 | [-0.1127, 0.0141] | 1/4/66 | 0.375 | **아니오** | 7173 | - |
| minimal_text_vs_full_text[BM25] | +0.0000 | [-0.0563, 0.0563] | 2/2/67 | 1 | 예 | 142 | 393 |
| minimal_no_code_vs_full_text[hybrid_0.5] | -0.0845 | [-0.1831, 0.0000] | 3/9/59 | 0.146 | **아니오** | - | - |
| minimal_no_code_vs_full_text[dense] | -0.0845 | [-0.1690, 0.0000] | 2/8/61 | 0.109 | **아니오** | - | - |
| minimal_no_code_vs_full_text[BM25] | +0.0000 | [-0.0563, 0.0563] | 2/2/67 | 1 | 예 | 142 | 393 |

### 마진별 민감도 (p_max, δ가 클수록 통과하기 쉬움)

| 비교 | δ=0.03 | δ=0.05 | δ=0.075 | δ=0.1 | δ=0.15 |
|---|---|---|---|---|---|
| minimal_text_vs_full_text[hybrid_0.5] | 0.482 | 0.293 | 0.121 | 0.0362 | 0.00115 |
| minimal_text_vs_full_text[dense] | 0.652 | 0.402 | 0.148 | 0.0326 | 0.00029 |
| minimal_text_vs_full_text[BM25] | 0.145 | 0.039 | 0.0041 | 0.000212 | 6.2e-08 |
| minimal_no_code_vs_full_text[hybrid_0.5] | 0.871 | 0.763 | 0.578 | 0.374 | 0.0866 |
| minimal_no_code_vs_full_text[dense] | 0.894 | 0.785 | 0.586 | 0.361 | 0.067 |
| minimal_no_code_vs_full_text[BM25] | 0.145 | 0.039 | 0.0041 | 0.000212 | 6.2e-08 |

> p_max < 0.05 이면 해당 마진에서 등가(비열등)로 볼 수 있다. 표본이 작으면
> 좁은 마진은 원리상 통과할 수 없으므로 '필요 n' 열을 함께 읽어야 한다.
