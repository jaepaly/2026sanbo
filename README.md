# 전략물자 AI 사전 트리아지 실험

이 저장소는 외부 AI/검색 서비스에 기술정보를 전송할 때, 반환·처리하는 정보량을 줄이면서 공개 통제목록 후보검색 성능을 어느 정도 유지할 수 있는지 검증하기 위한 연구용 실험 저장소입니다.

중요한 정정:

- 이 실험은 전략물자 해당/비해당을 법적으로 판정하지 않습니다.
- 이 실험은 수출허가를 대신하거나, 자가판정·전문판정을 보조하는 수준을 넘어서지 않습니다.
- 이전 버전의 "정답 코드가 쿼리에 포함된 A-scenario"는 후보탐지 실험으로 부적절하여 제거했습니다.
- 법제 라우팅 "정확도" 수치는 공식 라벨이 아니므로 제거했습니다.
- **투명 기준선은 BM25이지만, 실제 시스템 구성은 다국어 hybrid(BM25 + 다국어 dense)입니다.** 이전 판의 "BM25-only baseline을 쓰고 임베딩 실험은 후속 연구로 분리한다"는 문장은 같은 문서 안의 hybrid 결과 및 논문 본문 주장과 모순되어 삭제했습니다. 코퍼스가 100% 영어이므로 BM25 단독은 한국어 질의에서 구조적으로 R@10=0이며(§한계), dense 성분 없이는 한국어 상담 질의를 다룰 수 없습니다. LLM reranker는 여전히 후속 연구입니다.
- "privacy-preserving" 표현은 과장 소지가 있어, "controlled disclosure", "reduced exposure", "minimum necessary disclosure"를 사용합니다.

## 현재 연구 질문

공개 통제목록 설명문에서 파생한 제품·기술 설명형 쿼리를 사용할 때, 통제번호를 쿼리에 넣지 않고도 후보 통제항목을 검색할 수 있는가? 또한 검색 결과로 반환하는 정보량을 줄이면 Recall@k와 정보노출량은 어떻게 변하는가?

## 데이터

정화 후 코퍼스는 1,797개 항목입니다.

| 소스 | 항목 수 | 원문 |
|---|---:|---|
| Wassenaar Arrangement 2025 | 585 | [공식 PDF](https://www.wassenaar.org/app/uploads/2025/12/List-of-Dual-Use-Goods-and-Technologies-and-ML-2025.pdf) |
| India SCOMET 2024 | 575 | [DGFT 공식 PDF](https://content.dgft.gov.in/Website/UPDATED%20SCOMET%20List%202024%20as%20on%2002.09.2024.pdf) |
| U.S. eCFR CCL, 15 CFR Part 774 Supp. 1 | 637 | [eCFR](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-774/appendix-Supplement%20No.%201%20to%20Part%20774) |

품질 리포트: `data/corpus/corpus_quality_report.json`

## 쿼리

`generate_queries.py`는 정답 통제번호를 포함하지 않는 설명형 쿼리만 생성합니다.

- 총 쿼리: 780개
- train/val/test: 78 / 78 / 624
- 소스 분포: 각 소스 260개
- 언어 분포: EN 390개, KO 390개
- 코드 누출 검증: 통과

품질 리포트: `data/query_quality_report.json`

## 상담형 모사 질의셋 (stress test)

본 저장소는 합성 benchmark와 별도로, 외부 모사 질의셋을 통해 BM25 단독 기준선의 한계를 드러내는 stress test를 포함한다. (이 30개 셋은 라벨이 연구자 예비 추정값이라 노이즈가 크다. 헤드라인 평가셋은 `data/validated_queries_expanded.json`의 n=71이다.)

| 항목 | 내용 |
|---|---|
| 파일 | `data/external_consultation_queries.json` |
| 질의 수 | 30개 (KO 16, EN 14) |
| 라벨 | 연구자가 예비로 부여한 `candidate_labels`. 정답이 아님. |
| 평가 스크립트 | `evaluate_external_queries.py` |
| 평가 결과 | `output/external_eval.json`, `output/external_eval.md` |
| 라벨 감사 | `output/external_label_audit.json` |

주의: 본 외부 질의셋은 "상담형 모사" 일 뿐, 실제 기업 질의를 대체하거나 현장 검증을 완료한 것이 아니다.

## 현재 결과

### (1) 합성셋 — **자기참조 재검색 조건** (일반화 금지)

> ⚠ **이 표의 쿼리는 각 코퍼스 항목 자기 본문에서 코드만 제거해 만든 것**이라 정답
> 문서와 near-duplicate입니다(평균 Jaccard 0.485). 따라서 아래 R@10은 **후보 발견
> 능력이 아니라 자기참조 재검색 성능**입니다. 절대수치를 단독 헤드라인으로 쓰지
> 마십시오. 실제 상담형 질의 성능은 아래 (2)를 보십시오.

BM25 단독, 코퍼스 1,797개, 테스트 쿼리 624개. 수치는 후보검색 성능이지 법적 판정 정확도가 아닙니다.
출처: `output/experiment_logs.json` (정정 후).

| 조건 | R@1 | R@5 | R@10 | R@20 | MRR | nDCG@10 | 노출량@10 | 노출량@10(정정 전) | 고유 색인문서 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full_text | 0.8686 | 0.9904 | 0.9968 | 0.9984 | 0.9231 | 0.9416 | 4,917 | 4,834 | 1,797 |
| minimal_text | 0.7804 | 0.9599 | 0.9792 | 0.9856 | 0.8589 | 0.8883 | 1,708 | 1,623 | 1,797 |
| minimal_no_code | 0.7772 | 0.9631 | 0.9808 | 0.9856 | 0.8575 | 0.8877 | 1,592 | 1,592 | 1,683 |
| route_only | 0.0000 | 0.0000 | 0.0016 | 0.0064 | 0.0010 | 0.0005 | 425 | 425 | **19** |
| random_baseline | - | - | 0.0048 | - | - | - | - | - | - |

- 자기참조 의존성 실증: 정답 문서와 공유하는 고-IDF 토큰 5개만 제거하면 `minimal_text`
  R@10이 0.9792 → **0.7596**, 10개에서 **0.4407**로 붕괴합니다(`output/paraphrase_gap.md`).
- `route_only`는 **고유 색인문서가 19개뿐**인 퇴화 조건입니다(624개 질의 중 257개는
  어휘 교집합이 0이어서 애초에 아무것도 검색하지 못합니다). 랜덤 기준선과 구별되지 않는
  음성 대조군으로만 읽어야 하며, 소수 4자리 수치에 해석을 부여하면 안 됩니다. 이전 표의
  `route_only` R@10 0.0080은 동점 정렬 인공물이었고, 정정 후 값은 0.0016입니다.
- 랭킹을 결정론화(동점을 코퍼스 인덱스 오름차순으로 처리)하면서 R@1·R@5 일부 칸이
  ±0.007 이내로 변동했습니다. before/after 전량은 `docs/statistics.md` §6에 있습니다.
  **헤드라인 R@10 4개 값(0.9968 / 0.9792 / 0.7596 / 0.4407)은 불변입니다.**
- 노출량@10이 소폭 늘어난 것은 값이 나빠져서가 아니라 **정의가 정확해졌기 때문**입니다.
  정정 전 정의는 색인 텍스트에 붙는 통제번호 문자열을 노출량에서 빠뜨렸고,
  `minimal_text`와 `minimal_no_code`에 동일한 값을 부여했습니다.

상세 결과: `output/report.md`, `output/experiment_logs.json`

### (2) 검증셋 n=71 — 비자기참조, 실제 한국어 포함 (헤드라인)

eCFR 항목 역생성으로 만든 검증 질의셋(영어 26 / 한국어 45), 라벨은 정확한 full eCFR
code. 색인 `minimal_text`, dense = multilingual MiniLM.

| retriever | 전체 R@10 | 95% CI (Clopper-Pearson) | 영어 R@10 | 한국어 R@10 |
|---|---:|---|---:|---:|
| BM25 (α=1.0) | 0.1549 | [0.080, 0.260] | 0.4231 | **0.0000** |
| dense (α=0.0) | 0.5493 | [0.427, 0.668] | 0.4615 | 0.6000 |
| hybrid (α=0.5) | **0.5775** | [0.454, 0.694] | 0.5385 | 0.6000 |

- **BM25 한국어 R@10은 0.0000입니다.** 이전 산출물의 0.0222는 오류였습니다. 한국어
  질의 45개 중 **44개**가 BM25 점수 벡터 전부 0(영어 코퍼스와 어휘 교집합 0)인데,
  이전 코드가 `np.argsort(-scores)`로 정렬해 **코퍼스 배열 앞머리 10행**을 결과로
  집계했고 정답이 우연히 그 안에 있으면 적중으로 세었습니다.
- hybrid − BM25 = **+0.4225**, exact McNemar 양측 p = 1.9e-09 (30승 0패 41무).
  한국어만 보면 +0.6000, p = 1.5e-08 (27승 0패).
- hybrid − dense = +0.0282, p = 0.62로 **유의하지 않습니다**. 한국어에서는 BM25 점수가
  항등 0이므로 α<1의 랭킹이 dense와 수학적으로 동일합니다(0승 0패). 즉 데이터가
  지지하는 진술은 "하이브리드가 필요하다"가 아니라 **"dense 성분이 필요하다"**입니다.

상세: `output/validated_suite.md`, `docs/statistics.md`

### (3) 노출량 — 비용은 '색인 축소'에서만 발생

색인 모드와 반환 모드를 분리해 측정한 결과, 색인을 `full_text`로 유지한 채 **반환
텍스트만** `minimal_text`로 줄이면 노출량@10이 9,730 → 1,811자(**81.4% 감소**)인데
랭킹이 전혀 바뀌지 않으므로 R@10은 0.6056 그대로입니다. 즉 **반환량 축소는 성능 비용이
0이고, 비용은 색인을 줄일 때만 발생합니다.** 기존 설계는 색인 모드와 반환 모드를 같은
값으로 묶어 두어 이 조건을 표현할 수 없었습니다.

> 이전 노출량 정의에는 버그가 있었습니다. `minimal_text`와 `minimal_no_code`에
> **1,797개 항목 전부 동일한 값**을 반환해 두 조건을 구분하지 못했습니다. 현재 노출량은
> 실제 반환 문자열에서 파생하며, 이전 값은 각 산출물의 `*_legacy` 필드에 남겼습니다.

## 그림

`python make_figures.py`가 `output/`에 5종을 생성합니다(matplotlib, 200 dpi, 한글 라벨).

| 파일 | 내용 | 오차막대 |
|---|---|---|
| `fig_validated_retriever.png` | 검증셋 n=71 검색기 비교 (절대 R@10 + 짝지음 차이) | 절대율 Clopper-Pearson / 차이 paired bootstrap |
| `fig_exposure_recall.png` | 노출-성능 frontier, **합성(자기참조) / 검증셋 2패널** | Clopper-Pearson |
| `fig_embedding_robustness.png` | dense 모델 교체 시 우위 유지 여부 | 절대율 Clopper-Pearson / 차이 paired bootstrap |
| `fig_paraphrase_gap.png` | 어휘격차에 따른 자기참조 의존성 붕괴 | Clopper-Pearson |
| `fig_retriever_alpha.png` | 합성셋 alpha 스윕 | Clopper-Pearson |

한글 폰트는 Windows의 `Malgun Gothic`을 사용하며, 없으면 영문 라벨로 폴백하고 그 사실을
stdout에 출력합니다.

> **`docs/figures/fig1~3.png` 폐기.** `fig1_scope_decomposition.png`,
> `fig2_privacy_utility_map.png`, `fig3_scenario_scope.png` 세 파일은 **생성 코드가
> 저장소에 없고** README·PAPER·docs 어디에서도 참조되지 않습니다(참조 0건). 재현이
> 불가능하므로 **폐기**로 결정했으며 `make_figures.py`에 통합하지 않습니다. 파일 자체는
> 감사 목적으로 삭제하지 않고 그대로 둡니다. 논문에 쓰려면 생성 코드를 새로 작성해
> `make_figures.py`에 넣어야 합니다.

## 법제·업무흐름 라우팅

`experiment_legal_route.py`는 정확도 평가를 하지 않습니다. 대신 보수적 업무흐름 힌트를 요약합니다.

- 전략물자 후보 검토 및 YesTrade 자가·전문판정 안내
- 외국 공개 통제목록 참고자료 표시
- 국가핵심기술 가능 키워드가 있을 때 2차 검토 플래그 표시

공식 참고:

- [YesTrade 제도개요](https://www.yestrade.go.kr/system-guidance)
- [YesTrade 온라인 자가판정 한계](https://www.yestrade.go.kr/judgements/self/intro)
- [전략물자수출입고시](https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000270104&chrClsCd=010201)
- [대외무역법](https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=241530&lsNm=%EB%8C%80%ED%99%98%EB%AC%B4%EC%97%85%EB%B2%95)
- [산업기술보호법](https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=247501&lsNm=%EC%82%B0%EC%97%85%EA%B8%B0%EC%88%A0%EB%B3%B4%ED%98%B8%EB%B2%95)
- [국가핵심기술 제도](https://kaits.or.kr/web/content.do?menu_cd=000067)
- 한국 법제도 워크플로우 상세: `docs/korean_regulatory_framework.md`

## 재현 방법

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python build_corpus_clean.py
python generate_queries.py
python run_experiments.py
python experiment_legal_route.py
python evaluate_external_queries.py    # 외부 모사 질의 stress test
python experiment_paraphrase_gap.py    # 자기참조 의존성 검증 (TASK A)
python experiment_retriever_compare.py # BM25 vs Dense vs Hybrid, 합성 (TASK E)
python experiment_external_retriever.py# BM25 vs Dense vs Hybrid, 외부셋 (TASK E)
python build_validated_queries.py      # 충돌제거 검증 라벨셋 생성 (TASK B/C)
python experiment_crosslingual_eval.py # 한국어 KO-원문/번역/EN 비교 (TASK D)
python validate_query_slice.py data/validated_queries_slice_<이름>.json  # G 슬라이스 검증
python build_expanded_validated.py     # 검증셋+G슬라이스 병합 → data/validated_queries_expanded.json

# 검증셋 헤드라인 (n=71). 이 한 스크립트가 아래 3개를 대체한다.
python experiment_validated_suite.py
#   SANBO_MODELS=MiniLM python experiment_validated_suite.py   # 단일 모델 스모크

python experiment_stats.py             # 통계 재집계 → output/stats_summary.json, docs/statistics.md
python make_figures.py                 # figure 5종 → output/fig_*.png
```

**대체된 스크립트** (실행은 되지만 헤드라인으로 인용하지 마십시오):

| 스크립트 | 대체 |
|---|---|
| `evaluate_validated_queries.py` (n=13) | `experiment_validated_suite.py` (n=71) |
| `build_expanded_validated.py`의 **평가** 부분 | 동상 (병합 기능은 계속 사용) |
| `experiment_embedding_robustness.py` | 동상 (모델별 hit 벡터 포함) |
| `experiment_exposure_frontier_validated.py` | 동상 (색인×반환 2차원 노출표) |

> 참고: dense를 쓰는 스크립트는 다국어 모델
> (`paraphrase-multilingual-MiniLM-L12-v2`, 약 470MB)을 처음 실행 시 자동 다운로드합니다.
> 임베딩 연산은 전부 로컬에서 수행되며 외부 추론 API를 호출하지 않습니다.
> `experiment_validated_suite.py`는 기본적으로 3개 모델을 돌아 오래 걸립니다. 코드 변경을
> 빠르게 검증하려면 `SANBO_MODELS=MiniLM`으로 단일 모델 스모크 경로를 쓰십시오.

---

## 코퍼스 v2 채택 매뉴얼

### 왜 교체하는가

v1 파서에 결함이 있고, 그중 일부는 **코퍼스에 존재하지 않는 문서를 만들었습니다.**

| 결함 | 실측 |
|---|---|
| 유령 항목 (번호목록을 항목으로 오인) | **5건**. `1.A.n` `2.A.n` `2.A.t` `3.A.n` `5.A.n`. 예: `3.A.n`은 757자 항목인데 원문은 *"3. An inert powder, most frequently alumina."* 한 줄 |
| 통째로 사라진 진짜 항목 | **3건**. `3.A.2.d.4` (584자) / `.5` (921자) / `.6` (558자) |
| 페이지 경계 절단으로 폐기된 본문 | Wassenaar 3,544행·172,620자 / SCOMET 5,093행·278,443자 |
| 부속서 흡수 | `1.E.2.g` 134자 → 5,092자로 부풀음 |
| 푸터·각주 혼입 | 푸터 잔재 53건, 각주 본문 흡수 2건 |

논문이 "정화 후 1,797개 항목"이라고 쓰는 한, 그중 5개가 유령이고 3개가 누락이라는 사실은 남습니다. 심사위원이 원문 PDF와 대조하면 나옵니다.

교정 근거와 원문 인용 예시는 [`docs/corpus_parsing_fixes.md`](docs/corpus_parsing_fixes.md)에 16건 있습니다.

### 교체가 수치에 미치는 영향 (측정 완료)

`compare_corpus_versions.py`와 `check_v2_exposure_impact.py`로 실측했습니다.

| 항목 | 결과 |
|---|---|
| **검증셋 정답 문서** | **70개 전부 무변경.** 라벨이 전부 eCFR이고 v2에서 eCFR은 바이트 단위 동일(637건·105,567자) |
| **검증셋 R@10** | **213개 판정 전부 동일** (71질의 × BM25/dense/hybrid). BM25 0.1549 / dense 0.5493 / hybrid 0.5775 — 언어별도 동일 |
| **노출량@10** | **크게 이동.** full_text 4,043 → **9,730자**(+140%). minimal_text는 1,820 → 1,811로 거의 불변 |
| **헤드라인 노출 감소율** | **55.0% → 81.4%** (+26.4%p) |
| top-10 문서 집합 | full_text 색인에서 27/71만 동일, minimal_text 57/71 |
| 코퍼스 구성 | 1,797 → **1,783** (Wassenaar 585→568, SCOMET 575→578, eCFR 637→637) |

즉 **논문에 유리한 방향입니다.** v1은 본문이 잘려 있어 full_text가 실제로 얼마나 노출하는지를 과소계상했습니다. 성능 손실 0에 노출 감소가 55%가 아니라 81.4%가 됩니다.

### 무엇을 다시 돌려야 하는가

| 다시 돌려야 함 | 이유 |
|---|---|
| 합성 질의셋 | 코퍼스 본문에서 파생되므로 교체 즉시 무효 |
| 합성셋 실험 + ablation (주장 1) | 위와 같음. 값이 이동함 |
| 검증셋 3모델 통합 실행 | recall은 불변이나 **노출량@10이 크게 이동**하므로 필수 |
| 통계·그림·claim registry | 위 산출물에 의존 |

| 다시 안 돌려도 됨 | 이유 |
|---|---|
| 질의 노출 사다리 (L0~L4) | 질의 재작성물이며 코퍼스와 무관. 단 frontier 실험은 재실행 |
| 자기참조 게이트 임계값 | 대조군이 코퍼스 텍스트가 아닌 별도 필드 기반 |
| 등가 라벨 사전 | eCFR 무변경이므로 정답 쪽은 그대로. Wassenaar/SCOMET 대응은 `audit_label_quality.py audit` 재실행 권장 |

---

### 내가 할 일

배정받은 **모델 하나**를 돌려서 결과 파일 **하나**를 보내면 끝입니다. 판단할 것은 없습니다.

먼저 콘솔 인코딩을 설정합니다. Windows 기본 콘솔(cp949)에서는 한글 출력이 깨집니다.

```bash
$env:PYTHONIOENCODING="utf-8"
```

mac/linux 라면:

```bash
export PYTHONIOENCODING=utf-8
```

#### 1. 저장소 준비

```bash
git clone https://github.com/jaepaly/2026sanbo.git
```

```bash
cd 2026sanbo && python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt
```

이미 클론해 둔 저장소가 있으면 `git pull` 하십시오.

#### 2. 코퍼스를 교정판으로 맞춘다

```bash
python adopt_corpus_v2.py
```

"이미 v2가 활성 상태입니다"가 나오면 정상이니 다음으로 넘어가십시오.

#### 3. 배정받은 모델을 돌린다

`<배정모델>` 자리에 아래 표에서 받은 값을 그대로 넣으십시오.

```bash
python run_model_shard.py <배정모델>
```

중간에 끊어도 안전합니다. 부분 결과를 쓰지 않으므로 처음부터 다시 돌리면 됩니다.

#### 4. 검증한다

```bash
python validate_shard.py output/shards/shard_<배정모델>.json
```

마지막 줄이 **"모든 검증 통과"** 여야 합니다. 실패하면 출력을 그대로 공유해 주십시오. 아래 '내 결과가 맞는지 확인하기'와 '문제가 생기면'을 먼저 보셔도 됩니다.

#### 5. 파일 하나만 보낸다

```
output/shards/shard_<배정모델>.json
```

이 파일만 보내면 됩니다. 커밋도, PR도 필요 없습니다. 다른 파일은 건드리지 마십시오.

---

### 모델 배정

| 담당 | `<배정모델>` | 모델 |
|---|---|---|
| 이예찬 | `bge-m3` | BAAI/bge-m3 |
| 장승우 | `e5-base` | intfloat/multilingual-e5-base |

GPU가 있으면 훨씬 빠릅니다. 없어도 그냥 돌아갑니다.

---

### 내 결과가 맞는지 확인하기

`validate_shard.py` 출력에서 아래 값을 직접 확인하십시오. **세 사람의 값이 서로 같아야 합니다.** BM25는 임베딩 모델을 전혀 쓰지 않으므로 모델이 달라도 결과가 같아야 하고, 다르면 무언가 잘못된 것입니다.

| 확인 항목 | 기대값 |
|---|---|
| BM25 R@10 (minimal_text) | **11/71** |
| BM25 무신호 질의 | **44/71** |
| hybrid ≡ dense 건수 | **44/71** |
| hit 벡터 길이 | 71 |
| 코퍼스 항목수 | 1,783 |

교정판 코퍼스가 제대로 적용됐는지 확인하려면:

```bash
python -c "import json;c=json.load(open('data/corpus/combined.json',encoding='utf-8'));k={e['code'] for e in c};print(len(c), [x for x in ['3.A.n','5.A.n'] if x in k] or 'ok', [x for x in ['3.A.2.d.4'] if x in k])"
```

`1783 ok ['3.A.2.d.4']` 가 나와야 합니다.

---

### 문제가 생기면

| 증상 | 대응 |
|---|---|
| 한글이 `?`나 깨진 문자로 출력 | `PYTHONIOENCODING=utf-8`을 설정하지 않았습니다 |
| 모델 다운로드가 느림 | `pip install hf_xet` |
| 메모리 부족 | `experiment_validated_suite.py`의 `batch_size=32`를 8로 낮추십시오. 결과는 동일합니다 |
| `revision: None` 경고 | `pip install huggingface_hub` 후 다시 돌리십시오. 재현성 기록이 비면 논문 부록에 쓸 수 없습니다 |
| `validate_shard.py`가 BM25 불일치를 보고 | 코퍼스·질의 파일이 최신인지 확인하십시오. `git pull` 후 `python adopt_corpus_v2.py`, 그다음 3번부터 다시 |
| `output/shards/`에 예전 파일이 있음 | 지우고 3번부터 다시 돌리십시오. 예전 코퍼스로 계산된 결과가 섞이면 안 됩니다 |
| 그 외 | `validate_shard.py` 출력 전체를 공유해 주십시오 |

---

### 하지 말아야 할 것

| 항목 | 이유 |
|---|---|
| `retrieval_core.py` 수정 | 33개 검증이 걸려 있고 scipy와 대조되어 있습니다. 여기가 틀리면 모든 수치가 조용히 틀어집니다 |
| 등가성 마진 δ, α, 시드 변경 | 실험 전에 고정한 값입니다. 결과를 보고 바꾸면 사전지정의 의미가 사라집니다 |
| `output/` 의 다른 파일 수정·삭제 | 자기 샤드 외에는 건드리지 마십시오 |
| 논문 수치를 직접 고치기 | `verify_claims.py`가 산출물과 대조합니다. 손으로 고치면 대조가 깨집니다 |


---

## 완료된 이전 라운드 (기록)

아래 작업은 모두 완료되어 저장소에 반영되어 있습니다. 상세 스펙과 당시 사용한 프롬프트는
[`docs/RESEARCH_IMPROVEMENT_PLAN.md`](docs/RESEARCH_IMPROVEMENT_PLAN.md)에 있습니다.

| TASK | 내용 | 산출물 |
|---|---|---|
| A | 합성셋 자기참조 의존성 정량화 | `output/paraphrase_gap.*` |
| B/C | 코드 충돌 제거 + 검증 라벨셋 구축 | `data/external_consultation_queries_validated.json` |
| D | 한국어 cross-lingual 트랙 | `output/crosslingual_eval.*` |
| E | BM25 vs Dense vs Hybrid 비교 | `output/retriever_compare.*` |
| F | 논문 figure + 통계 보강 | `output/fig_*.png`, `docs/statistics.md` |
| G | 검증 질의셋 역생성 확장 (n=71) | `data/validated_queries_slice_*.json` |
| H | 임베딩 robustness (3개 인코더) | `output/validated_suite.*` |
| I | 슬라이스 병합·재집계 | `data/validated_queries_expanded.json` |

이후 외부 감사에서 나온 결함 수정 내역은 커밋 히스토리와 아래 문서에 있습니다.

| 문서 | 내용 |
|---|---|
| [`docs/threat_model.md`](docs/threat_model.md) | 보호자산·신뢰경계·노출채널 정의 |
| [`docs/selfreference.md`](docs/selfreference.md) | 자기참조 게이트의 공허성과 대칭 ablation |
| [`docs/corpus_parsing_fixes.md`](docs/corpus_parsing_fixes.md) | 코퍼스 파서 결함과 교정 (원문 인용 16건) |
| [`docs/label_audit.md`](docs/label_audit.md) | 정답셋 오염 감사 |
| [`docs/statistics.md`](docs/statistics.md) | 검증셋 통계 (paired bootstrap · exact McNemar · TOST) |
| [`docs/reproducibility.md`](docs/reproducibility.md) | 전체 재현 절차와 환경 |
| [`docs/claim_registry.json`](docs/claim_registry.json) | 논문 수치 ↔ 산출물 대조 결과 |

검증 명령:

```bash
python verify_claims.py
```

논문의 모든 수치를 산출물과 대조합니다. 불일치 목록이 곧 고쳐야 할 논문 수치 목록입니다.

```bash
python tests/test_retrieval_core.py
```

통계 코어 검증(scipy와 독립 대조). `tests/` 아래 나머지 테스트도 같은 방식으로 실행합니다.


## 한계

- 합성 쿼리는 각 코퍼스 항목 **자기 본문**에서 코드만 제거해 만든 것이라 정답 문서와 near-duplicate입니다(평균 Jaccard 0.485). 따라서 합성 R@10 0.9792는 자기참조 재검색 성능에 가깝고, 후보 발견 능력의 절대 지표로 직접 일반화할 수 없습니다. `experiment_paraphrase_gap.py`로 검증: 정답 문서와 공유하는 변별(고-IDF) 토큰 5개를 제거하면 minimal_text R@10이 0.9792→0.7596, 10개에서 0.4407로 떨어집니다(`output/paraphrase_gap.md`).
- 합성 "한국어" 쿼리는 설명 본문이 영어라 언어 분리가 가짜입니다. 진짜 언어 격차는 검증셋(한국어 45개)에서만 관찰됩니다.
- 외부 모사 질의셋(`data/external_consultation_queries.json`) 30개의 `candidate_labels`는 연구자 예비 추정값이며 검증된 정답이 아닙니다. 30개 중 13개는 코드 정규화 충돌을 가집니다. 따라서 R@10=0은 "BM25 현장 성능=0"이 아니라 "불확실한 후보 라벨 기준 비수렴"으로 읽어야 합니다.
- Retriever 비교(TASK E): 자기참조 합성셋은 BM25에 구조적으로 유리해 retriever 비교에 부적합합니다. 이전 판에는 **입력 비대칭 결함**도 있었습니다 — dense에만 구두점이 제거되고 소문자화된 `" ".join(tokens)` 문자열을 주고 BM25에는 토큰 형태를 주었습니다. 양쪽에 동일한 문자열(원문에서 대상 토큰만 word-boundary 삭제)을 주도록 고치고 재실행한 결과, 격차는 사실상 그대로였습니다(전 조건 |Δ| ≤ 0.016; before/after 전량은 `docs/statistics.md` §6-2). 즉 **결함은 실재했지만 BM25 우위의 원인은 아니었고, 원인은 자기참조 구조**입니다. 외부 모사셋 30개에서는 BM25 R@10=0(30개 중 14개가 BM25 무신호), hybrid(α=0.5) 0.10, 한국어 0→0.0625입니다(`output/external_retriever.md`). 라벨 노이즈가 커서 절대값 해석은 피하고, 헤드라인은 위 검증셋 n=71을 쓰십시오.
- 검증 라벨셋 n=13(TASK B/C)은 **대체되었습니다**. 당시 표기했던 "한국어 0→0.20, hybrid 0.2308"과 "표본이 작아 경향으로 보고"라는 판단은 `docs/statistics_n13_superseded.md`에 보존했습니다. 그 판단의 근거였던 95% CI [0.0000, 0.4615]는 소표본 percentile bootstrap의 **이산 경계 인공물**입니다: 3승 0패 10무에서 재표본에 승리 질의가 하나도 안 뽑힐 확률이 (10/13)^13 = 0.0330 > 0.025라서 2.5분위수가 **구조적으로** 0이 됩니다. 즉 n=13에서 3승 0패인 어떤 결과도 자동으로 "CI가 0을 포함"합니다. 동시에 exact McNemar p=0.25이므로 n=13은 실제로도 검정력이 부족했습니다. **소표본 이진 짝지음의 primary 검정은 exact McNemar / Clopper-Pearson입니다**(`docs/statistics.md` §5).
- 검증셋 확장(TASK G/I): eCFR 항목 역생성으로 n=71(영어 26, 한국어 45). hybrid(α=0.5) vs BM25 = **+0.4225**, exact McNemar 양측 p=1.9e-09(30승 0패 41무), paired bootstrap 95% CI [0.310, 0.535]. 한국어 BM25 **0.0000**(이전 표기 0.022는 오류) → dense/hybrid 0.60. 단 **hybrid vs dense는 유의하지 않습니다**(+0.028, p=0.62). 한국어에서 BM25 점수가 항등 0이면 α<1의 랭킹이 dense와 수학적으로 동일하므로(0승 0패), 데이터가 지지하는 진술은 "하이브리드가 필요하다"가 아니라 **"dense 성분이 필요하다"**입니다. 라벨은 여전히 코퍼스 텍스트 근거이며 전문가 검증은 후속 과제입니다.
- 역생성 질의의 자기참조 게이트(`jaccard(질의, 정답 minimal_text) < 0.30`)는 **한국어 45개 전부에서 정확히 0.0000**입니다. 한국어 질의와 영어 정답 텍스트는 토큰이 겹칠 수 없으므로 이 게이트는 한국어에 대해 아무것도 검사하지 못합니다(영어 26개는 평균 0.0941, 최대 0.2364로 한 번도 발동하지 않았습니다). 또 역생성 질의는 코퍼스 등장 순서를 훑은 흔적이 있습니다(slice_yechan 28/28, slice_seungwoo 25/28 단조증가). 언어중립 게이트가 필요합니다.
- 임베딩 robustness(TASK H): 이전 판은 세 모델이 **동일한 bootstrap 리샘플 행렬**을 공유해 모델별 CI가 독립적으로 얻어진 것처럼 보였습니다. 모델별 seed로 분리했습니다. 3모델 결과는 `experiment_validated_suite.py` 본실행 산출물로 갱신해야 합니다.
- 노출-성능: full_text→minimal_text로 **색인**을 줄이면 hybrid R@10 0.6056→0.5775로 감소합니다. 반면 색인은 그대로 두고 **반환 텍스트만** minimal_text로 줄이면 노출량@10이 9,730→1,811자(81.4% 감소)인데 랭킹이 바뀌지 않아 R@10은 0.6056 그대로입니다. 즉 반환량 축소는 비용이 0이고 비용은 색인 축소에서만 발생합니다. **"CI가 0을 포함하므로 손실이 없다"는 주장은 하지 않습니다**(귀무가설 수용). 등가 주장은 사전지정 마진 δ에 대한 TOST로만 합니다.
- 코퍼스 파싱은 정규식 기반이므로 수작업 표본 검수가 필요합니다.
- LLM reranker 비교는 아직 수행하지 않았습니다(후속 연구). Dense·hybrid는 이미 본 실험에 포함되어 있습니다.
- 노출량은 문자 수 기반 proxy입니다. 실제 영업비밀·기술정보 민감도와 동일하지 않습니다. 이전 정의에는 `minimal_text`와 `minimal_no_code`에 1,797개 항목 전부 동일한 값을 부여하는 버그가 있었습니다.
- BM25 단독은 어휘 불일치·언어 격차에서 구조적 한계를 보입니다(`docs/case_analysis.md`). "실제 현장에서 충분하다"고 단정하지 마십시오.
- 독립 누출 감사에서 원 검사기가 놓친 실제 코드 누출 4건이 발견되었습니다(예: q0613의 "ML19"). 원 검사기가 질의 생성에 쓴 정규식을 그대로 재사용해 구조적으로 누출을 찾을 수 없었기 때문입니다.

## 제출 논문에서 안전한 주장

사용 가능:

> 정답 통제번호를 쿼리에 포함하지 않는 합성 설명형 쿼리에서, 공개 통제목록 후보검색 기준 `minimal_text` 조건은 `full_text` 대비 평균 반환 정보량을 약 66.4% 줄이면서 R@10 0.9792를 유지했다. 단, 이 합성 쿼리는 코퍼스 항목 자기 본문에서 파생되어 정답 문서와 near-duplicate 관계이므로 절대수치는 자기참조 재검색에 가깝다(고-IDF 공유토큰 5개 제거 시 0.7596, 10개 제거 시 0.4407). 자기참조가 아닌 검증셋 n=71(영어 26 / 한국어 45)에서는 BM25 단독 R@10이 0.1549이고 한국어에서는 정확히 0.0000인 반면, 다국어 dense 성분을 넣으면 0.5493~0.5775로 올라간다(exact McNemar 양측 p=1.9e-09, 30승 0패). 즉 합성 benchmark 결과를 현장 성능으로 직접 일반화하지 않으며, 다국어 상담 질의에는 dense 성분이 필요하다. 상세는 `docs/statistics.md`, `docs/case_analysis.md` 참조.

> 색인 텍스트와 반환 텍스트를 분리하면, 색인을 그대로 두고 반환 텍스트만 줄이는 조건에서 top-10 반환 문자 수가 9,730 → 1,811(81.4% 감소)인데 랭킹이 바뀌지 않으므로 R@10은 0.6056으로 동일하다. 정보 노출 축소의 비용은 반환 단계가 아니라 색인 단계에서 발생한다.

사용 금지:

- “AI가 전략물자 여부를 판정한다”
- “법제 라우팅 정확도 n%”
- “전문판정/자가판정을 대체할 수 있다”
- “실제 기업 질의에서 검증됐다”
- “BM25 baseline이 실제 현장에서 충분하다”
- “다국어 **하이브리드**가 유의하게 필요하다” — 검증셋에서 hybrid vs dense는 유의하지 않다(p=0.62). 지지되는 진술은 “**dense 성분**이 필요하다”이다.
- “노출을 줄여도 성능 손실이 없다” — CI가 0을 포함한다는 것은 등가성의 근거가 아니다. 사전지정 마진에 대한 TOST가 통과했을 때만 비열등을 말한다.
- “검증셋 한국어 BM25 R@10 = 0.0222” — 실제 값은 **0.0000**이다.
