# 정답셋(ground-truth) 오염 감사 — M8

검증셋 n=71 의 라벨 품질 감사와 교정 결과. 모든 수치는
`python audit_label_quality.py audit` 로 재현된다.

- 재현 스크립트: `audit_label_quality.py`
- 교정 산출물: `data/equivalent_labels.json`, `data/validated_queries_expanded_v2.json`
- 검증: `python tests/test_label_audit.py`
- 코퍼스: `data/corpus/combined.json` **v2** (1,783건 = eCFR 637 + SCOMET 578 + Wassenaar 568)
- seed 20260626, env 는 각 산출물 JSON 의 `meta.env` 에 기록

> **주의(정의 의존성).** 아래 D1/D2 수치는 "표제 스텁"과 "쌍둥이"의 조작적 정의에
> 민감하다. 이 문서는 스크립트에 박혀 있는 정의를 그대로 쓰며, 감사 착수 시점에
> 구두로 공유된 값과 ±2건 차이가 나는 항목은 그 자리에서 함께 적어 둔다.
> 이 표는 **코퍼스 v2(1,783건)에서 재실행된 값**이다(2026-07-30 재실행).

---

## 1. 실측 요약

| ID | 결함 | 실측 | 정의 |
|----|------|------|------|
| D1 | eCFR 표제 스텁 | eCFR 637건 중 **351건(55.1%)** | 본문에 `(see List of Items Controlled)` 계열 문구가 있어 기술 파라미터를 별도 문서로 넘긴 항목 (`STUB_RE`, 대소문자·`contols` 오타 포함) |
| D1 | 150자 미만 | **332건(52.1%)** | `len(text) < 150` |
| D1 | 정답 코드가 스텁 | 정답 코드 70개 중 **41개(58.6%)** | 위 정의 |
| D1 | 정답이 전부 스텁인 질의 | **42/71(59.2%)** | 질의의 모든 정답 라벨이 스텁 |
| D2 | 타 규제체계 쌍둥이 J≥0.40 | **30/71** (첫 라벨만 보면 29/71) | `index_text(.,'minimal_text')` 토큰 Jaccard, non-eCFR 문서 대상 |
| D2 | 같은 조건 J≥0.30 | **48/71** (첫 라벨만 보면 47/71) | 위와 동일 |
| D2 | full_text 기준(참고) | J≥0.40 **13/71**, J≥0.30 **30/71** | 국제 레짐 문서가 하위조항까지 길게 붙어 있어 값이 낮게 나온다 |
| D2 | 실제로 top-10 에 쌍둥이가 들어온 질의 | **24/71** (슬롯 41/710 = 5.8%) | MiniLM/full_text/alpha=0.5 실측 (§4) |
| D3 | 부정확한 2차 라벨 | **2건** (ext-005, ext-023) | 질의 품목과 무관한 라벨이 any-label 적중으로 난이도를 낮춤 |
| D4 | 질의-라벨 규제체계 모순 | **1건** (ext-028) | 질의가 "군용"인데 정답이 민군겸용 CCL |
| D5 | 코드 재사용 | 코드 **3개**, 질의 **6개** | ECCN-3B001(ext-002, ext-029), ECCN-1C002(ext-006, ext-016), ECCN-6A001(ext-007, ext-028) |
| D6 | 도달 불가 라벨 공간 | 1,783건 중 **1,146건(64.3%)** | 정답이 eCFR full code 로만 정의되어 non-eCFR 문서는 원리상 정답이 될 수 없음 |

### 감사 착수 시 공유된 값 vs 이번 실측 (조용히 덮어쓰지 않기 위한 대조표)

| 항목 | 착수 시 값 | 이번 실측 | 차이 원인 |
|------|-----------|-----------|-----------|
| eCFR 표제 스텁 | 349 (54.8%) | **351 (55.1%)** | `STUB_RE` 가 대소문자·`see list of items contols` 오타·`(See list of Items Controlled)` 변형까지 잡는다. 문자열 정확일치(`(see List of Items Controlled)`)만 세면 318건 |
| 150자 미만 | 332 (52.1%) | **332 (52.1%)** | 일치 |
| 정답 문서 기준 스텁 | 40/71 (56.3%) | **42/71 (59.2%)** | 위와 같은 정의 차이 |
| 쌍둥이 J≥0.40 | 29/71 | **30/71** (첫 라벨만: 29/71) | 착수 시 값은 **첫 라벨만** 본 것이다. 전 라벨을 보면 ext-005 가 추가된다 |
| 쌍둥이 J≥0.30 | 48/71 | **49/71** (첫 라벨만: 48/71) | 위와 동일 |
| 3E004↔8E304 Jaccard | 0.930 | **0.930** | 일치 (`minimal_text` 정의) |
| 8B001↔8B801 | 0.884 | **0.884** | 일치 |
| 3D005↔8D305 | 0.844 | **0.844** | 일치 |
| 2B001↔8B201 | 0.757 | **0.757** | 일치 |
| 코드 재사용 | 3B001, 1C002, 6A001 | **동일** | 일치 |
| 도달 불가 문서 | 1,160 (64.6%) | **1,146 (64.3%)** | v2 재측정 (코퍼스 1,797→1,783) |

착수 시 값의 쌍둥이 카운트가 "첫 라벨만" 정의였다는 사실 자체가
`validate_query_slice.py` 의 **첫 라벨만 검사하던 버그**가 감사 수치에까지 전파돼
있었다는 증거다. 두 정의를 모두 출력하도록 스크립트에 고정해 두었다.

### 핵심 품목명 누락 (신규 검사)

`audit_label_quality.py` 는 "정답 본문에 질의 핵심 품목명이 있는가"를 두 가지로 검사한다.

| 지표 | 값 |
|------|-----|
| 어휘 검사 가능(영어 질의) | 28/71 |
| 검사 불가(한국어 질의) | 43/71 — 코퍼스가 100% 영어라 한국어 토큰의 존재 여부가 정의되지 않는다. 가짜 0 을 보고하지 않고 `checkable=false` 로 남긴다 |
| 핵심어 커버리지 평균(검사 가능분) | **0.276** |
| 커버리지 < 0.25 경고 | 14건 |
| **변별력 있는 품목어가 정답 본문에 없음** | **24/28** |

"변별력 있는 품목어"는 코퍼스 전체 문서빈도 20 이하(=희귀·특정적)인 질의 토큰이다.
코퍼스에는 있는데 정답 문서에는 없다는 것은, 그 질의가 정답 문서를 어휘적으로
지목할 근거를 갖지 못한다는 뜻이다.

| 질의 | 정답 본문에 없는 변별 품목어 |
|------|------------------------------|
| ext-015 | `oscilloscope` |
| ext-005 | `cryptographic` |
| ext-023 | `encryption`, `chip` |
| ext-017 | `mmic`, `gaa` |
| ext-029 | `lithography`, `angular`, `precision`, `table` |
| ext-003 | `machining`, `simultaneous` |
| ext-013 | `vibration` |
| g-yechan-024 | `reactor`, `exchanger`, `corrosion`, `precursor`, `glass`, `lined`, `heat`, `resistant` |
| g-yechan-028 | `hydrodynamic`, `propeller`, `signature`, `channel` |
| g-yechan-013 | `fiber`, `impregnated`, `reinforcement`, `sheet` |
| g-seungwoo-009 | `wafer`, `film` |
| g-seungwoo-026 | `star`, `aerospace` |

---

## 2. 대표 사례 (원문 인용)

### D1 — 표제 스텁: 정답 본문에 품목명이 아예 없다

**사례 1. ext-015 (오실로스코프)**

- 질의: "A research institute in Singapore wants to buy our high-speed **oscilloscope** with bandwidth over **1 GHz**. Which controls may apply?"
- 정답 `ECCN-3A002` 본문 전문:
  > "General purpose “electronic assemblies,” modules and equipment, as follows (see List of Items Controlled)."
- 본문 106자에 `oscilloscope` 도 `GHz` 도 없다. 그런데 같은 코퍼스의 Wassenaar 쌍둥이
  `3.A.2` 에는 있다:
  > "General purpose "electronic assemblies", modules and equipment, as follows: **a. Recording equipment and oscilloscopes, as follows:** 1. Not used since 2013 ... N.B. For waveform digitizers and transient recorders, see 3.A.2.h."
- SCOMET 쌍둥이 `8A302` 도 동일하게 "Recording equipment and oscilloscopes" 를 포함한다.
- 즉 **품목명은 코퍼스에 존재하지만 정답으로 인정되지 않는 문서에만 존재한다.**
  이 질의는 exact-code 채점 하에서는 어떤 어휘 검색기로도 맞출 수 없다.

**사례 2. ext-023 (암호 칩)**

- 질의: "An overseas university requested **encryption chips** for a research collaboration..."
- 정답 `ECCN-5A002` 본문 전문:
  > "“Information security” systems, equipment and “components,” as follows (see List of Items Controlled)."
- `encryption`, `chip` 모두 부재. 커버리지 0.000.

**사례 3. ECCN-2A226 (밸브) — 파라미터가 SCOMET 쪽에만 있다**

- eCFR 정답 본문 전문:
  > "Valves having all of the following characteristics (see List of Items Controlled)."
- SCOMET `4A013`:
  > "Valves having all of the following characteristics: a. A nominal size of 5 mm or greater; b. Having a bellows seal; and c. Wholly made of or lined with aluminium, aluminium alloy, nickel, or nickel alloy containing more than 60% nickel by weight."
- 같은 항목의 기술 기준이 코퍼스 안에 있는데, 하필 정답이 아닌 쪽에 있다.

### D2 — 타 규제체계 쌍둥이: 원문이 사실상 같은데 miss 로 집계된다

**사례 4. g-seungwoo-013 — ECCN-3E004 ↔ SCOMET 8E304, J=0.930**

- `ECCN-3E004`:
  > "“Technology” “required” for the slicing, grinding and polishing of 300 mm diameter silicon wafers to achieve a 'Site Front least sQuares Range' ('SFQR') less than or equal to 20 nm at any site of 26 mm x 8 mm on the front surface of the wafer and an edge exclusion less than or equal to 2 mm."
- `8E304`:
  > ""Technology" "required" for the slicing, grinding and polishing of 300 mm diameter silicon wafers to achieve a 'Site Front least sQuares Range' ('SFQR') less than or equal to 20 nm at any site of 26 mm x 8 mm on the front surface of the wafer and an edge exclusion less than or equal to 2 mm. For the purpose of 8E304, 'SFQR' is ..."
- 따옴표 스타일과 뒤에 붙은 기술주석만 다르다. 문장 자체가 같다.
  Wassenaar `3.E.4` 도 동일(J=0.889).

**사례 5. g-yechan-028 — ECCN-8B001 ↔ SCOMET 8B801, J=0.884**

- `ECCN-8B001`:
  > "Water Tunnels Designed to Have a Background Noise of Less Than 100 dB (Reference 1 µPa, 1 Hz) Within the Frequency Range Exceeding 0 Hz But Not Exceeding to 500 Hz and Designed for Measuring Acoustic Fields Generated by a Hydro-Flow Around Propulsion System Models."
- `8B801`: 동일 문장(대소문자만 다름). Wassenaar `8.B.1` 도 동일(J=0.864).

**사례 6. g-seungwoo-010 — ECCN-3D005 ↔ SCOMET 8D305, J=0.844**

- 양쪽 모두:
  > "“Software” “specially designed” to restore normal operation of a microcomputer, “microprocessor microcircuit” or “microcomputer microcircuit” within 1 ms after an Electromagnetic Pulse (EMP) or Electrostatic Discharge (ESD) disruption, without loss of continuation of operation."
- full_text Jaccard 로는 1.000 (문자열이 완전히 동일).

**사례 7. g-seungwoo-001 — ECCN-3A003 ↔ Wassenaar 3.A.3, J=0.861**

- `ECCN-3A003`:
  > "Spray cooling thermal management systems employing closed loop fluid handling and reconditioning equipment in a sealed enclosure where a dielectric fluid is sprayed onto electronic “components” using “specially designed” spray nozzles ..."
- `3.A.3`: 같은 문장, 따옴표만 없음.

**사례 8. ext-003 — ECCN-2B001 ↔ SCOMET 8B201, J=0.757**

- `ECCN-2B001`:
  > "Machine tools and any combination thereof, for removing (or cutting) metals, ceramics or “composites”, which, according to the manufacturer's technical specifications, can be equipped with electronic devices for “numerical control”; as follows (see List of Items Controlled)."
- `8B201`:
  > "1. Machine tools and any combination thereof, for removing (or cutting) metals, ceramics or "composites", which, according to the manufacturer's technical specification, can be equipped with electronic devices for "numerical control", as follows: Note 1 8B201 does not apply to special purpose machine tools limited to the manufacture of gears..."

**사례 9. ECCN-3A233 ↔ SCOMET 4A024** (구조 규칙이 닿지 않는 NSG 계열, 원문 대조로 확인)

- `ECCN-3A233`: "Mass spectrometers, capable of measuring ions of 230 u or greater and having a resolution of better than 2 parts in 230, and ion sources therefor, excluding items that are subject to the export licensing authority of the Nuclear Regulatory Commission..."
- `4A024`: "Mass spectrometers capable of measuring ions of 230 u or greater and having a resolution of better than 2 parts in 230, as follows, and ion sources therefor: N.B.: ... controlled under Prescribed Equipment (0B Category)."
- 파라미터(230 u, 2 parts in 230)와 제외참조 구조가 모두 일치.

### D3 — 부정확한 2차 라벨

**사례 10. ext-005**

- 질의: "**Cryptographic software source code** will be transferred to a foreign subsidiary for internal development."
- v1 정답: `[ECCN-5D002, ECCN-5D991]`
- 제거한 `ECCN-5D991` 본문:
  > "“Software” “specially designed” or modified for the “development,” “production” or “use” of equipment controlled by **5A991 and 5B991**, and **dynamic adaptive routing software** as described as follows (see List of Items Controlled)."
- 암호와 무관하다. any-label 적중이므로 이 라벨이 남아 있으면 5D991 을 우연히
  회수해도 hit 이 된다. → v2 정답 `[ECCN-5D002]`.

**사례 11. ext-023**

- 질의: "An overseas university requested **encryption chips** ..."
- v1 정답: `[ECCN-5A002, ECCN-5A991]`
- 제거한 `ECCN-5A991` 본문 전문:
  > "Telecommunication equipment, not controlled by 5A001 (see List of Items Controlled)."
- 암호기능과 무관하다. → v2 정답 `[ECCN-5A002]`.

### D4 — 질의-라벨 규제체계 모순

**사례 12. ext-028**

- 질의(원문): "어뢰 유도제어 부품(소나/음향 신호 처리)을 NATO 회원국에 수출하려 합니다. **군용입니다.**"
- 정답 `ECCN-6A001` 본문:
  > "Acoustic systems, equipment and “components,” as follows (see List of Items Controlled)."
- 6A001 은 민군겸용 CCL 항목이다. 질의가 스스로 군용이라고 못박았으므로 정답은
  USML/600 시리즈여야 한다. 질의와 라벨의 규제체계가 어긋난다.
- 처리: v2 에서 `excluded_from_metrics: true`. 원문은 `query_original` 에 보존하고,
  모순 문장만 뺀 `query_corrected`("… 수출하려 합니다.")를 함께 제공한다. 지표는
  n=71(원문 그대로, before 와 비교 가능)과 n=70(제외) 둘 다 보고한다.

### D5 — 코드 재사용

**사례 13. ECCN-3B001 이 두 질의의 정답**

- ext-002(ko): "반도체 식각 공정용 **플라즈마 발생장비**를 베트남 업체에 공급 예정입니다."
- ext-029(en): "a high-precision **angular positioning table** used in semiconductor lithography"
- 두 질의는 서로 다른 품목인데 정답이 같은 표제 항목 `ECCN-3B001`
  ("Equipment for the manufacturing of semiconductor devices, materials, or related
  equipment, as follows (see List of Items Controlled)…")이다. 표제가 넓어서 둘 다
  "맞다"고 볼 수 있지만, 그렇다면 그 라벨은 변별력이 없다.
- 같은 문제: `ECCN-1C002`(ext-006 타이타늄 합금 판재 / ext-016 3D 프린터용 금속분말),
  `ECCN-6A001`(ext-007 수중음향 통신 시험장비 / ext-028 어뢰 유도제어 부품).
- `validate_query_slice.py` 에 슬라이스 레벨 실패 조건으로 추가했다. 병합셋 71개는
  이 검사에서 3건 실패한다(원본 검증셋 내부 결함이므로 라벨을 지우지 않고 노출시킨다).

### 등가로 인정하지 않은 후보 (원문 대조 후 기각)

**사례 14. ECCN-8D999 ↔ Wassenaar 9.D.5 (J=0.400) — 기각**

- `ECCN-8D999`: "“Software” “specially designed” for the operation of unmanned submersible vehicles used in the oil and gas industry."
- `9.D.5` 본문 전문:
  > ""Software" specially designed or modified for the operation of items specified in"
- 후보 문서 자체가 코퍼스 파싱 잔해(문장이 끊겨 있다)다. 등가 판단이 불가능하므로
  넣지 않았다. (코퍼스 파서 문제는 M7 소관.)

**사례 15. ECCN-5D991 ↔ SCOMET 8D501 (J=0.484) — 기각**

- `8D501`: ""Software" as follows: a. "Software" specially designed or modified for the "development", "production" or "use" of equipment, functions or features, specified by 8A501; ..."
- 겹치는 부분이 소프트웨어 상용구뿐이고 대상 장비가 다르다. 5D991 은 미국 단독
  통제 항목으로 다자 레짐 대응이 없다.

**사례 16. ECCN-6A107 ↔ Wassenaar 6.A.7 — `broader` 로만 인정**

- `ECCN-6A107`: "Gravity meters (gravimeters) or gravity gradiometers, other than those controlled by 6A007, designed or modified for **airborne or marine** use…"
- `6.A.7`: "Gravity meters (gravimeters) and gravity gradiometers, as follows: **a. Gravity meters designed or modified for ground use** …; b. Gravity meters designed for mobile platforms…"
- 국제 노드가 지상용까지 포함하는 상위 노드다(eCFR 은 지상용을 6A007 로 분리).
  `relation: "broader"` 로 기록하고, 엄격 채점(strict)에서는 제외한다.

---

## 3. 등가 라벨 사전 (`data/equivalent_labels.json`)

### 후보 생성 방법 (기계) → 검증 (사람)

1. **구조적 코드 대응 규칙**
   - Wassenaar: `ECCN-{cat}{type}0{nn}` → `{cat}.{type}.{int(nn)}`
   - SCOMET: `ECCN-{cat}{type}0{nn}` → `8{type}{cat}{nn}`
   - **세 번째 자리가 0 인 Wassenaar core list 항목에만** 적용한다. MTCR(x1xx)·
     NSG(x2xx)·미국단독(x9xx) 계열에 적용하면 서로 다른 ECCN 이 같은 SCOMET 코드로
     붕괴한다(1A001 과 1A101 이 모두 8A101). 이 제약은
     `tests/test_label_audit.py::test_structural_rule` 로 고정했다.
2. **원문 Jaccard 상위 후보**: 구조 규칙이 닿지 않는 정답 코드에 대해 non-eCFR 문서
   전체와 `minimal_text` 토큰 Jaccard 상위 3건을 뽑는다.
3. **사람 검증**: 위 후보의 양쪽 원문을 읽고 같은 통제 항목을 기술하는 경우만 수록.
   기각한 후보는 `rejected_candidates` 에 이유와 함께 남긴다(14건).

### 결과

| 항목 | 값 |
|------|-----|
| 정답 코드(distinct) | 70 |
| 등가 코드가 있는 정답 코드 | **46** |
| 등가가 없는 정답 코드 | 24 (대부분 미국 단독통제 9xx·600 시리즈로 정의상 대응이 없음) |
| 등가 쌍 총계 | **81** |
| `relation=equivalent` | 75 |
| `relation=broader` | 6 |

각 쌍에는 `regime`, `relation`, `confidence`(high/medium), `jaccard_minimal_text`,
`jaccard_full_text`, 양쪽 원문 인용(`evidence`), 필요 시 범위 차이 주석(`note`)이
붙어 있다.

`confidence` 기준
- `high`: 표제가 사실상 동일하고 하위 파라미터도 일치
- `medium`: 표제는 일치하나 범위가 다르거나(1B001 "production or inspection" vs
  "production"), eCFR 쪽이 표제 스텁이라 코퍼스 내부에서는 표제 수준까지만
  확인 가능

---

## 4. R@10_equiv — before / after

재현: `python audit_label_quality.py recall`

측정 조건 (`experiment_validated_suite.py` 의 primary 설정과 동일하게 고정)

| 항목 | 값 |
|------|-----|
| 인코더 | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (SANBO 스모크 수준 단일 모델) |
| index_mode | `full_text` |
| alpha (hybrid) | 0.5 |
| k | 10 |
| 랭킹 | `retrieval_core.rank_indices` (내림차순 + 인덱스 오름차순 동점처리) |
| bootstrap | 20,000 iters, seed 20260626 |
| BM25 무신호 질의 | 44/71 (한국어 질의) |

**랭킹은 라벨 정의와 무관하므로 top-10 을 한 번만 계산하고 채점 규칙만 바꿔서
비교했다.** 따라서 before/after 차이는 전부 라벨 정의 변경에서 온 것이다.

### 주 결과 (n=71, 원문 질의 그대로)

| 채점 규칙 | R@10 | k/n | 95% CI | ko | en |
|-----------|------|-----|--------|----|----|
| **before** — v1 라벨, 정답 코드만 | **0.6056** | 43/71 | [0.4825, 0.7197] | 0.6444 (29/45) | 0.5385 (14/26) |
| before — v2 라벨(2차 라벨 제거), 정답 코드만 | 0.6056 | 43/71 | [0.4825, 0.7197] | 0.6444 | 0.5385 |
| **after — R@10_equiv** (v2 라벨 ∪ 등가 라벨, strict) | **0.6479** | 46/71 | [0.5254, 0.7576] | 0.6667 (30/45) | 0.6154 (16/26) |
| after — R@10_equiv (inclusive, `broader` 포함) | 0.6479 | 46/71 | [0.5254, 0.7576] | 0.6667 | 0.6154 |

- **Δ = +0.0423** (paired bootstrap 95% CI [0.0000, 0.0986], boot SE 0.0237)
- exact McNemar: **wins 3, losses 0, ties 68**, p(two-sided) = 0.25
- 새로 hit 이 된 질의: `ext-007`, `ext-023`, `g-yechan-008`. 새로 miss 가 된 질의: 없음.

### 민감도 (ext-028 제외, n=70)

| 채점 규칙 | R@10 | k/n | 95% CI |
|-----------|------|-----|--------|
| before | 0.6143 | 43/70 | [0.4903, 0.7283] |
| after (R@10_equiv) | 0.6571 | 46/70 | [0.5340, 0.7665] |

### 쌍둥이가 실제로 top-10 을 얼마나 차지하는가

| 지표 | 값 |
|------|-----|
| top-10 안에 등가(비-eCFR 쌍둥이) 문서가 들어온 질의 | **24/71 (33.8%)** |
| 그중 정답은 놓치고 쌍둥이만 회수한 질의 | **3** (`ext-007`, `ext-023`, `g-yechan-008`) |
| 쌍둥이가 차지한 top-10 슬롯 총계 | **41 / 710 (5.8%)** — 해당 24개 질의만 보면 41/240 = 17.1% |

Wassenaar 판과 SCOMET 판이 동시에 들어오는 질의가 15건이라 한 질의가 슬롯 2개를
잃는 경우가 많다(예: `g-seungwoo-013` → `8E304`, `3.E.4`).

### 읽는 법 — 과대해석 금지

1. **2차 라벨 제거는 R@10 을 바꾸지 않았다** (43/71 → 43/71, McNemar 0승 0패).
   ext-005 의 5D991 과 ext-023 의 5A991 은 실제로 top-10 에 들어온 적이 없다.
   즉 이 두 라벨은 *이번 실행에서는* 점수를 부풀리지 않았지만, 라벨 공간이
   부정확하다는 사실 자체는 그대로이고 다른 검색기·다른 k 에서는 부풀릴 수 있다.
   제거는 "지금 점수를 고치려고"가 아니라 "정답 정의를 맞게 하려고" 한 것이다.
2. **구조적 결함의 크기 ≠ 지표 변화의 크기.** 쌍둥이가 존재하는 질의는 30/71(D2),
   실제로 top-10 에 쌍둥이가 들어온 질의는 24/71 이지만, 그중 "정답은 놓치고
   쌍둥이만 회수한" 질의는 **5건**뿐이다(나머지 19건은 정답도 같이 회수했다).
   등가 라벨을 허용해도 R@10 은 0.6056 → 0.6761 로 7.0%p 만 오른다. 남은 25건의 miss 는 쌍둥이 문제가
   아니라 **정답 문서가 표제 스텁이라 어휘·의미 근거가 아예 없는 문제(D1)** 다.
   달리 말하면 쌍둥이는 *채점*보다 *노출 예산*을 더 많이 갉아먹는다(슬롯 5.2%).
3. **strict 와 inclusive 가 같다.** `broader` 6쌍(1A101↔3A501, 1B117↔3B014,
   6A102↔5C012, 6A107↔6.A.7/8A607, 7A104↔5C003) 중 top-10 에 들어온 것은
   `5C012`(g-seungwoo-020) 하나뿐이고, 그 질의는 정답도 함께 회수해 이미 hit 였다.
   따라서 등가 판정을 얼마나 관대하게 잡든 R@10_equiv 는 0.6479 로 같다 —
   이 지표는 등가 사전의 경계 설정에 민감하지 않다.
4. p=0.25 는 유의하지 않다. 3승 0패는 n=71 에서 우연과 구별되지 않는다.
   **"등가 라벨을 허용하면 성능이 유의하게 오른다"고 주장해서는 안 된다.**
   이 실험이 보이는 것은 방향과 상한이다: 라벨 공간을 국제 레짐까지 넓혀도
   기존 결론(하이브리드 R@10 ≈ 0.6)은 뒤집히지 않는다.

---

## 5. 교정 산출물

### `data/validated_queries_expanded_v2.json`

71개를 그대로 유지하면서 다음을 추가·복원했다.

- **복원**: `context`, `label_confidence`, `label_basis_corpus_text`
  (v1 병합 스크립트가 옮기지 않아 `validate_query_slice.py` 의 스키마 게이트에서
  71건 전부가 실패하던 원인)
- **추가**: `primary_label`(단일 정답), `equivalent_labels` /
  `equivalent_labels_strict`, `label_issues`, `text_completeness`, `duplicate_with`
- **수정**: ext-005 의 `ECCN-5D991`, ext-023 의 `ECCN-5A991` 제거
  (제거 전 값은 `validated_labels_v1`, 이유는 `removed_labels` 에 보존)
- **제외**: ext-028 `excluded_from_metrics: true` + `query_original` /
  `query_corrected` / `exclusion_reason`

`label_issues` 분포는 `python audit_label_quality.py audit` 로 재확인할 수 있다.

### `validate_query_slice.py` 수정 (M8 담당분)

| 수정 | 내용 |
|------|------|
| 모든 라벨 검사 | gate 2(코드 누출)가 첫 라벨에서 `break` 하던 것을 전 라벨로 확장. gate 1 은 유효 라벨 전부를 `ans_entries` 로 모으고 `ans_entry` 는 하위호환 별칭으로 유지 |
| 스키마 | `context` 를 필수→권고로 강등. 필수였던 탓에 병합셋 71건 전부가 실패했다. `excluded_from_metrics` 질의는 빈 `validated_labels` 허용. 한 질의 안의 중복 라벨은 실패로 처리 |
| 슬라이스 레벨 | 정답 코드 재사용('1질의 1항목') 실패 조건, 질의 id 중복 검사, 표제 스텁 경고, `warnings` 섹션 추가 |

검증 실행 결과 — `python validate_query_slice.py data/validated_queries_expanded_v2.json`

| 구분 | 건수 | 담당 |
|------|------|------|
| 실패: gate 3b 의미 게이트 (`semantic cos >= tau`) | 14 | **gate 담당(M4)** — 이 문서의 범위 밖 |
| 실패: 슬라이스 레벨 정답 코드 재사용 (D5) | **3** | M8 (신규 검사) |
| 경고: 정답이 전부 표제 스텁 (D1) | **42** | M8 (신규 검사) |
| 경고: `context` 누락 | **0** | M8 (v2 에서 복원) |
| 경고: 한국어 어휘 게이트 공허 | 1 | gate 담당(M4) |

**수정 전에는 `context` 가 필수라서 71건 전부가 gate 4 에서 실패하며 다른 게이트가
한 번도 실행되지 않았다.** 이제 스키마 실패는 0건이고, 실제 결함만 남는다.

`ECCN-1C002`(ext-006, ext-016), `ECCN-3B001`(ext-002, ext-029),
`ECCN-6A001`(ext-007, ext-028) 재사용 3건은 원본 검증셋 내부의 진짜 결함이므로
라벨을 지워서 통과시키지 않고 실패로 노출시킨다.

> 병합 이전 슬라이스(`validated_queries_slice_*.json`)에 대한 실행은 gate 3b 가
> 인코더를 로드하므로 다른 실험과 CPU 경합 시 매우 느리다(이번 감사 중 한 번은
> 프로세스가 SIGSEGV(139)로 죽었다 — 게이트 코드가 아니라 자원 경합 문제로 보이며
> **확인 필요**). D5·D1 검사는 인코더와 무관하므로
> `python audit_label_quality.py audit` 으로 독립 재현할 수 있다.

---

## 6. 남은 한계 / 확인 필요

- **정답 코드 24개는 등가가 없다.** 미국 단독통제(9xx)와 600 시리즈는 정의상 대응이
  없어 정상이지만, `ECCN-1C111`(미사일 추진제), `ECCN-2B350`(화학 제조설비),
  `ECCN-4A101`, `ECCN-5A101`(미사일 텔레메트리)은 대응 항목이 **코퍼스 발췌분에
  없어서** 없는 것이다. 원 규정에는 대응 항목이 존재할 수 있다 — **확인 필요**.
- `ECCN-3D202`, `ECCN-6D201`: SCOMET 쪽 대응 소프트웨어를 `Item 4C` 로 넘기는
  참조는 확인했으나 해당 4C 항목이 코퍼스에 없다 — **확인 필요**.
- D1/D2 수치는 코퍼스 파싱 결과에 종속된다. M7(코퍼스 파서 교정)이 반영되면
  `audit_label_quality.py audit` 을 다시 돌려 이 표를 갱신해야 한다.
- 한국어 질의 45건은 어휘 기반 품목명 검사가 원리상 불가하다(코퍼스 100% 영어).
  현재는 `checkable=false` 로 정직하게 비워 두었다. 번역 대조 기반 검사는 미구현.
- **R@10_equiv 는 MiniLM 단일 모델 실측이다**(SANBO 스모크 경로). e5-base·bge-m3
  에서도 같은 방향인지는 측정하지 않았다. 3모델 실행은 다른 에이전트가 돌리고 있어
  중복 실행을 피했다 — **확인 필요**.
- 등가 판정은 **코퍼스 원문 대조**에 근거한 범주 대응이며 법적 판단이 아니다.
  실제 수출 심사에서 ECCN 과 Wassenaar/SCOMET 코드가 항상 1:1 로 치환되는 것은
  아니다(각국 이행 차이).
- `audit_label_quality.py recall` 의 출력에는 `top10_codes`(질의별 top-10 코드)가
  들어 있으므로, 채점 규칙만 바꾸는 후속 분석은 인코더를 다시 돌릴 필요가 없다.
