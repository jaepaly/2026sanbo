# 재현 절차 (docs/reproducibility.md)

이 문서는 **아무것도 없는 상태에서 논문 수치까지** 다시 만드는 절차를 적는다.
각 단계의 입력·출력·소요시간·필요 용량, 그리고 **어떤 조건이 갖춰져야 수치가
비트 단위로 같아지는지**를 함께 기록한다.

- 작성일: 2026-07-30
- 검증 환경: Python **3.10.5**, Windows-10-10.0.26200-SP0, CPU 전용
- 관련 문서: `data/SOURCES.md`(출처·권리), `NOTICE`(데이터 라이선스), `LICENSE`(코드)

> 시간 표기: **실측**은 이 환경에서 직접 측정한 값이고, **확인 필요**는 측정하지
> 못해 단정하지 않은 값이다. 추정치를 실측처럼 적지 않았다.

---

## 0. 환경 구성

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

# torch는 CPU 휠 인덱스에서 먼저 설치 (로컬 버전 +cpu 는 PyPI에 없다)
python -m pip install torch==2.6.0+cpu --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
```

### 0.1 환경 버전 표 (실측, `python -m pip list`)

| 구분 | 패키지 | 고정 버전 | 왜 고정하는가 |
|---|---|---|---|
| 런타임 | Python | 3.10.5 | `requires-python = ">=3.10,<3.13"` |
| 수치 | numpy | 2.2.6 | 정렬·부동소수 세부가 버전마다 달라 동점 처리 결과가 갈릴 수 있다 |
| 통계 | scipy | 1.15.3 | `tests/test_retrieval_core.py`가 통계 헬퍼를 scipy와 대조 검증한다 |
| 그림 | matplotlib | 3.10.9 | 그림 픽셀 재현 |
| 코퍼스 | pdfplumber | 0.11.10 | PDF 텍스트 추출 결과가 버전마다 달라진다 |
| 코퍼스 | pdfminer.six | 20260107 | pdfplumber 백엔드 |
| 코퍼스 | pypdfium2 | 5.12.1 | pdfplumber 백엔드 |
| 코퍼스 | pillow | 12.3.0 | pdfplumber 의존 |
| dense | torch | 2.6.0+cpu | 임베딩 수치 재현 |
| dense | sentence-transformers | 3.4.1 | 풀링·정규화 기본값이 버전마다 바뀐 이력이 있다 |
| dense | transformers | 4.57.6 | 토크나이저 동작 |
| dense | tokenizers | 0.22.2 | 토크나이저 동작 |
| dense | huggingface-hub | 0.36.2 | 모델 다운로드 |
| dense | safetensors | 0.8.0 | 가중치 로드 |
| dense | scikit-learn | 1.7.2 | sentence-transformers 의존 |
| 테스트 | pytest | 9.1.1 | — |

`fetch_sources.py` / `fetch_ecfr.py`는 **표준 라이브러리만** 쓴다(`urllib`, `xml.etree`,
`hashlib`). 자료 취득 단계에는 추가 의존성이 없다.

### 0.2 필요 디스크 / 다운로드 용량

| 항목 | 용량 | 비고 |
|---|---:|---|
| 원본 PDF 2종 | 약 5.0 MB | Wassenaar 1.37 MB + SCOMET 3.81 MB (실측) |
| eCFR 원문 XML | 2.0 MB | `fetch_ecfr.py --save-xml` (실측 1,999,647 B) |
| 코퍼스 산출물 | 약 1.6 MB | `combined.json` 1.40 MB + `ecfr_supp1.json` 0.18 MB (실측) |
| 질의셋 | 약 0.5 MB | `data/queries.json` 432 KB 등 (실측) |
| 임베딩 모델 3종 | 약 3.9 GB | 아래 표 (Hugging Face API 실측, 주 가중치 기준) |
| 실행 캐시·산출물 | 약 100 MB | 그림·JSON·HF 캐시 메타 (확인 필요, 대략치) |

임베딩 모델 (Hugging Face API로 확인, 2026-07-30):

| 모델 | 주 가중치 | 저장소 revision (sha) |
|---|---:|---|
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | 471 MB | `e8f8c211226b` |
| `intfloat/multilingual-e5-base` | 1,112 MB | `d12875059715` |
| `BAAI/bge-m3` | 2,271 MB | `5617a9f61b02` |
| `sentence-transformers/LaBSE` (진단용) | 1,884 MB | `836121a0533e` |
| `sentence-transformers/distiluse-base-multilingual-cased-v2` | 539 MB | `bfe45d0732ca` |

> 저장소에 따라 `.safetensors`와 `.bin`, ONNX/OpenVINO 변형이 함께 있어
> 저장소 전체 크기는 위 값보다 크다. sentence-transformers는 보통
> `model.safetensors` 하나만 받는다.

---

## 1. 자료 취득 (원본 재취득)

이 저장소는 제3자 원본을 **재배포하지 않고 재취득**하는 방향으로 정리했다
(근거·판단은 `data/SOURCES.md`).

```bash
# 1-a. 로컬에 있는 파일이 기대 해시와 맞는지 (네트워크 불필요)
python fetch_sources.py verify --light-env

# 1-b. 원격 URL이 살아 있고 같은 바이트를 주는지
python fetch_sources.py check-remote --light-env

# 1-c. 없으면 받아오기 (기존 파일은 --force 없이는 건드리지 않는다)
python fetch_sources.py fetch
```

| 명령 | 소요시간 | 출력 |
|---|---|---|
| `verify` | **7.2s (실측)** | `output/source_manifest.json` |
| `check-remote` | **6.6s (실측)** | 상동 (PDF 5 MB 다운로드 포함) |
| `fetch` | **약 7s (실측)** | `data/*.pdf` |

취득 대상과 확인된 SHA-256:

| 파일 | SHA-256 | 원격 일치 |
|---|---|---|
| `data/wassenaar_2025.pdf` | `1a92a954…be43fb` | 예 (2026-07-30) |
| `data/india_scomet_2024_official.pdf` | `4e26322b…10681f` | 예 (2026-07-30) |

> **주의 — 상류 URL 오기.** `build_corpus_clean.py`의 `SOURCE_META`에 적힌 Wassenaar URL
> (`/app/uploads/2025/12/…-ML-2025.pdf`)은 **정정 전 판**(242쪽, `2a6b2af7…`)을 준다.
> 코퍼스를 만든 실제 원본은 `/app/uploads/2026/01/…-ML-2025-Corr.pdf`(243쪽, `1a92a954…`)다.
> `fetch_sources.py`에는 올바른 URL이 들어 있다. `build_corpus_clean.py` 수정은
> 코퍼스 담당자 몫이다.

### 1.1 eCFR (미국 CCL) — 코퍼스 35%의 재현 경로

이전에는 `data/corpus/ecfr_supp1.json`만 있고 **취득·파싱 스크립트가 없었다.**
`fetch_ecfr.py`가 그 경로를 복원한다.

```bash
# 최신 판본으로 취득 + 파싱 (판본을 고정하려면 --date 2026-07-23)
python fetch_ecfr.py --date 2026-07-23 --text-field full \
    --save-xml data/raw/ecfr_supp1.xml \
    --out data/corpus/ecfr_supp1_full.json --light-env

# 네트워크 없이 저장된 XML만으로 재파싱 (결정론적)
python fetch_ecfr.py --xml data/raw/ecfr_supp1.xml --text-field full --out ... --light-env
```

| 항목 | 값 |
|---|---|
| 소요시간 | **20.4s (실측, `--light-env`, XML 취득 2.4s 포함)** |
| XML 크기 | 1,999,647 B (sha256 `a20c1f8c…22176`, 2026-07-23 판본) |
| 결과 항목 | **638건** |
| 표제뿐인 항목 | **47건** |
| 텍스트 총량 | 표제만 117,539자 → 표제+Items **814,807자** |

`--light-env`를 붙이면 `torch` import를 건너뛴다(이 파싱은 torch와 무관한데
import에 수 분이 걸리는 환경이 있다). 대신 매니페스트의 torch 버전 칸이
`not_probed`로 기록된다.

---

## 2. 코퍼스 구축

```bash
python build_corpus_clean.py
```

- 입력: `data/wassenaar_2025.pdf`, `data/india_scomet_2024_official.pdf`,
  `data/corpus/ecfr_supp1.json`
- 출력: `data/corpus/combined.json`(**1,783건**, v2), `data/corpus/corpus_quality_report.json`
- 소요시간: **PDF 파싱 245.5s (실측)** — `parse_wassenaar` 85.5s(614건),
  `parse_scomet` 160.0s(578건). 나머지 정제·중복제거·직렬화는 초 단위다.
  이 두 raw 카운트(614 / 578)는 `corpus_quality_report.json`의
  `raw_count_by_source`와 정확히 일치하므로, **현재 로컬 PDF에서 코퍼스가
  재현된다는 것이 확인됐다.**

> **미해결 불일치 (조용히 고치지 않고 기록).**
> `corpus_quality_report.json`이 기록한 `ecfr_supp1.json`의 SHA-256은
> `c15d80cd131e7f0e0ee23fc8af3f729e5683b17b908c3bd927a7392aa7c43f04`인데,
> 작업 트리와 HEAD 커밋의 실제 해시는 모두 `e3df05c369a9…`다.
> 두 PDF 해시는 정확히 일치하므로 eCFR 입력만 어긋나 있다.
> 즉 품질보고서가 입력 파일에 대해 **stale**하다 → 코퍼스 담당자 확인 필요.

---

## 3. 질의 생성

```bash
python generate_queries.py          # 합성 질의 (자기 본문에서 코드 제거)
python build_validated_queries.py   # 충돌 제거 검증 라벨셋
python validate_query_slice.py data/validated_queries_slice_<이름>.json
python build_expanded_validated.py  # 검증셋 + G슬라이스 병합 (n=71)
```

- 소요시간: **확인 필요** (합성 질의는 코퍼스 크기에 선형)
- 주의: 합성 질의는 정답 문서와 near-duplicate(평균 Jaccard 0.485)이므로
  합성셋 R@10을 후보 발견 능력의 절대 지표로 일반화하지 말 것.

---

## 4. 실험

```bash
python run_experiments.py
python experiment_retriever_compare.py
python experiment_external_retriever.py
python experiment_paraphrase_gap.py
python experiment_crosslingual_eval.py
python experiment_exposure_frontier_validated.py

# 검증셋 통합 평가 (3모델). 오래 걸린다.
python experiment_validated_suite.py
#   단일 모델 스모크:
SANBO_MODELS=MiniLM python experiment_validated_suite.py
```

- 소요시간: **확인 필요.** 3모델 전량 실행은 임베딩 인코딩이 지배적이다
  (코퍼스 1,783건 × 3모델, CPU). 코드 변경 검증은 반드시 `SANBO_MODELS=MiniLM`
  단일 모델 스모크 경로를 먼저 쓸 것.
- 관련 환경변수: `SANBO_MODELS`, `SANBO_ABLATION_MODEL`, `SANBO_PAGE_CACHE`

---

## 5. 통계 · 그림

```bash
python experiment_stats.py   # -> output/stats_summary.json, docs/statistics.md
python make_figures.py       # -> output/fig_*.png (200 dpi)
```

- 소요시간: **확인 필요** (기존 `output/*.json`만 읽으므로 짧다)

---

## 6. 테스트

```bash
python tests/test_retrieval_core.py     # 33개 검증
python tests/test_fetch_sources.py      # 취득·파싱 검증 (네트워크 불필요)
python tests/test_selfreference.py
python tests/test_disclosure_ladder.py
python tests/test_label_audit.py
```

`tests/test_fetch_sources.py`는 실제 eCFR 원문 구조의 변형 사례를 담은 XML
fixture로 파싱을 검증하므로 **오프라인에서 결정론적으로** 통과한다.

---

## 7. 결정론성 보장 조건

수치가 비트 단위로 같아지려면 아래가 모두 지켜져야 한다.

### 7.1 동점 처리 (가장 중요)

`np.argsort(-scores)`를 **쓰지 말 것.** numpy 기본 정렬은 quicksort라 동점의
순서가 보장되지 않고, 구현·버전·플랫폼에 따라 달라진다. 이 저장소는
`retrieval_core.rank_indices(scores)`로 **점수 내림차순 + 인덱스 오름차순**을
강제한다. 검색 상위 k에 동점이 흔한 이 과제에서 이 조건이 R@10을 실제로 바꾼다.

### 7.2 검색 실패 처리

전 점수가 0인 질의는 "검색 실패"로 빈 결과를 돌려준다
(`retrieval_core.retrieve(..., zero_is_failure=True)`).
이 처리가 없으면 코퍼스 앞머리 k개를 결과로 집계해 R@10이 부풀려진다.

### 7.3 시드

- 통계 부트스트랩·순열 검정은 스크립트별로 명시적 seed를 쓴다.
- 임베딩 robustness에서는 **모델별로 seed를 분리**해야 한다. 세 모델이 같은
  리샘플 행렬을 공유하면 모델별 CI가 독립적으로 얻어진 것처럼 보인다.
- 이번에 추가한 취득 스크립트는 무작위성을 쓰지 않지만, 감사 일관성을 위해
  산출물에 `seed`와 `randomness_used: "none"`을 함께 기록한다.

### 7.4 모델 revision

Hugging Face 저장소는 갱신될 수 있다. 현재 코드는 revision을 고정하지 않으므로
상류가 바뀌면 dense/hybrid 수치가 바뀔 수 있다. §0.2 표에 확인 시점 revision sha를
적어 두었다. **확인 필요:** `SentenceTransformer(..., revision=...)`로 고정할지
여부는 dense 실험 담당자 결정 사항이다.

### 7.5 판본 고정

- eCFR: `fetch_ecfr.py --date 2026-07-23`. 날짜를 안 주면 최신 판본을 받으므로
  개정이 있으면 항목 수가 달라진다.
- Wassenaar/SCOMET: `fetch_sources.py`가 SHA-256을 검증하고,
  **불일치하면 파일을 쓰지 않고 실패로 보고**한다(조용한 드리프트 방지).

### 7.6 환경 기록

모든 산출물 JSON은 `retrieval_core.env_meta()`와 seed를 담는다
(`output/source_manifest.json`, `output/ecfr_fetch_manifest.json` 포함).

---

## 8. 오프라인(네트워크 차단) 환경에서

| 단계 | 가능 여부 |
|---|---|
| 1. 자료 취득 | 불가. `fetch_sources.py`/`fetch_ecfr.py`가 항목별 실패 사유와 0이 아닌 종료 코드로 **명확히** 보고한다(조용히 성공한 척하지 않는다). |
| 1.1 eCFR 재파싱 | 가능. `--xml` 로 저장해 둔 원문 XML을 쓰면 된다. |
| 2. 코퍼스 구축 | 가능 (PDF가 로컬에 있으면). |
| 3~5. 질의·실험·그림 | 임베딩 모델이 HF 캐시에 이미 있으면 가능. 없으면 dense/hybrid 불가. |
| 6. 테스트 | 가능. 새 테스트는 네트워크를 쓰지 않는다. |

---

## 9. 재현 시 알려진 함정

1. **`output/` 무시 문제 (해결됨).** 이전 `.gitignore`는 `output/*`를 통째로 무시하고
   파일을 하나씩 `!`로 되살리는 허용목록이었다. 그래서 **새 산출물이 자동으로
   커밋에서 빠졌다.** 지금은 부정목록으로 바꿔 `output/`은 커밋하고
   `output/scratch/`, `output/tmp/`만 무시한다.
2. **비고정 의존성 (해결됨).** `numpy>=1.24`는 환경마다 다른 numpy를 설치시킨다.
   지금은 `numpy==2.2.6`으로 고정했다.
3. **`uv.lock`에 dense 의존성 없음.** `uv.lock`에는 sentence-transformers/torch가
   **0건**이다. `pyproject.toml`의 `[project.optional-dependencies].dense`를
   반영하려면 락 파일을 다시 만들어야 한다 → **확인 필요**(uv 사용 여부는 팀 결정).
4. **eCFR 표제뿐인 항목.** 기존 `ecfr_supp1.json`은 637건 중 **351건**(대소문자 무시,
   실측; 그중 315건은 문장 끝)이 "… (see List of Items Controlled)."로 본문을 가리키기만
   하는 표제였고, 텍스트 총량은 105,613자였다. `fetch_ecfr.py --text-field full`로 다시
   만들면 **638건 중 본문 없는 항목이 47건**으로 줄고 텍스트 총량이 **814,807자**가 된다
   (표제만 담는 `--text-field heading` 모드로는 117,539자).
   이 교체는 코퍼스·평가 수치를 바꾸므로 **코퍼스 담당자가 before/after를 함께
   남기고** 반영해야 한다. 이 작업에서는 기존 파일을 덮어쓰지 않았다.
