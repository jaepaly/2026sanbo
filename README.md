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
텍스트만** `minimal_no_code`로 줄이면 노출량@10이 4,043 → 1,729자(**57.2% 감소**)인데
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
#   SANBO_MODELS=MiniLM python experiment_validated_suite.py   # 단일 모델 스모크(수 분)

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

## 팀 협업 가이드 (작업 분담)

이 저장소는 팀 분담으로 진행됩니다. 각 팀원은 저장소를 클론하고, **자신의 AI 에이전트에게 저장소를 읽힌 뒤** 아래 담당 TASK를 수행하고, 산출물을 PR(권장) 또는 파일로 제출합니다.

### 1. 담당 분배

| TASK | 담당 | 내용 | 상세 스펙 |
|---|---|---|---|
| **TASK F** | 이예찬 | 결과 시각화(논문 figure) + 통계 보강(CI·효과크기) + 재현성. **새 실험 없음**, 기존 `output/*.json`만 읽어 그림 생성 | `docs/RESEARCH_IMPROVEMENT_PLAN.md` §3 TASK F |
| **TASK D** | 장승우 | 한국어 cross-lingual 트랙(번역 필드/동의어 사전/다국어 임베딩). 검증셋 기준 KO 회복 정량화 | `docs/RESEARCH_IMPROVEMENT_PLAN.md` §3 TASK D |

**현재 진행 중인 라운드 (2026-06-26~)** — TASK F·D는 완료(검증·반영됨). 다음 분담:

| TASK | 담당 | 내용 | 상세 스펙 |
|---|---|---|---|
| **TASK G** | 팀원들(분할) | 검증 질의셋 80~100개로 확장. eCFR 항목 **역생성**으로 정답 확정 + 패러프레이즈로 자기참조 제거. 각자 겹치지 않는 ~30개씩 → 팀장 병합 | `docs/RESEARCH_IMPROVEMENT_PLAN.md` §3 TASK G |

> TASK G는 **반드시** `python validate_query_slice.py data/<슬라이스>.json`을 통과(exit 0)한 뒤 제출.
> 라벨 정확성·코드누출·자기참조 Jaccard<0.30·한국어 비율을 자동 검사하므로 팀장 검증이 1커맨드로 끝난다.

**TASK G 구간 배정 (3명 팀: 팀장=H/병합/I, 팀원 2명=G 분할)** — 겹치지 않는 eCFR 카테고리를 나눠 각자 ~40개씩 역생성 → 합계 ~80개. 각자 한국어 ≥ 40%.

| 담당 | `<배정구간>` (TASK G 프롬프트에 기입) | eCFR 풀 | 목표 |
|---|---|---:|---:|
| 이예찬 | eCFR 카테고리 **0·1·2·8** (`0xxx`,`1xxx`,`2xxx`,`8xxx` — 핵·소재·화학·생물·기계가공·해양) | 308 | ~40 |
| 장승우 | eCFR 카테고리 **3·4·5·6·7·9** (`3xxx`,`4xxx`,`5xxx`,`6xxx`,`7xxx`,`9xxx` — 전자·컴퓨터·통신·센서·항법·항공우주) | 329 | ~40 |

> 슬라이스 id에 담당자명을 넣고(`g-<이름>-001`) 코드 접두가 겹치지 않으므로 병합 시 중복이 자동 배제된다.
> 팀장은 H(임베딩 robustness)를 먼저 인프라/smoke로 준비하고, G 슬라이스가 모이면 병합 후 TASK I(재집계)와 H 본실행을 수행한다.

이미 완료된 TASK A/B/C/E의 배경·함정은 같은 문서와 `docs/case_analysis.md`, `PAPER.md`에 정리돼 있습니다.

### 2. 환경 셋업 (각 팀원, 1회)

```bash
git clone https://github.com/jaepaly/2026sanbo.git
cd 2026sanbo
python -m venv .venv
.venv\Scripts\activate          # Windows. (mac/linux: source .venv/bin/activate)
pip install -r requirements.txt
```

### 3. 작업 흐름 (Git)

```bash
git checkout -b task-f-<이름>    # 예: task-f-jihoon  (TASK D는 task-d-<이름>)
# ... 에이전트로 작업 수행, output/ 산출물 생성 ...
git add <생성·수정 파일>
git commit -m "TASK F: 논문 figure 4종 + 통계 표 생성"
git push origin task-f-<이름>
# GitHub에서 Pull Request 생성 → 리뷰 요청
```

> 충돌 방지: TASK F는 주로 `make_figures.py`·`output/fig_*.png`·`docs/statistics.md`를,
> TASK D는 `data/*crosslingual*`·`output/crosslingual_*`를 건드립니다. 서로 다른 파일이라
> 병렬 작업해도 충돌이 거의 없습니다. 기존 스크립트(`run_experiments.py` 등)는 수정하지 마세요.

### 4. 에이전트에게 줄 프롬프트 (복붙용)

> ⚠ **아래 TASK F·D 프롬프트는 당시 지시 기록(archival)이다.** 그대로 재사용하지 마라.
> 이후 감사에서 다음이 바뀌었다: figure는 4종이 아니라 **5종**이고,
> 검증셋 소스는 `output/validated_eval.json`(n=13)이 아니라
> `output/validated_suite.json`(n=71)이다. "bootstrap 95% CI"만 요구하던 통계 지시도
> **exact McNemar / Clopper-Pearson primary**로 바뀌었다(`docs/statistics.md` §5).

**TASK F 담당 — 에이전트 프롬프트 (archival)**
```
이 저장소(2026sanbo)는 전략물자 사전 트리아지 정보최소화 연구다. 먼저 README.md,
docs/RESEARCH_IMPROVEMENT_PLAN.md, PAPER.md를 읽어 맥락과 "절대 하지 말 것"을 파악하라.
그다음 docs/RESEARCH_IMPROVEMENT_PLAN.md의 TASK F(시각화+통계)를 수행하라:
- 새 실험을 돌리지 말고 기존 output/*.json만 읽어 make_figures.py를 작성하고
  output/에 fig_paraphrase_gap.png, fig_retriever_alpha.png, fig_exposure_recall.png,
  fig_validated_retriever.png 4종을 생성하라. 수치는 JSON과 정확히 일치해야 한다.
- experiment_stats.py로 주요 비교의 bootstrap 95% CI와 효과크기를 output/stats_summary.json,
  docs/statistics.md에 정리하라.
금지: 합성 R@10 0.97을 무수식 헤드라인화, 추정 라벨을 "정답"으로 호칭, "AI가 전략물자 판정" 류 주장.
마지막으로 docs/RESULT_REPORT_TEMPLATE.md를 복사해 report_task_f_<이름>.md로 채워라
(기준 커밋 해시, 생성 파일 목록, 핵심 결과표, 재현 방법, 가드레일 체크 포함).
이 리포트와 생성한 PNG/JSON 파일들을 함께 제출하면 된다고 안내하라.
```

**TASK D 담당 — 에이전트 프롬프트 (archival)**
```
이 저장소(2026sanbo)는 전략물자 사전 트리아지 정보최소화 연구다. 먼저 README.md,
docs/RESEARCH_IMPROVEMENT_PLAN.md, PAPER.md, docs/case_analysis.md를 읽어 맥락을 파악하라.
핵심 사실: 코퍼스는 100% 영어라 BM25가 한국어 질의에서 R@10=0이고, 다국어 dense가 일부
회복한다(output/validated_eval.json). docs/RESEARCH_IMPROVEMENT_PLAN.md의 TASK D를 수행하라:
- data/external_consultation_queries_validated.json을 기준 평가셋으로,
  KO-원문 vs KO-번역 vs EN, 그리고 BM25/dense/hybrid를 비교해
  output/crosslingual_eval.json, output/crosslingual_eval.md를 생성하라.
- 외부 API를 쓰면 반드시 명시하라(정보최소화 주제와 충돌). 가능하면 로컬 모델 사용.
- 한국어 표본이 5개로 작으니 결론은 "경향"으로 서술하고 표본 확대 필요성을 명시하라.
금지: 추정 라벨을 "정답"으로 호칭, "AI가 전략물자 판정" 류 주장.
마지막으로 docs/RESULT_REPORT_TEMPLATE.md를 복사해 report_task_d_<이름>.md로 채워라
(기준 커밋 해시, 생성 파일 목록, 핵심 결과표, 재현 방법, 가드레일 체크 포함).
이 리포트와 생성한 JSON/MD 파일들을 함께 제출하면 된다고 안내하라.
```

**TASK G 담당 — 에이전트 프롬프트** (담당 eCFR 구간을 `<배정구간>`에 기입)
```
이 저장소(2026sanbo)는 전략물자 사전 트리아지 정보최소화 연구다. 먼저 README.md,
docs/RESEARCH_IMPROVEMENT_PLAN.md(§3 TASK G), PAPER.md, docs/case_analysis.md를 읽어
맥락과 "절대 하지 말 것"을 파악하라. 목표: 검증 질의셋을 역생성으로 확장한다.
- data/corpus/combined.json에서 source=ecfr_part774 항목 중 내 담당 구간 <배정구간>
  (다른 팀원과 겹치지 않게)에서 설명 가능한 항목 약 30개를 고른다.
- 각 항목마다, 그 항목을 묘사하는 상담형 질의를 작성한다. 실제 시나리오(국가/용도)를 담되
  통제번호와 항목 원문 구절을 직접 인용하지 마라(자기참조 금지). 한국어를 40% 이상 포함.
- 라벨(validated_labels)은 그 항목의 정확한 full code(ECCN-XXXX)로 둔다.
- 결과를 data/validated_queries_slice_<이름>.json에 §3 TASK G 스키마대로 저장한다.
- 제출 전 반드시 `python validate_query_slice.py data/validated_queries_slice_<이름>.json`을
  실행해 exit 0(모든 게이트 통과: 라벨 정확·코드누출0·Jaccard<0.30·KO≥40%·≥25개)을 확인하라.
  실패하면 해당 질의를 고쳐 다시 통과시켜라.
금지: 추정 라벨을 "정답(법적)"으로 호칭, "AI가 전략물자 판정" 류 주장, 항목 원문 베껴쓰기.
마지막으로 docs/RESULT_REPORT_TEMPLATE.md를 복사해 report_task_g_<이름>.md로 채우고,
슬라이스 JSON과 validate_query_slice.py의 통과 출력을 함께 제출하면 된다고 안내하라.
```

### 5. 결과물 제출 (md 리포트 방식 — 기본)

각 팀원은 **표준 md 리포트 1장 + 생성한 산출물 파일**을 팀장에게 전달합니다. PR/push 권한이 필요 없습니다.

1. `docs/RESULT_REPORT_TEMPLATE.md`를 복사해 채운다 → `report_task_f_<이름>.md` (또는 `report_task_d_<이름>.md`)
2. 리포트에 **기준 커밋 해시, 무엇을 했는지, 생성 파일 목록, 핵심 결과표, 재현 방법, 가드레일 체크**를 기입
3. 리포트 md와 **생성한 산출물 파일을 함께** 전달 (md만으로는 부족 — 아래 주의)
   - **TASK F**: 그림은 PNG라 md에 안 담깁니다 → `output/fig_*.png`, `make_figures.py`, `output/stats_summary.json`을 **파일로 같이** 보낼 것
   - **TASK D**: `output/crosslingual_eval.json`, `output/crosslingual_eval.md`, 추가 스크립트를 같이 보낼 것
4. 전달 수단은 자유(메신저/메일/드라이브). 어느 커밋 기준인지만 리포트에 명시.

> (선택) PR을 쓸 수 있는 팀원은 §3 흐름대로 브랜치 푸시 후 PR을 열어도 됩니다. md 리포트 방식과 둘 중 편한 것을 쓰면 됩니다.

> 팀장 통합: 받은 md 리포트의 수치·해석을 `PAPER.md`에, 그림 PNG는 `output/`에 넣고 README/PAPER에서 참조하면 됩니다.

### 6. 반드시 지킬 것 (회귀 방지)

- 합성 R@10 0.9792는 **자기참조 재검색**이므로 무수식 헤드라인 금지(`docs/case_analysis.md`).
- 외부/검증셋 라벨은 **정답이 아님**(코퍼스 텍스트 근거 카테고리 라벨). "정답"으로 부르지 말 것.
- "AI가 전략물자 판정/자가판정 대체", "법제 라우팅 정확도 n%" 류 주장 금지(`PAPER.md` 참조).
- 기존 산출물 수치를 임의로 바꾸지 말 것. figure/통계는 기존 `output/*.json`과 일치해야 함.
  수치가 실제로 바뀌면 **삭제하지 말고 before/after를 함께 남길 것**(예: `docs/statistics.md` §3·§6,
  `docs/statistics_n13_superseded.md`, 각 JSON의 `*_legacy` 필드).
- **랭킹에 `np.argsort(-scores)`를 쓰지 말 것.** 동점 순서가 정렬 구현에 좌우된다.
  `retrieval_core.rank_indices`를 쓰고, 점수 벡터가 전부 0인 질의는 **검색 실패**로
  집계할 것(코퍼스 앞머리 k행을 결과로 세지 말 것).
- **집계 rate에서 per-query hit 벡터를 재구성하지 말 것.** 각 실험 스크립트가
  `hit_vectors`를 JSON에 저장하므로 그것을 읽어 paired 검정을 할 것. 벡터가 없으면
  추정하지 말고 "짝지음 불가"로 표시할 것.
- **"CI가 0을 포함"을 등가성의 근거로 쓰지 말 것**(귀무가설 수용). 사전지정 마진 δ에
  대한 TOST를 쓸 것. 소표본에서는 percentile bootstrap 대신 exact McNemar /
  Clopper-Pearson을 primary로 쓸 것.

---

## 한계

- 합성 쿼리는 각 코퍼스 항목 **자기 본문**에서 코드만 제거해 만든 것이라 정답 문서와 near-duplicate입니다(평균 Jaccard 0.485). 따라서 합성 R@10 0.9792는 자기참조 재검색 성능에 가깝고, 후보 발견 능력의 절대 지표로 직접 일반화할 수 없습니다. `experiment_paraphrase_gap.py`로 검증: 정답 문서와 공유하는 변별(고-IDF) 토큰 5개를 제거하면 minimal_text R@10이 0.9792→0.7596, 10개에서 0.4407로 떨어집니다(`output/paraphrase_gap.md`).
- 합성 "한국어" 쿼리는 설명 본문이 영어라 언어 분리가 가짜입니다. 진짜 언어 격차는 검증셋(한국어 45개)에서만 관찰됩니다.
- 외부 모사 질의셋(`data/external_consultation_queries.json`) 30개의 `candidate_labels`는 연구자 예비 추정값이며 검증된 정답이 아닙니다. 30개 중 13개는 코드 정규화 충돌을 가집니다. 따라서 R@10=0은 "BM25 현장 성능=0"이 아니라 "불확실한 후보 라벨 기준 비수렴"으로 읽어야 합니다.
- Retriever 비교(TASK E): 자기참조 합성셋은 BM25에 구조적으로 유리해 retriever 비교에 부적합합니다. 외부 모사셋 30개에서는 BM25 R@10=0(30개 중 14개가 BM25 무신호), hybrid(α=0.5) 0.10, 한국어 0→0.0625입니다(`output/external_retriever.md`). 다만 라벨 노이즈가 커서 절대값 해석은 피하고, 헤드라인은 위 검증셋 n=71을 쓰십시오.
- 검증 라벨셋 n=13(TASK B/C)은 **대체되었습니다**. 당시 표기했던 "한국어 0→0.20, hybrid 0.2308"과 "표본이 작아 경향으로 보고"라는 판단은 `docs/statistics_n13_superseded.md`에 보존했습니다. 그 판단의 근거였던 95% CI [0.0000, 0.4615]는 소표본 percentile bootstrap의 **이산 경계 인공물**입니다: 3승 0패 10무에서 재표본에 승리 질의가 하나도 안 뽑힐 확률이 (10/13)^13 = 0.0330 > 0.025라서 2.5분위수가 **구조적으로** 0이 됩니다. 즉 n=13에서 3승 0패인 어떤 결과도 자동으로 "CI가 0을 포함"합니다. 동시에 exact McNemar p=0.25이므로 n=13은 실제로도 검정력이 부족했습니다. **소표본 이진 짝지음의 primary 검정은 exact McNemar / Clopper-Pearson입니다**(`docs/statistics.md` §5).
- 검증셋 확장(TASK G/I): eCFR 항목 역생성으로 n=71(영어 26, 한국어 45). hybrid(α=0.5) vs BM25 = **+0.4225**, exact McNemar 양측 p=1.9e-09(30승 0패 41무), paired bootstrap 95% CI [0.310, 0.535]. 한국어 BM25 **0.0000**(이전 표기 0.022는 오류) → dense/hybrid 0.60. 단 **hybrid vs dense는 유의하지 않습니다**(+0.028, p=0.62). 한국어에서 BM25 점수가 항등 0이면 α<1의 랭킹이 dense와 수학적으로 동일하므로(0승 0패), 데이터가 지지하는 진술은 "하이브리드가 필요하다"가 아니라 **"dense 성분이 필요하다"**입니다. 라벨은 여전히 코퍼스 텍스트 근거이며 전문가 검증은 후속 과제입니다.
- 역생성 질의의 자기참조 게이트(`jaccard(질의, 정답 minimal_text) < 0.30`)는 **한국어 45개 전부에서 정확히 0.0000**입니다. 한국어 질의와 영어 정답 텍스트는 토큰이 겹칠 수 없으므로 이 게이트는 한국어에 대해 아무것도 검사하지 못합니다(영어 26개는 평균 0.0941, 최대 0.2364로 한 번도 발동하지 않았습니다). 또 역생성 질의는 코퍼스 등장 순서를 훑은 흔적이 있습니다(slice_yechan 28/28, slice_seungwoo 25/28 단조증가). 언어중립 게이트가 필요합니다.
- 임베딩 robustness(TASK H): 이전 판은 세 모델이 **동일한 bootstrap 리샘플 행렬**을 공유해 모델별 CI가 독립적으로 얻어진 것처럼 보였습니다. 모델별 seed로 분리했습니다. 3모델 결과는 `experiment_validated_suite.py` 본실행 산출물로 갱신해야 합니다.
- 노출-성능: full_text→minimal_text로 **색인**을 줄이면 hybrid R@10 0.6056→0.5775로 감소합니다. 반면 색인은 그대로 두고 **반환 텍스트만** minimal_no_code로 줄이면 노출량@10이 4,043→1,729자(57.2% 감소)인데 랭킹이 바뀌지 않아 R@10은 0.6056 그대로입니다. 즉 반환량 축소는 비용이 0이고 비용은 색인 축소에서만 발생합니다. **"CI가 0을 포함하므로 손실이 없다"는 주장은 하지 않습니다**(귀무가설 수용). 등가 주장은 사전지정 마진 δ에 대한 TOST로만 합니다.
- 코퍼스 파싱은 정규식 기반이므로 수작업 표본 검수가 필요합니다.
- LLM reranker 비교는 아직 수행하지 않았습니다(후속 연구). Dense·hybrid는 이미 본 실험에 포함되어 있습니다.
- 노출량은 문자 수 기반 proxy입니다. 실제 영업비밀·기술정보 민감도와 동일하지 않습니다. 이전 정의에는 `minimal_text`와 `minimal_no_code`에 1,797개 항목 전부 동일한 값을 부여하는 버그가 있었습니다.
- BM25 단독은 어휘 불일치·언어 격차에서 구조적 한계를 보입니다(`docs/case_analysis.md`). "실제 현장에서 충분하다"고 단정하지 마십시오.
- 독립 누출 감사에서 원 검사기가 놓친 실제 코드 누출 4건이 발견되었습니다(예: q0613의 "ML19"). 원 검사기가 질의 생성에 쓴 정규식을 그대로 재사용해 구조적으로 누출을 찾을 수 없었기 때문입니다.

## 제출 논문에서 안전한 주장

사용 가능:

> 정답 통제번호를 쿼리에 포함하지 않는 합성 설명형 쿼리에서, 공개 통제목록 후보검색 기준 `minimal_text` 조건은 `full_text` 대비 평균 반환 정보량을 약 66.4% 줄이면서 R@10 0.9792를 유지했다. 단, 이 합성 쿼리는 코퍼스 항목 자기 본문에서 파생되어 정답 문서와 near-duplicate 관계이므로 절대수치는 자기참조 재검색에 가깝다(고-IDF 공유토큰 5개 제거 시 0.7596, 10개 제거 시 0.4407). 자기참조가 아닌 검증셋 n=71(영어 26 / 한국어 45)에서는 BM25 단독 R@10이 0.1549이고 한국어에서는 정확히 0.0000인 반면, 다국어 dense 성분을 넣으면 0.5493~0.5775로 올라간다(exact McNemar 양측 p=1.9e-09, 30승 0패). 즉 합성 benchmark 결과를 현장 성능으로 직접 일반화하지 않으며, 다국어 상담 질의에는 dense 성분이 필요하다. 상세는 `docs/statistics.md`, `docs/case_analysis.md` 참조.

> 색인 텍스트와 반환 텍스트를 분리하면, 색인을 그대로 두고 반환 텍스트만 줄이는 조건에서 top-10 반환 문자 수가 4,043 → 1,729(57.2% 감소)인데 랭킹이 바뀌지 않으므로 R@10은 0.6056으로 동일하다. 정보 노출 축소의 비용은 반환 단계가 아니라 색인 단계에서 발생한다.

사용 금지:

- “AI가 전략물자 여부를 판정한다”
- “법제 라우팅 정확도 n%”
- “전문판정/자가판정을 대체할 수 있다”
- “실제 기업 질의에서 검증됐다”
- “BM25 baseline이 실제 현장에서 충분하다”
- “다국어 **하이브리드**가 유의하게 필요하다” — 검증셋에서 hybrid vs dense는 유의하지 않다(p=0.62). 지지되는 진술은 “**dense 성분**이 필요하다”이다.
- “노출을 줄여도 성능 손실이 없다” — CI가 0을 포함한다는 것은 등가성의 근거가 아니다. 사전지정 마진에 대한 TOST가 통과했을 때만 비열등을 말한다.
- “검증셋 한국어 BM25 R@10 = 0.0222” — 실제 값은 **0.0000**이다.
