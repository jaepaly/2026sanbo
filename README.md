# 전략물자 AI 사전 트리아지 실험

이 저장소는 외부 AI/검색 서비스에 기술정보를 전송할 때, 반환·처리하는 정보량을 줄이면서 공개 통제목록 후보검색 성능을 어느 정도 유지할 수 있는지 검증하기 위한 연구용 실험 저장소입니다.

중요한 정정:

- 이 실험은 전략물자 해당/비해당을 법적으로 판정하지 않습니다.
- 이 실험은 수출허가, 자가판정, 전문판정을 대체하지 않습니다.
- 이전 버전의 “정답 코드가 쿼리에 포함된 A-scenario”는 후보탐지 실험으로 부적절하여 제거했습니다.
- 법제 라우팅 “정확도” 수치는 공식 라벨이 아니므로 제거했습니다.

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
- [국가핵심기술 제도](https://kaits.or.kr/web/content.do?menu_cd=000067)

## 재현 방법

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python build_corpus_clean.py
python generate_queries.py
python run_experiments.py
python experiment_legal_route.py
```

## 한계

- 쿼리는 공개 통제목록 설명문에서 파생한 합성 쿼리입니다. 실제 기업·관세사 질의 대표성은 아직 부족합니다.
- 코퍼스 파싱은 정규식 기반이므로 수작업 표본 검수가 필요합니다.
- 현재 실험은 BM25 기준선입니다. Dense retrieval, reranker, LLM 비교는 기준선이 안정화된 뒤 별도 실험으로 추가해야 합니다.
- 노출량은 문자 수 기반 proxy입니다. 실제 영업비밀·기술정보 민감도와 동일하지 않습니다.

## 제출 논문에서 안전한 주장

사용 가능:

> 정답 통제번호를 쿼리에 포함하지 않는 합성 설명형 쿼리에서, 공개 통제목록 후보검색 기준 `minimal_text` 조건은 `full_text` 대비 평균 반환 정보량을 약 66.4% 줄이면서 R@10 0.9792를 유지했다.

사용 금지:

- “AI가 전략물자 여부를 판정한다”
- “법제 라우팅 정확도 n%”
- “전문판정/자가판정을 대체할 수 있다”
- “실제 기업 질의에서 검증됐다”
