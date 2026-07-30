# 자료 출처 · 권리 · 재배포 판단 (data/SOURCES.md)

이 문서는 `data/` 아래 제3자 자료의 출처, 권리자, 이용 근거, **저장소 재배포 가능성**을
정리한다. 기계가 읽는 같은 내용은 `fetch_sources.py`의 `SOURCES` 표에 있고,
`python fetch_sources.py verify` 로 해시 일치를 확인할 수 있다.

- 접근·확인 일자: **2026-07-30**
- 확인 도구: `python fetch_sources.py verify` / `check-remote`
- 생성 보고서: `output/source_manifest.json` (env_meta, seed 포함)

> **이 문서는 법률 자문이 아니다.** "확인 필요"로 남긴 항목은 단정하지 않았다.
> 각 항목에 확인 경로를 함께 적었다.

---

## 1. 요약표

| # | 파일 | 바이트 | 권리자 | 이용 근거 | 재배포 | 저장소 제거 대상 | 코퍼스 기여 | 자동 재취득 |
|---|---|---:|---|---|---|---|---:|---|
| 1 | `data/wassenaar_2025.pdf` | 1,366,353 | Wassenaar Arrangement Secretariat | 확인 필요 | 불가 | **예** | 585건 | 가능 (해시 일치 확인) |
| 2 | `data/india_scomet_2024_official.pdf` | 3,812,663 | DGFT, Government of India | 확인 필요 | 불가 | **예** | 575건 | 가능 (해시 일치 확인) |
| 3 | `data/corpus/ecfr_supp1.json` | 175,321 | U.S. Government (BIS/GPO) | 17 U.S.C. §105 (퍼블릭 도메인) | 가능 | 아니오 | 637건 | 가능 (`fetch_ecfr.py`) |
| 4 | `data/law_korea.html` | 77,374 | 국가법령정보센터(법제처) / 고시 본문은 산업통상부 | 고시 본문은 저작권법 제7조로 보호 제외, **페이지 HTML은 제7조 대상 아님** | 불가 | **예** | 0건 | 불가 (JS 렌더링) |
| 5 | `data/yestrade_post.html` | 21,700 | MINISTRY OF TRADE, INDUSTRY (YesTrade) | 확인 필요 (footer에 All Rights Reserved 명시) | 불가 | **예** | 0건 | 불가 (URL 미확인) |
| 6 | `data/wassenaar_2025.zip` | 59,256 | — (404 오류 페이지) | 해당 없음 | 불가 | **예** | 0건 | 해당 없음 (삭제만) |

`data/corpus/combined.json`(1,400,141B)은 위 1·2·3에서 파생된 **2차 산출물**이며,
Wassenaar 585건 254,332자 + SCOMET 575건 195,452자의 본문을 그대로 담고 있다.
따라서 원본 PDF를 지워도 combined.json이 남아 있으면 재배포 문제는 해소되지 않는다
(→ §4 참조).

---

## 2. 항목별 상세

### 2.1 `data/wassenaar_2025.pdf` — Wassenaar 이중용도품목 목록 2025 Corr.

| 항목 | 값 |
|---|---|
| URL | `https://www.wassenaar.org/app/uploads/2026/01/List-of-Dual-Use-Goods-and-Technologies-and-ML-2025-Corr.pdf` |
| SHA-256 | `1a92a954dc51211f6f39a8780525248d0338bc116a23f80164e2aa6541be43fb` |
| 바이트 | 1,366,353 |
| 판본 | Volume II, "2025 Corr.", 243쪽, PDF CreationDate 2026-01-15 |
| 접근일 | 2026-07-30 (원격 SHA-256이 로컬과 **정확히 일치**함을 확인) |
| 권리자 | Wassenaar Arrangement Secretariat |

**이용 근거 — 확인 필요.** Wassenaar Arrangement는 국제 협의체이며, 사무국 발간
"PUBLIC DOCUMENTS"는 공개 배포를 전제로 하지만 저장소 재배포를 허용하는 명시적
라이선스 문구를 확인하지 못했다. 한국 저작권법 제7조(법령·고시 등)는 **대한민국의**
법령·고시를 대상으로 하므로 국제기구 발간물에는 적용되지 않는다. 미국 17 U.S.C. §105도
적용되지 않는다.

- 확인 경로: `https://www.wassenaar.org/` Disclaimer 페이지, 또는 사무국(Vienna) 문의.

**재배포 판단: 불가 → 저장소에서 제거하고 `fetch_sources.py`로 재취득한다.**
원격 해시가 일치하므로 제거해도 재현성 손실이 없다.

> **URL 오기 발견.** `build_corpus_clean.py`의
> `SOURCE_META["wassenaar_2025"]["source_url"]`은
> `.../app/uploads/2025/12/List-of-Dual-Use-Goods-and-Technologies-and-ML-2025.pdf`로
> 적혀 있는데, 이 URL이 실제로 주는 파일은
> **정정 전 "2025" 판**(242쪽, 1,361,602B, SHA-256 `2a6b2af7...`, CreationDate 2025-12-05)이라
> 로컬 파일과 다른 판본이다. 코퍼스를 실제로 만든 원본은 위 표의 `/2026/01/...-Corr.pdf`다.
> `build_corpus_clean.py`는 이 작업의 소유 파일이 아니므로 수정하지 않았다.
> **코퍼스 담당자가 SOURCE_META의 URL을 정정해야 한다.**

### 2.2 `data/india_scomet_2024_official.pdf` — 인도 SCOMET 목록 2024

| 항목 | 값 |
|---|---|
| URL | `https://content.dgft.gov.in/Website/UPDATED%20SCOMET%20List%202024%20as%20on%2002.09.2024.pdf` |
| SHA-256 | `4e26322b3f05bea962b7451e66db967dc1ad8ed8816254e663dde80cc410681f` |
| 바이트 | 3,812,663 |
| 접근일 | 2026-07-30 (원격 SHA-256이 로컬과 **정확히 일치**) |
| 권리자 | Directorate General of Foreign Trade (DGFT), Government of India |

**이용 근거 — 확인 필요.** 인도 정부 저작물에는 Government Open Data License – India
(GODL-India) 또는 개별 사이트 이용약관이 적용될 수 있으나, 이 PDF에 적용되는 조건을
확인하지 못했다. 한국 저작권법 제7조도, 미국 17 U.S.C. §105도 적용되지 않는다.

- 확인 경로: `https://www.dgft.gov.in/` Terms & Conditions / Copyright Policy 페이지.

**재배포 판단: 불가 → 제거 후 재취득.** 원격 해시가 일치하므로 재현성 손실 없음.

### 2.3 `data/corpus/ecfr_supp1.json` — 미국 EAR CCL (15 CFR Part 774 Supp. No. 1)

| 항목 | 값 |
|---|---|
| 정본 URL | `https://www.ecfr.gov/current/title-15/subtitle-B/chapter-VII/subchapter-C/part-774/appendix-Supplement%20No.%201%20to%20Part%20774` |
| API URL | `https://www.ecfr.gov/api/versioner/v1/full/{date}/title-15.xml?chapter=VII&subchapter=C&part=774&appendix=Supplement+No.+1+to+Part+774` |
| 현재 파일 SHA-256 | `e3df05c369a9431a5b9755f75e1528a9b65cc67254f50d5992f5c182560f29f9` |
| 취득·파싱 스크립트 | `fetch_ecfr.py` (이번에 신설) |

**이용 근거: 17 U.S.C. §105.** 미국 연방정부 저작물은 저작권 보호 대상이 아니다(퍼블릭 도메인).
**재배포 판단: 가능. 제거 대상 아님.**

> **불일치 발견 (조용히 고치지 않고 기록).**
> `data/corpus/corpus_quality_report.json`은 이 파일의 SHA-256을
> `c15d80cd131e7f0e0ee23fc8af3f729e5683b17b908c3bd927a7392aa7c43f04`로 기록하고 있으나,
> 작업 트리와 HEAD 커밋의 실제 해시는 모두 `e3df05c369a9...`다.
> 즉 품질보고서가 입력 파일에 대해 **stale**하다. 코퍼스 35%의 입력 무결성 기록이
> 어긋나 있으므로 코퍼스 담당자 확인이 필요하다. 이 작업에서는 두 파일 모두
> 소유 파일이 아니므로 수정하지 않았다.

### 2.4 `data/law_korea.html` — 전략물자수출입고시 페이지 스크레이프

| 항목 | 값 |
|---|---|
| 추정 URL | `https://www.law.go.kr/행정규칙/전략물자수출입고시` (**정확한 스크레이프 URL 확인 필요**) |
| SHA-256 | `ffbaac38e6f1d77ea60967b29c1740e945ed4613151c14b4d9d6b1e95418e717` |
| 바이트 | 77,374 |
| 문서 메타 | 산업통상부고시 제2025-37호, 시행 2025-12-31 |

**실측 내용.** 파일명(`law_korea`)과 달리 실제 내용은 **전략물자수출입고시** 페이지의
JavaScript 셸이다. 텍스트를 추출하면 조문이 **0건**이다("전략물자" 3회, "수출허가" 0회,
"판정" 0회). 즉 이 파일에는 고시 본문이 들어 있지 않다.
저장소 코드 어디에서도 참조하지 않는다(grep 0건).

**이용 근거.** 고시 **본문**은 저작권법 제7조 제2호(고시·공고·훈령)로 보호 대상에서
제외된다. 그러나 이 파일에 들어 있는 것은 본문이 아니라 **국가법령정보센터 페이지의
HTML·스크립트·레이아웃**이며, 제7조는 여기에 적용되지 않는다.

**재배포 판단: 불가 → 제거.** 고시 본문이 필요하면 페이지 HTML을 재배포하지 말고
`admRulSeq` 기반 정본 URL을 인용하라. JS 렌더링이라 URL 취득만으로 동일 바이트 재현이
불가능하므로 `fetch_sources.py`는 자동 재취득을 지원하지 않는다(그 사실을 명시적으로 보고한다).

- 확인 필요: 원 스크레이프 URL(`admRulSeq` 파라미터 값). 파일 내부에 canonical/og:url이 없다.

### 2.5 `data/yestrade_post.html` — YesTrade 동향자료 게시글

| 항목 | 값 |
|---|---|
| 추정 URL | `https://www.yestrade.go.kr/` 하위 동향자료 상세 (**정확한 게시글 URL 확인 필요**) |
| SHA-256 | `fad6fade8971cc5d0b52de0349d16ab2e0d58d2e6d406d3bdb71de3077d16390` |
| 바이트 | 21,700 |
| 문서 제목 | `동향자료 > 상세보기 | YESTRADE` |

**이용 근거 — 확인 필요.** footer에
`Copyright © MINISTRY OF TRADE, INDUSTRY. All Rights Reserved.`가 명시되어 있다.
공공누리(KOGL) 유형 표시를 확인하지 못했다.

- 확인 경로: YesTrade 포털 하단 저작권 정책/공공누리 표시.

저장소 코드에서 참조 0건. **재배포 판단: 불가 → 제거.** 필요하면 URL 인용으로 대체하라.

### 2.6 `data/wassenaar_2025.zip` — 실제로는 404 오류 페이지

| 항목 | 값 |
|---|---|
| SHA-256 | `6f06d4655f79da5feac66e1edee1a6a4b6d2e568314fd44a68c27f67efb6331b` |
| 바이트 | 59,256 |

**실측 내용.** 확장자가 `.zip`이지만 zip 아카이브가 아니다. 첫 바이트가
`\n<!doctype html>`이고 `<title>`은 **`Page not found - The Wassenaar Arrangement`**다.
즉 Wassenaar 웹사이트의 404 오류 페이지를 `.zip`으로 저장한 것이다.
통제목록 데이터가 0건이므로 코퍼스에 기여한 바가 없고, 코드 참조도 0건이다.

**재배포 판단: 불가 → 단순 삭제.** 재취득 대상이 아니다.

---

## 3. 제거 대상 목록 (removal targets)

```
data/wassenaar_2025.pdf              # 재취득 가능 (fetch_sources.py)
data/india_scomet_2024_official.pdf  # 재취득 가능 (fetch_sources.py)
data/law_korea.html                  # 재취득 불가, 코드 참조 0건 -> 삭제
data/yestrade_post.html              # 재취득 불가, 코드 참조 0건 -> 삭제
data/wassenaar_2025.zip              # 404 오류 페이지 -> 삭제
```

**이 작업에서는 아무 파일도 삭제하지 않았다.** 삭제와 git 히스토리 정리는 팀장이
함께 결정할 사안이다.

### 3.1 제거 절차 (권장 순서)

1. **제거 전 상태 고정**

   ```bash
   python fetch_sources.py verify --light-env --report output/source_manifest.json
   ```

   6/6 `ok`가 나오는지 확인한다. 이 보고서가 "제거 전에 어떤 바이트가 있었는지"의 증거다.

2. **재취득 가능성 확인** (네트워크 필요)

   ```bash
   python fetch_sources.py check-remote --light-env
   ```

   `wassenaar_2025_corr_pdf`, `india_scomet_2024_pdf`가 `ok`(원격 해시 일치)여야 한다.

3. **작업 트리에서 제거**

   ```bash
   git rm --cached data/wassenaar_2025.pdf data/india_scomet_2024_official.pdf \
                   data/law_korea.html data/yestrade_post.html data/wassenaar_2025.zip
   # 로컬 파일은 남겨도 된다. .gitignore가 재추가를 막는다.
   ```

4. **`.gitignore` 확인.** 이미 위 5개 경로를 무시하도록 반영해 두었다.
   (`data/*.pdf`, `data/*.zip`, `data/*.html`)

5. **재취득 경로 검증** (제거가 재현성을 깨지 않는지)

   ```bash
   rm -rf /tmp/refetch && python fetch_sources.py fetch --dest-dir /tmp/refetch
   # 두 PDF가 원래 SHA-256과 일치하게 받아져야 한다.
   ```

6. **git 히스토리 정리 (팀장 결정 사항).** 위 3단계는 최신 커밋에서만 파일을 뺀다.
   과거 커밋에는 그대로 남는다. 히스토리에서 지우려면 `git filter-repo` 등이
   필요하고, 이는 공개된 커밋 해시를 모두 바꾸므로 협업자 합의가 필요하다.
   **이 작업 범위 밖이다.**

7. **`data/corpus/combined.json` 판단 필요 (§4).**

---

## 4. 미해결: 2차 산출물의 본문 수록 문제

`data/corpus/combined.json`에는 Wassenaar 585건(254,332자)과 SCOMET 575건(195,452자)의
**본문 텍스트가 그대로** 들어 있다. 원본 PDF를 저장소에서 지워도 이 파일이 남아 있으면
같은 제3자 저작물을 계속 재배포하는 셈이다.

선택지 (팀장·코퍼스 담당자 판단 필요):

- (a) `combined.json`도 저장소에서 빼고, `build_corpus_clean.py`로 재생성하게 한다.
  → `fetch_sources.py fetch` + `fetch_ecfr.py` + `build_corpus_clean.py` 로 완전 재현 가능하므로
  기술적으로는 문제 없다. 실행 시간 비용만 든다(`docs/reproducibility.md` §소요시간).
- (b) 본문을 빼고 코드·offset·해시만 남긴 축약본을 배포한다. → 실험 재현이 어려워진다.
- (c) 현행 유지하고 권리자 허가를 확보한다. → §2.1, §2.2의 "확인 필요"를 먼저 해소해야 한다.

**권고: (a).** 재취득·재생성 경로가 이번에 코드로 갖춰졌으므로 비용이 가장 낮다.
다만 `data/corpus/combined.json`은 이 작업의 소유 파일이 아니므로 손대지 않았다.

---

## 5. 인용 표기 (본문·논문용)

원본을 재배포하지 않고 인용할 때 쓸 표기:

- Wassenaar Arrangement Secretariat, *List of Dual-Use Goods and Technologies and Munitions List*,
  Volume II, 2025 Corr. (2026-01-15), accessed 2026-07-30.
- Directorate General of Foreign Trade (DGFT), Government of India,
  *Updated SCOMET List 2024 (as on 02.09.2024)*, accessed 2026-07-30.
- U.S. Bureau of Industry and Security, *Commerce Control List*,
  15 C.F.R. pt. 774, supp. no. 1 (eCFR, amended 2026-07-23), accessed 2026-07-30.
- 산업통상부, 「전략물자수출입고시」 산업통상부고시 제2025-37호 (시행 2025-12-31).
