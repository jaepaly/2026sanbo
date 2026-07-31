# 인수인계 (HANDOFF)

> 다른 기기·다른 세션·다른 에이전트가 이 저장소를 이어받을 때 **가장 먼저 읽는 문서**.
> 최종 갱신: 2026-07-31 / 기준 커밋: `16e4e37`

---

## 0. 30초 요약

산업보안논문경진대회 제출용 연구. **논문 초안은 `PAPER.md`에 완성돼 있고, 그 안의 모든 수치는 `python verify_claims.py`가 산출물과 자동 대조한다(현재 OK=104 / MISMATCH=0).**

논문의 세 축:
1. **최소화 대상은 반환량이 아니라 질의다.** 반환 텍스트는 공개문서이고 색인에 안 들어가 랭킹을 안 바꾸므로 축소 비용이 구조적으로 0이다(노출량 81.4%↓, R@10 변화 0.0000).
2. **질의 측에서 정량 사양치 삭제(L1)는 등가가 입증**됐다(3개 인코더 중 2개). **운용 권고는 L1**(보수적) — 권고 등급이 인코더에 따라 갈린다(MiniLM·e5-base L2, bge-m3 L1). L3는 세 모델 모두 자기참조 교란으로 거부.
3. **저노출 후보검색엔 dense 성분이 필수.** BM25는 한국어에서 구조적으로 R@10 0.0000. dense−BM25는 3개 인코더 전부에서 유의, **hybrid−dense는 어디서도 유의하지 않다**.

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

**기대: `OK=104` / `MISMATCH=0` / exit 0.** 하나라도 MISMATCH면 논문과 근거가 어긋난 것이니 **먼저 그것부터 해결**한다(산출물이 낡았으면 재실행, 논문이 낡았으면 논문 수정).

```bash
python tests/test_repo_invariants.py
python tests/test_corpus.py
python tests/test_label_audit.py
python tests/test_retrieval_core.py
python tests/test_selfreference.py
```
(`pytest`가 없으면 위처럼 직접 실행. 전부 exit 0이어야 한다.)

---

## 3. 현재 확정된 수치 (2026-07-31)

**코퍼스 v2**: 1,783건 = eCFR 637 + SCOMET 578 + Wassenaar 568. **100% 영어**(한글 항목 0).
**검증셋**: n=71 (영어 26 / 한국어 45), 정답은 eCFR full code.

### 검색기 (색인 `minimal_text`)
| 인코더 | BM25 | dense | hybrid(α0.5) | 한국어 hybrid | dense−BM25 Holm | hybrid−dense |
|---|---:|---:|---:|---:|---|---|
| MiniLM | 0.1549 | 0.5493 | 0.5775 | 0.6000 | 3.5×10⁻⁷ 유의 | 비유의 |
| e5-base | 0.1549 | 0.4648 | 0.4930 | 0.4889 | 1.8×10⁻⁵ 유의 | 비유의 |
| bge-m3 | 0.1549 | 0.5634 | 0.5634 | 0.6222 | 1.8×10⁻⁷ 유의 | 비유의 |

BM25 한국어 = **0.0000** (45개 중 44개가 어휘 교집합 0).

### 노출 2차원표 (MiniLM, hybrid α0.5)
| 색인 ＼ 반환 | full_text | minimal_text | minimal_no_code | R@10 |
|---|---:|---:|---:|---:|
| full_text | 9,729.9 | **1,810.9** | 1,720.8 | 0.6056 |
| minimal_text | 6,149.2 | 1,856.7 | 1,765.2 | 0.5775 |
| minimal_no_code | 6,277.1 | 1,764.3 | 1,674.2 | 0.5211 |

**운용점**: 색인 `full_text` + 반환 `minimal_text` → 노출 **−81.4%**, R@10 변화 **정확히 0.0**.

### 질의 노출 사다리 (hybrid α0.5)
| 등급 | 민감토큰 | R@10 | 증거등급 |
|---|---:|---:|---|
| L0 | 7.35 | 0.5775 | 기준 |
| L1 | 6.41 | 0.5775 | **A. 등가 입증** (TOST p_max 0.0063) |
| L2 | 5.63 | 0.5493 | B. 하락 미검출 (n≈1,102 필요) ← **운용 권고** |
| L3 | 0.00 | 0.5775 | **D. 자기참조 교란 → 사용 금지** |
| L4 | 0.00 | 0.4507 | C. 손실 징후 (−0.1268) |

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

③ 항상 마지막
   make_figures.py → experiment_stats.py → verify_claims.py
```

---

## 8. 알려진 함정

- **cp949 인코딩**: Windows 콘솔에서 유니코드(—, −, ≥) 출력 시 `UnicodeEncodeError`로 스크립트가 죽는다. `verify_claims.py`는 고쳤지만 다른 스크립트는 아직이다. 증상이 보이면 `PYTHONIOENCODING=utf-8 python ...`로 실행.
- **`np.argsort(-scores)` 함정**: 점수가 전부 0인 벡터를 정렬하면 코퍼스 배열 앞머리가 결과로 나온다. 이 때문에 BM25 한국어 R@10이 0.0222로 잘못 집계된 적이 있다. **랭킹은 반드시 `retrieval_core.rank_indices`를 쓰고, 무신호 질의는 검색 실패로 집계**한다.
- **`.gitignore` 방침**: `output/`은 이제 **기본 커밋 대상**이다(허용목록 → 부정목록으로 전환). 새 산출물이 조용히 빠지지 않는다.
- **낡은 v1 산출물**: `external_eval`, `external_label_audit`, `external_retriever`, `retriever_compare`는 코퍼스 v1 기준이며 논문이 인용하지 않는다. `meta.superseded_by`가 박혀 있으니 되살리지 말 것.
- **문서의 v1 수치는 의도적일 수 있다**: README 변경이력표, `docs/corpus_parsing_fixes.md`, `docs/statistics_n13_superseded.md`, `docs/case_analysis.md`(superseded 배너)는 v1을 **일부러** 참조한다. 일괄 치환 금지.

---

## 9. 팀 협업 현황

| 사람 | 담당 | 상태 |
|---|---|---|
| 팀장(jaepaly) | 통합·검증·논문 | 진행 중 |
| 이예찬 | TASK F(그림·통계), TASK G 슬라이스(0/1/2/8), bge-m3 샤드 | 완료·병합됨 |
| 장승우 | TASK D(한국어), TASK G 슬라이스(3~7/9), e5-base 샤드 | 완료·병합됨 |

새 작업을 팀원에게 분담할 때는 `README.md` §코퍼스 v2 채택 매뉴얼의 1인칭 절차(배정모델만 바꿔 재사용)와 `docs/RESULT_REPORT_TEMPLATE.md` 양식을 쓴다. 이전 라운드의 에이전트 프롬프트 전문은 `docs/RESEARCH_IMPROVEMENT_PLAN.md`에 있다. 샤드 제출물은 반드시 `validate_shard.py`로 검증한 뒤 병합한다(BM25 히트 벡터가 바이트 단위로 일치해야 하며, 이것이 상대 환경을 신뢰하지 않고도 동일 조건이었음을 보장한다).

---

## 10. 남은 과제 (우선순위)

1. ~~표제 스텁 보강~~ — **완료·반증**(§6). 코퍼스를 실제로 고쳐 측정했으나 성능 향상 없음. v3는 아티팩트로 보존, 채택 안 함. 음성 결과로 논문 한계 절에 사용 가능
2. **표본 확대 (TASK J, 분담 중)** — 스펙: `docs/TASK_J_SAMPLE_EXPANSION.md`. n=71 → 151 목표. 핵심 질문은 "bge-m3의 L2 손실 징후가 n=151에서도 유지되는가"(모델 차이 vs 검정력 부족). **L2 등가(δ=0.05) 입증은 이 코퍼스로 불가**(필요 n≈1,102, 상한 328)
3. ~~대칭 ablation·사다리의 다모델 확장~~ — **완료**(PAPER 4.8, `output/tier1_crossmodel.md`). ablation 방향은 일반화되나 최대 압력 유의성은 2/3, 운용 권고는 모델 의존적
4. **실제 기업 질의 확보** — 현장 대표성(현재 전부 역생성 합성)
5. ~~전문가 라벨 검수~~ — **범위 밖으로 확정**. 대신 PAPER 4.7의 라벨 강건성 분석으로 대체함(라벨 결함 질의를 모두 제거해도 결론 유지)
