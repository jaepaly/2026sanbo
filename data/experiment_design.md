# 정정 실험 설계서

검증일: 2026-06-25

## 1. 목적

본 실험은 외부 AI/검색 서비스에 기술정보를 전송하는 상황에서, 통제목록 후보검색에 필요한 정보량을 줄일 수 있는지 평가한다. 법적 판정이나 수출허가 여부 판단은 실험 범위가 아니다.

## 2. 핵심 정정

기존 A-scenario는 쿼리에 정답 통제번호가 포함되어 있었다. 이 경우 높은 Recall@k는 통제번호 문자열 매칭 결과일 가능성이 크므로 후보탐지 실험으로 사용할 수 없다. 정정 실험은 모든 쿼리에서 정답 코드와 코드 형태 토큰을 제거하고, 누출 검사를 통과한 쿼리만 사용한다.

## 3. 데이터

| 소스 | 기준 파일 | 정화 후 항목 수 | 공식 링크 |
|---|---|---:|---|
| Wassenaar Arrangement 2025 | `data/wassenaar_2025.pdf` | 585 | https://www.wassenaar.org/control-lists/ |
| India SCOMET 2024 | `data/india_scomet_2024_official.pdf` | 575 | https://content.dgft.gov.in/Website/UPDATED%20SCOMET%20List%202024%20as%20on%2002.09.2024.pdf |
| U.S. eCFR CCL | `data/corpus/ecfr_supp1.json` | 637 | https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-774/appendix-Supplement%20No.%201%20to%20Part%20774 |

품질 검증 산출물:

- `data/corpus/corpus_quality_report.json`
- `data/query_quality_report.json`

## 4. 쿼리 생성

`generate_queries.py`는 각 통제항목 설명문에서 통제번호 패턴을 제거한 뒤 설명형 쿼리를 만든다. 쿼리 생성 후 다음을 검사한다.

- 정답 코드 문자열 포함 여부
- 정답 코드의 `ECCN-` 제거 변형 포함 여부
- 점/하이픈을 공백으로 바꾼 변형 포함 여부
- 일반 통제번호 형태 토큰 포함 여부

하나라도 걸리면 해당 쿼리는 폐기한다.

현재 쿼리셋:

- 총 780개
- train/val/test = 78/78/624
- EN 390개, KO 390개
- 세 소스별 260개씩 균형화

## 5. 비교 조건

| 조건 | 설명 |
|---|---|
| `full_text` | 통제번호와 원문 설명 전체를 색인·반환하는 상한 기준선 |
| `minimal_text` | 통제번호와 첫 핵심 설명만 사용하는 정보최소화 조건 |
| `minimal_no_code` | 통제번호 없이 첫 핵심 설명만 사용하는 조건 |
| `route_only` | 통제체계와 업무흐름 힌트만 사용하는 극단적 저노출 조건 |

## 6. 평가 지표

- Recall@1/5/10/20
- MRR
- nDCG@10
- 평균 노출량@10: 상위 10개 후보에 대해 조건별 반환 문자열 길이 합산
- random baseline Recall@10
- paired permutation test: R@10 기준

## 7. 현재 결과 요약

| 조건 | R@10 | 평균 노출량@10 |
|---|---:|---:|
| `full_text` | 0.9968 | 4,834 |
| `minimal_text` | 0.9792 | 1,623 |
| `minimal_no_code` | 0.9808 | 1,592 |
| `route_only` | 0.0080 | 702 |
| random baseline | 0.0048 | - |

`minimal_text`는 `full_text` 대비 평균 노출량@10을 약 66.4% 줄이며, R@10은 1.76%p 낮다. 이 차이는 통계적으로 유의하므로 “성능 차이가 없다”고 주장하면 안 된다. 대신 “작은 성능 감소를 감수하고 큰 노출량 감소를 얻는다”고 표현한다.

## 8. 법제 라우팅 처리

이 저장소는 법제 라우팅 정확도를 보고하지 않는다. 기존 `law_type`은 공식 라벨이 아니라 휴리스틱 라벨이었기 때문이다.

대신 `experiment_legal_route.py`는 다음 업무흐름 힌트를 요약한다.

- 전략물자 후보 검토 및 YesTrade 자가·전문판정 안내
- 외국 공개 통제목록 참고자료 표시
- 국가핵심기술 가능 키워드가 있을 경우 2차 검토 플래그 표시

## 9. 남은 한계

1. 합성 쿼리이므로 실제 기업 질의 대표성 부족
2. 공개 PDF/HTML 파싱 결과의 수작업 표본 검수 필요
3. 노출량이 문자 수 기반 proxy
4. Dense retrieval, reranker, LLM 비교 미실시
5. 후보검색 성능과 법적 판정 정확도를 혼동하면 안 됨
