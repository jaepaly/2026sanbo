# 재현 절차 (docs/reproducibility.md)

이 문서는 **아무것도 없는 상태에서 논문 수치까지** 다시 만드는 절차를 적는다.
각 단계의 입력·출력·소요시간·필요 용량, 그리고 **어떤 조건이 갖춰져야 수치가
비트 단위로 같아지는지**를 함께 기록한다.

- 작성일: 2026-07-30 / 개정: 2026-08-11
- 검증 환경: **두 스택이 섞여 있다.** 현재 산출물 대부분은 Python **3.11.15**,
  Windows-10-10.0.19045-SP0, torch **2.6.0+cu124**(로컬 GPU)에서 나왔고,
  일부 오래된 산출물은 Python **3.10.5**, Windows-10-10.0.26200-SP0, torch **2.6.0+cpu**에서
  나왔다. 어느 수치가 어느 스택에서 나왔는지는 §0.1 하단 표에 적었다.
- 관련 문서: `data/SOURCES.md`(출처·권리), `NOTICE`(데이터 라이선스), `LICENSE`(코드)

> 시간 표기: **실측**은 직접 측정한 값이고, **확인 필요**는 측정하지
> 못해 단정하지 않은 값이다. 추정치를 실측처럼 적지 않았다.
> 소요시간은 하드웨어에 종속되므로 어느 기계에서 잰 값인지 함께 적는다.
> 2026-08-11 개정에서 다시 잰 값은 "실측(2026-08-11)"으로 표시했다.

---

## 0. 환경 구성

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

# torch는 별도 휠 인덱스에서 먼저 설치 (로컬 버전 +cpu / +cu124 는 PyPI에 없다)
# CPU 스택(구 산출물):
python -m pip install torch==2.6.0+cpu --index-url https://download.pytorch.org/whl/cpu
# CUDA 스택(현재 산출물):
python -m pip install torch==2.6.0+cu124 --index-url https://download.pytorch.org/whl/cu124
python -m pip install -r requirements.txt
```

### 0.1 환경 버전 표

**`requirements.txt` / `pyproject.toml`의 고정값과 현재 `.venv`의 실제 설치본이
서로 다르다.** 이 어긋남을 감춘 채 한쪽만 적으면 재현 보고가 거짓이 되므로 둘 다 적는다.
현재 산출물 대부분(§0.1 하단 표)은 **오른쪽 열**에서 나왔다.

| 구분 | 패키지 | `requirements.txt` 고정값 | 현재 `.venv` 실측 (2026-08-11) | 왜 고정하는가 |
|---|---|---|---|---|
| 런타임 | Python | 3.10.5 | **3.11.15** | `requires-python = ">=3.10,<3.13"` (둘 다 범위 안) |
| 수치 | numpy | 2.2.6 | **2.4.6** | 정렬·부동소수 세부가 버전마다 달라 동점 처리 결과가 갈릴 수 있다 |
| 통계 | scipy | 1.15.3 | **1.17.1** | `tests/test_retrieval_core.py`가 통계 헬퍼를 scipy와 대조 검증한다 |
| 그림 | matplotlib | 3.10.9 | **3.11.1** | 그림 픽셀 재현 |
| 코퍼스 | pdfplumber | 0.11.10 | 0.11.10 | PDF 텍스트 추출 결과가 버전마다 달라진다 |
| 코퍼스 | pdfminer.six | 20260107 | 20260107 | pdfplumber 백엔드 |
| 코퍼스 | pypdfium2 | 5.12.1 | 5.12.1 | pdfplumber 백엔드 |
| 코퍼스 | pillow | 12.3.0 | 12.3.0 | pdfplumber 의존 |
| dense | torch | 2.6.0+cpu | **2.6.0+cu124** | 임베딩 수치 재현 |
| dense | sentence-transformers | 3.4.1 | **5.6.1** | 풀링·정규화 기본값이 버전마다 바뀐 이력이 있다 |
| dense | transformers | 4.57.6 | **5.14.1** | 토크나이저 동작 |
| dense | tokenizers | 0.22.2 | 0.22.2 | 토크나이저 동작 |
| dense | huggingface-hub | 0.36.2 | **1.26.0** | 모델 다운로드 |
| dense | safetensors | 0.8.0 | 0.8.0 | 가중치 로드 |
| dense | scikit-learn | 1.7.2 | **1.9.0** | sentence-transformers 의존 |
| dense | tqdm | 4.67.3 | **4.70.0** | 진행 표시만 |
| 테스트 | pytest | 9.1.1 | **미설치** | 테스트는 `python tests/test_*.py` 직접 실행이라 pytest 없이도 돈다 |

> **확인 필요 — 고정값을 어느 쪽으로 맞출 것인가.** `requirements.txt`/`pyproject.toml`을
> 그대로 설치하면 현재 논문 수치를 낳은 스택이 **재현되지 않는다**(특히
> sentence-transformers 3.4.1 vs 5.6.1은 풀링·정규화 기본값 차이로 dense 점수를 바꿀 수 있다).
> 고정 파일을 CUDA 스택으로 올릴지, 아니면 CPU 스택으로 되돌려 전량 재실행할지는
> 팀 결정 사항이다. 결정 전까지 이 표가 유일한 정직한 기록이다.

#### 산출물별 환경 (`output/**/*.json`의 `meta.env` / `env`, 43개 스캔, 실측 2026-08-11)

| 스택 | 개수 | 해당 산출물 |
|---|---:|---|
| Python 3.11.15 / numpy 2.4.6 / torch 2.6.0+cu124 / s-t 5.6.1 / Win-10-10.0.19045 | **17** | `disclosure_frontier{,_bge-m3,_e5-base,_strict_detector}.json`, `exposure_decomposition.json`, `ladder_selfreference.json`, `selfreference_audit.json`, `source_manifest.json`, `stats_summary.json`, `symmetric_ablation{,_bge-m3,_e5-base,_partial_coverage}.json`, `validated_suite.json`, `shards/shard_{MiniLM,e5-base,bge-m3}.json` |
| Python 3.10.5 / numpy 2.2.6 / torch 2.6.0+cpu / s-t 3.4.1 / Win-10-10.0.26200 | **9** | `corpus_v3_impact.json`, `corpus_version_comparison.json`, `ecfr_fetch_manifest.json`, `experiment_logs.json`, `external_retriever.json`, `paraphrase_gap.json`, `retriever_compare.json`, `v2_exposure_impact.json`, `validated_suite_smoke.json` |
| Python 3.11.15 / numpy 2.4.6 / **torch 2.5.1+cu121** / s-t 5.6.1 | **1** | `validated_expanded_eval.json` (중간 스택. 위 둘 중 어디에도 속하지 않는다) |
| 환경 기록 없음 | **13** | `alpha_sweep_v4.json`, `crosslingual_eval.json`, `embedding_robustness.json`, `error_analysis.json`, `experiment_logs_v4.json`, `exposure_frontier_validated.json`, `external_eval.json`, `external_label_audit.json`, `label_sensitivity.json`, `llm_rerank_cache.json`, `routing_summary.json`, `tier1_crossmodel.json`, `validated_eval.json` |

즉 **논문 본문 수치(n=151 검증셋 스위트, 대칭 ablation, 노출 분해, 사다리, 통계)는
전부 CUDA 스택(3.11.15)에서 나왔고**, `paraphrase_gap`·`retriever_compare` 등
합성셋·외부질의 계열은 아직 구 CPU 스택(3.10.5) 산출물이다. 두 계열의 수치를
같은 문장에서 나란히 비교할 때는 이 차이를 밝혀야 한다.

`fetch_sources.py` / `fetch_ecfr.py`는 **표준 라이브러리만** 쓴다(`urllib`, `xml.etree`,
`hashlib`). 자료 취득 단계에는 추가 의존성이 없다.

### 0.2 필요 디스크 / 다운로드 용량

아래는 모두 2026-08-11에 다시 잰 실측값이다(1 MB = 10^6 B).

| 항목 | 용량 | 비고 |
|---|---:|---|
| 원본 PDF 2종 | 5.18 MB | Wassenaar 1,366,353 B + SCOMET 3,812,663 B |
| eCFR 원문 XML | 2.00 MB | `fetch_ecfr.py --save-xml` (1,999,647 B). `data/raw/`는 `.gitignore` 대상이라 저장소에는 없다 |
| 코퍼스 산출물 (활성) | 2.33 MB | `combined.json` 2.16 MB(v2) + `ecfr_supp1.json` 0.18 MB |
| 코퍼스 산출물 (전체) | 14.26 MB | `data/corpus/*.json` 10개. v1 보존본·v3·`ecfr_supp1_full.json` 4.37 MB 포함 |
| 질의·라벨셋 | 2.12 MB | `data/*.json` 14개. `queries.json` 444,823 B, `disclosure_ladder.json` 937,140 B 등 |
| 임베딩 모델 3종 | 약 3.9 GB | 아래 표 (Hugging Face API, 주 가중치 기준) |
| 실행 산출물 `output/` | 41.37 MB | 파일 80개. 이 중 `llm_rerank_cache.json` 하나가 33.30 MB(`.gitignore` 대상), 그림 9장 1.00 MB |

> 이전 판의 "코퍼스 산출물 약 1.6 MB (`combined.json` 1.40 MB)"는 **corpus v1** 기준이었다.
> v1 본체는 지금 `combined_v1_superseded.json`(1.42 MB)으로 남아 있고, 활성
> `combined.json`은 v2라 2.16 MB다. 이전 판의 "실행 캐시·산출물 약 100 MB (확인 필요)"는
> 대략치였고, 실제 `output/` 은 41.37 MB다. HF 캐시(`~/.cache/huggingface`)는
> 이 수치에 포함하지 않았다.

임베딩 모델 (Hugging Face API로 확인, 2026-07-30. 이번 개정에서 네트워크 재확인은 하지 않았다):

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

실험에 실제로 쓰인 세 모델의 revision sha는 산출물에도 기록돼 있어 오프라인에서
대조할 수 있다 — `output/validated_suite.json`의 `meta.model_revisions`가
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`(MiniLM),
`d128750597153bb5987e10b1c3493a34e5a4502a`(e5-base),
`5617a9f61b028005a4858fdac845db406aefb181`(bge-m3)로 위 표의 12자리 접두사와 일치한다(실측).
진단용 LaBSE·distiluse의 sha는 어떤 산출물에도 기록돼 있지 않아 위 표의 값을
오프라인에서 검증할 수 없다 → **확인 필요**.

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
| `verify --light-env` | **0.5s (실측 2026-08-11, 3회 평균 0.50s)** | `output/source_manifest.json` |
| `verify` (`--light-env` 없이) | **7.9s (실측 2026-08-11)** | 상동. 차이는 전부 torch import 프로브다 |
| `check-remote` | 6.6s (n=71 판 실측. 2026-08-11 재측정 안 함 — 네트워크 필요) | 상동 (PDF 5 MB 다운로드 포함) |
| `fetch` | 약 7s (n=71 판 실측. 2026-08-11 재측정 안 함) | `data/*.pdf` |

> 이전 판은 `--light-env`가 붙은 명령 블록 옆에 7.2s를 적어 두었는데, 이는 사실
> **`--light-env` 없이** 잰 값(torch 프로브 포함)이다. 위 표에서 두 경로를 분리했다.

`verify`는 PDF 2종만이 아니라 **6개 파일**을 검사한다(실측: `verify: 6/6 ok`).
확인된 SHA-256:

| 파일 | SHA-256 | 로컬 일치 | 원격 일치 |
|---|---|---|---|
| `data/wassenaar_2025.pdf` | `1a92a954…be43fb` | 예 (실측 2026-08-11) | 예 (2026-07-30) |
| `data/india_scomet_2024_official.pdf` | `4e26322b…10681f` | 예 (실측 2026-08-11) | 예 (2026-07-30) |
| `data/corpus/ecfr_supp1.json` | `e3df05c3…f29f9` | 예 (실측 2026-08-11) | 원격 URL 없음 (`fetch_ecfr.py`로 재생성) |
| `data/law_korea.html` | `ffbaac38…18e717` | 예 (실측 2026-08-11) | 확인 필요 |
| `data/yestrade_post.html` | `fad6fade…d16390` | 예 (실측 2026-08-11) | 확인 필요 |
| `data/wassenaar_2025.zip` | `6f06d465…b6331b` | 예 (실측 2026-08-11) | 확인 필요 |

> `output/source_manifest.json`의 `sources[].corpus_entries`는 Wassenaar 585 /
> SCOMET 575로 적혀 있는데 이는 **corpus v1** 값이다. 현재 활성 코퍼스(v2)는 568 / 578이다
> (§2). 매니페스트의 이 필드는 stale → `fetch_sources.py`의 `SOURCE_META` 갱신 필요.

> **주의 — 상류 URL 오기.** `build_corpus_clean.py`의 `SOURCE_META`에 적힌 Wassenaar URL
> (`/app/uploads/2025/12/…-ML-2025.pdf`)은 **정정 전 판**(242쪽, `2a6b2af7…`)을 준다.
> 코퍼스를 만든 실제 원본은 `/app/uploads/2026/01/…-ML-2025-Corr.pdf`(243쪽, `1a92a954…`)다.
> `fetch_sources.py`에는 올바른 URL이 들어 있다. `build_corpus_clean.py` 수정은
> 코퍼스 담당자 몫이다.
> (2026-08-11 재확인: `build_corpus_clean.py` 40행이 여전히 `/2025/12/…-ML-2025.pdf`,
> `fetch_sources.py` 63행이 `/2026/01/…-Corr.pdf`다. **아직 미수정 상태다.**)

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

| 항목 | 값 | 근거 |
|---|---|---|
| 소요시간 | **30.4s** | `output/ecfr_fetch_manifest.json`의 `elapsed_sec`. 구 CPU 스택(3.10.5)에서 잰 값이다 |
| XML 크기 | 1,999,647 B (sha256 `a20c1f8c…22176`, 2026-07-23 판본) | 매니페스트 `xml_bytes`/`xml_sha256` (실측 확인) |
| 결과 항목 | **638건** | 매니페스트 `counts.entries`, `ecfr_supp1_full.json` 실측 638 |
| 표제뿐인 항목 | **47건** | 매니페스트 `counts.heading_only` |
| 텍스트 총량 | 표제만 117,539자 → 표제+Items **814,807자** | 매니페스트, `ecfr_supp1_full.json` 실측 814,807자 일치 |

> 이전 판은 소요시간을 "20.4s (실측, `--light-env`, XML 취득 2.4s 포함)"으로 적었으나
> 산출된 매니페스트는 `elapsed_sec: 30.4`다. 20.4s와 그 안의 2.4s 분해는 어떤
> 산출물에도 근거가 없어 매니페스트 값으로 바꿨다. 항목 수·문자 수·해시는 전부 재현된다.

`--light-env`를 붙이면 `torch` import를 건너뛴다(이 파싱은 torch와 무관한데
import에 수 분이 걸리는 환경이 있다). 대신 매니페스트의 torch 버전 칸이
`not_probed`로 기록된다.

> **주의.** `--save-xml`의 기본 경로 `data/raw/`는 `.gitignore` 대상이고 현재
> 작업 트리에 `data/raw/`가 **없다**. 따라서 "네트워크 없이 저장된 XML만으로 재파싱"
> 경로는 *이미 한 번 온라인으로 받아 둔 사람에게만* 열려 있다(§8도 같이 참조).

---

## 2. 코퍼스 구축

**`build_corpus_clean.py` 한 줄로는 현재 코퍼스가 나오지 않는다.** 기본 실행은
v1(1,797건)을 만들고, 논문이 쓰는 v2(1,783건)는 별도 경로다.

```bash
python build_corpus_clean.py          # v1 -> combined.json(1,797), corpus_quality_report.json
python build_corpus_clean.py --v2     # v2 -> combined_v2.json(1,783), corpus_quality_report_v2.json
python adopt_corpus_v2.py --check     # 무엇이 바뀌는지만 보기
python adopt_corpus_v2.py             # combined.json <- combined_v2.json (v1은 combined_v1_superseded.json으로 보존)
```

- 입력: `data/wassenaar_2025.pdf`, `data/india_scomet_2024_official.pdf`,
  `data/corpus/ecfr_supp1.json`(637건, 105,613자 — 실측)
- 현재 활성 출력: `data/corpus/combined.json` = **1,783건** (v2, sha256 `55ce7917…`),
  `data/corpus/corpus_quality_report_v2.json`, `data/corpus/corpus_version_manifest.json`

| 소스 | v1 raw | v1 kept | v2 raw = kept | 활성 `combined.json` 실측 |
|---|---:|---:|---:|---:|
| `wassenaar_2025` | 614 | 585 | **568** | **568** |
| `india_scomet_2024` | 578 | 575 | **578** | **578** |
| `ecfr_part774` | 637 | 637 | **637** | **637** |
| 합계 | — | 1,797 | **1,783** | **1,783** |

**PDF 파싱은 현재 로컬 PDF에서 항목 수가 정확히 재현된다** (실측 2026-08-11,
Python 3.11.15 / RTX 3060 기계에서 파서 함수를 직접 호출):

| 파서 | 소요시간 | 항목 수 | 대조 |
|---|---:|---:|---|
| `parse_wassenaar` (v1) | 15.6s | 614 | v1 보고서 `raw_count_by_source` 614 일치 |
| `parse_wassenaar_v2` | 15.3s | 568 | v2 보고서 568 일치 |
| `parse_scomet` (v1) | 31.2s | 578 | v1 보고서 578 일치 |
| `parse_scomet_v2` | 31.2s | 578 | v2 보고서 578 일치 |

> 이전 판은 "PDF 파싱 245.5s — `parse_wassenaar` 85.5s(614건), `parse_scomet` 160.0s(578건)"으로
> 적었다. **항목 수는 그대로 재현되지만 시간은 재현되지 않는다**: 같은 파서가 이 기계에서
> v1 경로 46.8s로 끝난다(약 5배 빠름). 245.5s는 구 CPU 스택 기계(Win-10-10.0.26200)의
> 값으로 보존하되, 하드웨어 종속 값임을 밝힌다. 또한 이전 판이 든 raw 카운트 614/578은
> **v1 경로**의 값이고, 논문이 쓰는 v2 경로의 raw는 568/578이다.

> **`corpus_quality_report.json`은 v1 보고서다 (현재 코퍼스를 설명하지 않는다).**
> 이 파일의 `kept_count_by_source`는 eCFR 637 / SCOMET 575 / Wassenaar 585 = **1,797**이라
> 활성 `combined.json`(1,783; 637/578/568)과 맞지 않는다. 현재 코퍼스의 보고서는
> `corpus_quality_report_v2.json`이다. 파일명이 버전을 드러내지 않아 혼동을 부른다.

> **해소된 불일치 (기록 보존).**
> v1 보고서가 기록한 `ecfr_supp1.json`의 SHA-256은
> `c15d80cd131e7f0e0ee23fc8af3f729e5683b17b908c3bd927a7392aa7c43f04`인데
> 작업 트리의 실제 해시는 `e3df05c369a9431a5b9755f75e1528a9b65cc67254f50d5992f5c182560f29f9`다
> (실측 2026-08-11에도 동일). 두 PDF 해시는 정확히 일치하므로 eCFR 입력만 어긋나 있었다.
> 이는 **v1 보고서가 stale하기 때문**이며, v2 보고서는 이 어긋남을
> `source_sha256_vs_v1_report`에 `match: false`로 명시하고 실제 해시(`e3df05c3…`)를 기록해
> 두었다. 즉 미해결 상태가 아니라 **v2에서 문서화된 채로 정리**됐다.

---

## 3. 질의 생성

```bash
python generate_queries.py          # 합성 질의 (자기 본문에서 코드 제거)
python build_validated_queries.py   # 충돌 제거 검증 라벨셋
python validate_query_slice.py data/validated_queries_slice_<이름>.json
python build_expanded_validated.py  # 검증셋 + G/J 슬라이스 병합 (현재 n=151)
```

- 현재 산출물: `data/validated_queries_expanded.json` = **151건 (en 42 / ko 109)** (실측).
  n=71 판에서는 검증셋 + G슬라이스만 병합했다. 현재는 TASK J 슬라이스
  (`validated_queries_slice_j_yechan.json`, `..._j_seungwoo.json`)까지 합쳐 151건이다.
- 소요시간: **확인 필요** (합성 질의는 코퍼스 크기에 선형)
- 주의: 합성 질의는 정답 문서와 near-duplicate이므로 합성셋 R@10을 후보 발견 능력의
  절대 지표로 일반화하지 말 것. 평균 Jaccard는 `output/paraphrase_gap.json`의
  level 0에서 **`minimal_text` 0.4871 / `full_text` 0.5214**다(합성 질의 624건, corpus v2, 실측).
  이전 판의 0.485는 corpus v1 시절 값이다.
  단 이 산출물은 아직 **구 CPU 스택(3.10.5)**에서 나온 것이다(§0.1).

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
#   모델별 분담 실행 후 병합:
python run_model_shard.py MiniLM|e5-base|bge-m3
python merge_shards.py

# 논문 본문의 현재 수치를 내는 실험 (위 목록만 돌려서는 재현되지 않는다)
python build_disclosure_ladder.py          # -> data/disclosure_ladder.json
python experiment_symmetric_ablation.py    # -> output/symmetric_ablation*.json
python experiment_disclosure_frontier.py   # -> output/disclosure_frontier*.json
python report_exposure_decomposition.py    # -> output/exposure_decomposition.json
python audit_ladder_selfreference.py       # -> output/ladder_selfreference.json
python experiment_label_sensitivity.py     # -> output/label_sensitivity.json
python run_tier1.py && python report_tier1_crossmodel.py
```

- **실행 장치.** 현재 산출물은 torch **`2.6.0+cu124`** 스택에서 나왔고 이 기계에는
  CUDA가 잡힌다(실측: `torch.cuda.is_available() == True`, NVIDIA GeForce RTX 3060).
  이전 판의 "CPU"는 구 `2.6.0+cpu` 스택 기준이다. 다만 **산출물 JSON 어디에도
  `device` 필드가 없어**, 각 산출물이 실제로 GPU에서 계산됐는지 파일만으로는
  단정할 수 없다 → **확인 필요**. 인코딩 장치가 바뀌면 dense 점수의 하위 비트가
  달라질 수 있으므로 `env_meta()`에 device를 추가하는 것이 옳다.
- 소요시간: **확인 필요.** 3모델 전량 실행은 임베딩 인코딩이 지배적이다
  (코퍼스 1,783건 × 3모델). 코드 변경 검증은 반드시 `SANBO_MODELS=MiniLM`
  단일 모델 스모크 경로를 먼저 쓸 것.
- 관련 환경변수 (실측, 소스 grep 2026-08-11):
  `SANBO_BATCH`(`experiment_validated_suite.py`, `experiment_symmetric_ablation.py`,
  `experiment_disclosure_frontier.py` — dense 인코딩 배치 크기. 8GB GPU에서 bge-m3가
  OOM 나면 낮춘다. 배치 크기는 임베딩 값을 바꾸지 않는다),
  `SANBO_MODELS`(`experiment_validated_suite.py`, `experiment_symmetric_ablation.py`,
  `experiment_disclosure_frontier.py`),
  `SANBO_MODEL_KEY`(`experiment_symmetric_ablation.py`, `experiment_disclosure_frontier.py`,
  `run_tier1.py`),
  `SANBO_ABLATION_MODEL`(`experiment_symmetric_ablation.py`, 하위호환),
  `SANBO_PAGE_CACHE`(`build_corpus.py`)

---

## 5. 통계 · 그림

```bash
python experiment_stats.py   # -> output/stats_summary.json, docs/statistics.md
python make_figures.py       # -> output/fig_*.png (200 dpi)
python verify_claims.py      # PAPER.md 수치 ↔ 산출물 대조 (exit 0 = 전부 일치)
```

- `make_figures.py`의 `DPI = 200` 확인(실측, 소스 59행). 현재 `output/fig_*.png` 9장,
  합계 1.00 MB. 이 중 `fig_*_v4.png` 3장은 구 v4 실험 잔여물이고 `.gitignore` 대상이다.
- 소요시간: **확인 필요** (기존 `output/*.json`만 읽으므로 짧다)
- **범위 한계.** `verify_claims.py`의 청구 레지스트리는 `PAPER.md`를 대상으로 한다.
  **이 문서(`docs/reproducibility.md`)의 수치는 자동 검증 대상이 아니다** — 이번 개정에서
  드러난 stale 수치(§0.1 환경, §0.2 용량, §2 코퍼스 카운트, §3 Jaccard, §6 테스트 개수)가
  아무 검사에도 걸리지 않은 이유가 이것이다. 레지스트리를 이 문서까지 넓히는 것이
  가장 확실한 재발 방지책이다 → **확인 필요**(담당자 결정).

---

## 6. 테스트

```bash
python tests/test_retrieval_core.py     # 32개 검증 (7개 묶음)
python tests/test_fetch_sources.py      # 취득·파싱 검증 (네트워크 불필요, 6개 파일)
python tests/test_selfreference.py
python tests/test_disclosure_ladder.py
python tests/test_label_audit.py
# 위 목록에 빠져 있던 나머지
python tests/test_corpus.py
python tests/test_m9_m14_fixes.py       # np.argsort 재도입 방지 등 회귀 방어
python tests/test_repo_invariants.py
```

2026-08-11 실행 결과: 위 목록의 **앞 5개는 현재 스택(Python 3.11.15)에서 전부 통과**한다(실측).
뒤 3개(`test_corpus.py`, `test_m9_m14_fixes.py`, `test_repo_invariants.py`)는 이번에
실행하지 않았다 → **확인 필요**.
`test_retrieval_core.py`의 검증 개수는 **32개**다(출력 `ok` 라인 32, 소스의 `check(` 호출 32).
이전 판의 "33개"는 재현되지 않아 32로 고쳤다.

`tests/test_fetch_sources.py`는 실제 eCFR 원문 구조의 변형 사례를 담은 XML
fixture로 파싱을 검증하므로 **오프라인에서 결정론적으로** 통과한다.
`pytest`는 현재 `.venv`에 설치돼 있지 않지만, 테스트가 전부 `python tests/test_*.py`
직접 실행형이라 문제되지 않는다.

---

## 7. 결정론성 보장 조건

수치가 비트 단위로 같아지려면 아래가 모두 지켜져야 한다.

> **먼저 밝힐 것.** 아래 7.1~7.3·7.5는 코드에 실제로 강제돼 있고 이번에 재확인했다.
> 그러나 **비트 단위 동일성은 지금 저장소 상태에서 성립하지 않는다.** 이유는 세 가지다.
> (1) 고정 파일(`requirements.txt`)의 스택과 산출물을 만든 스택이 다르다(§0.1).
> (2) 산출물이 두 스택에 걸쳐 있어 서로 다른 numpy/torch/sentence-transformers로 계산됐다.
> (3) 인코딩 장치(CPU/GPU)가 어디에도 기록돼 있지 않다(§4).
> 따라서 이 절은 "현재 보장된다"가 아니라 **"보장하려면 무엇이 필요한가"**의 목록이다.

### 7.1 동점 처리 (가장 중요)

`np.argsort(-scores)`를 **쓰지 말 것.** numpy 기본 정렬은 quicksort라 동점의
순서가 보장되지 않고, 구현·버전·플랫폼에 따라 달라진다. 이 저장소는
`retrieval_core.rank_indices(scores)`로 **점수 내림차순 + 인덱스 오름차순**을
강제한다. 검색 상위 k에 동점이 흔한 이 과제에서 이 조건이 R@10을 실제로 바꾼다.

확인(실측 2026-08-11): `rank_indices`는 `retrieval_core.py` 193행에 있고, 저장소의
실행 코드 어디에도 `argsort` **호출**이 남아 있지 않다(남은 등장은 전부 정정 경위를
설명하는 주석·docstring이다). `tests/test_m9_m14_fixes.py::test_no_argsort_in_ranking`이
이를 회귀 테스트로 강제한다.

### 7.2 검색 실패 처리

전 점수가 0인 질의는 "검색 실패"로 빈 결과를 돌려준다
(`retrieval_core.retrieve(..., zero_is_failure=True)` — 208행, **기본값이 True**, 실측).
이 처리가 없으면 코퍼스 앞머리 k개를 결과로 집계해 R@10이 부풀려진다.

### 7.3 시드

- 통계 부트스트랩·순열 검정은 스크립트별로 명시적 seed를 쓴다.
  주 산출물의 seed는 `20260626`, 부트스트랩 반복은 `20000`이다
  (`validated_suite.json`·`symmetric_ablation.json`의 `meta`, 실측).
- 임베딩 robustness에서는 **모델별로 seed를 분리**해야 한다. 세 모델이 같은
  리샘플 행렬을 공유하면 모델별 CI가 독립적으로 얻어진 것처럼 보인다.
  `experiment_embedding_robustness.py`는 이를 `default_rng(SEED + i)`로 구현하고
  모델별 `bootstrap_seed`를 JSON에 기록하게 돼 있다(소스 118·148행, 실측).
- 이번에 추가한 취득 스크립트는 무작위성을 쓰지 않지만, 감사 일관성을 위해
  산출물에 `seed`와 `randomness_used: "none"`을 함께 기록한다
  (실측: `source_manifest.json`·`ecfr_fetch_manifest.json` 모두 `seed: 20260730`).

> **`output/embedding_robustness.json`은 seed 분리 이전 산출물이다.** 실측(2026-08-11)
> 이 파일에는 `bootstrap_seed`·`seed_base`가 **0건**이고 `env` 기록도 없으며,
> `meta.n`이 **71**(en 26 / ko 45)이다. 즉 위 seed 분리 규칙을 코드에 넣기 전,
> 질의셋이 n=71이던 시절의 결과다. 현재 검증셋은 **n=151**(en 42 / ko 109)이다.
> 이 파일과 그로부터 만든 `output/fig_embedding_robustness.png`는 **재실행이 필요하다**
> → 확인 필요. 이 문서·논문의 n=151 수치와 같은 표에 나란히 놓지 말 것.

### 7.4 모델 revision

Hugging Face 저장소는 갱신될 수 있다. 현재 코드는 revision을 **고정하지 않는다**
(`SentenceTransformer(..., revision=...)` 호출이 없다 — 실측). 상류가 바뀌면
dense/hybrid 수치가 바뀔 수 있다.

다만 **기록은 한다**: `experiment_validated_suite.py`와 `experiment_disclosure_frontier.py`의
`resolved_revision()`이 로드된 실제 sha를 산출물에 남긴다. 실측으로 확인한 기록 위치는
`validated_suite.json`(3모델 전부), `shards/shard_*.json`, `disclosure_frontier{,_e5-base,_strict_detector}.json`,
`validated_suite_smoke.json`이다. 즉 **사후 감사는 가능하고, 사전 고정은 안 돼 있다.**
`validate_shard.py`는 revision이 비어 있으면 실패시킨다.

**확인 필요:** `revision=`으로 사전 고정할지 여부는 dense 실험 담당자 결정 사항이다.

### 7.5 판본 고정

- eCFR: `fetch_ecfr.py --date 2026-07-23`. 날짜를 안 주면 최신 판본을 받으므로
  개정이 있으면 항목 수가 달라진다.
- Wassenaar/SCOMET: `fetch_sources.py`가 SHA-256을 검증하고,
  **불일치하면 파일을 쓰지 않고 실패로 보고**한다(조용한 드리프트 방지).

### 7.6 환경 기록

`retrieval_core.env_meta()`(462행)와 seed를 담는 것이 규칙이고, 취득 스크립트 산출물
(`output/source_manifest.json`, `output/ecfr_fetch_manifest.json`)도 이를 따른다.

그러나 **"모든 산출물"은 사실이 아니다.** `output/**/*.json` **43개**를 스캔한 결과
(실측 2026-08-11, 판정식: 최상위 또는 `meta` 아래에 비어 있지 않은 `env` 키가 있는가):

| 항목 | 개수 |
|---|---:|
| 환경(`meta.env` / `env`) 기록 있음 | **25 / 43** |
| seed 기록 있음 | **32 / 43** |
| 환경·seed 둘 다 없음 | **11 / 43** |

환경이 빠진 18개: `alpha_sweep_v4`, `crosslingual_eval`, `ecfr_fetch_manifest`,
`embedding_robustness`, `error_analysis`, `experiment_logs_v4`,
`exposure_frontier_validated`, `external_eval`, `external_label_audit`,
`label_sensitivity`, `llm_rerank_cache`, `routing_summary`, `source_manifest`,
`tier1/tier1_{MiniLM,bge-m3,e5-base}`, `tier1_crossmodel`, `validated_eval`.
(분모가 40에서 43으로 는 것은 `output/tier1/` 3개가 스캔 대상에 들어왔기 때문이다.) 이 중
`label_sensitivity.json`, `tier1_crossmodel.json`, `validated_eval.json`,
`external_eval.json`은 현재 문서가 인용하는 계열이므로 **환경 기록 추가가 필요하다**
→ 담당자 확인 필요. 또한 `env_meta()`에 **device(CPU/CUDA) 항목이 없다**(§4).

---

## 8. 오프라인(네트워크 차단) 환경에서

| 단계 | 가능 여부 |
|---|---|
| 1. 자료 취득 | 불가. `fetch_sources.py`/`fetch_ecfr.py`가 항목별 실패 사유와 0이 아닌 종료 코드로 **명확히** 보고한다(조용히 성공한 척하지 않는다). |
| 1.1 eCFR 재파싱 | **조건부.** `--xml` 로 저장해 둔 원문 XML이 있어야 한다. 그런데 `data/raw/`는 `.gitignore` 대상이고 현재 작업 트리에 그 XML이 **없다**. 저장소만 받은 사람은 이 단계에서 최소 한 번 온라인 취득이 필요하다. |
| 2. 코퍼스 구축 | 가능 (PDF가 로컬에 있으면). 실측 확인: v1/v2 파서 모두 로컬 PDF에서 항목 수가 재현된다(§2). |
| 3~5. 질의·실험·그림 | 임베딩 모델이 HF 캐시에 이미 있으면 가능. 없으면 dense/hybrid 불가. `resolved_revision()`은 캐시된 sha를 읽으므로 오프라인에서도 기록된다. |
| 6. 테스트 | 가능. 새 테스트는 네트워크를 쓰지 않는다. 2026-08-11 오프라인 실행에서 §6 목록의 앞 5개 통과(실측), 나머지 3개는 미실행. |

---

## 9. 재현 시 알려진 함정

1. **`output/` 무시 문제 (해결됨).** 이전 `.gitignore`는 `output/*`를 통째로 무시하고
   파일을 하나씩 `!`로 되살리는 허용목록이었다. 그래서 **새 산출물이 자동으로
   커밋에서 빠졌다.** 지금은 부정목록으로 바꿔 `output/`을 기본 커밋 대상으로 두었다.
   다만 무시 대상은 `output/scratch/`·`output/tmp/`만이 아니다 — 실측으로
   `output/*.tmp`, `output/*.partial`, `output/.ipynb_checkpoints/`,
   `output/llm_rerank_cache.json`(33.30 MB), `output/*_v4.json`, `output/fig_*_v4.png`,
   `output/report_v4.md`, `output/error_analysis.json`도 무시된다. 즉 v4 계열 잔여물과
   대용량 캐시는 여전히 저장소 밖이다.
2. **비고정 의존성 (파일은 고정, 환경은 어긋남).** `numpy>=1.24`는 환경마다 다른
   numpy를 설치시킨다. `requirements.txt`/`pyproject.toml`은 지금 `numpy==2.2.6`으로
   고정돼 있다. **그런데 현재 `.venv`에는 numpy 2.4.6이 깔려 있고 현재 산출물도
   2.4.6에서 나왔다**(§0.1). 고정 파일대로 설치하면 논문 수치가 나온 환경이
   재현되지 않는다. 고정 자체는 옳았지만 **고정값이 현실을 따라가지 못한 상태**다
   → 팀 결정 필요(§0.1의 확인 필요 항목과 같은 사안).
3. **`uv.lock`이 `pyproject.toml`보다 오래됐다.** 실측(2026-08-11) `uv.lock`의
   패키지 항목 수: sentence-transformers **0건**, torch **0건**, **scipy 0건**,
   numpy 5건, pdfplumber 3건. 즉 빠진 것은 `[project.optional-dependencies].dense`뿐이
   아니라 **기본 의존성인 scipy까지**다. 락 파일을 다시 만들어야 한다
   → **확인 필요**(uv 사용 여부는 팀 결정). 그때까지 `uv sync`는 재현 경로가 아니다.
4. **eCFR 표제뿐인 항목.** 기존 `ecfr_supp1.json`은 637건, 텍스트 총량 105,613자다
   (실측 2026-08-11, 정확히 재현). "본문을 가리키기만 하는 표제"의 건수는 **어떤 문자열로
   세느냐에 따라 달라지므로** 판정식을 함께 적는다(전부 실측, 대소문자 무시):

   | 판정식 | 건수 |
   |---|---:|
   | `list of items controlled` 포함 | **351** |
   | `see list of items controlled` 포함 | 349 |
   | `(see list of items controlled)` + 마침표(선택)로 **끝남** | **315** |

   이전 판의 "351건 … 그중 315건은 문장 끝"은 위 표의 첫 행과 셋째 행에 해당하며 재현된다.
   셋째 행의 판정식은 **마침표를 선택**으로 둔다(대소문자 무시, 꼬리 공백 제거). 마침표를
   필수로 하면 310, `contols` 오타 변형까지 넣어도 315로 같다. 재현:

   ```bash
   python -c "import json,re;e=json.load(open('data/corpus/ecfr_supp1.json',encoding='utf-8'))['entries'];p=re.compile(r'\(see list of items controlled\)\.?\s*$',re.I);print(sum(1 for x in e if p.search(x.get('text') or '')))"
   ```

   `fetch_ecfr.py --text-field full`로 다시 만들면 **638건 중 본문 없는 항목이 47건**으로
   줄고 텍스트 총량이 **814,807자**가 된다(표제만 담는 `--text-field heading` 모드로는
   117,539자). 638건·814,807자는 현재 `data/corpus/ecfr_supp1_full.json`(4.37 MB)에서
   실측으로 일치 확인했다.
   이 교체는 코퍼스·평가 수치를 바꾸므로 **코퍼스 담당자가 before/after를 함께
   남기고** 반영해야 한다. 이 작업에서는 기존 파일을 덮어쓰지 않았다.
