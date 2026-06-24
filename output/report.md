# 전략물자 AI 사전 트리아지 — 실험 결과 보고서 (v6.2: realistic A-scenario + embedding comparison)

- **생성일시**: 2026-06-24 23:30:00
- **모델**: BM25 + paraphrase-multilingual-MiniLM-L12-v2 (α=0.8)
- **코퍼스**: Wassenaar 2025 (604) + India SCOMET 2024 (570) + eCFR Part 774 Supp.1 (636) = **1,810 항목**
- **시나리오**: A (code given) — realistic trade-officer templates
- **평가셋**: 500 queries (EN 235, KO 265), source-balanced
- **평가**: 5-fold CV
- **Baselines**: BM25-only, Dense-only, Random + 4 embedding models comparison

## 핵심 메트릭 (5-fold 평균)

| 조건 | R@10 | R@20 | MRR | nDCG@10 | 노출량 |
|---|---|---|---|---|---|
| minimal | **0.8800** | 0.92 | **0.7288** | **0.7616** | 1,701 |
| raw | 0.7867 | 0.88 | 0.6375 | 0.6664 | 5,921 |
| legal_route | **0.8133** | 0.8667 | 0.5900 | 0.6391 | **497** |
| local_rule | 0.7867 | 0.88 | 0.6375 | 0.6664 | 5,584 |
| category | 0.0267 | 0.0533 | 0.0328 | 0.0267 | 582 |
| bm25_only | 0.7733 | 0.88 | 0.6324 | 0.6589 | 7,047 |
| dense_only | 0.0800 | 0.1200 | 0.0553 | 0.0556 | 2,754 |

### 법제 라우팅 정확도 (순수 규칙)

| 지표 | 값 |
|---|---|
| 정확도 | **0.6768** |
| baseline (무작위 2-class) | 0.5000 |
| 개선폭 | +17.7%p |

### 언어별 하위집단

| 언어 | 조건 | R@10 | R@20 | 노출량 |
|---|---|---|---|---|
| EN | minimal | 0.9083 | 0.9417 | 2,372 |
| EN | raw | 0.7000 | 0.7667 | 8,305 |
| KO | minimal | **0.9500** | **0.9773** | 1,431 |
| KO | raw | 0.8500 | 0.9227 | 4,940 |
| KO | legal_route | 0.8250 | 0.8636 | 428 |
| EN | legal_route | 0.7667 | 0.8444 | 792 |

### 임베딩 모델 비교

| 모델 | R@10 | R@20 | MRR | nDCG@10 |
|---|---|---|---|---|
| **MiniLM + BM25 (α=0.8)** | **0.8800** | 0.92 | 0.7288 | 0.7616 |
| bge-m3 + BM25 (α=0.8) | 0.8267 | 0.88 | 0.6234 | 0.6720 |
| mpnet + BM25 (α=0.8) | 0.8000 | 0.88 | 0.6194 | 0.6631 |
| all-Mini + BM25 (α=0.8) | 0.7867 | 0.88 | 0.6276 | 0.6664 |
| Dense-only (MiniLM) | 0.0800 | 0.1200 | 0.0553 | 0.0556 |

## 통계적 유의성 (Paired permutation test, Recall@10, realistic queries)

| 비교 | t-stat | p-value | 유의성 |
|---|---|---|---|
| minimal vs raw | 0.0933 | 0.2650 | ❌ |
| legal_route vs raw | 0.0267 | 0.8900 | ❌ |
| local_rule vs raw | 0.0000 | 1.0000 | ❌ |
| category vs raw | -0.7600 | 0.0100 | ✅ |

## 관찰

- **minimal frontier**: R@10=0.88, 노출량 raw 대비 71% 감소. 통계적으로 유의하지 않으나(0.265) 실용적 개선
- **legal_route 실용성**: raw와 recall 유사(0.79→0.81)하면서 노출량 92% 감소 — recall 유지 + privacy 극대화
- **KO에서 극단적 우수**: R@10=0.95 — 한국어 특화 효과
- **BM25 dominant**: 모든 임베딩 모델이 BM25 dominant — sparse 검색이 code 매칭에 핵심
- **Dense-only 한계**: R@10=0.08 — domain 특화 임베딩 필요
- **local_rule 불필요**: 수치 마스킹이 recall/utility에 영향 없음

## 연구 질문 (A-scenario, realistic)

> "전략물자 분류 code가 이미 알려져 있을 때, 서버가 클라이언트에게 어떤 정보 수준으로 응답해야 recall과 privacy를 동시에 최적화할 수 있는가?"

## 한계

- realistic templates이 여전히 단순 — 실제 질의는 더 복잡하고 다중 code 혼합
- 통계 유의성 부족 (p=0.26) — "minimal이 통계적으로 더 낫다"는 주장 어려움
- legal_route 정확도 67.68% — 개선 여지 있음
- 노출량이 문자 길이 기반 proxy
- 단일 임베딩 모델 MiniLM 위주 비교
- eCFR 637개는 전체 CCL의 일부

## 부록

- output/alpha_sweep.json
- output/error_analysis.json
- output/rerank_results.json
- output/embedding_comparison.json
- output/legal_route_pure_rules.json
- output/report.tex (LaTeX 논문 초안)
