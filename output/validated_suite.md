# 검증셋 통합 평가 (n=151, 영어 42 / 한국어 109)

사전지정: 등가성 마진 δ=0.05, 기본 α=0.5, bootstrap 20000회(seed 20260626). 민감도 δ는 민감도 분석으로만 보고한다.

라벨: 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).

## 1. 진단 — BM25가 애초에 아무 신호도 내지 못하는 질의

| 색인 모드 | BM25 무신호 질의 | 고유 색인문서 | hybrid top-10 = dense top-10 (α=0.5) |
|---|---:|---:|---:|
| full_text | 95/151 | 1783 | 95/151 |
| minimal_text | 96/151 | 1783 | 96/151 |
| minimal_no_code | 96/151 | 1656 | 96/151 |

> 무신호 질의는 어휘 교집합이 0이어서 top-10을 만들 수 없다. 이전 코드는 이 경우
> 코퍼스 배열 앞머리를 결과로 집계했다.

## 2. R@10 (95% CI = Clopper-Pearson)

### bge-m3 (revision `5617a9f61b028005a4858fdac845db406aefb181`)

| 색인 | retriever | 전체 R@10 | 95% CI | 영어 | 한국어 |
|---|---|---:|---|---:|---:|
| full_text | BM25 | 0.1523 | [0.099, 0.220] | 0.4524 | 0.0367 |
| full_text | hybrid_0.7 | 0.5629 | [0.480, 0.643] | 0.5238 | 0.5780 |
| full_text | hybrid_0.5 | 0.5828 | [0.500, 0.662] | 0.5476 | 0.5963 |
| full_text | hybrid_0.3 | 0.6026 | [0.520, 0.681] | 0.6190 | 0.5963 |
| full_text | dense | 0.5894 | [0.506, 0.669] | 0.5714 | 0.5963 |
| minimal_text | BM25 | 0.1523 | [0.099, 0.220] | 0.4762 | 0.0275 |
| minimal_text | hybrid_0.7 | 0.5364 | [0.454, 0.618] | 0.5238 | 0.5413 |
| minimal_text | hybrid_0.5 | 0.5497 | [0.467, 0.631] | 0.5238 | 0.5596 |
| minimal_text | hybrid_0.3 | 0.5894 | [0.506, 0.669] | 0.5952 | 0.5872 |
| minimal_text | dense | 0.5695 | [0.486, 0.650] | 0.5476 | 0.5780 |
| minimal_no_code | BM25 | 0.1523 | [0.099, 0.220] | 0.4762 | 0.0275 |
| minimal_no_code | hybrid_0.7 | 0.5430 | [0.460, 0.624] | 0.5000 | 0.5596 |
| minimal_no_code | hybrid_0.5 | 0.5430 | [0.460, 0.624] | 0.5000 | 0.5596 |
| minimal_no_code | hybrid_0.3 | 0.5563 | [0.473, 0.637] | 0.5238 | 0.5688 |
| minimal_no_code | dense | 0.5695 | [0.486, 0.650] | 0.5476 | 0.5780 |

### e5-base (revision `d128750597153bb5987e10b1c3493a34e5a4502a`)

| 색인 | retriever | 전체 R@10 | 95% CI | 영어 | 한국어 |
|---|---|---:|---|---:|---:|
| full_text | BM25 | 0.1523 | [0.099, 0.220] | 0.4524 | 0.0367 |
| full_text | hybrid_0.7 | 0.4570 | [0.376, 0.540] | 0.5238 | 0.4312 |
| full_text | hybrid_0.5 | 0.4768 | [0.395, 0.560] | 0.5476 | 0.4495 |
| full_text | hybrid_0.3 | 0.4768 | [0.395, 0.560] | 0.5476 | 0.4495 |
| full_text | dense | 0.4371 | [0.357, 0.520] | 0.4524 | 0.4312 |
| minimal_text | BM25 | 0.1523 | [0.099, 0.220] | 0.4762 | 0.0275 |
| minimal_text | hybrid_0.7 | 0.4636 | [0.382, 0.546] | 0.5238 | 0.4404 |
| minimal_text | hybrid_0.5 | 0.4901 | [0.408, 0.573] | 0.5714 | 0.4587 |
| minimal_text | hybrid_0.3 | 0.5099 | [0.427, 0.592] | 0.5952 | 0.4771 |
| minimal_text | dense | 0.4768 | [0.395, 0.560] | 0.5000 | 0.4679 |
| minimal_no_code | BM25 | 0.1523 | [0.099, 0.220] | 0.4762 | 0.0275 |
| minimal_no_code | hybrid_0.7 | 0.4702 | [0.389, 0.553] | 0.5000 | 0.4587 |
| minimal_no_code | hybrid_0.5 | 0.4901 | [0.408, 0.573] | 0.5476 | 0.4679 |
| minimal_no_code | hybrid_0.3 | 0.5033 | [0.421, 0.586] | 0.5952 | 0.4679 |
| minimal_no_code | dense | 0.4967 | [0.414, 0.579] | 0.5238 | 0.4862 |

### MiniLM (revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`)

| 색인 | retriever | 전체 R@10 | 95% CI | 영어 | 한국어 |
|---|---|---:|---|---:|---:|
| full_text | BM25 | 0.1523 | [0.099, 0.220] | 0.4524 | 0.0367 |
| full_text | hybrid_0.7 | 0.5430 | [0.460, 0.624] | 0.5238 | 0.5505 |
| full_text | hybrid_0.5 | 0.5497 | [0.467, 0.631] | 0.5238 | 0.5596 |
| full_text | hybrid_0.3 | 0.5497 | [0.467, 0.631] | 0.5238 | 0.5596 |
| full_text | dense | 0.5166 | [0.434, 0.599] | 0.4524 | 0.5413 |
| minimal_text | BM25 | 0.1523 | [0.099, 0.220] | 0.4762 | 0.0275 |
| minimal_text | hybrid_0.7 | 0.4702 | [0.389, 0.553] | 0.5000 | 0.4587 |
| minimal_text | hybrid_0.5 | 0.5099 | [0.427, 0.592] | 0.5476 | 0.4954 |
| minimal_text | hybrid_0.3 | 0.5099 | [0.427, 0.592] | 0.5476 | 0.4954 |
| minimal_text | dense | 0.4503 | [0.369, 0.533] | 0.3810 | 0.4771 |
| minimal_no_code | BM25 | 0.1523 | [0.099, 0.220] | 0.4762 | 0.0275 |
| minimal_no_code | hybrid_0.7 | 0.4570 | [0.376, 0.540] | 0.4762 | 0.4495 |
| minimal_no_code | hybrid_0.5 | 0.4901 | [0.408, 0.573] | 0.5238 | 0.4771 |
| minimal_no_code | hybrid_0.3 | 0.4967 | [0.414, 0.579] | 0.5476 | 0.4771 |
| minimal_no_code | dense | 0.4437 | [0.363, 0.527] | 0.4286 | 0.4495 |

## 3. 검색기 비교 (paired bootstrap + exact McNemar, Holm 보정)

| 모델 | 색인 | 비교 | 평균차 | 95% CI | 승/패/무 | exact p | Holm p |
|---|---|---|---:|---|---:|---:|---:|
| bge-m3 | full_text | hybrid_vs_bm25[overall] | +0.4305 | [0.3510, 0.5099] | 65/0/86 | 5.42e-20 | 0 |
| bge-m3 | full_text | dense_vs_bm25[overall] | +0.4371 | [0.3510, 0.5232] | 69/3/79 | 2.64e-17 | 0 |
| bge-m3 | full_text | hybrid_vs_dense[overall] | -0.0066 | [-0.0397, 0.0265] | 3/4/144 | 1 | 1 |
| bge-m3 | full_text | hybrid_vs_bm25[en] | +0.0952 | [0.0238, 0.1905] | 4/0/38 | 0.125 | 0.625 |
| bge-m3 | full_text | dense_vs_bm25[en] | +0.1190 | [0.0000, 0.2619] | 7/2/33 | 0.18 | 0.719 |
| bge-m3 | full_text | hybrid_vs_dense[en] | -0.0238 | [-0.1190, 0.0714] | 2/3/37 | 1 | 1 |
| bge-m3 | full_text | hybrid_vs_bm25[ko] | +0.5596 | [0.4679, 0.6514] | 61/0/48 | 8.67e-19 | 0 |
| bge-m3 | full_text | dense_vs_bm25[ko] | +0.5596 | [0.4587, 0.6514] | 62/1/46 | 1.39e-17 | 0 |
| bge-m3 | full_text | hybrid_vs_dense[ko] | +0.0000 | [-0.0275, 0.0275] | 1/1/107 | 1 | 1 |
| bge-m3 | minimal_text | hybrid_vs_bm25[overall] | +0.3974 | [0.3179, 0.4768] | 60/0/91 | 1.73e-18 | 0 |
| bge-m3 | minimal_text | dense_vs_bm25[overall] | +0.4172 | [0.3377, 0.5033] | 65/2/84 | 3.09e-17 | 0 |
| bge-m3 | minimal_text | hybrid_vs_dense[overall] | -0.0199 | [-0.0530, 0.0132] | 2/5/144 | 0.453 | 1 |
| bge-m3 | minimal_text | hybrid_vs_bm25[en] | +0.0476 | [0.0000, 0.1190] | 2/0/40 | 0.5 | 1 |
| bge-m3 | minimal_text | dense_vs_bm25[en] | +0.0714 | [-0.0476, 0.1905] | 5/2/35 | 0.453 | 1 |
| bge-m3 | minimal_text | hybrid_vs_dense[en] | -0.0238 | [-0.1190, 0.0714] | 2/3/37 | 1 | 1 |
| bge-m3 | minimal_text | hybrid_vs_bm25[ko] | +0.5321 | [0.4404, 0.6239] | 58/0/51 | 6.94e-18 | 0 |
| bge-m3 | minimal_text | dense_vs_bm25[ko] | +0.5505 | [0.4587, 0.6422] | 60/0/49 | 1.73e-18 | 0 |
| bge-m3 | minimal_text | hybrid_vs_dense[ko] | -0.0183 | [-0.0459, 0.0000] | 0/2/107 | 0.5 | 1 |
| bge-m3 | minimal_no_code | hybrid_vs_bm25[overall] | +0.3907 | [0.3113, 0.4702] | 59/0/92 | 3.47e-18 | 0 |
| bge-m3 | minimal_no_code | dense_vs_bm25[overall] | +0.4172 | [0.3377, 0.4967] | 64/1/86 | 3.58e-18 | 0 |
| bge-m3 | minimal_no_code | hybrid_vs_dense[overall] | -0.0265 | [-0.0596, 0.0000] | 1/5/145 | 0.219 | 1 |
| bge-m3 | minimal_no_code | hybrid_vs_bm25[en] | +0.0238 | [0.0000, 0.0714] | 1/0/41 | 1 | 1 |
| bge-m3 | minimal_no_code | dense_vs_bm25[en] | +0.0714 | [-0.0238, 0.1667] | 4/1/37 | 0.375 | 1 |
| bge-m3 | minimal_no_code | hybrid_vs_dense[en] | -0.0476 | [-0.1429, 0.0476] | 1/3/38 | 0.625 | 1 |
| bge-m3 | minimal_no_code | hybrid_vs_bm25[ko] | +0.5321 | [0.4404, 0.6239] | 58/0/51 | 6.94e-18 | 0 |
| bge-m3 | minimal_no_code | dense_vs_bm25[ko] | +0.5505 | [0.4587, 0.6422] | 60/0/49 | 1.73e-18 | 0 |
| bge-m3 | minimal_no_code | hybrid_vs_dense[ko] | -0.0183 | [-0.0459, 0.0000] | 0/2/107 | 0.5 | 1 |
| e5-base | full_text | hybrid_vs_bm25[overall] | +0.3245 | [0.2517, 0.4040] | 50/1/100 | 4.62e-14 | 0 |
| e5-base | full_text | dense_vs_bm25[overall] | +0.2848 | [0.1987, 0.3709] | 49/6/96 | 1.82e-09 | 1.09e-08 |
| e5-base | full_text | hybrid_vs_dense[overall] | +0.0397 | [0.0000, 0.0795] | 8/2/141 | 0.109 | 0.547 |
| e5-base | full_text | hybrid_vs_bm25[en] | +0.0952 | [0.0000, 0.2143] | 5/1/36 | 0.219 | 0.875 |
| e5-base | full_text | dense_vs_bm25[en] | +0.0000 | [-0.1429, 0.1190] | 4/4/34 | 1 | 1 |
| e5-base | full_text | hybrid_vs_dense[en] | +0.0952 | [0.0000, 0.2143] | 5/1/36 | 0.219 | 0.875 |
| e5-base | full_text | hybrid_vs_bm25[ko] | +0.4128 | [0.3211, 0.5046] | 45/0/64 | 5.68e-14 | 0 |
| e5-base | full_text | dense_vs_bm25[ko] | +0.3945 | [0.2936, 0.4954] | 45/2/62 | 1.6e-11 | 1e-10 |
| e5-base | full_text | hybrid_vs_dense[ko] | +0.0183 | [-0.0183, 0.0550] | 3/1/105 | 0.625 | 1 |
| e5-base | minimal_text | hybrid_vs_bm25[overall] | +0.3377 | [0.2649, 0.4172] | 51/0/100 | 8.88e-16 | 0 |
| e5-base | minimal_text | dense_vs_bm25[overall] | +0.3245 | [0.2384, 0.4106] | 54/5/92 | 1.91e-11 | 1e-10 |
| e5-base | minimal_text | hybrid_vs_dense[overall] | +0.0132 | [-0.0331, 0.0596] | 7/5/139 | 0.774 | 1 |
| e5-base | minimal_text | hybrid_vs_bm25[en] | +0.0952 | [0.0238, 0.1905] | 4/0/38 | 0.125 | 0.625 |
| e5-base | minimal_text | dense_vs_bm25[en] | +0.0238 | [-0.0952, 0.1429] | 4/3/35 | 1 | 1 |
| e5-base | minimal_text | hybrid_vs_dense[en] | +0.0714 | [-0.0476, 0.1905] | 5/2/35 | 0.453 | 1 |
| e5-base | minimal_text | hybrid_vs_bm25[ko] | +0.4312 | [0.3394, 0.5229] | 47/0/62 | 1.42e-14 | 0 |
| e5-base | minimal_text | dense_vs_bm25[ko] | +0.4404 | [0.3394, 0.5413] | 50/2/57 | 6.12e-13 | 0 |
| e5-base | minimal_text | hybrid_vs_dense[ko] | -0.0092 | [-0.0459, 0.0275] | 2/3/104 | 1 | 1 |
| e5-base | minimal_no_code | hybrid_vs_bm25[overall] | +0.3377 | [0.2649, 0.4172] | 51/0/100 | 8.88e-16 | 0 |
| e5-base | minimal_no_code | dense_vs_bm25[overall] | +0.3444 | [0.2649, 0.4305] | 56/4/91 | 9.08e-13 | 0 |
| e5-base | minimal_no_code | hybrid_vs_dense[overall] | -0.0066 | [-0.0464, 0.0331] | 4/5/142 | 1 | 1 |
| e5-base | minimal_no_code | hybrid_vs_bm25[en] | +0.0714 | [0.0000, 0.1667] | 3/0/39 | 0.25 | 1 |
| e5-base | minimal_no_code | dense_vs_bm25[en] | +0.0476 | [-0.0714, 0.1905] | 5/3/34 | 0.727 | 1 |
| e5-base | minimal_no_code | hybrid_vs_dense[en] | +0.0238 | [-0.0714, 0.1190] | 3/2/37 | 1 | 1 |
| e5-base | minimal_no_code | hybrid_vs_bm25[ko] | +0.4404 | [0.3486, 0.5321] | 48/0/61 | 7.11e-15 | 0 |
| e5-base | minimal_no_code | dense_vs_bm25[ko] | +0.4587 | [0.3578, 0.5596] | 51/1/57 | 2.35e-14 | 0 |
| e5-base | minimal_no_code | hybrid_vs_dense[ko] | -0.0183 | [-0.0550, 0.0183] | 1/3/105 | 0.625 | 1 |
| MiniLM | full_text | hybrid_vs_bm25[overall] | +0.3974 | [0.3179, 0.4768] | 61/1/89 | 2.73e-17 | 0 |
| MiniLM | full_text | dense_vs_bm25[overall] | +0.3642 | [0.2781, 0.4570] | 61/6/84 | 1.49e-12 | 0 |
| MiniLM | full_text | hybrid_vs_dense[overall] | +0.0331 | [0.0066, 0.0662] | 5/0/146 | 0.0625 | 0.312 |
| MiniLM | full_text | hybrid_vs_bm25[en] | +0.0714 | [-0.0238, 0.1667] | 4/1/37 | 0.375 | 1 |
| MiniLM | full_text | dense_vs_bm25[en] | +0.0000 | [-0.1190, 0.1190] | 4/4/34 | 1 | 1 |
| MiniLM | full_text | hybrid_vs_dense[en] | +0.0714 | [0.0000, 0.1667] | 3/0/39 | 0.25 | 1 |
| MiniLM | full_text | hybrid_vs_bm25[ko] | +0.5229 | [0.4312, 0.6147] | 57/0/52 | 1.39e-17 | 0 |
| MiniLM | full_text | dense_vs_bm25[ko] | +0.5046 | [0.4037, 0.6055] | 57/2/50 | 6.14e-15 | 0 |
| MiniLM | full_text | hybrid_vs_dense[ko] | +0.0183 | [0.0000, 0.0459] | 2/0/107 | 0.5 | 1 |
| MiniLM | minimal_text | hybrid_vs_bm25[overall] | +0.3576 | [0.2848, 0.4371] | 54/0/97 | 1.11e-16 | 0 |
| MiniLM | minimal_text | dense_vs_bm25[overall] | +0.2980 | [0.2119, 0.3841] | 53/8/90 | 2.99e-09 | 1.79e-08 |
| MiniLM | minimal_text | hybrid_vs_dense[overall] | +0.0596 | [0.0199, 0.1060] | 10/1/140 | 0.0117 | 0.0586 |
| MiniLM | minimal_text | hybrid_vs_bm25[en] | +0.0714 | [0.0000, 0.1667] | 3/0/39 | 0.25 | 0.75 |
| MiniLM | minimal_text | dense_vs_bm25[en] | -0.0952 | [-0.2143, 0.0238] | 2/6/34 | 0.289 | 0.75 |
| MiniLM | minimal_text | hybrid_vs_dense[en] | +0.1667 | [0.0476, 0.3095] | 8/1/33 | 0.0391 | 0.156 |
| MiniLM | minimal_text | hybrid_vs_bm25[ko] | +0.4679 | [0.3761, 0.5596] | 51/0/58 | 8.88e-16 | 0 |
| MiniLM | minimal_text | dense_vs_bm25[ko] | +0.4495 | [0.3486, 0.5505] | 51/2/56 | 3.18e-13 | 0 |
| MiniLM | minimal_text | hybrid_vs_dense[ko] | +0.0183 | [0.0000, 0.0459] | 2/0/107 | 0.5 | 0.75 |
| MiniLM | minimal_no_code | hybrid_vs_bm25[overall] | +0.3377 | [0.2649, 0.4172] | 51/0/100 | 8.88e-16 | 0 |
| MiniLM | minimal_no_code | dense_vs_bm25[overall] | +0.2914 | [0.2053, 0.3775] | 50/6/95 | 1.02e-09 | 6.1e-09 |
| MiniLM | minimal_no_code | hybrid_vs_dense[overall] | +0.0464 | [0.0066, 0.0927] | 9/2/140 | 0.0654 | 0.327 |
| MiniLM | minimal_no_code | hybrid_vs_bm25[en] | +0.0476 | [0.0000, 0.1190] | 2/0/40 | 0.5 | 1 |
| MiniLM | minimal_no_code | dense_vs_bm25[en] | -0.0476 | [-0.1667, 0.0714] | 2/4/36 | 0.688 | 1 |
| MiniLM | minimal_no_code | hybrid_vs_dense[en] | +0.0952 | [-0.0238, 0.2381] | 6/2/34 | 0.289 | 1 |
| MiniLM | minimal_no_code | hybrid_vs_bm25[ko] | +0.4495 | [0.3578, 0.5413] | 49/0/60 | 3.55e-15 | 0 |
| MiniLM | minimal_no_code | dense_vs_bm25[ko] | +0.4220 | [0.3211, 0.5229] | 48/2/59 | 2.27e-12 | 0 |
| MiniLM | minimal_no_code | hybrid_vs_dense[ko] | +0.0275 | [0.0000, 0.0642] | 3/0/106 | 0.25 | 1 |

> `hybrid_vs_dense`는 기존 산출물에 한 번도 없던 비교다. 한국어에서 BM25 점수가
> 항등 0이면 α<1의 랭킹은 dense와 수학적으로 동일하므로 승/패가 0/0으로 나오는 것이
> 정상이다 — 즉 '하이브리드가 필요하다'가 아니라 'dense 성분이 필요하다'가 데이터가
> 지지하는 진술이다.

## 4. 노출량@10 — 색인 모드 × 반환 모드

| 색인 모드 | 반환=full_text | 반환=minimal_text | 반환=minimal_no_code | 정정 전 정의 |
|---|---|---|---|---|
| full_text | 7886 | 1781 | 1691 | 7796 |
| minimal_text | 5868 | 1806 | 1715 | 1715 |
| minimal_no_code | 5804 | 1708 | 1618 | 1618 |

> 정정 전 정의는 `minimal_text`와 `minimal_no_code`에 동일한 값을 부여했다.
> 대각선이 아닌 칸(예: 색인=minimal_text, 반환=minimal_no_code)은 색인 품질을
> 유지하면서 반환량만 줄이는 조건이며, 기존 설계로는 측정할 수 없었다.

## 5. 정보최소화 등가성 검정 (TOST)

사전지정 마진 δ=0.05. 'CI가 0을 포함' 은 등가성의 근거가 아니다.

| 비교 | 평균차 | 95% CI | 승/패/무 | exact p | δ=0.05 등가? | δ=0.05 필요 n | δ=0.03 필요 n |
|---|---:|---|---:|---:|---|---:|---:|
| minimal_text_vs_full_text[hybrid_0.5] | -0.0397 | [-0.0927, 0.0132] | 5/11/135 | 0.21 | **아니오** | 6166 | - |
| minimal_text_vs_full_text[dense] | -0.0662 | [-0.1126, -0.0265] | 1/11/139 | 0.00635 | **아니오** | - | - |
| minimal_text_vs_full_text[BM25] | +0.0000 | [-0.0331, 0.0397] | 4/4/143 | 1 | 예 | 132 | 367 |
| minimal_no_code_vs_full_text[hybrid_0.5] | -0.0596 | [-0.1192, 0.0000] | 7/16/128 | 0.0931 | **아니오** | - | - |
| minimal_no_code_vs_full_text[dense] | -0.0728 | [-0.1325, -0.0132] | 5/16/130 | 0.0266 | **아니오** | - | - |
| minimal_no_code_vs_full_text[BM25] | +0.0000 | [-0.0331, 0.0397] | 4/4/143 | 1 | 예 | 132 | 367 |

### 마진별 민감도 (p_max, δ가 클수록 통과하기 쉬움)

| 비교 | δ=0.03 | δ=0.05 | δ=0.075 | δ=0.1 | δ=0.15 |
|---|---|---|---|---|---|
| minimal_text_vs_full_text[hybrid_0.5] | 0.644 | 0.349 | 0.0906 | 0.0112 | 1.46e-05 |
| minimal_text_vs_full_text[dense] | 0.947 | 0.766 | 0.347 | 0.0656 | 9.04e-05 |
| minimal_text_vs_full_text[BM25] | 0.0552 | 0.0039 | 3.29e-05 | 5.16e-08 | 7.23e-16 |
| minimal_no_code_vs_full_text[hybrid_0.5] | 0.826 | 0.62 | 0.312 | 0.0998 | 0.00205 |
| minimal_no_code_vs_full_text[dense] | 0.924 | 0.778 | 0.471 | 0.182 | 0.00489 |
| minimal_no_code_vs_full_text[BM25] | 0.0552 | 0.0039 | 3.29e-05 | 5.16e-08 | 7.23e-16 |

> p_max < 0.05 이면 해당 마진에서 등가(비열등)로 볼 수 있다. 표본이 작으면
> 좁은 마진은 원리상 통과할 수 없으므로 '필요 n' 열을 함께 읽어야 한다.
