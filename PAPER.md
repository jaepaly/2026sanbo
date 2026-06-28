# 최소정보노출 사전검토에서의 전략물자 후보검색: 자기참조 평가의 함정과 다국어 하이브리드 검색의 필요성

> 본 문서는 산업보안논문경진대회 제출용 논문 초안이다. 모든 수치는 저장소의 재현 가능한 스크립트(시드 고정, 외부 추론 API 미사용)가 생성한 `output/*.json`에서 직접 가져왔으며, 14절(재현성)에 청구↔근거 매핑을 둔다.

## 초록

기업이 외부 인공지능·검색 서비스로 전략물자 통제목록 후보를 탐색하려면 제품·기술 사양을 외부 시스템에 전송해야 하는 정보노출 부담을 진다. 본 연구는 법적 판정이 아닌 **사전 후보검색** 단계에서, 반환·처리하는 통제목록 정보량을 줄이면서 후보검색 성능을 유지할 수 있는지를 실험적으로 분석한다. Wassenaar Arrangement 2025, India SCOMET 2024, U.S. eCFR Commerce Control List를 정화해 1,797개 항목 코퍼스를 구축하고, 두 종류의 평가셋(① 통제목록 설명문에서 파생한 합성 쿼리 780개, ② 통제항목을 *역으로* 묘사한 검증 상담형 질의 71개)을 사용한다.

세 가지 핵심 결과를 보고한다. 첫째, **자기참조 합성 평가의 위험**: 합성 쿼리가 정답 문서 본문에서 파생될 때 BM25는 R@10 0.9792로 보이지만, 정답과 공유하는 변별어를 5개만 제거하면 0.7596으로 급락한다. 즉 이 수치는 후보 발견이 아니라 자기참조 재검색에 가깝다. 둘째, **검증 데이터에서의 정보최소화**: 비자기참조 검증셋(n=71)에서 반환 정보량을 55.6% 줄여도(full_text→minimal_text) 하이브리드 검색의 R@10 변화는 통계적으로 유의하지 않다(차이 −0.028, 95% CI [−0.113, +0.042]). 셋째, **저노출 후보검색에는 다국어 하이브리드가 필요**: 같은 검증셋에서 BM25는 R@10 0.169(한국어 0.022)에 그치지만 다국어 하이브리드는 0.578(한국어 0.600)이며, 그 차이는 통계적으로 유의하고(95% CI [0.296, 0.521], 29승 0패) 세 개의 독립 다국어 임베딩에서 모두 재현된다.

본 연구의 기여는 배포형 판정 시스템이 아니라 (1) 노출량-성능을 함께 보는 최소노출 평가 프레임워크, (2) 자기참조 평가 과대평가의 정량적 폭로와 교정, (3) 충돌 없는 코퍼스 텍스트 근거 검증 질의셋과 자동 누출검사기다. 본 시스템은 전략물자 해당 여부를 판정하지 않으며, 한국 대외무역법·전략물자수출입고시·산업기술보호법·국가핵심기술 제도와 연계한 보수적 사전검토 보조로 한정한다.

---

## 1. 서론

### 1.1 문제의식
전략물자 수출 시 기업은 자사 품목이 통제목록에 해당하는지 사전 검토해야 한다. 최근 외부 LLM·검색 서비스를 이용한 후보검색이 늘고 있으나, 이 과정에서 **도면·사양·기술설명 등 민감한 기술정보가 외부 시스템으로 전송**된다. 이는 산업보안 관점에서 영업비밀·국가핵심기술 유출 위험을 수반한다. 본 연구는 "후보검색 성능을 유지하면서 외부로 노출·반환하는 정보량을 줄일 수 있는가"라는 **정보최소화(minimum necessary disclosure)** 질문을 다룬다.

### 1.2 본 연구가 하지 않는 것 (범위 한정)
본 시스템은 전략물자 해당/비해당을 **법적으로 판정하지 않는다.** 자가판정·전문판정을 대체하거나 보조하지 않으며, 산출물은 "후보 통제항목 목록"일 뿐이다. 모든 수치는 후보검색 성능(Recall@k)이며 법적 분류 정확도가 아니다.

### 1.3 기여
1. **최소노출 평가 프레임워크**: 노출 모드(full/minimal/minimal_no_code)와 retriever(BM25/dense/hybrid)를 교차하여 노출량-성능 frontier를 정식화한다.
2. **자기참조 평가의 과대평가 폭로와 교정**: 합성 벤치마크가 sparse retrieval을 과대평가함을 정량화하고(어휘 민감도), 비자기참조 검증셋으로 교정한다.
3. **충돌 없는 검증 질의셋과 자동 검사기**: 통제항목을 역으로 묘사한 71개 검증 질의와, 코드누출·자기참조(Jaccard)·언어비율을 강제하는 `validate_query_slice.py`.
4. **한국 법제 연계 워크플로우**: 판정이 아닌 사전검토 보조로 한정한 보수적 설계.

---

## 2. 배경 및 관련 연구

- **전략물자 통제체계**: Wassenaar(국제 이중용도·군용), India SCOMET, U.S. EAR Commerce Control List(eCFR Part 774). 항목은 통제번호(ECCN 등)와 설명문으로 구성된다.
- **검색 기반 분류**: 통제목록 후보검색은 정보검색(IR) 문제로 볼 수 있다. 선행연구로 수출통제 분류에 BERT·머신러닝을 적용한 사례(Ryu et al. 2025; Nelson, WCO)가 있으나, 본 연구의 초점은 분류 정확도가 아니라 **정보노출 최소화 하에서의 후보검색**이다.
- **정보최소화·보안**: 외부 추론 호출 자체가 노출 경로이므로, 본 연구는 인덱싱·검색을 로컬에서 수행하고 외부 추론 API를 호출하지 않는 설계를 전제로 한다.
- **한국 법제**: 대외무역법, 전략물자수출입고시, 산업기술보호법, 국가핵심기술 제도(6절).

---

## 3. 데이터와 방법

### 3.1 코퍼스
정화 후 1,797개 항목.

| 소스 | 항목 수 |
|---|---:|
| Wassenaar Arrangement 2025 | 585 |
| India SCOMET 2024 | 575 |
| U.S. eCFR CCL (15 CFR Part 774 Supp.1) | 637 |

코퍼스는 **100% 영어**(한글 포함 항목 0개)이며, 이는 한국어 질의의 cross-lingual 문제(4.6)의 배경이 된다.

### 3.2 노출 조건(반환 정보량)
| 조건 | 색인·반환 정보 | 노출량 proxy |
|---|---|---|
| `full_text` | 통제번호 + 설명 전체 | 전체 문자 수 |
| `minimal_text` | 통제번호 + 첫 핵심 문장 | 첫 문장 문자 수 |
| `minimal_no_code` | 첫 핵심 문장(통제번호 제외) | 첫 문장 문자 수 |
| `route_only` | 통제체계·업무흐름 힌트 | 극단 저노출 음성 대조군 |

노출량@10 = top-10 반환 문서의 노출 proxy 합(문자 수 기반 proxy이며 실제 민감도와 동일하지 않음, 7절).

### 3.3 검색기(retriever)
- **BM25**: 투명 sparse 기준선(자체 구현, k1=1.2, b=0.75).
- **Dense**: 다국어 문장 임베딩(`paraphrase-multilingual-MiniLM-L12-v2`; robustness용으로 `multilingual-e5-base`, `bge-m3` 추가). 코사인 유사도.
- **Hybrid**: 쿼리별 min-max 정규화 후 `α·BM25 + (1−α)·Dense` (α=0.5 기본). 모든 임베딩은 로컬 실행, 외부 추론 API 미사용.

### 3.4 평가셋
1. **합성셋(780)**: 각 코퍼스 항목 본문에서 통제번호를 제거해 템플릿에 감싼 설명형 쿼리(train/val/test = 78/78/624). 코드누출 자동 차단. **한계: 쿼리가 정답 문서 본문에서 파생되어 near-duplicate**(4.1).
2. **검증 상담형 질의셋(71)**: 통제항목을 *먼저 고르고 그 항목을 묘사하는* 상담형 질의를 원문 인용 없이 역생성(라벨이 구조적으로 확정). eCFR full code로 핀 고정(충돌 0). `validate_query_slice.py`가 코드누출 0, 질의-항목 Jaccard < 0.30, 한국어 비율 ≥ 0.40을 강제. 영어 26 / 한국어 45.
   - 라벨 성격: **코퍼스 텍스트 근거 카테고리 라벨**(법적 판정 아님, 전문가 검증 아님).

### 3.5 지표·통계
Recall@1/5/10, MRR, nDCG@10, 노출량@10. 통계는 seed 고정 bootstrap(20,000회) 95% 신뢰구간과 효과크기(평균차); 검증셋은 질의별 hit를 쓰는 paired bootstrap. 합성셋 조건 비교는 permutation test 병행.

---

## 4. 결과

### 4.1 자기참조 합성 평가의 과대평가
합성셋에서 `minimal_text`는 `full_text` 대비 노출량@10을 **66.4% 감소**(4,834→1,623자)시키면서 R@10 0.9968→0.9792를 보였다. 그러나 쿼리-정답(minimal_text) 평균 Jaccard가 **0.485**로, 쿼리와 정답 문서가 near-duplicate다. 정답 문서와 공유하는 고-IDF 변별어를 N개 제거하면:

| 제거 변별어 N | R@10 (minimal_text) |
|---:|---:|
| 0 (기존 헤드라인) | 0.9792 |
| 5 | 0.7596 |
| 10 | 0.4407 |

변별어 5개 제거에 R@10이 −22%p, 10개에 반토막. **합성 R@10 0.9792는 후보 발견이 아니라 자기참조 재검색에 가깝다.** 따라서 절대수치를 헤드라인으로 쓰지 않는다.

### 4.2 검색기 비교: 합성셋은 BM25를 구조적으로 과대평가
자기참조 합성셋에서는 BM25가 모든 어휘격차 레벨에서 dense를 앞서고(N=10에서도 0.441 vs 0.253), 합성 "한국어" 쿼리가 한국어 지시문 + **영어 본문**이라 BM25 한국어 R@10이 0.98로 나오는 등 언어 분리가 가짜다. **즉 합성 벤치마크는 retriever 비교·cross-lingual 평가에 부적합하다.** 반면 진짜 패러프레이즈·진짜 한국어가 있는 외부 상담셋에서는 BM25 R@10=0인데 다국어 hybrid가 매칭을 회복한다(4.3에서 검증 라벨로 정밀화).

### 4.3 검증셋과 표본 확장: 효과의 통계적 입증
충돌·추정 라벨을 제거한 검증셋에서 출발(n=13: BM25 0.000, hybrid 0.231, dense 0.154; 단 hybrid−BM25의 95% CI [0.0, 0.46]은 0을 포함, 비유의). 이어 통제항목을 역생성한 검증 질의 60개를 추가·병합(중복 코드 자동 배제)하여 **n=71(영어 26, 한국어 45)**로 확대:

| retriever | 전체 R@10 | 영어 R@10 | 한국어 R@10 |
|---|---:|---:|---:|
| BM25 (α=1.0) | 0.169 | 0.423 | 0.022 |
| **Hybrid (α=0.5)** | **0.578** | 0.538 | **0.600** |
| Dense (α=0.0) | 0.549 | 0.462 | 0.600 |

paired bootstrap 95% CI: **Hybrid−BM25 = +0.409, [0.296, 0.521], 29승 0패**; Dense−BM25 = +0.380, [0.254, 0.493]. **n=13에서 0을 포함하던 차이가 n=71에서 0을 벗어나 통계적으로 유의**해졌다. BM25는 영어에서도 0.42, 한국어에서 0.022로 상담형·한국어 질의에 부적합하다.

### 4.4 임베딩 robustness
같은 확장셋에서 dense 모델을 교체:

| dense 모델 | Hybrid(α0.5) 전체 | 한국어 | Hybrid−BM25 95% CI | 유의 |
|---|---:|---:|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | 0.578 | 0.600 | [0.296, 0.521] | 예 |
| intfloat/multilingual-e5-base | 0.437 | 0.400 | [0.155, 0.380] | 예 |
| BAAI/bge-m3 | 0.563 | 0.622 | [0.282, 0.507] | 예 |

(BM25 동일: 전체 0.169, 한국어 0.022.) **세 독립 인코더 모두 hybrid>BM25가 유의**하고 한국어가 회복된다. 우위는 모델 특이적 산물이 아니다(절대값은 MiniLM≈bge-m3 > e5-base).

### 4.5 노출-성능 frontier (검증 데이터)
정보최소화 주장을 자기참조 합성셋이 아니라 **확장 검증셋(n=71)**에서 직접 측정:

| 노출 모드 | 노출량@10 | Hybrid R@10 | BM25 R@10 |
|---|---:|---:|---:|
| full_text | 3,952 | 0.606 | 0.183 |
| minimal_text | 1,754 | 0.578 | 0.169 |
| minimal_no_code | 1,663 | 0.521 | 0.169 |

full_text→minimal_text는 **노출량 55.6% 감소**에 hybrid R@10 0.606→0.578, 차이 −0.028, **95% CI [−0.113, +0.042]로 0을 포함 — 유의한 성능 손실 없음.** 즉 정보최소화가 성능을 유의하게 해치지 않는다는 핵심 주장이 검증 데이터로 입증된다. BM25는 노출을 늘려도 0.17대로 정체 — 한계가 정보량이 아니라 어휘·언어 불일치임을 재확인한다.

### 4.6 한국어 cross-lingual
코퍼스가 100% 영어라 BM25는 한국어에서 어휘 매칭이 불가능하다. 검증셋 한국어 질의 5개를 사람이 영어로 수동 번역(외부 API 미사용)해 비교:

| track | BM25 | Hybrid(α0.5) | Dense | n |
|---|---:|---:|---:|---:|
| KO-원문 | 0.000 | 0.200 | 0.200 | 5 |
| KO-번역 | 0.200 | 0.200 | 0.200 | 5 |
| EN-원문 | 0.000 | 0.250 | 0.125 | 8 |

KO-원문 BM25=0에서 (a) 영어 번역 시 BM25 0→0.20, (b) 다국어 dense는 번역 없이도 0.20. **번역 경로와 다국어 임베딩 경로가 한국어 0점을 비슷하게 회복**한다(표본 5개, 경향). 4.3의 확장셋(한국어 n=45)에서 다국어 hybrid의 한국어 0.60은 이를 더 큰 표본으로 뒷받침한다.

---

## 5. 논의

본 연구의 두 축이 모두 검증 데이터 위에 선다.
1. **정보최소화는 성능을 유의하게 해치지 않는다**(노출 −55.6%, 유의 손실 없음; 4.5).
2. **그 저노출 후보검색에는 BM25가 아니라 다국어 hybrid가 통계적으로 유의하게 필요하다**(4.3–4.4).

부수적이지만 방법론적으로 중요한 기여는 **자기참조 합성 평가가 sparse retrieval을 과대평가**한다는 정량적 폭로다(4.1–4.2). 정보검색·RAG 연구에서 평가셋을 코퍼스에서 자동 파생할 때 흔한 함정이며, 본 연구는 역생성·자동 누출검사로 이를 교정하는 절차를 제시한다. 실용적 함의: 외부 AI 사전검토 도구는 (a) 반환 정보량을 최소화하고, (b) 한국어·상담형 질의를 위해 다국어 dense/hybrid를 채택해야 하며, (c) 산출물을 후보목록으로 한정하고 공식 판정 절차로 연결해야 한다.

---

## 6. 한국 법제도 연계 및 운영 워크플로우

minimal_text 후보검색은 다음과 연계된다: 대외무역법 제18조(전략물자 수출 제한)·전략물자수출입고시(신고 절차), 산업기술보호법(해외 기술유출 방지), 국가핵심기술 제도(해외 이전 승인). 워크플로우 전제:
1. 본 시스템은 **사전 후보검색 보조로만** 사용한다.
2. 최종 판정은 YesTrade 자가판정/전문판정, 관세사 검토, 산업통상자원부 승인을 따른다.
3. 기술자료(도면·특허·소스코드) 동반 이전 시 산업기술보호법상 별도 검토가 필요하다.

상세: `docs/korean_regulatory_framework.md`.

---

## 7. 한계

1. **라벨이 전문가 검증이 아님**: 검증 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 법적·전문가 판정이 아니다. 관세사/실무자 검수가 후속 과제다.
2. **질의가 합성(역생성)**: 실제 기업·관세사 질의가 아니다. 역생성으로 라벨 확정성과 자기참조 제거는 달성했으나 현장 대표성은 제한된다.
3. **표본·라벨공간**: 검증셋 n=71(영어 26/한국어 45)로 여전히 중간 규모이며, 정답 라벨은 eCFR로 한정했다.
4. **절대 성능은 중간 수준**: 최고 hybrid R@10 0.578로 top-10에서 관련 항목의 약 42%를 놓친다. 배포 가능성을 주장하지 않으며 사전검토 보조로만 본다.
5. **단일 라벨**: 한 질의에 한 항목을 정답으로 두어, 여러 ECCN에 걸치는 품목에서 과소집계될 수 있다(상대 비교에는 영향이 작다).
6. **노출량 proxy**: 문자 수 기반으로 실제 영업비밀 민감도와 동일하지 않다.

---

## 8. 결론

외부 AI 기반 전략물자 사전검토에서 **정보최소화는 후보검색 성능을 유의하게 해치지 않으며(노출 −55.6%, 유의 손실 없음), 그 저노출 후보검색에는 sparse BM25가 아니라 다국어 hybrid 검색이 통계적으로 유의하게 필요**하다(세 임베딩에서 재현, 한국어 회복). 또한 자기참조 합성 평가가 sparse retrieval을 과대평가함을 정량적으로 보였다. 향후 과제: 전문가 라벨 검수, 실제 기업 질의 확보, 표본·라벨공간 확대, 민감도 가중 노출 proxy.

---

## 9. 절대 쓰면 안 되는 주장 (작성 가드레일)
- "AI가 전략물자 해당/비해당을 판정한다."
- "본 시스템이 자가판정/전문판정을 대체·보조한다."
- "추정 라벨/검증 라벨이 법적 정답이다."
- "법제 라우팅 정확도가 검증되었다."
- "실제 기업·관세사 질의까지 일반화가 확인되었다."
- "합성 R@10 0.9792가 후보검색 성능이다"(자기참조 재검색임을 명시).

---

## 10. 참고문헌·근거 링크
- [Wassenaar Arrangement Control Lists](https://www.wassenaar.org/control-lists/) · [2025 PDF](https://www.wassenaar.org/app/uploads/2025/12/List-of-Dual-Use-Goods-and-Technologies-and-ML-2025.pdf)
- [DGFT Updated SCOMET List 2024 PDF](https://content.dgft.gov.in/Website/UPDATED%20SCOMET%20List%202024%20as%20on%2002.09.2024.pdf)
- [eCFR 15 CFR Part 774 Supplement No. 1](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-774/appendix-Supplement%20No.%201%20to%20Part%20774)
- [BIS Interactive Commerce Control List](https://www.bis.gov/regulations/ear/interactive-commerce-control-list)
- [YesTrade 제도개요](https://www.yestrade.go.kr/system-guidance) · [온라인 자가판정 한계](https://www.yestrade.go.kr/judgements/self/intro)
- [전략물자수출입고시](https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000270104&chrClsCd=010201) · [국가핵심기술 제도](https://kaits.or.kr/web/content.do?menu_cd=000067)
- [Ryu, Won & Kim (2025), Intelligent Decision Support System for Nuclear Export Control: A BERT-Based Approach](https://www.tandfonline.com/doi/full/10.1080/00295450.2025.2556617)
- [Nelson, Improving Strategic Trade Detection and Classification Through Machine Learning (WCO News 94)](https://mag.wcoomd.org/magazine/wco-news-94/strategic-trade-detection-machine-learning/)

---

## 11. 재현성 (청구 ↔ 근거)

| 결과(절) | 스크립트 | 산출물 |
|---|---|---|
| 합성 frontier·자기참조(4.1) | `run_experiments.py`, `experiment_paraphrase_gap.py` | `output/experiment_logs.json`, `output/paraphrase_gap.{json,md}` |
| 검색기 비교(4.2) | `experiment_retriever_compare.py`, `experiment_external_retriever.py` | `output/retriever_compare.*`, `output/external_retriever.*` |
| 검증셋·확장·유의성(4.3) | `build_validated_queries.py`, `validate_query_slice.py`, `evaluate_validated_queries.py`, `build_expanded_validated.py` | `output/validated_eval.*`, `output/validated_expanded_eval.*` |
| 임베딩 robustness(4.4) | `experiment_embedding_robustness.py` | `output/embedding_robustness.*` |
| 노출 frontier 검증(4.5) | `experiment_exposure_frontier_validated.py` | `output/exposure_frontier_validated.*` |
| 한국어 cross-lingual(4.6) | `experiment_crosslingual_eval.py` | `output/crosslingual_eval.*` |
| 통계·figure | `experiment_stats.py`, `make_figures.py` | `output/stats_summary.json`, `docs/statistics.md`, `output/fig_*.png` |

모든 실험은 seed 고정·결정론적이며 외부 추론 API를 호출하지 않는다(dense 임베딩은 로컬 모델). 검증 데이터: `data/external_consultation_queries_validated.json`, `data/validated_queries_slice_*.json`, `data/validated_queries_expanded.json`.
