# 인수인계 (HANDOFF)

> 다른 기기·다른 세션·다른 에이전트가 이 저장소를 이어받을 때 **가장 먼저 읽는 문서**.
> 최종 갱신: 2026-08-01 / TASK J 병합 + 민감토큰 계량기 경계 정정까지 반영 (검증셋 **n=151**, 사다리 **n=133**)

---

## 0. 30초 요약

산업보안논문경진대회 제출용 연구. **논문 초안은 `PAPER.md`에 완성돼 있고, 그 안의 모든 수치는 `python verify_claims.py`가 산출물과 자동 대조한다(현재 OK=112 / MISMATCH=0).**

논문의 세 축:
1. **최소화 대상은 반환량이 아니라 질의다.** 반환 텍스트는 공개문서이고 색인에 안 들어가 랭킹을 안 바꾸므로 축소 비용이 구조적으로 0이다(노출량 77.4%↓, R@10 변화 0.0000).
2. **질의 측 운용 권고는 L1**(정량 사양치 삭제)이고 **세 인코더가 모두 L1로 일치**한다. 단 **어느 모델에서도 TOST 등가는 입증되지 않았다**(L1 p_max 0.05~0.32, 입증에 n≈556 필요) — 지지되는 진술은 "무해 입증"이 아니라 "손실 징후 없음"이다. L2·L4는 세 모델 모두 손실 징후, L3는 세 모델 모두 자기참조 교란으로 거부. 또한 **용도로 정의된 품목군에는 노출 축소의 바닥이 있어 사다리가 L2에서 멈춘다**.
3. **저노출 후보검색엔 dense 성분이 필수.** BM25는 한국어에서 R@10 0.0275(151개 중 96개 무신호). dense−BM25는 3개 인코더 전부에서 유의, **hybrid−dense는 세 모델 모두 Holm 보정 후 비유의**(MiniLM만 보정 전 0.012 → 보정 후 0.059로 경계).

> **n=71 → n=151에서 바뀐 것**: 권고의 모델 의존성 해소(강화), 최대 압력 하 dense 우위 2/3→3/3(강화), 정답 스텁 오염 59.2%→27.8%(강화) / L1 등가 입증 2/3→0/3(약화), L2가 검정력 부족→손실 징후(약화). 양방향을 모두 논문에 적었다.

---

## 1. 새 기기 셋업

```bash
git clone https://github.com/jaepaly/2026sanbo.git
cd 2026sanbo
python -m venv .venv
.venv\Scripts\activate          # mac/linux: source .venv/bin/activate
pip install -r requirements.txt
```

**원본 PDF·HTML은 저장소에 없다**(제3자 저작물이라 `.gitignore`로 제외). 그러나 **정화된 코퍼스(`data/corpus/combined.json`)와 모든 질의셋이 커밋돼 있으므로 실험 재현에는 원본이 필요 없다.** 코퍼스를 처음부터 다시 만들 때만 `python fetch_sources.py fetch`로 재취득한다(`data/SOURCES.md` 참조).

**dense 모델은 첫 실행 시 자동 다운로드**된다(로컬 실행, 외부 추론 API 호출 없음).
- `paraphrase-multilingual-MiniLM-L12-v2` ~470MB (주 모델)
- `intfloat/multilingual-e5-base` ~1.1GB
- `BAAI/bge-m3` ~2.2GB
- `sentence-transformers/LaBSE` ~1.8GB (자기참조 감사 전용, 평가에 미사용)

---

## 2. 인수 직후 첫 명령 (건강검진)

```bash
python verify_claims.py
```

**기대: `OK=112` / `MISMATCH=0` / exit 0.** 하나라도 MISMATCH면 논문과 근거가 어긋난 것이니 **먼저 그것부터 해결**한다(산출물이 낡았으면 재실행, 논문이 낡았으면 논문 수정).

```bash
for f in tests/test_*.py; do python "$f" >/dev/null && echo "PASS $f" || echo "FAIL $f"; done
```
(`pytest`가 없으면 위처럼 직접 실행. 8개 파일 전부 exit 0이어야 한다.)

> **Windows 주의**: `core.autocrlf=true`인 클론에서 원본 출처 파일이 CRLF로 변환되면
> `fetch_sources.py verify`의 SHA-256이 전부 어긋난다. `.gitattributes`가 이를 막고
> 있으니 지우지 말 것. 콘솔이 cp949면 `PYTHONIOENCODING=utf-8`을 앞에 붙인다.

---

## 3. 현재 확정된 수치 (2026-07-31)

**코퍼스 v2**: 1,783건 = eCFR 637 + SCOMET 578 + Wassenaar 568. **100% 영어**(한글 항목 0).
**검증셋**: n=151 (영어 42 / 한국어 109), 정답은 eCFR full code.
**사다리 분석 대상**: n=133 (정의 위반 18건 제외 — `data/disclosure_ladder.json` → `ladder_spec_exclusions`).
남은 18건은 **통제 범주 자체가 용도로 정의된 품목**(군용 전자·로켓 추진·방사성 선원)이라 L3의 '민감토큰 0'에 원리상 도달할 수 없다. 계량기 결함이 아니라 논문 4.5가 보고하는 **결과**다.

### 검색기 (색인 `minimal_text`)
| 인코더 | BM25 | dense | hybrid(α0.5) | 한국어 hybrid | dense−BM25 Holm | hybrid−dense |
|---|---:|---:|---:|---:|---|---|
| MiniLM | 0.1523 | 0.4503 | 0.5099 | 0.4954 | 1.8×10⁻⁸ 유의 | +0.060, p_adj 0.059 비유의 |
| e5-base | 0.1523 | 0.4768 | 0.4901 | 0.4587 | 1.0×10⁻¹⁰ 유의 | +0.013, p_adj 1 비유의 |
| bge-m3 | 0.1523 | **0.5695** | 0.5497 | 0.5596 | <10⁻¹⁵ 유의 | **−0.020** (dense가 더 높다) |

BM25 한국어 = **0.0275** (151개 중 96개가 어휘 교집합 0. n=71에서는 정확히 0이었고, 확장 질의의 숫자·라틴 토큰이 드물게 교집합을 만든다).

### 노출 2차원표 (MiniLM, hybrid α0.5)
| 색인 ＼ 반환 | full_text | minimal_text | minimal_no_code | R@10 |
|---|---:|---:|---:|---:|
| full_text | 7,886.2 | **1,780.8** | 1,691.0 | 0.5497 |
| minimal_text | 5,868.2 | 1,805.5 | 1,714.6 | 0.5099 |
| minimal_no_code | 5,804.2 | 1,708.1 | 1,618.4 | 0.4901 |

**운용점**: 색인 `full_text` + 반환 `minimal_text` → 노출 **−77.4%**, R@10 변화 **정확히 0.0**.
색인 축소는 비용이 있다: `minimal_text` −0.0397, δ=0.05 등가 미성립(입증에 n≈6,166 필요).

### 질의 노출 사다리 (hybrid α0.5)
| 등급 | 민감토큰 | R@10 | 평균차 | 증거등급 |
|---|---:|---:|---:|---|
| L0 | 5.35 | 0.5188 | — | 기준 |
| L1 | 4.77 | 0.4962 | −0.0226 | B. 하락 미검출 (TOST p_max 0.112, n≈556 필요) ← **운용 권고** |
| L2 | 4.19 | 0.4211 | −0.0977 | **C. 손실 징후** (Holm p_adj 0.018) |
| L3 | 0.00 | 0.4586 | −0.0602 | **D. 자기참조 교란 → 사용 금지** |
| L4 | 0.00 | 0.3835 | −0.1353 | **C. 손실 징후** (Holm p_adj 0.019) |

세 인코더 전부 L1을 권고하고 L2·L4를 손실 징후로 분류한다(`frontier_recommendation_is_model_dependent: false`). **등가가 입증된 등급은 하나도 없다.**

> **L1 등가는 이 코퍼스로 도달 불가**다. 필요 n≈556인데, 스텁이 아닌 eCFR 항목을 전부 소진해도 1질의 1항목 상한이 **328**이다(비스텁 286 − 사용중 109 = 미사용 177, 151+177=328). 등가 주장을 원하면 라벨 공간 자체를 넓혀야 한다.

---

## 4. 저장소 지도

| 목적 | 파일 |
|---|---|
| **논문 초안** | `PAPER.md` |
| **수치 자동 검증** | `verify_claims.py` → `docs/claim_registry.json` |
| 위협모형 (왜 질의 측을 재는가) | `docs/threat_model.md` |
| 헤드라인 결과 | `output/validated_suite.{json,md}` |
| 질의 사다리 결과 | `output/disclosure_frontier.{json,md}` |
| 노출 분해 | `output/exposure_decomposition.{json,md}` |
| 자기참조 감사 | `docs/selfreference.md`, `output/symmetric_ablation.md`, `output/ladder_selfreference.md` |
| 라벨 감사 | `docs/label_audit.md` |
| 라벨 강건성 | `output/label_sensitivity.md` |
| 통계 | `docs/statistics.md` |
| 재현 절차 | `docs/reproducibility.md` |
| 팀 분담 이력 | `README.md` §완료된 이전 라운드, `docs/RESEARCH_IMPROVEMENT_PLAN.md` |
| 공통 검색 코어 | `retrieval_core.py` (BM25·랭킹·노출·통계 단일 출처) |

---

## 5. 절대 하지 말 것 (가드레일)

- "AI가 전략물자 해당/비해당을 판정한다" / "자가판정·전문판정을 대체한다"
- "검증 라벨이 법적 정답이다" — 코퍼스 텍스트 근거 카테고리 라벨이다
- **"신뢰구간이 0을 포함하므로 손실이 없다"** — 귀무가설 수용 오류. 등가는 사전지정 δ의 TOST로만
- **"하이브리드가 필요하다"** — 데이터가 지지하는 건 **dense 성분**의 필요성
- "합성 R@10 0.9840이 후보검색 성능이다" — 자기참조 재검색임을 명시
- "L3까지 지워도 안전하다" — 자기참조 교란으로 **철회된 결론**
- "반환량을 줄여 기업 비밀을 보호했다" — 반환 텍스트는 공개문서

---

## 6. 표제 스텁 보강 — 시도했고 반증됨 (닫힘)

> **결론: 가설은 반증됐다. v3는 채택하지 않는다.**
>
> 실제로 코퍼스를 고쳐 측정했다. eCFR 본문을 원문 XML에서 복구해
> `data/corpus/combined_v3.json` 을 만들었고(본문 105,567 → 814,646자, 내용 기준
> 스텁 475 → 48, 정답이 전부 스텁인 질의 47 → 1), 검색 성능은 **어느 색인 모드에서도
> 유의하게 오르지 않았다**(`output/corpus_v3_impact.md`).
>
> | 색인 | BM25 | dense | hybrid |
> |---|---:|---:|---:|
> | minimal_text | +0.0282 | −0.0141 | −0.0141 (p=1) |
> | full_text | +0.0423 | −0.0423 | +0.0423 (p=0.549) |
>
> 이유 둘. (1) MiniLM `max_seq_length`=128 이라 v3 `full_text` 에서 eCFR 문서의
> **53%가 인코더에서 잘린다**(중앙 토큰 47 → 146). `minimal_text` 는 첫 문장 260자
> 상한이라 본문이 애초에 색인에 안 들어간다. (2) 더 근본적으로, **검증 질의는 그
> 당시 코퍼스에 있던 표제를 읽고 역생성**됐다 — 질의-표제 Jaccard 0.0373 vs
> 질의-본문 0.0197. 나중에 채운 본문은 질의가 보고 쓰인 적이 없어 매칭에 기여하지
> 못하고 dense 표현만 희석시킨다. 질의셋을 풍부해진 코퍼스에 맞춰 다시 만들면
> 자기참조가 되살아난다.
>
> 부수 발견: `audit_label_quality.is_stub` 는 `(see List of Items Controlled)`
> **문구** 존재를 보므로, 본문을 복구해도 표제에 문구가 남아 지표가 351 → 352 로
> 거의 움직이지 않는다. 지표가 재려던 것과 실제로 재는 것이 다르다.
> 상세: `docs/corpus_v3_stub_recovery.md`.
>
> 아래는 당시 문제 인식과 작업 지시를 기록으로 남긴 것이다.

### 문제
eCFR 637건 중 **351건(55.1%)**이 `(see List of Items Controlled)` 형태의 **표제 스텁**이라 기술 파라미터가 코퍼스에 없다. **검증셋 71개 중 42개(59.2%)는 정답이 전부 스텁**이다. 즉 어휘·의미로 맞출 근거가 애초에 코퍼스에 없는 질의가 절반을 넘는다. 이것이 현재 절대 성능(R@10 0.58)의 최대 상한 요인이다.

### 왜 지금 할 수 있나
`fetch_ecfr.py`에 이미 `SECTION_LIST_OF_ITEMS = "List of Items Controlled"` 상수와 해당 절 파싱 로직이 있다(76행 부근). 원문 XML에 내용이 존재하므로 **전문가 없이 파서 작업만으로** 해결 가능하다.

### 작업 지시
1. `python fetch_ecfr.py --save-xml data/raw/ecfr_supp1.xml --out <경로>` 로 원문 XML 확보.
2. 각 ECCN 항목에 대해 `List of Items Controlled` 절 본문을 추출해, 코퍼스 항목에 **새 필드**(예: `items_controlled`)로 붙이거나 `text`에 이어붙인다. **기존 `text` 정의를 바꾸면 모든 수치가 움직이므로**, v3 코퍼스로 분리하고 `data/corpus/corpus_version_manifest.json`에 등재할 것.
3. `python tests/test_corpus.py` 통과 확인.
4. 재실행 순서(아래 §7 의존 순서 반드시 준수) 후 `python verify_claims.py`로 어떤 수치가 움직였는지 확인하고 `PAPER.md`를 갱신.
5. **비교 보고**: v2 대비 스텁 비율, 42/71이 몇 개로 줄었는지, R@10이 얼마나 올랐는지. 오르지 않으면 그것도 결과다(스텁이 원인이 아니었다는 뜻).

### 수용 기준
- 코퍼스 v3가 v2와 분리 저장되고 매니페스트에 sha256 등재
- `docs/label_audit.md` 재실행(`python audit_label_quality.py audit`)으로 스텁 지표 갱신
- `verify_claims.py` OK / MISMATCH=0 복구
- PAPER 7절 한계 1의 수치 갱신

---

## 7. ⚠ 재실행 의존 순서 (이걸 어기면 산출물이 조용히 낡는다)

실제로 한 번 발생한 사고다. 샤드를 병합한 뒤 노출 분해를 재실행하지 않아 기준값이 4,043(구) → 9,730(신)으로 어긋난 채 문서에 인용됐다.

```
① 코퍼스 변경 시
   build_corpus_clean.py → generate_queries.py → run_experiments.py
   → experiment_paraphrase_gap.py
   → audit_label_quality.py audit      (라벨 감사)
   → audit_ladder_selfreference.py     (L3 판정)
   → experiment_disclosure_frontier.py (질의 사다리)

② 샤드(모델) 추가 시
   run_model_shard.py <model>  → validate_shard.py <파일>  → merge_shards.py
   → **report_exposure_decomposition.py**   ← 빠뜨리기 쉬움!
   → experiment_label_sensitivity.py

③ 질의셋(검증셋) 확대 시  ← TASK J 에서 실제로 밟은 순서
   build_expanded_validated.py            (슬라이스 병합, n 갱신)
   → build_disclosure_ladder.py           (사다리 + 정의 위반 제외 회계)
   → audit_ladder_selfreference.py        (L3 판정)
   → audit_label_quality.py audit / emit  (라벨 감사 + 등가 라벨 재생성)
   → selfreference_gate.py                (게이트 공허성 재측정) ← 빠뜨리기 쉬움!
   → run_model_shard.py ×3 → validate_shard.py → merge_shards.py
   → report_exposure_decomposition.py → experiment_label_sensitivity.py
   → experiment_disclosure_frontier.py → experiment_symmetric_ablation.py
   → run_tier1.py ×3 → validate_tier1.py ×3 → report_tier1_crossmodel.py

④ 치환 사전(data/hypernym_substitutions.json) 변경 시
   experiment_symmetric_ablation.py → run_tier1.py ×3 → validate_tier1.py ×3
   → report_tier1_crossmodel.py
   (사전은 ablation 에만 쓰이지만 Tier-1 번들이 ablation 을 포함하므로 3종 전부 재실행)

⑤ 민감토큰 계량기(build_disclosure_ladder.py 의 GRADE_TERMS/ATTRIBUTE_TERMS) 변경 시
   build_disclosure_ladder.py → audit_ladder_selfreference.py
   → experiment_disclosure_frontier.py → run_tier1.py ×3 → report_tier1_crossmodel.py

⑥ 항상 마지막
   make_figures.py → experiment_stats.py → verify_claims.py
   → for f in tests/test_*.py; do python "$f"; done
```

**GPU 실행 메모(RTX 3060 8GB)**: `.venv`는 torch 2.6.0+cu124다. bge-m3는 8GB에서 OOM이 나므로 `SANBO_BATCH`로 배치를 낮춘다 — 샤드/ablation은 `SANBO_BATCH=8`, Tier-1 bge-m3는 `SANBO_BATCH=2`. `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`도 함께 준다. 배치 크기는 임베딩 값을 바꾸지 않는다(수치 동일성 확인됨).

---

## 8. 알려진 함정

- **cp949 인코딩**: Windows 콘솔에서 유니코드(—, −, ≥) 출력 시 `UnicodeEncodeError`로 스크립트가 죽는다. `verify_claims.py`는 고쳤지만 다른 스크립트는 아직이다. 증상이 보이면 `PYTHONIOENCODING=utf-8 python ...`로 실행.
- **`np.argsort(-scores)` 함정**: 점수가 전부 0인 벡터를 정렬하면 코퍼스 배열 앞머리가 결과로 나온다. 이 때문에 BM25 한국어 R@10이 0.0222로 잘못 집계된 적이 있다. **랭킹은 반드시 `retrieval_core.rank_indices`를 쓰고, 무신호 질의는 검색 실패로 집계**한다.
- **`.gitignore` 방침**: `output/`은 이제 **기본 커밋 대상**이다(허용목록 → 부정목록으로 전환). 새 산출물이 조용히 빠지지 않는다.
- **낡은 v1 산출물**: `external_eval`, `external_label_audit`, `external_retriever`, `retriever_compare`는 코퍼스 v1 기준이며 논문이 인용하지 않는다. `meta.superseded_by`가 박혀 있으니 되살리지 말 것.
- **문서의 v1 수치는 의도적일 수 있다**: README 변경이력표, `docs/corpus_parsing_fixes.md`, `docs/statistics_n13_superseded.md`, `docs/case_analysis.md`(superseded 배너)는 v1을 **일부러** 참조한다. 일괄 치환 금지.
- **CRLF가 출처 해시를 깨뜨린다**: `core.autocrlf=true`인 Windows 클론은 체크아웃 때 텍스트 원본을 CRLF로 바꿔 `fetch_sources.py verify`의 SHA-256을 전부 어긋나게 만든다(원본은 그대로인데). `.gitattributes`가 해당 경로의 변환을 끄고 있으니 **지우지 말 것**.
- **사다리 정의 위반 18건은 버그가 아니라 결과**다: 고쳐서 통과시키지 않고 제외하고 세었다. `ladder_spec_compliant=false`인 질의를 사다리 분석에 되돌려 넣지 말 것(검색기 비교에는 그대로 쓴다).
- **민감토큰 계량기 경계를 함부로 옮기지 말 것**: `GRADE_TERMS`(계수) vs `ATTRIBUTE_TERMS`(function, 비계수)의 분류가 노출 축 전체를 좌우한다. `tests/test_disclosure_ladder.py::test_detector_boundary`가 대표 사례로 고정하고 있다. 옮겨야 한다면 **정의문에서 근거를 대고**, 정정 전후 frontier를 함께 보고할 것(`output/disclosure_frontier_strict_detector.json`이 수정 전 참조본).
- **치환 사전 커버리지는 151/151이다**(2026-08-01 확대 완료). `verify_claims.py`와 `tests/test_selfreference.py`가 전량 커버리지를 고정한다. 규칙을 지워 커버리지가 떨어지면 실패한다. 확대 전 산출물은 `output/symmetric_ablation_partial_coverage.json`에 있고, 확대는 dense 우위 폭을 +0.2450 → +0.2119로 **줄였다**(연구자에게 불리한 방향) — 이 대조가 PAPER 4.6 표에 있다.

---

## 9. 팀 협업 현황

| 사람 | 담당 | 상태 |
|---|---|---|
| 팀장(jaepaly) | 통합·검증·논문 | 진행 중 |
| 이예찬 | TASK F(그림·통계), TASK G 슬라이스(0/1/2/8), bge-m3 샤드·Tier-1, TASK J 슬라이스 40건 | 완료·병합됨 |
| 장승우 | TASK D(한국어), TASK G 슬라이스(3~7/9), e5-base 샤드, TASK J 슬라이스 40건 | 완료·병합됨 |

새 작업을 팀원에게 분담할 때는 `README.md` §코퍼스 v2 채택 매뉴얼의 1인칭 절차(배정모델만 바꿔 재사용)와 `docs/RESULT_REPORT_TEMPLATE.md` 양식을 쓴다. 이전 라운드의 에이전트 프롬프트 전문은 `docs/RESEARCH_IMPROVEMENT_PLAN.md`에 있다. 샤드 제출물은 반드시 `validate_shard.py`로 검증한 뒤 병합한다(BM25 히트 벡터가 바이트 단위로 일치해야 하며, 이것이 상대 환경을 신뢰하지 않고도 동일 조건이었음을 보장한다).

---

## 10. 남은 과제 (우선순위)

1. ~~표제 스텁 보강~~ — **완료·반증**(§6). 코퍼스를 실제로 고쳐 측정했으나 성능 향상 없음. v3는 아티팩트로 보존, 채택 안 함. 음성 결과로 논문 한계 절에 사용 가능
2. ~~표본 확대 (TASK J)~~ — **완료·병합**(n=151). 동기가 된 질문에 답이 나왔다: **bge-m3의 L2 손실 징후는 모델 차이가 아니라 검정력 부족이었고**, n=151에서는 세 모델 모두 L2가 손실 징후·L1 권고로 수렴했다. 대가로 L1 등가 입증이 사라졌다
3. ~~대칭 ablation·사다리의 다모델 확장~~ — **완료**(PAPER 4.8, `output/tier1_crossmodel.md`). n=151에서 최대 압력 유의성 3/3, 운용 권고 모델 비의존
4. **L1 등가 입증 — 이 코퍼스로는 불가로 확정**. 필요 n≈556 vs 상한 328. 지금 논문이 말할 수 있는 것은 "손실 징후 없음"까지다. 추진하려면 라벨 공간을 eCFR 밖으로 넓히는 설계 변경이 선행돼야 한다
5. ~~사다리 정의 위반 32건~~ — **계량기 경계 정정으로 18건까지 축소**(사다리 119 → 133). 남은 18건은 고칠 대상이 아니라 **보고할 결과**다(용도 정의형 품목군의 환원 불가능한 바닥). 더 줄이려면 그 품목군을 위한 별도 노출 축을 설계해야 한다
6. ~~치환 사전 커버리지 확대~~ — **완료**(71/151 → 151/151, 규칙 170 → 330개). 확대 전후를 PAPER 4.6에 병기했다
7. **실제 기업 질의 확보** — 현장 대표성(현재 전부 역생성 합성)
8. ~~전문가 라벨 검수~~ — **범위 밖으로 확정**. 대신 PAPER 4.7의 라벨 강건성 분석으로 대체함(라벨 결함 질의를 모두 제거해도 결론 유지)
9. **제출 형식 확정(팀장만 가능)** — 대회 마감일과 제출 포맷(hwp/docx/pdf·분량 제한)이 아직 미확인이다. `PAPER.md`는 마크다운뿐이라 변환·재편집 시간이 필요하다
