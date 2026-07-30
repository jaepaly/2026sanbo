# 코퍼스 v2 채택의 노출량 영향

**질문.** 코퍼스 v2 채택이 recall 말고 노출량 수치를 움직이는가

`compare_corpus_versions.py`는 적중 여부(recall)만 비교했다. 노출량@10은 top-10에 든 **문서들의** 반환 문자 수 합이므로, 적중 판정이 전부 같아도 문서 집합이 바뀌면 움직인다. 이 스크립트가 그 강한 성질을 확인한다.

## top-10 집합 동일성과 노출량

| 색인 모드 | 순서까지 동일 | 집합 동일 | 노출량@10 v1 → v2 (반환=minimal_text) | 변화 |
|---|---:|---:|---|---:|
| full_text | 23/71 | 27/71 | 1820.3 → 1810.9 | -9.4자 |
| minimal_text | 52/71 | 57/71 | 1845.1 → 1856.7 | +11.6자 |
| minimal_no_code | 41/71 | 45/71 | 1752.2 → 1764.3 | +12.1자 |

## 헤드라인 노출 감소율

색인=full_text 고정, 반환 full_text -> minimal_text 노출 감소율 (실사용 가능한 최적 운용점)

- v1: 4043.3 → 1820.3 = **55.0%**
- v2: 9729.9 → 1810.9 = **81.4%**

## 판정

**must_update**

헤드라인 노출 감소율이 55.0% -> 81.4% (26.4%p) 바뀐다. 4.5 표와 초록·결론의 감소율을 반드시 갱신해야 하고, 검증셋 통합 실행(3모델)도 다시 돌려야 한다.

- top-10 집합이 달라진 질의 84건
- 노출량@10 최대 변화 5686.6자
- 헤드라인 감소율 이동 26.40%p

## top-10 집합이 바뀐 질의

| 색인 | 질의 | v1에만 | v2에만 |
|---|---|---|---|
| full_text | ext-002 | 2.B.5 | ECCN-7B611 |
| full_text | ext-003 | 5A205 | 2.B.1 |
| full_text | ext-005 | 6A008, 7.D.4.a | 5.D.2.c, ECCN-7D004 |
| full_text | ext-006 | ECCN-7B103 | 8A910 |
| full_text | ext-007 | 6.A.1.c | 8A802 |
| full_text | ext-013 | 8A405, 8A705 | 5A303, 9.D.5 |
| full_text | ext-015 | 3.A.1.b.4, 3.A.1.b.4.b, 5.E.1.d.1 | 3.A.1.b.1.a, 3.A.1.b.2, 3.A.1.c |
| full_text | ext-016 | 9.D.4.a, ECCN-1C117 | 3B020, 8A201 |
| full_text | ext-017 | 3.A.1.b.2, 8A603, ECCN-6A611 | 5C010, 6.A.8, 6.A.8.l |
| full_text | ext-023 | 6A008, 8.E.2.a, 8E302, 9.E.3.a.1, ECCN-4A611 | 5.A.2, 5.E.1.e, 8E603, ECCN-0E521, ECCN-2D984 |
| full_text | ext-029 | 2.B.6.c, 2.E.3.f, 8B205, ECCN-1B234, ECCN-6C992 | 2.B.5, 4A002, 4A022, 4B008, 8B301 |
| full_text | g-seungwoo-002 | ECCN-2A290 | 0B008 |
| full_text | g-seungwoo-003 | 4A016 | 3.A.1.e |
| full_text | g-seungwoo-004 | 3.A.1.g | 0B001 |
| full_text | g-seungwoo-005 | 6.A.6.a.1, 8A108, 9.E.3.a.3.a | 2.B.5.b, 3.B, 3D012 |
| full_text | g-seungwoo-006 | 5.B.2, 8B502, ECCN-0E521 | 3D003, 5.A.3.b, 8A502 |
| full_text | g-seungwoo-008 | ECCN-4A004 | 6.A.2.a.2.c |
| full_text | g-seungwoo-009 | 3.C.1, 8C301 | 8B301, 8C305 |
| full_text | g-seungwoo-010 | ECCN-3D991 | 8E302 |
| full_text | g-seungwoo-012 | 5.A, 8A901, ECCN-7D103 | 3.A.1.a.14, 3.E.1, 4.E.1 |
| full_text | g-seungwoo-013 | 3.A.1.b.3 | 8E603 |
| full_text | g-seungwoo-014 | 9.A.4.g | 6A010 |
| full_text | g-seungwoo-015 | 3.D.2 | 2.D |
| full_text | g-seungwoo-017 | 5.A.3.b | 4.A.3.a |
| full_text | g-seungwoo-020 | 4A031 | 8A401 |
