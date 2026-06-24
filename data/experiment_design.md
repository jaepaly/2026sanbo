# 전략물자 AI 사전 트리아지 실험 설계서

> **기반**: Notion 연구기획 (2026-06-23)  
> **코퍼스**: Wassenaar Arrangement 2025 + India SCOMET 2024 (공식 PDF)  
> **검증일**: 2026-06-24

---

## 1. 실험 목적

본 연구의 핵심 질문은 외부 AI에 전송되는 기술정보의 **가중 정보노출량(W)**과 **Top-k 재현율(R)** 간 상충관계를 정량화하는 것이다. 이를 위해 4가지 입력 조건별로 W와 R을 측정하고 Privacy–Utility Frontier를 실증한다.

---

## 2. 데이터셋

### 2.1 코퍼스 구성

| 소스 | 경로 | 구조 | 규모 | 다운로드 확인 |
|------|------|------|------|--------------|
| Wassenaar 2025 | data/wassenaar_2025.pdf | 계층형 코드 (1.A.1.a., 8.E.2.b.) | 1,243 페이지 | 1.3MB PDF 수신 코드 완료 |
| India SCOMET 2024 | data/india_scomet.pdf | ECCN 형식 (0A101, 3B001, 6A008.g.) | 227 페이지 | 1.8MB PDF 수신 코드 완료 |
| 합계 | | | 1,470 페이지 | |

### 2.2 전처리 기준

- pdfplumber 기반 텍스트 추출 (UTF-8)
- 연속 공백 제거 + 코드·문장 단위 분리
- 필터: 광고, “Not used since”, 해더/푸터 라인 삭제
- 항목별 최소 `code` + `description` 보존

---

## 3. 4가지 비교 조건 (실험 변수)

모든 조건에서 **동일한 쿼리셋(200건)**과 **동일한 검색기(BM25+cosine 하이브리드)**를 사용한다.

| 조건 | 이름 | 서버 외부 전송 필드 | 예상 전송량 순서 |
|------|------|-------------------|-----------------|
| A | 원문 (Raw) | 전문 + 수치 + 유사 코드 | A > B > C ≈ D |
| B | 최소설명 (Minimal) | 품명·용도 1문장 + 수치 포함 | |
| C | 범주형 (Category) | 대분류 코드만 (예: `3A`, `6B`) | |
| D | 로컬규칙분리 | 서버 전송은 전체 원문, 하지만 수치의 임계값 검증은 사용자 단말 로컬에서 진행 | 높음 | 수치 마스킹 차이 |
| E | 법제 라우팅 | 품목 특성 기반 자동 분기 (대외무역법 / 산업기술보호법) | - | 분기 정확도 |

---

## 4. 실험 프로토콜

### 4.1 데이터 split

- `train`: 140건 (쿼리 다양성 확보)
- `val`: 30건 (threshold 튜닝)
- `test`: 30건 (최종 F1)

### 4.2 검색기

- 임베딩: `sentence-transformers/all-MiniLM-L6-v2` (다국어 대체: `paraphrase-multilingual-MiniLM-L12-v2`)
- BM25 정확도 > cosine 유사도 α = 0.5

### 4.3 평가 메트릭

| 메트릭 | 계산식 |
|--------|--------|
| Top-k 재현율 (R@k) | 정답 code ≥ top-k 중 포함 비율 (k = 5, 10, 20, 50) |
| 평균 역순위 (MRR) | 1 / 정답 code 등수 |
| 가중 노출량 (W) | 조건 A, B에서 전송된 모든 항목에 대해 민감도·관련성 가중 합산 |
| Privacy–Utility Frontier | (W, R@10) 좌표를 4개 조건이 점유하는 경계면 도출 |

---

## 5. 분석 흐름

1. **Baseline 검증**: 무작위 Baseline R@10 > 0.085 (230/1,174)
2. **4조건 비교**: R@k와 W를 테이블 + 그래프
3. **Sensitivity**: α를 [0.0, 0.3, 0.5, 0.7, 1.0]으로 sweep
4. **Frontier**: R@10 – W 곡선을 조건별로 점유 검정
5. **법제 라우팅 설계**: 대외무역법 / 산업기술보호법 분기 기준 문서화

---

## 6. 보고서 형식

- `report.md`: 테이블·그래프·경고·한계 포함
- `fig1_condition_compare.png`: 조건별 R@k bar
- `fig2_exposure_recall_tradeoff.png`: W – R scatter
- `fig3_sensitivity.png`: alpha sweep
- `fig4_frontier.png`: frontier curve + AUC

---

## 7. 학습/실행 주의사항 (read me)

- 한국어 쿼리는 **영어 번역 후 검색** → 결과의 한국어 정확도 낮을 수 있음
- Wassenaar는 군항목 포함 → 민군 혼합 분석 가능
- `wassenaar.json`, `india_scomet.json` 용량 큼. 주의할 것
