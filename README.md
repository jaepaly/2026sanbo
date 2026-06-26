# 전략물자 AI 사전 트리아지 실험

이 저장소는 외부 AI/검색 서비스에 기술정보를 전송할 때, 반환·처리하는 정보량을 줄이면서 공개 통제목록 후보검색 성능을 어느 정도 유지할 수 있는지 검증하기 위한 연구용 실험 저장소입니다.

중요한 정정:

- 이 실험은 전략물자 해당/비해당을 법적으로 판정하지 않습니다.
- 이 실험은 수출허가를 대신하거나, 자가판정·전문판정을 보조하는 수준을 넘어서지 않습니다.
- 이전 버전의 "정답 코드가 쿼리에 포함된 A-scenario"는 후보탐지 실험으로 부적절하여 제거했습니다.
- 법제 라우팅 "정확도" 수치는 공식 라벨이 아니므로 제거했습니다.
- 본 baseline은 BM25-only sparse retrieval을 사용합니다. LLM reranker·임베딩 기반 실험은 연구 질문(정보최소화)의 핵심을 흐리지 않도록 별도 후속 연구로 분리하는 방식을 권장합니다.
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

본 저장소는 합성 benchmark와 별도로, 외부 모사 질의셋을 통해 BM25-only baseline의 한계를 드러내는 stress test를 포함한다.

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

BM25 투명 기준선 결과입니다. 수치는 후보검색 성능이지 법적 판정 정확도가 아닙니다.

| 조건 | R@1 | R@5 | R@10 | R@20 | MRR | nDCG@10 | 평균 노출량@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| full_text | 0.8702 | 0.9904 | 0.9968 | 0.9984 | 0.9235 | 0.9419 | 4,834 |
| minimal_text | 0.7837 | 0.9583 | 0.9792 | 0.9856 | 0.8607 | 0.8896 | 1,623 |
| minimal_no_code | 0.7676 | 0.9615 | 0.9808 | 0.9856 | 0.8525 | 0.8840 | 1,592 |
| route_only | 0.0016 | 0.0032 | 0.0080 | 0.0160 | 0.0039 | 0.0038 | 702 |
| random_baseline | - | - | 0.0048 | - | - | - | - |

해석:

- `minimal_text`는 `full_text` 대비 평균 노출량@10을 약 66.4% 줄이면서 R@10은 0.9968 → 0.9792로 1.76%p 감소했습니다.
- `minimal_no_code`도 유사하게 낮은 노출량과 높은 R@10을 보입니다.
- `route_only`는 법제/업무흐름 힌트만으로는 후보검색이 거의 불가능하다는 음성 대조군입니다.
- **주의**: 합성 benchmark의 R@10 0.9792는 이상적인 어휘 매칭 환경이고, 상담형 모사 질의셋(30개)에서는 성공·실패 패턴이 분포한다. `docs/case_analysis.md` 참조.

상세 결과: `output/report.md`, `output/experiment_logs.json`

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
python evaluate_validated_queries.py   # 검증 라벨셋 retriever 평가 (TASK B/C/E)
python experiment_crosslingual_eval.py # 한국어 KO-원문/번역/EN 비교 (TASK D)
python experiment_stats.py             # bootstrap CI·효과크기 (TASK F)
python make_figures.py                 # 논문용 figure 4종 (TASK F)
```

> 참고: `experiment_*retriever*.py`와 `evaluate_validated_queries.py`는 다국어 dense 모델
> (`paraphrase-multilingual-MiniLM-L12-v2`, 약 470MB)을 처음 실행 시 자동 다운로드합니다.
> 무거운 임베딩 연산은 로컬에서 수행되며 외부 추론 API를 호출하지 않습니다.

---

## 팀 협업 가이드 (작업 분담)

이 저장소는 팀 분담으로 진행됩니다. 각 팀원은 저장소를 클론하고, **자신의 AI 에이전트에게 저장소를 읽힌 뒤** 아래 담당 TASK를 수행하고, 산출물을 PR(권장) 또는 파일로 제출합니다.

### 1. 담당 분배

| TASK | 담당 | 내용 | 상세 스펙 |
|---|---|---|---|
| **TASK F** | 팀원 A | 결과 시각화(논문 figure) + 통계 보강(CI·효과크기) + 재현성. **새 실험 없음**, 기존 `output/*.json`만 읽어 그림 생성 | `docs/RESEARCH_IMPROVEMENT_PLAN.md` §3 TASK F |
| **TASK D** | 팀원 B | 한국어 cross-lingual 트랙(번역 필드/동의어 사전/다국어 임베딩). 검증셋 기준 KO 회복 정량화 | `docs/RESEARCH_IMPROVEMENT_PLAN.md` §3 TASK D |

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

**TASK F 담당 — 에이전트 프롬프트**
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

**TASK D 담당 — 에이전트 프롬프트**
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

---

## 한계

- 합성 쿼리는 각 코퍼스 항목 **자기 본문**에서 코드만 제거해 만든 것이라 정답 문서와 near-duplicate입니다(평균 Jaccard 0.485). 따라서 합성 R@10 0.9792는 자기참조 재검색 성능에 가깝고, 후보 발견 능력의 절대 지표로 직접 일반화할 수 없습니다. `experiment_paraphrase_gap.py`로 검증: 정답 문서와 공유하는 변별(고-IDF) 토큰 5개를 제거하면 minimal_text R@10이 0.9792→0.7596, 10개에서 0.4407로 떨어집니다(`output/paraphrase_gap.md`).
- 외부 모사 질의셋(`data/external_consultation_queries.json`) 30개의 `candidate_labels`는 연구자 예비 추정값이며 검증된 정답이 아닙니다. 30개 중 13개는 코드 정규화 충돌을 가집니다. 따라서 R@10=0은 "BM25 현장 성능=0"이 아니라 "불확실한 후보 라벨 기준 비수렴"으로 읽어야 합니다.
- Retriever 비교(TASK E): 자기참조 합성셋은 BM25에 구조적으로 유리해 retriever 비교에 부적합합니다(합성 "한국어" 쿼리는 영어 본문이라 언어 분리도 가짜). 진짜 한국어가 있는 외부셋에서는 BM25 R@10=0인데 다국어 hybrid(α=0.5)가 0.10, 한국어 0→0.0625로 회복합니다(`output/external_retriever.md`). 즉 cross-lingual엔 다국어 dense가 필요합니다.
- 검증 라벨셋(TASK B/C): 코드충돌·추정 라벨을 제거하고 eCFR full code로 핀 고정한 검증셋(`data/external_consultation_queries_validated.json`, 평가 13/제외 17)에서 BM25 R@10=0(영어 포함), hybrid(α=0.5) 0.2308, 한국어 0→0.20. 라벨 노이즈 제거로 hybrid가 0.10→0.23으로 약 2배(`output/validated_eval.md`). 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 법적 판정·전문가 검증이 아닙니다.
- 코퍼스 파싱은 정규식 기반이므로 수작업 표본 검수가 필요합니다.
- 현재 실험은 BM25 기준선입니다. Dense retrieval, reranker, LLM 비교는 기준선이 안정화된 뒤 별도 실험으로 추가해야 합니다.
- 노출량은 문자 수 기반 proxy입니다. 실제 영업비밀·기술정보 민감도와 동일하지 않습니다.
- BM25-only baseline은 어휘 불일치·도메인 설명 격차에서 한계를 보입니다(`docs/case_analysis.md`). "실제 현장에서 충분하다"고 단정하지 마십시오.

## 제출 논문에서 안전한 주장

사용 가능:

> 정답 통제번호를 쿼리에 포함하지 않는 합성 설명형 쿼리에서, 공개 통제목록 후보검색 기준 `minimal_text` 조건은 `full_text` 대비 평균 반환 정보량을 약 66.4% 줄이면서 R@10 0.9792를 유지했다. 단, 이 합성 쿼리는 코퍼스 항목 자기 본문에서 파생되어 정답 문서와 near-duplicate 관계이므로 절대수치는 자기참조 재검색에 가깝다. 연구자가 예비 부여한(검증되지 않은) 후보 라벨 기준의 상담형 모사 질의셋 30개에서는 BM25 top-10이 후보 라벨로 수렴하지 못했다(R@10=0). 이는 합성 평가와 독립 패러프레이즈 평가 사이의 일반화 격차를 보여주는 증거이며, 합성 benchmark 결과를 현장 성능으로 직접 일반화하지 않는다. 상세는 `docs/case_analysis.md` 참조.

사용 금지:

- “AI가 전략물자 여부를 판정한다”
- “법제 라우팅 정확도 n%”
- “전문판정/자가판정을 대체할 수 있다”
- “실제 기업 질의에서 검증됐다”
- “BM25 baseline이 실제 현장에서 충분하다”
