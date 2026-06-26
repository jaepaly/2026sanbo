# TASK D (D1) — 한국어 cross-lingual: KO-원문 vs KO-번역 vs EN

- 질의셋: `external_consultation_queries_validated.json` (검증 라벨, exact full eCFR code 매칭)
- 번역: 사람 수동 번역 (외부 API 미사용) — `crosslingual_translations.json`
- Dense: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (로컬 실행)
- 표본: 한국어 5개 / 영어 8개
- **주의: 한국어 표본 5개로 매우 작음. 아래는 '경향'이며 통계적 결론 아님. 표본 확대 필요.**
- 라벨: 코퍼스 텍스트 근거 카테고리 라벨. 법적 판정 아님, 전문가 검증 아님.

## R@10 by track and retriever

| track | BM25 (α=1.0) | Hybrid (α=0.5) | Dense (α=0.0) |
|---|---:|---:|---:|
| KO-original | 0.0000 | 0.2000 | 0.2000 |
| KO-translated | 0.2000 | 0.2000 | 0.2000 |
| EN-original | 0.0000 | 0.2500 | 0.1250 |

## 해석 (경향)

- **KO-원문 + BM25**: 코퍼스가 100% 영어라 한국어 어휘 매칭이 구조적으로 불가능하다.
- **KO-번역 + BM25**: 한국어를 영어로 번역하면 BM25가 다시 어휘 매칭을 시도할 수 있다.
  번역이 BM25 경로에서 한국어 0점을 어느 정도 회복시키는지가 핵심 관찰점.
- **다국어 Dense/Hybrid**: 번역 없이도 한국어 질의와 영어 코퍼스를 같은 의미 공간에
  임베딩하여 cross-lingual 매칭을 시도한다.
- **EN-원문**: 영어 질의의 기준선. KO-번역이 EN-원문에 얼마나 근접하는지 비교.

## 한계

- 한국어 평가 표본이 5개뿐이라 1개 적중이 R@10을 0.20씩 움직인다. 절대값보다
  track 간 상대 경향으로만 해석해야 하며, 표본 확대가 후속 과제다.
- 번역 품질에 결과가 의존한다(사람 1인 번역). 다수 번역자/역번역 검증이 필요하다.
- 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 법적·전문가 판정이 아니다.
