# 검증 질의셋 평가 (TASK B/C/E)

- 질의셋: `external_consultation_queries_validated.json` (평가 13개 / 제외 17개)
- 매칭: exact full eCFR code (충돌 없음) / 노출 minimal_text / Dense sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
- 라벨 성격: 코퍼스 텍스트 근거 카테고리 라벨. 법적 판정 아님, 전문가 검증 아님.

| retriever | R@10 | 영어 R@10 | 한국어 R@10 |
|---|---:|---:|---:|
| BM25 (1.0) | 0.0000 | 0.0000 | 0.0000 |
| hybrid (0.7) | 0.1538 | 0.1250 | 0.2000 |
| hybrid (0.5) | 0.2308 | 0.2500 | 0.2000 |
| hybrid (0.3) | 0.2308 | 0.2500 | 0.2000 |
| Dense (0.0) | 0.1538 | 0.1250 | 0.2000 |

- 평가 표본: 영어 8개 / 한국어 5개 (소표본 주의).

## 해석
- 충돌 없는 정확 매칭 + 코퍼스 텍스트 근거 라벨에서의 retriever별 성능.
- BM25는 한국어에서 어휘 매칭 불가(코퍼스 100% 영어), 다국어 dense/hybrid의 cross-lingual 효과를 확인.
- 표본이 13개(영/한 분할)로 작으므로 절대값보다 retriever 간 상대 경향으로 해석.
