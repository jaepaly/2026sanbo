# TASK E (외부셋) — BM25 vs Dense vs Hybrid

- 코퍼스 1797 / 외부 상담셋 30개 / 노출 minimal_text
- Dense: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (다국어, 영어 코퍼스 + 한국어 질의 cross-lingual)
- 기준: 연구자 예비 `candidate_labels`(노이즈 있음, 13/30 코드충돌). 절대값보다 BM25 대비 변화에 주목.

| retriever | 전체 R@10 | 영어 R@10 | 한국어 R@10 |
|---|---:|---:|---:|
| BM25 (1.0) | 0.0000 | 0.0000 | 0.0000 |
| hybrid (0.7) | 0.0667 | 0.0714 | 0.0625 |
| hybrid (0.5) | 0.1000 | 0.1429 | 0.0625 |
| hybrid (0.3) | 0.1000 | 0.1429 | 0.0625 |
| Dense (0.0) | 0.0667 | 0.0714 | 0.0625 |

## 해석

- BM25(α=1.0)는 한국어 질의에서 어휘 매칭이 불가능하다(코퍼스 100% 영어).
- 다국어 Dense(α=0.0)가 한국어 R@10을 BM25 대비 회복시키는지가 핵심 지표.
- candidate_labels 노이즈 때문에 절대 R@10은 낮을 수 있으나, BM25→Dense 상대 변화는
  cross-lingual 검색 필요성의 정량 근거가 된다.
