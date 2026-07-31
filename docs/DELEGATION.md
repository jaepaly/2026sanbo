# 팀 분담 패키지 — 무거운 계산 넘기기

> **이 문서는 대체되었습니다.**
>
> 샤드 분담 절차는 [`README.md` §코퍼스 v2 채택 매뉴얼](../README.md#코퍼스-v2-채택-매뉴얼)에
> 팀원 1인칭으로 다시 쓰여 있고, 저장소를 이어받는 경우의 진입점은
> [`docs/HANDOFF.md`](HANDOFF.md)입니다. 두 문서를 먼저 보십시오.
>
> 이 문서는 코퍼스 v2 채택 **이전**에 작성되어 `adopt_corpus_v2.py` 단계가 빠져 있고,
> 아래 배정표와 '팀장이 할 일' 절은 이미 완료된 라운드의 것입니다. 그대로 따르면 안 됩니다.
> 당시 판단 근거(특히 BM25 히트 벡터가 왜 무결성 검사가 되는지)를 남기기 위해 보존합니다.


이 문서는 저장소의 기존 분담 방식(`validate_query_slice.py` 1커맨드 검증)을
그대로 따른다. 판단이 필요 없고 결과를 기계적으로 검증할 수 있는 작업만 넘긴다.

---

## 왜 이것만 넘기는가

수정 작업 중 사람의 판단이 필요했던 것 — 질의 노출 등급 L0~L4 재작성(284건), 위협모형 정의,
등가성 마진 사전지정, 라벨 감사, 코퍼스 파싱 규칙 — 은 이미 끝났고 저장소에 반영되어 있다.

남은 것은 **dense 인코더로 문서를 임베딩하는 계산** 하나다. 이것은

- 시드가 고정되어 있고(`SEED = 20260626`) 랭킹이 결정론적이므로 **누가 돌려도 같은 값**이 나오고,
- BM25는 인코더를 쓰지 않으므로 **결과 파일 하나로 무결성을 기계 검증**할 수 있으며,
- CPU에서 약 1시간, **CUDA GPU에서는 1~2분**이다.

그래서 이것만 넘긴다. 반대로 **넘기면 안 되는 것**은 아래 "넘기지 말 것"에 적어 두었다.

---

## 담당자에게 보낼 것 (복붙용)

> 안녕하세요. 2026sanbo 저장소에서 **임베딩 계산 한 개**만 돌려 주시면 됩니다.
> 판단할 것은 없고, 결과 파일 1개만 보내 주시면 됩니다. GPU 있으면 2분, CPU면 1시간쯤 걸립니다.
>
> ```bash
> git clone https://github.com/jaepaly/2026sanbo.git
> cd 2026sanbo
> python -m venv .venv
> .venv\Scripts\activate          # mac/linux: source .venv/bin/activate
> pip install -r requirements.txt
> ```
>
> 그다음 배정받은 모델 하나를 돌립니다(`<배정모델>` 자리에 `bge-m3` 또는 `e5-base`):
>
> ```bash
> python run_model_shard.py <배정모델>
> ```
>
> 끝나면 반드시 검증하세요. exit 0 이어야 합니다:
>
> ```bash
> python validate_shard.py output/shards/shard_<배정모델>.json
> ```
>
> `output/shards/shard_<배정모델>.json` **이 파일 하나만** 보내 주시면 됩니다.
> 다른 파일은 건드리지 마세요. 커밋도 필요 없습니다.
>
> 검증이 실패하면 출력에 이유가 나옵니다. 그대로 알려 주시면 됩니다.

---

## 배정표

| 담당 | `<배정모델>` | 모델 | 크기 | CPU 예상 | GPU 예상 |
|---|---|---|---:|---:|---:|
| (팀원 A) | `bge-m3` | BAAI/bge-m3 | 568M | 약 60분 | 1~2분 |
| (팀원 B) | `e5-base` | intfloat/multilingual-e5-base | 278M | 약 20분 | 1분 미만 |
| 팀장 | `MiniLM` | paraphrase-multilingual-MiniLM-L12-v2 | 118M | 약 5분 | 즉시 |

`MiniLM`이 **primary model**이다. 노출량@10과 등가성 검정이 primary model의 랭킹을 따르므로
MiniLM 샤드는 반드시 있어야 한다. 나머지 둘은 "우위가 특정 인코더의 산물이 아니다"라는
robustness 주장에만 쓰이므로, 하나가 빠져도 분석은 돌아간다(빠진 모델은 `meta.missing_models`에 기록되고,
robustness 주장을 포함된 모델 범위로 한정해 서술하면 된다).

---

## 팀장이 할 일 (샤드가 모이면)

```bash
python validate_shard.py output/shards/shard_bge-m3.json
python merge_shards.py
python report_exposure_decomposition.py
python verify_claims.py
```

`merge_shards.py`는 재인코딩을 하지 않는다. 샤드의 hit 벡터만 읽어 통계를 한 번 돌린다(수 초).

---

## 검증이 실제로 무엇을 잡는가

`validate_shard.py`의 핵심은 통계가 아니라 **구조적 대조**다.

> **BM25는 dense 인코더를 전혀 쓰지 않는다. 따라서 모든 샤드의 BM25 hit 벡터는 완전히 동일해야 한다.**

이 한 가지 성질이 다음을 전부 잡아낸다.

| 사고 | 어떻게 잡히는가 |
|---|---|
| 다른 코퍼스 버전으로 돌림 (`combined.json` vs `combined_v2.json`) | BM25 벡터 불일치 |
| 다른 질의셋으로 돌림 | `query_ids` 불일치 + BM25 벡터 불일치 |
| 옛 코드(`np.argsort`)로 돌림 | 무신호 질의 44건 처리가 달라져 BM25 벡터 불일치 |
| 시드·색인모드·α 격자를 바꿈 | 메타 필드 불일치 |
| 결과를 손으로 고침 | BM25 벡터 또는 진단 정합성 불일치 |
| 모델 revision 미기록 | 재현 불가로 경고 |

비교할 다른 샤드가 아직 없으면 검증기가 **BM25를 로컬에서 직접 재계산해** 대조한다.
BM25는 인코더가 필요 없어 몇 초면 끝나므로, 첫 샤드도 무조건 검증된다.

추가로 검사하는 정합성:

- 무신호 질의 수와 BM25 적중 수가 모순되지 않는가
- `hybrid ≡ dense` 건수 ≥ 무신호 건수 (BM25 점수가 전부 0이면 α<1 랭킹은 dense와 수학적으로 동일해야 한다)
- hit 벡터 길이 = 71, 값이 0/1, retriever 키 완비, exposure@10 기록

---

## 넘기지 말 것

| 항목 | 이유 |
|---|---|
| 통계 코드(`retrieval_core.py`) 수정 | 33개 검증(`tests/test_retrieval_core.py`)이 걸려 있고 scipy와 대조되어 있다. 여기가 틀리면 모든 수치가 조용히 틀어진다 |
| 등가성 마진 δ, α, 시드 변경 | 사전지정 값이다. 결과를 보고 바꾸면 사전지정의 의미가 사라진다 |
| 질의 노출 등급 재작성 | 이미 완료됨(`data/disclosure_ladder.json`). 다시 쓰면 frontier 수치가 전부 바뀐다 |
| 코퍼스 교체 결정 | `combined_v2.json`이 생성되어 있으나 교체 시 **논문의 모든 수치가 바뀐다**. 팀장이 시점을 정할 사안 |
| 논문 수치 수동 수정 | `verify_claims.py`가 산출물과 대조한다. 손으로 고치면 대조가 깨진다 |

---

## 문제가 생기면

| 증상 | 대응 |
|---|---|
| `validate_shard.py`가 BM25 불일치를 보고 | 코퍼스·질의 파일이 최신 main인지 확인. `git pull` 후 재실행 |
| 모델 다운로드가 느림 | `pip install hf_xet` 하면 다운로드가 빨라진다 |
| CPU에서 너무 느림 | `run_model_shard.py`는 중단해도 안전하다(부분 결과를 쓰지 않는다). GPU 있는 사람에게 넘겨라 |
| `revision: None` | `pip install huggingface_hub` 후 재실행. 없으면 재현성 기록이 비어 논문 부록에 쓸 수 없다 |
| 메모리 부족 | `experiment_validated_suite.py`의 `batch_size=32`를 8로 낮춰라. 결과는 동일하다 |
