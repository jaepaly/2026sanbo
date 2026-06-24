# 전략물자 AI 사전 트리아지

**리포지토리**: https://github.com/jaepaly/2026sanbo  
**코퍼스**: Wassenaar Arrangement 2025 (604) + India SCOMET 2024 (570) + eCFR Part 774 Supp.1 (636) = **1,810 항목**

---

## 연구 질문 (A-scenario)

전략물자 분류 code가 이미 알려져 있을 때, 서버가 클라이언트에게 **어떤 정보 수준으로 응답해야 recall과 privacy를 동시에 최적화할 수 있는가?**

- code는 클라이언트가 이미 알고 있음 (e.g., 관세사가 ECCN 코드를 특정한 상태)
- 서버는 code에 대한 추가 설명을 raw(원문 전체) / minimal(첫 문장) / legal_route(법제 라벨) 등으로 응답
- 각 응답 수준별 **Recall@10**과 **Weighted Exposure(문자 길이 기반 privacy proxy)**를 측정

---

## 최종 결과 (v6.2: realistic A-scenario + embedding comparison, 5-fold, ALPHA=0.8)

| 조건 | R@10 | R@20 | MRR | nDCG@10 | 노출량 | 감소율 |
|---|---|---|---|---|---|---|
| **minimal** | **0.8800** | 0.92 | **0.7288** | **0.7616** | **1,701** | **71%** ↓ |
| raw | 0.7867 | 0.88 | 0.6375 | 0.6664 | 5,921 | — |
| **legal_route** | **0.8133** | 0.8667 | 0.5900 | 0.6391 | **497** | **92%** ↓ |
| local_rule | 0.7867 | 0.88 | 0.6375 | 0.6664 | 5,584 | 6% ↓ |
| category | 0.0267 | 0.0533 | 0.0328 | 0.0267 | 582 | 90% ↓ |
| bm25_only | 0.7733 | 0.88 | 0.6324 | 0.6589 | 7,047 | — |
| dense_only | 0.0800 | 0.1200 | 0.0553 | 0.0556 | 2,754 | — |

### 법제 라우팅 정확도 (순수 규칙, law_type 레이블 제외)

| 지표 | 값 |
|---|---|
| ECCN prefix + keyword 정확도 | **0.6768** |
| 무작위 baseline (2-class) | 0.5000 |
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

### 임베딩 모델 비교 (A-scenario)

| 모델 | R@10 | R@20 | MRR | nDCG@10 |
|---|---|---|---|---|
| **MiniLM + BM25 (α=0.8)** | **0.8800** | 0.92 | 0.7288 | 0.7616 |
| **bge-m3 + BM25 (α=0.8)** | 0.8267 | 0.88 | 0.6234 | 0.6720 |
| mpnet + BM25 (α=0.8) | 0.8000 | 0.88 | 0.6194 | 0.6631 |
| all-Mini + BM25 (α=0.8) | 0.7867 | 0.88 | 0.6276 | 0.6664 |
| Dense-only (MiniLM) | 0.0800 | 0.1200 | 0.0553 | 0.0556 |

### 통계적 유의성 (Paired permutation test, Recall@10, realistic queries)

| 비교 | p-value | 유의성 |
|---|---|---|
| minimal vs raw | 0.2650 | ❌ 통계적으로 유의하지 않음 |
| legal_route vs raw | 0.8900 | ❌ |
| local_rule vs raw | 1.0000 | ❌ |
| category vs raw | 0.0100 | ✅ |

---

## 핵심 발견

1. **practical privacy-utility optimization**: minimal이 raw와 recall 차이가 작으면서(0.79→0.88) 노출량 71% 감소 — 현장 적용 가능
2. **legal_route의 압도적 privacy 효율**: raw와 recall 동일(0.79→0.81)하면서 노출량 92% 감소 — 법제 분류 정확도만 보장되면 이상적
3. **한국어 특화**: KO minimal R@10=0.95
4. **BM25 dominant**: 임베딩 모델 바꿔도 큰 차이 없음 — sparse 검색이 code 매칭에 압도적
5. **Dense-only 한계**: R@10=0.08 — domain 특화 필요

---

## 솔직한 한계

1. **Synthetic→Realistic transition**: templates가 여전히 간단함. 실제 무역 담당자의 질의는 더 복잡함
2. **통계 유의성 부족**: realistic queries에서 p=0.26 — "minimal이 통계적으로 더 낫다"는 주장 어려움
3. **법제 라우팅 정확도 67.68%**: 개선 여지 있음 (LLM reranking, 국가별 매핑 테이블)
4. **단일 임베딩 모델**: bge-m3까지 비교했으나 여전히 소수
5. **노출량 Proxy**: 문자 길이 기반. 실제 정보 누출과 차이 있음
6. **eCFR 637개**: 전체 CCL 대비 일부
7. **A-scenario 가정**: code가 이미 알려진 상태

---

## 실행 방법

```bash
cd C:/Users/dor12/ai-agent-privacy-demo
uv sync
uv run python build_corpus_v2.py
uv run python generate_queries.py
uv run python run_experiments_v3.py
```

---

## 라이선스

MIT
