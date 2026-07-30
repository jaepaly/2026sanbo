# 코퍼스 파싱 결함 교정 (M7)

`data/corpus/combined.json`(v1)을 만든 파서에서 발견된 결함과 그 교정 내역이다.

> **중요.** 교정 결과는 `data/corpus/combined_v2.json` 으로 **별도 생성**했다.
> `combined.json` 과 `corpus_quality_report.json` 은 **한 바이트도 바꾸지 않았다.**
> 코퍼스를 교체하면 논문의 모든 검색 수치가 바뀌므로, 교체 시점은 팀이 결정한다.

| 파일 | 역할 |
| --- | --- |
| `build_corpus.py` | v1 파서(`parse_wassenaar`/`parse_scomet`) 보존 + v2 파서(`*_v2`) 추가 |
| `build_corpus_clean.py` | `--v2` 플래그로 v2 산출물 생성 (플래그 없으면 v1 동작 그대로) |
| `data/corpus/combined_v2.json` | 교정 코퍼스 |
| `data/corpus/corpus_quality_report_v2.json` | before/after 수치, 결함별 실측 건수, SHA-256, `env_meta()`, seed |
| `tests/test_corpus.py` | 회귀 검증 |

재생성:

```bash
python build_corpus_clean.py --v2        # combined_v2.json + corpus_quality_report_v2.json
python tests/test_corpus.py              # 회귀 검증
```

PDF 재파싱이 느리면 `SANBO_PAGE_CACHE=<디렉터리>` 를 지정해 페이지 텍스트를 캐시할 수 있다
(캐시는 파싱 결과에 영향을 주지 않는다).

---

## 1. 총괄 before/after

| 소스 | 항목수 v1 → v2 | 본문 총 문자수 v1 → v2 | 종결부호 미완 비율 v1 → v2 |
| --- | --- | --- | --- |
| `wassenaar_2025` | 585 → **568** | 254,332 → **351,380** (+38.2%) | 161/585 = 0.2752 → **97/568 = 0.1708** |
| `india_scomet_2024` | 575 → **578** | 195,452 → **574,007** (+193.7%) | 199/575 = 0.3461 → **196/578 = 0.3391** |
| `ecfr_part774` | 637 → 637 | 105,567 → 105,567 (변화 없음) | 1/637 = 0.0016 → 0.0016 |
| **합계** | **1,797 → 1,783** | **555,351 → 1,030,954 (+85.6%)** | — |

* eCFR은 PDF 파싱 산출물이 아니라 사전 구축 JSON(`data/corpus/ecfr_supp1.json`)이므로
  페이지 경계 결함이 없다. v2에서도 그대로 통과시켰다(`parse_flags=["prebuilt_json_source"]`).
* **항목수는 14건 줄었는데 본문은 85.6% 늘었다.** 늘어난 본문은 페이지 경계에서
  버려지던 실제 규제 조문이다.

Wassenaar 항목 증감 내역 (585 − 44 + 27 = 568):

| 사라진 44건 | 건수 | 내용 |
| --- | --- | --- |
| 번호목록 오인 (v1 필터를 통과해 코퍼스에 남아 있던 것) | 5 | `1.A.n 2.A.n 2.A.t 3.A.n 5.A.n` |
| 부속서(Sensitive/Very Sensitive List, 170-180쪽) 전용 코드 | 34 | `1.A.2.a.1 1.D.2 2.D.1 3.B.1.a.2 4.A.3.b 5.D.1.a` 등 |
| 줄바꿈된 상호참조 행 오인 | 5 | `3.A.1.a.10 5.A.1.h.1 6.A.4.d.2.a 6.A.5.b.6.c 8.E.2.a` |

| 새로 생긴 27건 | 건수 | 내용 |
| --- | --- | --- |
| 카테고리 표제 (v1이 `non_control_or_reserved_heading` 으로 드롭) | 13 | `1.A 1.E 2.C 2.E 3.E 4.C 4.E 6.E 7.C 7.E 8.A 8.E 9.C` |
| v1이 `invalid_code_format` 으로 통째로 버린 진짜 항목 | 3 | `3.A.2.d.4 (584자) 3.A.2.d.5 (921자) 3.A.2.d.6 (558자)` |
| v1 정규식이 깊이를 못 따라가 상위 코드에 뭉뚱그렸던 항목 | 10 | `3.A.1.b.4.b.4 6.A.1.a.1.a.2 6.A.1.a.1.a.3 6.A.1.a.1.c.1 6.A.1.a.1.c.2 6.A.1.a.2.a.1 6.A.5.b.6.c.2 6.A.5.d.1.d.2 6.A.5.d.1.d.3 6.A.5.d.1.d.4` |
| v1이 `short_fragment` 로 드롭 | 1 | `5.D.2.b` |

> v1의 `corpus_quality_report.json` 이 `invalid_code_format` 15건으로 기록한 코드
> (`2.I.n 3.I.n 5.C.P` 등)는 **드롭되어 `combined.json` 에 남아 있지 않다.**
> 다만 그 본문은 직전 항목의 연속이었으므로 드롭 = 본문 폐기였다.
> 반면 `1.A.n 2.A.n 2.A.t 3.A.n 5.A.n` 다섯 건은 코드 문법 검사를 **통과해**
> 실제로 코퍼스에 가짜 항목으로 남아 있었다(2절 결함 2의 표 참조).

SCOMET은 v1이 `[Reserved]` 로 드롭했던 `0A307 3D002 3D003` 3건이 stub으로 되살아나
575 → 578이 됐다.

`text_completeness` 분포(v2):

| 소스 | full | heading_only | stub |
| --- | --- | --- | --- |
| `wassenaar_2025` | 494 | 37 | 37 |
| `india_scomet_2024` | 563 | 0 | 15 |
| `ecfr_part774` | 637 | 0 | 0 |
| **합계** | **1,694** | **37** | **52** |

`parse_flags` 분포(v2): `prebuilt_json_source` 637, `unterminated_text` 294,
`page_continuation` 175, `table_row_merged` 61, `spans_many_pages` 27,
`duplicate_occurrences` 10, `footnote_marker_stripped` 4, `code_repaired` 0.

---

## 2. 결함별 실측치와 교정

### 결함 1 — 페이지 경계에서 항목 본문이 조용히 사라짐

v1 파서는 페이지 루프 **끝**에서 다음을 실행했다(`build_corpus.py` v1, Wassenaar 71-73행 / SCOMET 109-111행 위치):

```python
if current and current["text"]:
    entries.append(current)
    current = None          # <-- 여기가 문제
```

다음 페이지 첫머리의 연속 행은 `current is None` 이라 `if current:` 분기에 들어가지 못하고
**아무 로그도 없이 버려졌다**.

| 실측 | wassenaar | scomet |
| --- | --- | --- |
| 페이지 경계 flush 횟수 | 167 | 251 |
| `current is None` 상태에서 버려진 행 수 | 3,544 | 5,093 |
| 같은 조건에서 버려진 문자 수 | 172,620 | 278,443 |

(버려진 행에는 표지·목차 같은 비본문도 섞여 있다. 실제 회복량은 위 총괄표의
`chars` 증가분 — Wassenaar +97,048자, SCOMET +378,555자 — 로 판단하는 것이 정확하다.)

종결부호(`. ; : ) ] " '`)로 끝나지 않는 항목 비율은 이 절단의 대리지표다:
wassenaar 161/585(27.5%) → **97/568(17.1%)**, scomet 199/575(34.6%) → 196/578(33.9%),
ecfr 1/637(0.16%) → 변화 없음.

**교정.** 페이지 경계에서 flush하지 않는다. 대신
(a) 러닝 헤더/푸터/각주를 명시적으로 제거하고,
(b) `DUAL-USE LIST` 러닝 헤더가 있는 페이지에서만 항목을 누적해
목차·MUNITIONS LIST·정의절·부속서가 본문에 섞이지 않게 했다.
페이지를 넘긴 항목에는 `parse_flags=["page_continuation"]`, 3쪽 초과면
`spans_many_pages` 를 추가로 붙인다.

### 결함 2 — 번호목록을 가짜 항목으로 오인

v1 정규식은 코드 성분 뒤 마침표를 `\.?`(선택)로 뒀다. 그래서 영어 문장의
"2. In the form of ..." 이 `code=2.I.n`, `text="the form of ..."` 으로 잡혔다.

원문에서 **26회** 등장, 고유 코드 **15개**:
`2.I.n 3.I.n 5.C.P 2.I.s 2.T.o 3.A.2.d.4.A 3.A.2.d.5.A 3.A.2.d.6.A 1.T.o 1.I.t 2.I.t 2.C.W 1.C.W 4.C.W 2.A.P`

v1의 `corpus_quality_report.json` 은 이 15개를 `invalid_code_format` 으로 **드롭**했다.
문제는 두 가지다.

1. 이 행들의 본문은 실제로 **직전 항목의 연속**이었다. 드롭은 곧 본문 폐기였다.
2. `3.A.2.d.4.A / .5.A / .6.A` 는 진짜 항목 `3.A.2.d.4 / .5 / .6` 였다. 통째로 사라졌다.

**더 나쁜 경우가 따로 있다.** 같은 오인이 만든 `1.A.n 2.A.n 2.A.t 3.A.n 5.A.n` 다섯 건은
코드 문법 검사(`^[0-9]\.[A-E](\.[a-z])?...`)를 **통과해** `combined.json` 에
가짜 항목으로 그대로 남아 있다(`combined.json` 실측):

| 가짜 코드 | 쪽 | 본문 길이 | 본문 앞부분 (원문 행에서 코드로 오인된 부분을 뗀 나머지) |
| --- | --- | --- | --- |
| `1.A.n` | 4 | 68자 | `organic "matrix" and "fibrous or filamentary materials" specified in` |
| `2.A.n` | 45 | 39자 | `activator (normally a halide salt); and` |
| `2.A.t` | 29 | 175자 | `least two rotary axes having all of the following: a. Can be coordinated ...` |
| `3.A.n` | 45 | 757자 | `inert powder, most frequently alumina. The substrate and powder mixture ...` |
| `5.A.n` | 106 | 630자 | `assembled array of less than 40 mm in diameter; 6. Not used since 2007 ...` |

(원문 행은 각각 `1. An organic "matrix" ...`, `2. An activator (normally a halide salt); and`,
`2. At least two rotary axes ...`, `3. An inert powder, most frequently alumina.`,
`5. An assembled array of less than 40 mm in diameter;` 이다. `An`/`At` 의 `A` 가
카테고리 문자로, `n`/`t` 가 하위 문자로 잘못 소비됐다.)

즉 "필터에 15건 기록됨"은 문제의 전부가 아니었다. 필터를 통과해 검색 코퍼스에 실제로
들어간 가짜 문서가 5건 더 있었다.

**교정.** v2 전용 정규식 `WASS_ENTRY_V2_RE` 가 코드 성분마다 **마침표 + 공백**을 요구한다.

```
^(\d)\s*\.\s+([A-E])\s*\.\s+(?:(\d+)\s*\.\s+)?(?:([a-z])\s*\.\s+)?...(\S.*)$
```

원문은 항목 코드를 띄어 쓴 형태(`3. A. 2. d. 4.`)로 인쇄하지만, 번호목록은
`2. In ...` 처럼 두 번째 성분 뒤에 마침표가 없다. 이 한 조건으로 15개 가짜 코드가
전부 사라지고, `3.A.2.d.4/5/6` 세 항목이 정상 코드로 복원된다.

같은 조건이 **줄바꿈된 상호참조 행**(붙여 쓴 형태)도 걸러낸다. 실측 17건:

```
3.A.1.a.10. and 3.A.1.a.12., based upon any compound semiconductor
5.D.2.c.3.a.;
6.A.3.a.3., 6.A.3.a.4. or 6.A.3.a.5., according to the
7.E.4.a.3., 7.E.4.a.5., 7.E.4.a.6. or 7.E.4.b., for any of the following:
8.E.2.a. & 8.E.2.b.
```

이 17건은 전부 연속 행이므로 항목으로 만들지 않아도 본문 손실이 없다
(해당 하위항목 서술은 상위 항목 본문 안에 그대로 남는다).

남는 예외를 위해 `repair_wassenaar_code()` 도 유지한다. 마지막 한 토큰(1글자)만
잘라내면 유효해지고 결과 코드가 3성분 이상일 때만 복구하고, 잘라낸 토큰은 본문 앞에
되돌린다. 현재 코퍼스에서 이 경로가 발동하는 항목은 0건이다(정규식이 먼저 처리).

v2 코퍼스의 코드 문법 위반 항목: **0건**.

### 결함 3 — 스텁·푸터·헤더·각주 혼입

**푸터.** Wassenaar 푸터는 쪽마다 두 형태가 번갈아 나온다.

```
- 40 - 15-01-2026        (짝수쪽)
15-01-2026 - 95 -        (홀수쪽)
```

v1의 `skip_tail = r"\d+\s*-\s*\d+\s*-\s*\d+$"` 는 `$` 앞이 숫자여야 해서 **후자를 놓쳤다**
(전자는 `skip_prefixes` 의 `"-"` 에 우연히 걸렸다). 결과적으로 본문에 날짜/쪽번호가
섞인 항목이 `combined.json` 기준 **53건**(중복 제거 전 원시 항목 기준 59건).
v2 잔재: **0건**.

**각주.** 각주 본문 `* The Russian Federation and Ukraine view this list as a reference
list drawn up to help in the selection of dual-use goods ...` 이 페이지 하단에 붙는다.
`skip_prefixes` 에 `"*"` 가 없어 v1은 각주 첫 줄부터 통째로 직전 항목 본문에 흡수했다
(`combined.json` 기준 **2건**: `2.B`, `9.A.2`). v2는 `^\*` 행을 만나면 그 페이지의
나머지를 버린다(각주 블록은 항상 푸터 바로 위에 있음을 확인). v2 잔재: **0건**.

**러닝 헤더.** v1은 `"Wassenaar Arrangement"`, `"Items"` 같은 넓은 prefix 매칭을 써서
본문 3행을 잘못 버렸다(`Wassenaar Arrangement Participating States; and` 등).
v2는 정확한 헤더/푸터 패턴만 제거해 이 3행을 되살린다.

**SCOMET 카테고리 표제행.** `0A2 Special Fissionable Material`, `8A3 ELECTRONICS (...)`
같은 표제행은 코드가 3자리가 아니라 항목 정규식에 걸리지 않고 직전 항목 꼬리에 붙었다.
실측 68행 중 66행이 표제(나머지 2행 `8B1 or 8C.`, `8D2 and 8E2.` 는 문장 중간 연속행이라
뒤 문구가 대문자로 시작할 때만 표제로 판정한다).

**스텁.** 삭제하지 않고 표시한다.

| | v1 원시 항목 | v1 `combined.json` 처리 | v2 |
| --- | --- | --- | --- |
| `Not used since ...` (Wassenaar) | 44건 | 44건 그대로 잔류(푸터가 붙은 것도 있음) | 37건 `stub` (44 − 부속서 전용 8건 + 새로 인식된 `6.A.1.a.1.c.2` 1건) |
| `[Reserved]` / `(Reserved)` (SCOMET) | 16건 | `non_control_or_reserved_heading` 으로 드롭 | 15건 `stub` |
| 카테고리 표제 (`1.A "SYSTEMS, EQUIPMENT AND COMPONENTS"` 등) | — | `non_control_or_reserved_heading` 으로 드롭 | 37건 `heading_only` |

v2는 버리는 대신 표시만 한다. 정보를 잃지 않으면서 한 줄 필터로 제외할 수 있다.

> 검색 코퍼스로 쓸 때는 스텁을 빼는 것을 권장한다:
> `[e for e in corpus if e["text_completeness"] != "stub"]`

### 결함 4 — 본문의 리터럴 `.*` : **정규식 잔재가 아니다**

합성 쿼리 q0613의 `"see ML19. Note .* 1."` 을 근거로 코드 치환 로직의 정규식 잔재가
의심됐다. 원문을 확인한 결과 **원문 각주 표식(asterisk)** 이었다.

* `wassenaar_2025.pdf` 130쪽, 원문 행 그대로: `2.d.*`
* `wassenaar_2025.pdf` 157쪽: `ionizing radiation, see the Munitions List.*`
* 두 쪽 모두 하단에 각주 본문
  `* The Russian Federation and Ukraine view this list as a reference list drawn up to help in the selection of dual-` 을 포함한다.

즉 `.` + 각주표식 `*` 가 이어져 `.*` 로 보였을 뿐, 코드 치환 로직에는 문제가 없다.
v1 코퍼스에서 리터럴 `.*` 를 가진 항목은 `6.A.5.f`, `9.A` 두 건이었다.
v2는 문말 각주 표식을 떼고 `footnote_marker_stripped` 플래그를 남긴다. v2 잔재: **0건**.

### 결함 5 (신규 발견) — SCOMET 표의 하위 문단 소실

SCOMET 원문은 좌측에 코드 열이 있는 표이고, 같은 코드의 하위 문단마다 코드가 반복된다.

```
6A001  Smooth-bore weapons with a calibre of less than 20 mm, ...
6A001  b. Smooth-bore weapons as follows:
6A001  c. Weapons using caseless ammunition;
6A001  d. Accessories designed for arms specified by 6A001.a ...
```

v1은 각 행을 **새 항목**으로 만들었고, 중복 제거 단계에서 코드당 하나만 남겨
b/c/d 를 전부 잃었다. 설명이 소문자로 시작하는(=하위 문단인) 행이 **380행**이었다.

**교정.** 직전 항목과 코드가 같으면 새 항목이 아니라 연속 행으로 합친다
(`table_row_merged`, 61건). 이것이 SCOMET 본문이 3배로 늘어난 주된 이유다.

### 결함 6 (신규 발견) — 부속서 나열을 1차 항목으로 생성

Wassenaar 170-180쪽의 `Sensitive List` / `Very Sensitive List` 는 본문 항목이 아니라
코드를 나열한 부속서다. v1은 여기서도 항목을 만들었고, 그 본문은 1차 항목 서술의
축약본이거나 `3.B.1.a.2. Not used since 2011` 같은 껍데기였다.
v2가 제외한 부속서 전용 코드: **34건**.

또 Category 1 의 `ANNEX / LIST - "EXPLOSIVES"`(23-24쪽)는 항목 코드가 없는 목록이라
직전 항목 `1.E.2.g` 에 그대로 흡수돼 134자 → 5,092자로 부풀었다. v2는 `ANNEX` 행에서
누적을 끊는다.

---

## 3. 실제 예시 (원문 인용)

### (1) `1.A.2` — 열거 목록 전체 소실

* v1 (83자): `"Composite" structures or laminates, as follows: a. Made from any of the following:`
* v2 (1,565자): `... a. Made from any of the following: 1. An organic "matrix" and "fibrous or filamentary materials" specified in 1.C.10.c. or 1.C.10.d.; or 2. Prepregs or preforms specified in 1.C.10.e.; b. Made from a metal or carbon "matrix", and any of the following: ...`

### (2) `1.A.4.c` — 5쪽 `j.` 에서 끊기고 6쪽 `k.`~`o.` 유실

원문 5쪽 마지막 본문 행: `j. Cyanogen bromide (CAS 506-68-3);`
원문 6쪽 첫 본문 행: `k. Bromo methylethylketone (CAS 816-40-0);`

* v1 (785자): `... i. Bromo acetone (CAS 598-31-2); j. Cyanogen bromide (CAS 506-68-3);` 에서 종료
* v2 (945자, `page_continuation`): `... k. Bromo methylethylketone (CAS 816-40-0); l. Chloro acetone (CAS 78-95-5); m. Ethyl iodoacetate (CAS 623-48-3); n. Iodo acetone (CAS 3019-04-3); o. Chloropicrin (CAS 76-06-2).` 까지 포함

### (3) `1.C.2.d` — 가짜 코드 `2.I.n` 로 잘려나간 본문의 복원

* 원문 행: `2. In the form of uncomminuted flakes, ribbons or thin rods; and` → v1은 이 행을 코드 `2.I.n` 의 시작으로 오인
* v1 (115자): `Alloyed materials having all of the following: 1. Made from any of the composition systems specified in 1.C.2.c.1.;`
* v2 (2,179자): `... 2. In the form of uncomminuted flakes, ribbons or thin rods; and 3. Produced in a controlled environment by any of the following: a. 'Splat quenching'; b. 'Melt spinning'; or c. 'Melt extraction'; Technical Notes ...`

### (4) `3.A.2.d.4` — v1에서 통째로 폐기된 진짜 항목

* 원문 행: `3. A. 2. d. 4. A Single Sideband (SSB) phase noise, in dBc/Hz, specified as being`
* v1: 코드를 `3.A.2.d.4.A` 로 잘못 만들고 `invalid_code_format` 으로 드롭 → **코퍼스에 없음**
* v2 (584자): `A Single Sideband (SSB) phase noise, in dBc/Hz, specified as being any of the following: a. Less (better) than -(126+20 log F-20 log f) ...`
  (`3.A.2.d.5`, `3.A.2.d.6` 도 동일하게 복원)

### (5) `3.A.1.a.5.b` — 표제만 남고 사양 전체 소실

* v1 (33자): `DACs having any of the following:`
* v2 (1,991자, `page_continuation`): `... 1. A resolution of 10 bit or more, but less than 12 bit, with an 'adjusted update rate' exceeding 3,500 MSPS; or 2. A resolution of 12 bit or more and having any of the following: ...`

### (6) `2.E.3.f` — 16쪽짜리 증착기술 표

* v1 (1,067자): 표를 참조하는 문장만 남음
* v2 (21,576자, 34-49쪽, `spans_many_pages`): 표 본체 + Notes + Technical Note +
  Statement of Understanding 포함. 항목 본문이 `... specified in column 1 of the following table` 이라고
  명시하므로 표는 이 항목에 속한다.
  (매쪽 반복되는 러닝 서브헤더 `TABLE - DEPOSITION TECHNIQUES` 는 제거)

### (7) `6.A.5.f` — 각주 표식 `.*`

* 원문 130쪽 행: `2.d.*` (바로 아래 각주 본문 `* The Russian Federation and Ukraine view ...`)
* v1 (871자): `... see ML19. Note 2.d.* 1. Not used since 2017 ...`
* v2 (870자, `footnote_marker_stripped`): `... see ML19. Note 2.d. 1. Not used since 2017 ...`

### (8) `9.A.2` — 각주 본문이 항목에 흡수됨

* v1 (1,151자) 꼬리: `... of dual-use goods which could contribute to the indigenous development, production or enhancement of conventional munitions capabilities. 15-01-2026 - 157 -`
  → 각주 둘째 줄 + 페이지 푸터가 그대로 본문에 들어갔다.
* v2 (888자) 꼬리: `... net specific energy (i.e., net heating value) of 42MJ/kg (ISO 3977-2:1997).`

### (9) `6.A.4.d.4` — 스텁에 붙은 푸터

* v1 (38자): `Not used since 2014 15-01-2026 - 119 -`
* v2 (19자, `text_completeness="stub"`): `Not used since 2014`

### (10) `1.C.10.c` — 다른 항목 본문 혼입 제거

* v1 (1,396자) 꼬리: `... Note 5 1.A.2.b.1. does not apply to mechanically chopped, milled, or cut carbon "fibrous or filamentary materials" 25.0 mm or less in length.`
  → `1.A.2.b.1.` 의 Note 가 `1.C.10.c` 본문에 붙어 있었다.
* v2 (853자) 꼬리: `... c. Boron fibres; d. Discontinuous ceramic fibres with a melting, softening, decomposition or sublimation point lower than 2,043 K (1,770°C) in an inert environment.`

### (11) `6A001` (SCOMET) — 표 하위 문단 b/c/d 복원

* v1 (1,027자): `a.` 문단까지
* v2 (4,035자, `table_row_merged`, 147-149쪽): `b. Smooth-bore weapons as follows:`,
  `c. Weapons using caseless ammunition;`, `d. Accessories designed for arms specified by 6A001.a ...` 포함

### (12) `8A301` (SCOMET) — 20쪽짜리 전자 항목

* v1 (455자): 244쪽 첫 문단만
* v2 (36,960자, 244-264쪽, `spans_many_pages`): 원문 표에서 코드 열 `8A301` 이 반복되는
  a.1 ~ h. 전 하위 문단 포함
* **확인 필요**: 37KB 단일 문서는 검색 단위로 지나치게 클 수 있다. 하위 문단
  (`8A301.a.5.b` 등) 단위 분할이 필요한지는 별도 설계 결정이다.

### (13) `0B005` (SCOMET) — 우라늄 농축 설비

* v1 (2,073자, 48쪽) → v2 (15,263자, 48-54쪽, `spans_many_pages`)

### (14) `1.E.2.g` — 부속서 흡수 차단

* v1 (134자): `"Libraries" specially designed or modified to enable equipment to perform the functions of equipment specified in 1.A.4.c. or 1.A.4.d.`
* 중간 버전(ANNEX 차단 전, 5,092자): `... 1.A.4.d. ANNEX LIST - "EXPLOSIVES" 1. ADNBF (aminodinitrobenzofuroxan ...` — 23-24쪽 폭발물 부속서를 통째로 흡수
* v2 (134자): v1과 동일. `ANNEX` 행에서 누적을 끊었다.

---

## 4. 새 스키마

`combined_v2.json` 의 각 엔트리는 v1 필드(`code`, `text`, `source`, `page`,
`control_system`, `source_name`, `source_url`, `official_route`, `review_flags`)에 더해
다음을 갖는다.

| 필드 | 값 |
| --- | --- |
| `pages` | 항목이 걸친 원문 쪽 번호 목록 |
| `text_completeness` | `"full"` / `"heading_only"` / `"stub"` |
| `parse_flags` | 아래 표 |
| `duplicate_occurrences` | 같은 코드가 원문에서 몇 번 더 나왔는지(최장 본문을 채택) |

`parse_flags` 값:

| 플래그 | 뜻 |
| --- | --- |
| `page_continuation` | 페이지를 넘겨 이어붙인 항목 (v1에서 잘리던 것) |
| `spans_many_pages` | 3쪽 초과. 정상일 수 있으나 감사 대상 |
| `table_row_merged` | SCOMET 표에서 같은 코드의 하위 문단 행을 합침 |
| `code_repaired` | 코드 마지막 토큰을 잘라 복구(잘린 토큰은 본문 앞으로) |
| `footnote_marker_stripped` | 문말 각주 표식 `*` 제거 |
| `unterminated_text` | 종결부호로 끝나지 않음 (원문 자체가 그런 경우 포함) |
| `duplicate_occurrences` | 같은 코드가 원문에 2회 이상 등장 |
| `prebuilt_json_source` | eCFR — PDF 파싱을 거치지 않음 |

---

## 5. 남은 한계 (확인 필요)

1. **SCOMET 종결부호 미완 비율이 33.9%로 거의 그대로다.** 남은 항목 대부분은
   `2A001 Bacillus anthracis` 같은 생물체 목록 표 행으로, 원문 자체에 종결부호가 없다.
   즉 이 지표는 SCOMET에서는 절단의 좋은 대리지표가 아니다.
2. **SCOMET 파서의 스킵 집합**(`"Technical Note"`, `"Item"`, `"Notification"` 등)은
   v1과 동일하게 유지했다. 이번 교정의 효과만 분리 측정하기 위해서다.
   이 스킵이 본문 일부를 버리는지는 별도 검토가 필요하다.
3. **Wassenaar MUNITIONS LIST(ML\*) 항목은 v1/v2 모두 코퍼스에 없다.** 코드 문법이
   dual-use 정규식과 달라서다. 포함 여부는 설계 결정 사항이다.
4. **부속서(Sensitive List / Very Sensitive List / ANNEX) 내용은 v2에서 코퍼스에 없다.**
   민감 목록 지정 정보가 필요하면 별도 필드로 다루는 편이 낫다.
5. **일부 항목이 매우 길다**(`8A301` 36,960자, `2.E.3.f` 22,180자). 원문 구조에 충실한
   결과지만 검색 단위로는 분할이 필요할 수 있다. `spans_many_pages` 플래그로 표시했다.
6. **`combined_v2.json` 은 아직 어떤 실험에도 연결하지 않았다.** 교체 시 논문의 모든
   검색 수치(합성셋 R@10 포함)가 바뀐다.
7. **v1 리포트의 eCFR SHA-256 이 현재 파일과 다르다 (확인 필요).**
   `corpus_quality_report.json` 은 `data/corpus/ecfr_supp1.json` 의 sha256을
   `c15d80cd131e7f0e0ee23fc8af3f729e5683b17b908c3bd927a7392aa7c43f04` 로 기록했지만,
   현재 커밋된 파일의 실제 sha256은
   `e3df05c369a9431a5b9755f75e1528a9b65cc67254f50d5992f5c182560f29f9` 이다
   (`git status` 상 이 파일은 미변경). 두 PDF의 해시는 일치한다.
   즉 v1 리포트의 eCFR 해시는 현재 원본으로 재현되지 않는다. v2 리포트의
   `source_sha256_vs_v1_report` 필드가 매 실행마다 이 대조를 자동 기록한다.
   원인 규명은 이 작업 범위 밖이다.
