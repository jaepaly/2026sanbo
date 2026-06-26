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
```

## 한계

- 합성 쿼리는 각 코퍼스 항목 **자기 본문**에서 코드만 제거해 만든 것이라 정답 문서와 near-duplicate입니다(평균 Jaccard 0.485). 따라서 합성 R@10 0.9792는 자기참조 재검색 성능에 가깝고, 후보 발견 능력의 절대 지표로 직접 일반화할 수 없습니다. `experiment_paraphrase_gap.py`로 검증: 정답 문서와 공유하는 변별(고-IDF) 토큰 5개를 제거하면 minimal_text R@10이 0.9792→0.7596, 10개에서 0.4407로 떨어집니다(`output/paraphrase_gap.md`).
- 외부 모사 질의셋(`data/external_consultation_queries.json`) 30개의 `candidate_labels`는 연구자 예비 추정값이며 검증된 정답이 아닙니다. 30개 중 13개는 코드 정규화 충돌을 가집니다. 따라서 R@10=0은 "BM25 현장 성능=0"이 아니라 "불확실한 후보 라벨 기준 비수렴"으로 읽어야 합니다.
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
