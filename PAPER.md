# 논문 초안 메모 — 전략물자 AI 사전 트리아지

## 권장 제목

기술정보 최소노출과 전략물자 후보검색 성능의 상충관계: 공개 통제목록 기반 설명형 쿼리 실험

## 초록 초안

외부 인공지능 또는 검색 서비스를 활용해 전략물자 통제목록 후보를 탐색할 때, 기업은 기술사양과 제품 설명을 외부 시스템에 전송해야 하는 부담을 가진다. 본 연구는 법적 판정이 아닌 사전 후보검색 단계에서, 반환·처리되는 통제목록 정보량을 줄이면서 후보검색 성능을 얼마나 유지할 수 있는지 실험적으로 분석한다. Wassenaar Arrangement 2025, India SCOMET 2024, U.S. eCFR Commerce Control List의 공개 통제목록을 정화하여 1,797개 항목의 코퍼스를 구축하고, 정답 통제번호가 포함되지 않는 설명형 합성 쿼리 780개를 생성하였다. BM25 기준선 실험 결과, `minimal_text` 조건은 `full_text` 대비 평균 노출량@10을 약 66.4% 감소시키면서 Recall@10 0.9792를 유지했다. 다만 쿼리는 공개 목록 설명문에서 파생한 합성 데이터이므로 실제 기업 질의 일반화에는 추가 검증이 필요하다. 본 연구는 전략물자 판정 자동화가 아니라, YesTrade 자가·전문판정 전 단계에서 활용 가능한 보수적 후보검색 및 정보최소화 설계 원칙을 제시한다.

## 연구질문

1. 정답 통제번호를 쿼리에 포함하지 않는 설명형 쿼리에서도 공개 통제목록 후보검색이 가능한가?
2. 반환 정보량을 `full_text`에서 `minimal_text`로 줄이면 Recall@k와 평균 노출량은 어떻게 변하는가?
3. 법제·업무흐름 힌트만 제공하는 `route_only` 조건은 후보검색에 충분한가?
4. 검색 결과는 어떤 표현 정책을 따라야 법적 판정 오해를 줄일 수 있는가?

## 실험 설계

### 코퍼스

| 소스 | 항목 수 | 성격 |
|---|---:|---|
| Wassenaar Arrangement 2025 | 585 | 국제 이중용도·군용물자 통제목록 |
| India SCOMET 2024 | 575 | 인도 SCOMET 공개 통제목록 |
| U.S. eCFR CCL | 637 | 미국 EAR Commerce Control List |

### 비교 조건

| 조건 | 색인·반환 정보 | 목적 |
|---|---|---|
| `full_text` | 통제번호 + 원문 설명 전체 | 상한 기준선 |
| `minimal_text` | 통제번호 + 첫 핵심 설명 | 정보 최소화 후보 |
| `minimal_no_code` | 첫 핵심 설명, 통제번호 제외 | 코드 노출까지 줄인 조건 |
| `route_only` | 통제체계·업무흐름 힌트 | 극단적 저노출 음성 대조군 |

### 주요 결과

| 조건 | R@10 | 평균 노출량@10 |
|---|---:|---:|
| `full_text` | 0.9968 | 4,834 |
| `minimal_text` | 0.9792 | 1,623 |
| `minimal_no_code` | 0.9808 | 1,592 |
| `route_only` | 0.0080 | 702 |

## 해석

`minimal_text`와 `minimal_no_code`는 `full_text`보다 R@10이 낮지만, 감소 폭은 약 1.6~1.8%p 수준이다. 반면 평균 노출량@10은 약 66~67% 감소한다. 따라서 사전 트리아지 단계에서는 원문 전체를 반환하기보다 핵심 설명 중심 후보목록을 먼저 제공하고, 사용자가 공식 판정 절차로 이동하도록 설계하는 편이 안전하다.

`route_only`는 성능이 낮다. 이는 법제 안내만으로는 기술적 후보검색을 대체할 수 없음을 보여준다. 따라서 법제 라우팅은 검색 대체물이 아니라 검색 결과에 붙는 보수적 안내 레이어로 다루어야 한다.

## 절대 쓰면 안 되는 주장

- AI가 전략물자 해당/비해당을 판정한다.
- 본 시스템이 YesTrade 자가판정 또는 전문판정을 대체한다.
- 법제 라우팅 정확도가 검증되었다.
- 실제 기업/관세사 질의에서 일반화가 확인되었다.
- 국가핵심기술 해당 여부를 자동 판단한다.

## 검증된 참고문헌·근거 링크

- [Wassenaar Arrangement Control Lists](https://www.wassenaar.org/control-lists/)
- [Wassenaar Arrangement 2025 PDF](https://www.wassenaar.org/app/uploads/2025/12/List-of-Dual-Use-Goods-and-Technologies-and-ML-2025.pdf)
- [DGFT Updated SCOMET List 2024 PDF](https://content.dgft.gov.in/Website/UPDATED%20SCOMET%20List%202024%20as%20on%2002.09.2024.pdf)
- [eCFR 15 CFR Part 774 Supplement No. 1](https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-774/appendix-Supplement%20No.%201%20to%20Part%20774)
- [BIS Interactive Commerce Control List](https://www.bis.gov/regulations/ear/interactive-commerce-control-list)
- [YesTrade 제도개요](https://www.yestrade.go.kr/system-guidance)
- [YesTrade 온라인 자가판정 한계](https://www.yestrade.go.kr/judgements/self/intro)
- [전략물자수출입고시](https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000270104&chrClsCd=010201)
- [국가핵심기술 제도](https://kaits.or.kr/web/content.do?menu_cd=000067)
- [Ryu, Won & Kim, Intelligent Decision Support System for Nuclear Export Control: A BERT-Based Approach](https://www.tandfonline.com/doi/full/10.1080/00295450.2025.2556617)
- [Nelson, Improving Strategic Trade Detection and Classification Through Machine Learning](https://mag.wcoomd.org/magazine/wco-news-94/strategic-trade-detection-machine-learning/)

## 다음 보강 과제

1. 실제 기업 제품설명·카탈로그·특허 초록 기반 외부 검증셋 구축
2. 통제목록 파싱 결과 표본 100개 수작업 검수
3. Dense retrieval 및 reranker 추가 실험
4. 전문가 2인 이상 후보 적합성 평가
5. 노출량 proxy를 문자 수에서 민감도 가중치 기반으로 확장
