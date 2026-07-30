# 자기참조 게이트 전량 감사 (검증셋 n=71)

## 0. 무엇이 고장나 있었나

기존 gate 3: `jaccard(tokenize(query), tokenize(minimal_text)) < 0.30`

tokenize는 [A-Za-z0-9가-힣]+이고 코퍼스는 100% 영어 → 한국어 질의의 교집합은 원리상 공집합. 전체 71개의 63%(45개)에서 게이트가 아무것도 검사하지 않았고, 영어 26개에서도 한 번도 발동하지 않았다.

## 1. 언어별 분포 — 어휘 게이트의 공허성

| 언어 | n | 어휘 Jaccard 평균 | 최대 | 전부 정확히 0? | 의미 cos 평균 | 중앙값 | 최대 |
|---|---:|---:|---:|---|---:|---:|---:|
| en | 26 | 0.0953 | 0.2364 | 아니오 | 0.2616 | 0.2720 | 0.4942 |
| ko | 45 | 0.0000 | 0.0000 | **예** | 0.3637 | 0.3613 | 0.5639 |

정답 라벨이 복수인 질의(ext-005, ext-023 두 건)에서는 **게이트에 가장 불리한**
라벨(가장 유사한 라벨)을 정답 텍스트로 쓴다. 기존 산출물과 비교할 수 있게 첫-라벨
정의도 함께 기록한다 — 이 선택이 영어 평균을 바꾸는 유일한 원인이다:

| 언어 | 어휘 Jaccard 평균 (최유사 라벨) | 어휘 Jaccard 평균 (첫 라벨, 기존 정의) | 최대(최유사) | 최대(첫 라벨) |
|---|---:|---:|---:|---:|
| en | 0.0953 | 0.0941 | 0.2364 | 0.2364 |
| ko | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

> **경고 (ko)**: 어휘 Jaccard가 45개 전부 정확히 0 — 이 언어에서 어휘 게이트는 아무것도 검사하지 않는다(코퍼스가 100% 영어이므로 교집합이 원리상 공집합).

## 2. 슬라이스(origin)별 분포

| origin | n | 어휘 Jaccard 평균 | 의미 cos 평균 | 최소 | 최대 | 코퍼스 대비 z 평균 |
|---|---:|---:|---:|---:|---:|---:|
| slice_seungwoo | 29 | 0.0510 | 0.4157 | 0.1589 | 0.5639 | +2.96 |
| slice_yechan | 29 | 0.0193 | 0.2935 | 0.1253 | 0.4584 | +1.71 |
| validated_base | 13 | 0.0339 | 0.1999 | 0.0132 | 0.3436 | +0.57 |

## 3. 임계값을 어떻게 정했나 (데이터에 맞추지 않기 위해)

- 게이트 모델: `sentence-transformers/LaBSE` — 평가용 3모델과 겹치지 않는다: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, `intfloat/multilingual-e5-base`, `BAAI/bge-m3`
- 규칙: tau_semantic = floor_2dp(POS-B의 10퍼센타일). POS-B는 정답 항목을 한국어로 옮긴 근거문 ↔ 정답 영어 원문의 cos이며, 71개 질의의 cos 값과 독립이다.
- 근거: 정당한 패러프레이즈 질의는 '정답 항목의 한국어 대역'보다 정답과 덜 비슷해야 한다. 10퍼센타일은 보수적(플래그가 덜 나오는) 컷이므로 자기참조 잔존 주장에 불리한 방향이다.

| 대조군 | n | 평균 | SD | 최소 | p10 | 중앙값 | 최대 |
|---|---:|---:|---:|---:|---:|---:|---:|
| POS-A 사람 번역쌍(ko↔en) | 5 | 0.8384 | 0.0197 | 0.8226 | 0.8230 | 0.8307 | 0.8697 |
| POS-B 정답의 한국어 대역 ↔ 정답 원문 | 57 | 0.5515 | 0.0767 | 0.3615 | 0.4425 | 0.5579 | 0.7080 |
| NEG 무관쌍(질의↔비정답 항목) | 1420 | 0.1598 | 0.0909 | -0.1422 | 0.0375 | 0.1667 | 0.4590 |

→ **tau_semantic = 0.44** (민감도용 중앙값 컷 = 0.55)

## 4. 판정

| 컷 | 임계값 | 의미 게이트 초과 | 어휘 게이트 초과 | 의미만 잡아낸 건수 |
|---|---:|---:|---:|---:|
| 주 분석(보수적, POS-B p10) | 0.44 | 14/71 | 0/71 | 14 |
| 민감도(POS-B 중앙값) | 0.55 | 2/71 | 0/71 | 2 |

### 주 분석에서 임계 초과한 질의

| id | 언어 | 정답 | 의미 cos | 어휘 Jaccard |
|---|---|---|---:|---:|
| g-seungwoo-010 | ko | ECCN-3D005 | 0.5639 | 0.0000 |
| g-seungwoo-029 | ko | ECCN-6B108 | 0.5547 | 0.0000 |
| g-seungwoo-013 | ko | ECCN-3E004 | 0.5199 | 0.0000 |
| g-seungwoo-024 | ko | ECCN-6D201 | 0.5195 | 0.0000 |
| g-seungwoo-027 | ko | ECCN-7A115 | 0.5147 | 0.0000 |
| g-seungwoo-001 | ko | ECCN-3A003 | 0.5101 | 0.0000 |
| g-seungwoo-016 | ko | ECCN-5A101 | 0.5055 | 0.0000 |
| g-seungwoo-015 | ko | ECCN-4D993 | 0.4944 | 0.0000 |
| g-seungwoo-026 | en | ECCN-7A104 | 0.4942 | 0.1556 |
| g-seungwoo-022 | ko | ECCN-6A991 | 0.4698 | 0.0000 |
| g-yechan-018 | ko | ECCN-2A984 | 0.4584 | 0.0000 |
| g-seungwoo-030 | en | ECCN-3D202 | 0.4495 | 0.2105 |
| g-seungwoo-007 | ko | ECCN-3B002 | 0.4481 | 0.0000 |
| g-seungwoo-020 | en | ECCN-6A102 | 0.4450 | 0.1509 |

## 5. 의미 cos 상위 15건 — 원문과 나란히

직역 여부를 육안으로 확인하기 위한 것이다. 어휘 Jaccard 열이 0인데 cos이 높은 행이
바로 기존 게이트가 볼 수 없었던 '번역된 자기참조'다.

**1. g-seungwoo-010** (ko, slice_seungwoo, 정답 `ECCN-3D005`) — cos **0.5639**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +4.46

- 질의: 전자기 펄스나 정전기 충격이 발생해도 마이크로컴퓨터가 1밀리초 안에 정상 동작을 회복하게 만드는 소프트웨어를 해외 방산업체에 제공하려 합니다. 통제 여부를 알고 싶습니다.
- 정답 원문(minimal_text): ECCN-3D005 “Software” “specially designed” to restore normal operation of a microcomputer, “microprocessor microcircuit” or “microcomputer microcircuit” within 1 ms after an Electromagnetic Pulse (EMP) or Electrostatic Discharge (ESD) disruption, without loss of continua

**2. g-seungwoo-029** (ko, slice_seungwoo, 정답 `ECCN-6B108`) — cos **0.5547**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +3.41

- 질의: 로켓이나 무인기의 레이더 반사 면적을 측정하기 위해 특별히 만든 시스템을 외국 항공 회사에 공급하려 합니다. 사거리가 긴 비행체용이라 통제 여부가 궁금합니다.
- 정답 원문(minimal_text): ECCN-6B108 Systems, other than those controlled by 6B008, “specially designed” for radar cross section measurement usable for rockets, missiles, or unmanned aerial vehicles capable of achieving a “range” equal to or greater than 300 km and their subsystems.

**3. g-seungwoo-013** (ko, slice_seungwoo, 정답 `ECCN-3E004`) — cos **0.5199**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +4.22

- 질의: 300밀리미터 실리콘 웨이퍼를 매우 평탄하게 절삭하고 연마하는 데 필요한 공정 기술을 외국 파운드리에 이전하려 합니다. 통제 대상인지 확인 부탁드립니다.
- 정답 원문(minimal_text): ECCN-3E004 “Technology” “required” for the slicing, grinding and polishing of 300 mm diameter silicon wafers to achieve a 'Site Front least sQuares Range' ('SFQR') less than or equal to 20 nm at any site of 26 mm x 8 mm on the front surface of the wafer and an edge exclu

**4. g-seungwoo-024** (ko, slice_seungwoo, 정답 `ECCN-6D201`) — cos **0.5195**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +3.52

- 질의: 고속 카메라와 영상 장치의 성능을 끌어올리거나 제한을 풀어주는 소프트웨어를 해외 연구기관에 제공하려 합니다. 통제 여부를 확인하고 싶습니다.
- 정답 원문(minimal_text): ECCN-6D201 “Software” “specially designed” to enhance or release the performance characteristics of high-speed cameras and imaging devices, and components therefor, to meet or exceed the level of the performance characteristics described in ECCN 6A203.

**5. g-seungwoo-027** (ko, slice_seungwoo, 정답 `ECCN-7A115`) — cos **0.5147**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +4.67

- 질의: 특정 전자기 발생원의 방위를 알아내는 수동형 방향 탐지 센서를 외국 업체에 보내려 합니다. 미사일 용도 가능성이 있어 분류 확인이 필요합니다.
- 정답 원문(minimal_text): ECCN-7A115 Passive sensors for determining bearing to specific electromagnetic sources (direction finding equipment) or terrain characteristics, designed or modified for use in “missiles”.

**6. g-seungwoo-001** (ko, slice_seungwoo, 정답 `ECCN-3A003`) — cos **0.5101**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +4.48

- 질의: 밀폐 용기 안에서 절연성 액체를 전자 부품에 직접 뿌려 작동 온도를 유지시키는 냉각 장치를 베트남 데이터센터에 납품하려 합니다. 수출 통제 대상인지 확인이 필요합니다.
- 정답 원문(minimal_text): ECCN-3A003 Spray cooling thermal management systems employing closed loop fluid handling and reconditioning equipment in a sealed enclosure where a dielectric fluid is sprayed onto electronic “components” using “specially designed” spray nozzles that are designed to main

**7. g-seungwoo-016** (ko, slice_seungwoo, 정답 `ECCN-5A101`) — cos **0.5055**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +2.08

- 질의: 사거리 300킬로미터 이상 무인 비행체에 쓰도록 설계된 원격 측정 및 원격 제어 장비를 외국 항공우주 기관에 보내려 합니다. 분류 확인이 필요합니다.
- 정답 원문(minimal_text): ECCN-5A101 Telemetering and telecontrol equipment, including ground equipment, designed or modified for unmanned aerial vehicle (including cruise missiles, target drones, and reconnaissance drones) or rocket systems (including ballistic missiles, space launch vehicles, a

**8. g-seungwoo-015** (ko, slice_seungwoo, 정답 `ECCN-4D993`) — cos **0.4944**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +3.68

- 질의: 실시간 처리 장비를 위해 소스 코드를 자동으로 생성해 주는 운영체제 소프트웨어를 해외 업체에 납품할 예정입니다. 통제 분류를 알고 싶습니다.
- 정답 원문(minimal_text): ECCN-4D993 “Program” proof and validation “software,” “software” allowing the automatic generation of “source codes,” and operating system “software” that are “specially designed” for “real-time processing” equipment (see List of Items Controlled).

**9. g-seungwoo-026** (en, slice_seungwoo, 정답 `ECCN-7A104`) — cos **0.4942**, 어휘 Jaccard 0.1556, 코퍼스 대비 z +3.60

- 질의: Our device determines orientation by automatically tracking stars or satellites, used for navigation. A foreign aerospace firm requested a sample. Which control code?
- 정답 원문(minimal_text): ECCN-7A104 Gyro-astro compasses and other devices, other than those controlled by 7A004, which derive position or orientation by means of automatically tracking celestial bodies or satellites and “specially designed” “parts” and “components” therefor.

**10. g-seungwoo-022** (ko, slice_seungwoo, 정답 `ECCN-6A991`) — cos **0.4698**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +3.53

- 질의: 물속 물체를 탐지하고 위치를 파악하는 해양 음향 장비를 동남아 조선소에 납품할 예정입니다. 분류 검토가 필요합니다.
- 정답 원문(minimal_text): ECCN-6A991 Marine or terrestrial acoustic equipment, n.e.s., capable of detecting or locating underwater objects or features or positioning surface vessels or underwater vehicles;

**11. g-yechan-018** (ko, slice_yechan, 정답 `ECCN-2A984`) — cos **0.4584**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +3.71

- 질의: 보안검색 장비 업체가 원거리에서 의복 안 물체를 확인하는 밀리미터파 스캐너를 공항 운영사에 판매하려 합니다. 감시 장비 성격이 있어 후보 항목을 확인합니다.
- 정답 원문(minimal_text): ECCN-2A984 Concealed object detection equipment operating in the frequency range from 30 GHz to 3000 GHz and having a spatial resolution of 0.1 milliradian up to and including 1 milliradian at a standoff distance of 100 meters;

**12. g-seungwoo-030** (en, slice_seungwoo, 정답 `ECCN-3D202`) — cos **0.4495**, 어휘 Jaccard 0.2105, 코퍼스 대비 z +4.53

- 질의: Our software boosts the performance of frequency converters and generators to reach a specified high level. A buyer overseas requested it. Which export classification fits?
- 정답 원문(minimal_text): ECCN-3D202 “Software” “specially designed” to enhance or release the performance characteristics of frequency changers or generators to meet or exceed the level of the performance characteristics described in ECCN 3A225.

**13. g-seungwoo-007** (ko, slice_seungwoo, 정답 `ECCN-3B002`) — cos **0.4481**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +2.51

- 질의: 완성 단계의 반도체 소자를 검사하고 시험하기 위해 특별히 만든 장비를 말레이시아 공장에 공급하려 합니다. 분류 확인이 필요합니다.
- 정답 원문(minimal_text): ECCN-3B002 Test or inspection equipment “specially designed” for testing or inspecting finished or unfinished semiconductor devices as follows (see List of Items Controlled) and “specially designed” “components” and “accessories” therefor.

**14. g-seungwoo-020** (en, slice_seungwoo, 정답 `ECCN-6A102`) — cos **0.4450**, 어휘 Jaccard 0.1509, 코퍼스 대비 z +3.28

- 질의: Our product is a sensor hardened against nuclear radiation effects, usable on missile platforms, rated for very high total dose. A foreign client asked about it. Which ECCN?
- 정답 원문(minimal_text): ECCN-6A102 Radiation hardened detectors, other than those controlled by 6A002, “specially designed” or modified for protecting against nuclear effects (e.g., Electromagnetic Pulse (EMP), X-rays, combined blast and thermal effects) and usable for “missiles,” designed or r

**15. g-seungwoo-002** (ko, slice_seungwoo, 정답 `ECCN-3A225`) — cos **0.4384**, 어휘 Jaccard 0.0000, 코퍼스 대비 z +3.34

- 질의: 모터 구동용으로 쓰이는 가변 주파수 변환 장치를 인도 제조사에 공급할 예정입니다. 원자력 규제 대상은 아닌데 일반 수출 통제에 걸리는지 궁금합니다.
- 정답 원문(minimal_text): ECCN-3A225 Frequency changers (a.k.a. converters or inverters) and generators, except those subject to the export licensing authority of the Nuclear Regulatory Commission (see 10 CFR part 110 ), that are usable as a variable frequency or fixed frequency motor drive and h

## 6. 한계

- POS-A는 n=5로 매우 작다 — 참고값.
- POS-B 근거문은 요약된 대역이라 완전 번역보다 cos이 낮게 나오는 하한 성향이 있다.
- 정답과의 유사도만으로 '좋은 질의'와 '베낀 질의'를 원리적으로 구분할 수 없다. 최종 판정은 사람이 해야 한다 — 확인 필요.

히스토그램용 원자료는 `selfreference_audit.json`의 `histograms`에 있다.
