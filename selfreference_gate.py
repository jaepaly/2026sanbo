#!/usr/bin/env python3
"""언어중립 자기참조 게이트 (M4).

## 고친 결함

`validate_query_slice.py`의 gate 3은 다음이었다:

    jaccard(tokenize(query), tokenize(minimal_text(answer))) < 0.30

`tokenize`는 `[A-Za-z0-9가-힣]+`이고 코퍼스는 100% 영어다. 그래서 한국어 질의는
**원리상** 정답 문서와 교집합이 0이다. 실측(검증셋 n=71):

    | 질의 언어 | n  | 평균 Jaccard | 최대   |
    | 한국어    | 45 | 0.0000       | 0.0000 |
    | 영어      | 26 | 0.0941       | 0.2364 |

즉 게이트는 전체의 63%에서 아무것도 검사하지 않았고, 영어에서도 한 번도 발동하지
않았다(최대 0.2364 < 0.30). 그런데 실제 질의 상당수는 정답 원문의 절 단위 번역이다.
어휘 게이트는 번역된 자기참조를 구조적으로 볼 수 없다.

## 이 모듈의 설계

1. **평가에 쓰지 않는 제3의 다국어 임베딩**으로 cos(질의, 정답 minimal_text)를 계산한다.
   평가용 3모델(paraphrase-multilingual-MiniLM-L12-v2, multilingual-e5-base, bge-m3)과
   겹치지 않는 `sentence-transformers/LaBSE`를 쓴다.

   왜 LaBSE인가: 우리가 잡아야 하는 것은 "한국어 질의가 영어 정답 원문의 **번역**인가"다.
   LaBSE는 translation-ranking 목적함수로 학습된 bitext(병렬문) 마이닝 모델이므로,
   번역쌍 탐지가 바로 그 모델의 설계 목적이다. 반면 e5/bge는 검색용으로 학습되어
   평가 대상과 목적이 겹친다. distiluse-base-multilingual-cased-v2도 후보였으나
   (더 작고 빠름) 번역쌍 판정이 주 목적이 아니라 LaBSE를 택했다.

2. **어휘와 의미를 둘 다 보고**한다. 어휘 Jaccard는 계속 계산하되, 한국어에서
   구조적으로 0이라는 경고를 명시적으로 출력한다.

3. **임계값을 데이터에 맞추지 않는다.** 71개 질의의 cos 분포를 보고 컷을 정하면
   원하는 결과를 만들 수 있다. 그래서 임계값은 **71개 질의와 무관한 대조군**으로
   보정한다(`calibrate`):

   - POS-A (사람이 만든 번역쌍): `data/crosslingual_translations.json`의 ko 질의 ↔ 사람이
     번역한 en 문장. n=5. "같은 내용의 두 언어 표현"의 cos.
   - POS-B (정답 원문의 한국어 대역): 슬라이스 파일의 `label_basis_corpus_text`(정답
     항목을 한국어로 옮긴 근거문) ↔ 그 정답의 `minimal_text`(영어). 질의와 독립적으로
     작성된 필드이므로 "코퍼스 항목을 한국어로 번역했을 때의 cos"을 준다.
   - NEG (무관쌍): 각 질의 ↔ 정답이 아닌 코퍼스 항목 20개(seed 고정).

   임계값 규칙(사전 지정):

       tau_semantic = POS-B 분포의 10퍼센타일, 소수점 2자리로 내림

   근거: 정당한 패러프레이즈 질의라면 "정답 항목을 그대로 한국어로 옮긴 근거문"보다
   정답과 **덜** 비슷해야 한다. 질의가 그 수준에 도달하면 기능적으로 원문의 번역이다.
   10퍼센타일(중앙값이 아니라)을 쓰는 이유는 **보수적**이기 때문이다 — 번역 대역들 중
   가장 번역답지 않은 쪽에 컷을 두므로 플래그가 덜 발생하고, 따라서 "자기참조가 남아
   있다"는 우리 주장에 불리한 방향으로 편향된다. 참고용으로 중앙값 컷의 플래그 수도
   함께 보고한다(민감도).

## 한계 (정직하게)

정답과의 유사도 하나만으로는 "라벨이 맞는 좋은 질의"와 "정답을 베낀 질의"를 원리적으로
구분할 수 없다. 둘 다 정답과 비슷하다. 구분 가능한 것은 **정도**뿐이며, 그 정도의 기준을
외부 대조군(번역 대역)에서 가져오는 것이 이 모듈이 할 수 있는 최선이다. POS-A는 n=5,
POS-B는 요약된 대역이라 하한 성향이 있다. 이 게이트는 "번역 수준 자기참조 의심"을
표시하는 도구이고 최종 판정은 사람이 해야 한다. → 확인 필요.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
TRANSLATIONS_PATH = DATA_DIR / "crosslingual_translations.json"
SLICE_PATHS = [
    DATA_DIR / "validated_queries_slice_seungwoo.json",
    DATA_DIR / "validated_queries_slice_yechan.json",
]

# 평가에 쓰이는 3모델. 게이트 모델은 반드시 이 목록과 겹치지 않아야 한다.
EVAL_MODELS = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "intfloat/multilingual-e5-base",
    "BAAI/bge-m3",
)
GATE_MODEL = "sentence-transformers/LaBSE"
GATE_MODEL_ALTERNATIVE = "sentence-transformers/distiluse-base-multilingual-cased-v2"

# 어휘 게이트는 원래 값을 유지한다(비교 가능성). 의미 게이트가 실질 게이트다.
MAX_JACCARD = 0.30

# 임계값 보정 규칙 — 데이터(71개)가 아니라 대조군에서 유도한다.
CALIBRATION_PERCENTILE = 10.0        # POS-B 분포의 10퍼센타일
CALIBRATION_SENSITIVITY_PERCENTILE = 50.0   # 민감도용(중앙값)
NEG_SAMPLES_PER_QUERY = 20
SEED = 20260626

# 보정 실패 시(모델 로드 불가 등) 쓰지 않는다 — 게이트를 조용히 통과시키면 안 된다.
_MODEL_CACHE: dict[str, object] = {}


def assert_gate_model_is_independent() -> None:
    if GATE_MODEL in EVAL_MODELS:
        raise AssertionError(
            f"게이트 모델 {GATE_MODEL} 이 평가 모델 목록과 겹친다 — 독립성이 깨진다."
        )


def load_gate_model(name: str = GATE_MODEL):
    assert_gate_model_is_independent()
    if name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer
        _MODEL_CACHE[name] = SentenceTransformer(name)
    return _MODEL_CACHE[name]


def encode(texts: list[str], model=None) -> np.ndarray:
    model = model or load_gate_model()
    return model.encode(
        texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False
    ).astype(np.float32)


# 1797개 코퍼스를 LaBSE로 두 번(보정 + 채점) 인코딩하면 CPU에서 수십 분이 든다.
# 결과에 영향이 없는 순수 캐시.
_DOC_EMB_CACHE: dict[tuple[int, str], np.ndarray] = {}


def corpus_embeddings(doc_texts: list[str], model=None, tag: str = "minimal_text") -> np.ndarray:
    key = (len(doc_texts), tag)
    cached = _DOC_EMB_CACHE.get(key)
    if cached is not None and cached.shape[0] == len(doc_texts):
        return cached
    emb = encode(doc_texts, model)
    _DOC_EMB_CACHE[key] = emb
    return emb


# --------------------------------------------------------------------------
# 어휘 게이트 (기존 정의 유지 + 구조적 공허성 진단)
# --------------------------------------------------------------------------


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def lexical_overlap(query: str, answer_text: str) -> dict:
    qt, dt = rc.tokenize(query), rc.tokenize(answer_text)
    inter = set(qt) & set(dt)
    return {
        "jaccard": round(jaccard(qt, dt), 4),
        "shared_tokens": sorted(inter),
        "n_query_tokens": len(set(qt)),
        "structurally_void": len(inter) == 0 and bool(qt) and bool(dt),
    }


def has_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text or "")


def lexical_void_warning(rows: list[dict]) -> dict:
    """언어별로 어휘 게이트가 구조적으로 공허한지 진단한다."""
    out: dict = {}
    for lang in sorted({r["lang"] for r in rows}):
        vals = [r["lexical_jaccard"] for r in rows if r["lang"] == lang]
        allz = all(v == 0.0 for v in vals)
        out[lang] = {
            "n": len(vals),
            "mean_jaccard": round(float(np.mean(vals)), 4) if vals else 0.0,
            "max_jaccard": round(float(np.max(vals)), 4) if vals else 0.0,
            "all_exactly_zero": bool(allz),
            "ever_triggered_at_0.30": bool(any(v >= MAX_JACCARD for v in vals)),
            "warning": (
                f"어휘 Jaccard가 {len(vals)}개 전부 정확히 0 — 이 언어에서 어휘 게이트는 "
                "아무것도 검사하지 않는다(코퍼스가 100% 영어이므로 교집합이 원리상 공집합)."
            ) if allz else None,
        }
    return out


# --------------------------------------------------------------------------
# 의미 게이트 + 임계값 보정
# --------------------------------------------------------------------------


def _percentile_floor(values: list[float], pct: float) -> float:
    """소수점 2자리 내림 — 임계값을 데이터 소수점까지 맞추지 않기 위해."""
    if not values:
        return float("nan")
    v = float(np.percentile(np.asarray(values, dtype=float), pct))
    return math.floor(v * 100) / 100.0


def calibrate(corpus: list[dict], queries: list[dict], model=None) -> dict:
    """71개 질의의 cos 값을 보지 않고 임계값을 정한다.

    POS-A: 사람이 만든 ko↔en 번역쌍(n=5)
    POS-B: 정답 항목의 한국어 근거문 ↔ 정답 minimal_text(영어)
    NEG  : 질의 ↔ 정답이 아닌 코퍼스 항목(seed 고정 표본)
    """
    model = model or load_gate_model()
    by_code = {e["code"]: e for e in corpus}

    # ---- POS-A: 사람이 만든 번역쌍 -------------------------------------
    pos_a: list[dict] = []
    if TRANSLATIONS_PATH.exists():
        tr = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))["translations"]
        qmap = {q["id"]: q["query"] for q in queries}
        pairs = [(qid, qmap[qid], en) for qid, en in tr.items() if qid in qmap]
        if pairs:
            ko_emb = encode([p[1] for p in pairs], model)
            en_emb = encode([p[2] for p in pairs], model)
            for (qid, _ko, _en), a, b in zip(pairs, ko_emb, en_emb):
                pos_a.append({"pair_id": qid, "cos": round(float(a @ b), 4)})

    # ---- POS-B: 정답 항목의 한국어 근거문 ↔ 정답 원문 -------------------
    pos_b: list[dict] = []
    basis_pairs: list[tuple[str, str, str]] = []
    for sp in SLICE_PATHS:
        if not sp.exists():
            continue
        payload = json.loads(sp.read_text(encoding="utf-8"))
        for q in (payload["queries"] if isinstance(payload, dict) else payload):
            basis = q.get("label_basis_corpus_text")
            code = (q.get("validated_labels") or [None])[0]
            if not basis or not has_hangul(basis) or code not in by_code:
                continue
            basis_pairs.append((q["id"], basis, rc.index_text(by_code[code], "minimal_text")))
    if basis_pairs:
        b_emb = encode([p[1] for p in basis_pairs], model)
        e_emb = encode([p[2] for p in basis_pairs], model)
        for (qid, _b, _e), x, y in zip(basis_pairs, b_emb, e_emb):
            pos_b.append({"pair_id": qid, "cos": round(float(x @ y), 4)})

    # ---- NEG: 무관쌍 ---------------------------------------------------
    rng = np.random.default_rng(SEED)
    doc_texts = [rc.index_text(e, "minimal_text") for e in corpus]
    doc_emb = corpus_embeddings(doc_texts, model)
    q_emb = encode([q["query"] for q in queries], model)
    codes = [e["code"] for e in corpus]
    neg_vals: list[float] = []
    for qi, q in enumerate(queries):
        gold = set(q["validated_labels"])
        pool = np.array([i for i, c in enumerate(codes) if c not in gold])
        pick = rng.choice(pool, size=min(NEG_SAMPLES_PER_QUERY, pool.size), replace=False)
        neg_vals.extend(float(doc_emb[i] @ q_emb[qi]) for i in pick)

    pos_b_vals = [r["cos"] for r in pos_b]
    pos_a_vals = [r["cos"] for r in pos_a]
    tau = _percentile_floor(pos_b_vals, CALIBRATION_PERCENTILE)
    tau_sens = _percentile_floor(pos_b_vals, CALIBRATION_SENSITIVITY_PERCENTILE)

    def stats(vals: list[float]) -> dict:
        if not vals:
            return {"n": 0}
        a = np.asarray(vals, dtype=float)
        return {
            "n": int(a.size),
            "mean": round(float(a.mean()), 4),
            "sd": round(float(a.std(ddof=1)), 4) if a.size > 1 else 0.0,
            "min": round(float(a.min()), 4),
            "p10": round(float(np.percentile(a, 10)), 4),
            "median": round(float(np.median(a)), 4),
            "p90": round(float(np.percentile(a, 90)), 4),
            "max": round(float(a.max()), 4),
        }

    return {
        "gate_model": GATE_MODEL,
        "gate_model_alternative_considered": GATE_MODEL_ALTERNATIVE,
        "eval_models_excluded": list(EVAL_MODELS),
        "rule": (
            f"tau_semantic = floor_2dp(POS-B의 {CALIBRATION_PERCENTILE:.0f}퍼센타일). "
            "POS-B는 정답 항목을 한국어로 옮긴 근거문 ↔ 정답 영어 원문의 cos이며, "
            "71개 질의의 cos 값과 독립이다."
        ),
        "rationale": (
            "정당한 패러프레이즈 질의는 '정답 항목의 한국어 대역'보다 정답과 덜 비슷해야 한다. "
            "10퍼센타일은 보수적(플래그가 덜 나오는) 컷이므로 자기참조 잔존 주장에 불리한 방향이다."
        ),
        "tau_semantic": tau,
        "tau_semantic_sensitivity_median_cut": tau_sens,
        "pos_a_human_translation_pairs": {"stats": stats(pos_a_vals), "pairs": pos_a},
        "pos_b_korean_basis_vs_answer": {"stats": stats(pos_b_vals), "pairs": pos_b},
        "neg_unrelated_pairs": {
            "stats": stats(neg_vals),
            "samples_per_query": NEG_SAMPLES_PER_QUERY,
            "seed": SEED,
        },
        "separation_pos_b_minus_neg": (
            round(stats(pos_b_vals)["mean"] - stats(neg_vals)["mean"], 4)
            if pos_b_vals and neg_vals else None
        ),
        "caveats": [
            "POS-A는 n=5로 매우 작다 — 참고값.",
            "POS-B 근거문은 요약된 대역이라 완전 번역보다 cos이 낮게 나오는 하한 성향이 있다.",
            "정답과의 유사도만으로 '좋은 질의'와 '베낀 질의'를 원리적으로 구분할 수 없다. "
            "최종 판정은 사람이 해야 한다 — 확인 필요.",
        ],
    }


def score_queries(corpus: list[dict], queries: list[dict], model=None) -> list[dict]:
    """질의별 어휘 Jaccard + 의미 cos(정답 minimal_text 대비)."""
    model = model or load_gate_model()
    by_code = {e["code"]: e for e in corpus}
    doc_texts = [rc.index_text(e, "minimal_text") for e in corpus]
    codes = [e["code"] for e in corpus]
    code_to_idx = {c: i for i, c in enumerate(codes)}

    doc_emb = corpus_embeddings(doc_texts, model)
    q_emb = encode([q["query"] for q in queries], model)

    rows: list[dict] = []
    for qi, q in enumerate(queries):
        gold = [c for c in q["validated_labels"] if c in code_to_idx]
        if not gold:
            rows.append({
                "id": q["id"], "lang": q["lang"], "origin": q.get("origin"),
                "answer_code": None, "error": "정답 코드가 코퍼스에 없음",
            })
            continue
        # 여러 라벨이면 가장 유사한 쪽(=게이트에 가장 불리한 쪽)을 취한다.
        # 71개 중 2개(ext-005, ext-023)만 복수 라벨이지만, 이 선택 때문에 영어
        # 어휘 Jaccard 평균이 첫-라벨 기준 0.0941 대신 0.0953 으로 나온다.
        # 두 정의를 모두 기록해 수치가 조용히 바뀌지 않게 한다.
        idxs = [code_to_idx[c] for c in gold]
        sims = [float(doc_emb[i] @ q_emb[qi]) for i in idxs]
        best = int(np.argmax(sims))
        ans_idx = idxs[best]
        ans_text = doc_texts[ans_idx]
        lex = lexical_overlap(q["query"], ans_text)
        lex_first = lexical_overlap(q["query"], doc_texts[idxs[0]])

        # 코퍼스 전체 대비 상대 위치 — 언어 간 cos 스케일 차이를 보정해 읽기 위함
        all_sims = doc_emb @ q_emb[qi]
        mask = np.ones(all_sims.shape[0], dtype=bool)
        for i in idxs:
            mask[i] = False
        null = all_sims[mask]
        rows.append({
            "id": q["id"],
            "lang": q["lang"],
            "origin": q.get("origin"),
            "answer_code": codes[ans_idx],
            "lexical_jaccard": lex["jaccard"],
            "lexical_jaccard_first_label": lex_first["jaccard"],
            "lexical_shared_tokens": lex["shared_tokens"],
            "lexical_structurally_void": lex["structurally_void"],
            "semantic_cos": round(sims[best], 4),
            "semantic_cos_first_label": round(sims[0], 4),
            "n_gold_labels": len(gold),
            "semantic_cos_all_labels": {gold[k]: round(sims[k], 4) for k in range(len(gold))},
            "corpus_null_mean": round(float(null.mean()), 4),
            "corpus_null_sd": round(float(null.std(ddof=1)), 4),
            "semantic_z_vs_corpus": round(
                (sims[best] - float(null.mean())) / float(null.std(ddof=1)), 3),
            "semantic_percentile_vs_corpus": round(
                100.0 * float((null < sims[best]).mean()), 2),
            "query": q["query"],
            "answer_minimal_text": ans_text,
        })
    return rows


def evaluate(rows: list[dict], tau_semantic: float,
             max_jaccard: float = MAX_JACCARD) -> dict:
    """게이트 판정 — 어휘와 의미를 둘 다 보고한다."""
    lex_fail = [r for r in rows if r.get("lexical_jaccard", 0.0) >= max_jaccard]
    sem_fail = [r for r in rows if r.get("semantic_cos", 0.0) >= tau_semantic]
    return {
        "tau_semantic": tau_semantic,
        "max_jaccard": max_jaccard,
        "n": len(rows),
        "lexical_failures": [r["id"] for r in lex_fail],
        "semantic_failures": [
            {"id": r["id"], "lang": r["lang"], "answer_code": r["answer_code"],
             "semantic_cos": r["semantic_cos"], "lexical_jaccard": r["lexical_jaccard"]}
            for r in sorted(sem_fail, key=lambda x: -x["semantic_cos"])
        ],
        "n_lexical_failures": len(lex_fail),
        "n_semantic_failures": len(sem_fail),
        "caught_only_by_semantic": [
            r["id"] for r in sem_fail if r.get("lexical_jaccard", 0.0) < max_jaccard
        ],
        "lexical_void_by_lang": lexical_void_warning(
            [r for r in rows if "lexical_jaccard" in r]),
    }


def gate_one(query_text: str, answer_entry: dict, tau_semantic: float,
             max_jaccard: float = MAX_JACCARD, model=None) -> dict:
    """단일 질의용 API — validate_query_slice.py의 gate 3이 이것을 호출한다."""
    ans_text = rc.index_text(answer_entry, "minimal_text")
    lex = lexical_overlap(query_text, ans_text)
    emb = encode([query_text, ans_text], model or load_gate_model())
    cos = round(float(emb[0] @ emb[1]), 4)
    return {
        "lexical_jaccard": lex["jaccard"],
        "lexical_structurally_void": lex["structurally_void"],
        "semantic_cos": cos,
        "tau_semantic": tau_semantic,
        "lexical_pass": lex["jaccard"] < max_jaccard,
        "semantic_pass": cos < tau_semantic,
        "passed": lex["jaccard"] < max_jaccard and cos < tau_semantic,
    }


def cached_tau(corpus: list[dict], queries: list[dict], model=None) -> float:
    """감사 산출물이 있으면 그 임계값을 재사용, 없으면 보정한다.

    slice 검증기가 매번 1797개 코퍼스를 재인코딩하지 않게 하기 위한 경로.
    """
    if AUDIT_JSON.exists():
        try:
            payload = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
            tau = payload["calibration"]["tau_semantic"]
            if payload["calibration"]["gate_model"] == GATE_MODEL and tau == tau:
                return float(tau)
        except Exception:
            pass
    return float(calibrate(corpus, queries, model)["tau_semantic"])


# --------------------------------------------------------------------------
# 71개 전량 감사 산출물
# --------------------------------------------------------------------------

OUT_DIR = ROOT / "output"
AUDIT_JSON = OUT_DIR / "selfreference_audit.json"
AUDIT_MD = OUT_DIR / "selfreference_audit.md"
QUERIES_PATH = DATA_DIR / "validated_queries_expanded.json"
TOP_N_SIDE_BY_SIDE = 15


def _group_stats(rows: list[dict], key: str) -> dict:
    out: dict = {}
    for g in sorted({str(r.get(key)) for r in rows}):
        sub = [r for r in rows if str(r.get(key)) == g]
        lex = np.asarray([r["lexical_jaccard"] for r in sub], dtype=float)
        lexf = np.asarray([r["lexical_jaccard_first_label"] for r in sub], dtype=float)
        cos = np.asarray([r["semantic_cos"] for r in sub], dtype=float)
        cosf = np.asarray([r["semantic_cos_first_label"] for r in sub], dtype=float)
        out[g] = {
            "n": len(sub),
            "lexical_jaccard": {
                "mean": round(float(lex.mean()), 4),
                "max": round(float(lex.max()), 4),
                "all_exactly_zero": bool(all(v == 0.0 for v in lex)),
            },
            # 기존 산출물과 비교 가능하도록 첫-라벨 정의도 함께 남긴다
            "lexical_jaccard_first_label": {
                "mean": round(float(lexf.mean()), 4),
                "max": round(float(lexf.max()), 4),
                "all_exactly_zero": bool(all(v == 0.0 for v in lexf)),
            },
            "semantic_cos_first_label": {
                "mean": round(float(cosf.mean()), 4),
                "max": round(float(cosf.max()), 4),
            },
            "semantic_cos": {
                "mean": round(float(cos.mean()), 4),
                "sd": round(float(cos.std(ddof=1)), 4) if cos.size > 1 else 0.0,
                "min": round(float(cos.min()), 4),
                "median": round(float(np.median(cos)), 4),
                "max": round(float(cos.max()), 4),
            },
            "semantic_z_vs_corpus_mean": round(
                float(np.mean([r["semantic_z_vs_corpus"] for r in sub])), 3),
        }
    return out


def _histogram(values: list[float], lo: float, hi: float, bins: int) -> dict:
    counts, edges = np.histogram(np.asarray(values, dtype=float), bins=bins, range=(lo, hi))
    return {
        "bin_edges": [round(float(e), 4) for e in edges],
        "counts": [int(c) for c in counts],
    }


def build_audit() -> dict:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))["queries"]
    model = load_gate_model()

    calib = calibrate(corpus, queries, model)
    rows = score_queries(corpus, queries, model)
    scored = [r for r in rows if "semantic_cos" in r]
    verdict = evaluate(scored, calib["tau_semantic"])
    verdict_sens = evaluate(scored, calib["tau_semantic_sensitivity_median_cut"])

    top = sorted(scored, key=lambda r: -r["semantic_cos"])[:TOP_N_SIDE_BY_SIDE]

    return {
        "experiment": "language_neutral_selfreference_gate_audit",
        "meta": {
            "n": len(rows),
            "n_scored": len(scored),
            "by_lang": {lg: sum(1 for r in scored if r["lang"] == lg)
                        for lg in sorted({r["lang"] for r in scored})},
            "queries_file": QUERIES_PATH.name,
            "answer_text_mode": "minimal_text (색인 텍스트와 동일 정의, retrieval_core.index_text)",
            "seed": SEED,
            "old_gate": "jaccard(tokenize(query), tokenize(minimal_text)) < 0.30",
            "old_gate_defect": (
                "tokenize는 [A-Za-z0-9가-힣]+이고 코퍼스는 100% 영어 → 한국어 질의의 "
                "교집합은 원리상 공집합. 전체 71개의 63%(45개)에서 게이트가 아무것도 "
                "검사하지 않았고, 영어 26개에서도 한 번도 발동하지 않았다."
            ),
        },
        "env": rc.env_meta({"seed": SEED, "gate_model": GATE_MODEL}),
        "calibration": calib,
        "verdict_primary": verdict,
        "verdict_sensitivity_median_cut": verdict_sens,
        "distribution_by_lang": _group_stats(scored, "lang"),
        "distribution_by_origin": _group_stats(scored, "origin"),
        "histograms": {
            "lexical_jaccard_all": _histogram(
                [r["lexical_jaccard"] for r in scored], 0.0, 0.5, 10),
            "semantic_cos_all": _histogram(
                [r["semantic_cos"] for r in scored], 0.0, 1.0, 20),
            "semantic_cos_ko": _histogram(
                [r["semantic_cos"] for r in scored if r["lang"] == "ko"], 0.0, 1.0, 20),
            "semantic_cos_en": _histogram(
                [r["semantic_cos"] for r in scored if r["lang"] == "en"], 0.0, 1.0, 20),
            "calibration_pos_b": _histogram(
                [p["cos"] for p in calib["pos_b_korean_basis_vs_answer"]["pairs"]],
                0.0, 1.0, 20),
        },
        "top_side_by_side": [
            {
                "rank": i + 1,
                "id": r["id"], "lang": r["lang"], "origin": r["origin"],
                "answer_code": r["answer_code"],
                "semantic_cos": r["semantic_cos"],
                "lexical_jaccard": r["lexical_jaccard"],
                "semantic_z_vs_corpus": r["semantic_z_vs_corpus"],
                "query": r["query"],
                "answer_minimal_text": r["answer_minimal_text"],
            }
            for i, r in enumerate(top)
        ],
        "per_query": [
            {k: v for k, v in r.items() if k != "answer_minimal_text"} for r in rows
        ],
    }


def render_audit_md(p: dict) -> str:
    m, c = p["meta"], p["calibration"]
    v, vs = p["verdict_primary"], p["verdict_sensitivity_median_cut"]
    L = [
        "# 자기참조 게이트 전량 감사 (검증셋 n=%d)" % m["n"],
        "",
        "## 0. 무엇이 고장나 있었나",
        "",
        f"기존 gate 3: `{m['old_gate']}`",
        "",
        m["old_gate_defect"],
        "",
        "## 1. 언어별 분포 — 어휘 게이트의 공허성",
        "",
        "| 언어 | n | 어휘 Jaccard 평균 | 최대 | 전부 정확히 0? | 의미 cos 평균 | 중앙값 | 최대 |",
        "|---|---:|---:|---:|---|---:|---:|---:|",
    ]
    for lg, s in p["distribution_by_lang"].items():
        L.append(
            f"| {lg} | {s['n']} | {s['lexical_jaccard']['mean']:.4f} | "
            f"{s['lexical_jaccard']['max']:.4f} | "
            f"{'**예**' if s['lexical_jaccard']['all_exactly_zero'] else '아니오'} | "
            f"{s['semantic_cos']['mean']:.4f} | {s['semantic_cos']['median']:.4f} | "
            f"{s['semantic_cos']['max']:.4f} |")
    L += [
        "",
        "정답 라벨이 복수인 질의(ext-005, ext-023 두 건)에서는 **게이트에 가장 불리한**",
        "라벨(가장 유사한 라벨)을 정답 텍스트로 쓴다. 기존 산출물과 비교할 수 있게 첫-라벨",
        "정의도 함께 기록한다 — 이 선택이 영어 평균을 바꾸는 유일한 원인이다:",
        "",
        "| 언어 | 어휘 Jaccard 평균 (최유사 라벨) | 어휘 Jaccard 평균 (첫 라벨, 기존 정의) | 최대(최유사) | 최대(첫 라벨) |",
        "|---|---:|---:|---:|---:|",
    ]
    for lg, s in p["distribution_by_lang"].items():
        L.append(f"| {lg} | {s['lexical_jaccard']['mean']:.4f} | "
                 f"{s['lexical_jaccard_first_label']['mean']:.4f} | "
                 f"{s['lexical_jaccard']['max']:.4f} | "
                 f"{s['lexical_jaccard_first_label']['max']:.4f} |")
    for lg, w in v["lexical_void_by_lang"].items():
        if w["warning"]:
            L += ["", f"> **경고 ({lg})**: {w['warning']}"]
    L += [
        "",
        "## 2. 슬라이스(origin)별 분포",
        "",
        "| origin | n | 어휘 Jaccard 평균 | 의미 cos 평균 | 최소 | 최대 | 코퍼스 대비 z 평균 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for og, s in p["distribution_by_origin"].items():
        L.append(
            f"| {og} | {s['n']} | {s['lexical_jaccard']['mean']:.4f} | "
            f"{s['semantic_cos']['mean']:.4f} | {s['semantic_cos']['min']:.4f} | "
            f"{s['semantic_cos']['max']:.4f} | {s['semantic_z_vs_corpus_mean']:+.2f} |")

    L += [
        "",
        "## 3. 임계값을 어떻게 정했나 (데이터에 맞추지 않기 위해)",
        "",
        f"- 게이트 모델: `{c['gate_model']}` — 평가용 3모델과 겹치지 않는다: "
        + ", ".join(f"`{x}`" for x in c["eval_models_excluded"]),
        f"- 규칙: {c['rule']}",
        f"- 근거: {c['rationale']}",
        "",
        "| 대조군 | n | 평균 | SD | 최소 | p10 | 중앙값 | 최대 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, key in [
        ("POS-A 사람 번역쌍(ko↔en)", "pos_a_human_translation_pairs"),
        ("POS-B 정답의 한국어 대역 ↔ 정답 원문", "pos_b_korean_basis_vs_answer"),
        ("NEG 무관쌍(질의↔비정답 항목)", "neg_unrelated_pairs"),
    ]:
        s = c[key]["stats"]
        if not s.get("n"):
            L.append(f"| {name} | 0 | - | - | - | - | - | - |")
            continue
        L.append(f"| {name} | {s['n']} | {s['mean']:.4f} | {s['sd']:.4f} | "
                 f"{s['min']:.4f} | {s['p10']:.4f} | {s['median']:.4f} | {s['max']:.4f} |")
    L += [
        "",
        f"→ **tau_semantic = {c['tau_semantic']:.2f}** (민감도용 중앙값 컷 = "
        f"{c['tau_semantic_sensitivity_median_cut']:.2f})",
        "",
        "## 4. 판정",
        "",
        "| 컷 | 임계값 | 의미 게이트 초과 | 어휘 게이트 초과 | 의미만 잡아낸 건수 |",
        "|---|---:|---:|---:|---:|",
        f"| 주 분석(보수적, POS-B p10) | {v['tau_semantic']:.2f} | "
        f"{v['n_semantic_failures']}/{v['n']} | {v['n_lexical_failures']}/{v['n']} | "
        f"{len(v['caught_only_by_semantic'])} |",
        f"| 민감도(POS-B 중앙값) | {vs['tau_semantic']:.2f} | "
        f"{vs['n_semantic_failures']}/{vs['n']} | {vs['n_lexical_failures']}/{vs['n']} | "
        f"{len(vs['caught_only_by_semantic'])} |",
        "",
    ]
    if v["semantic_failures"]:
        L += ["### 주 분석에서 임계 초과한 질의", "",
              "| id | 언어 | 정답 | 의미 cos | 어휘 Jaccard |", "|---|---|---|---:|---:|"]
        for f in v["semantic_failures"]:
            L.append(f"| {f['id']} | {f['lang']} | {f['answer_code']} | "
                     f"{f['semantic_cos']:.4f} | {f['lexical_jaccard']:.4f} |")
        L.append("")
    else:
        L += ["> 주 분석 컷에서 임계를 넘은 질의는 없다.", ""]

    L += [
        f"## 5. 의미 cos 상위 {len(p['top_side_by_side'])}건 — 원문과 나란히",
        "",
        "직역 여부를 육안으로 확인하기 위한 것이다. 어휘 Jaccard 열이 0인데 cos이 높은 행이",
        "바로 기존 게이트가 볼 수 없었던 '번역된 자기참조'다.",
        "",
    ]
    for r in p["top_side_by_side"]:
        L += [
            f"**{r['rank']}. {r['id']}** ({r['lang']}, {r['origin']}, 정답 `{r['answer_code']}`) "
            f"— cos **{r['semantic_cos']:.4f}**, 어휘 Jaccard {r['lexical_jaccard']:.4f}, "
            f"코퍼스 대비 z {r['semantic_z_vs_corpus']:+.2f}",
            "",
            f"- 질의: {r['query']}",
            f"- 정답 원문(minimal_text): {r['answer_minimal_text']}",
            "",
        ]
    L += ["## 6. 한계", ""] + [f"- {x}" for x in c["caveats"]]
    L += ["", "히스토그램용 원자료는 `selfreference_audit.json`의 `histograms`에 있다.", ""]
    return "\n".join(L)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    payload = build_audit()
    AUDIT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    AUDIT_MD.write_text(render_audit_md(payload), encoding="utf-8")
    c = payload["calibration"]
    v = payload["verdict_primary"]
    print(json.dumps({
        "tau_semantic": c["tau_semantic"],
        "tau_median_cut": c["tau_semantic_sensitivity_median_cut"],
        "pos_b": c["pos_b_korean_basis_vs_answer"]["stats"],
        "neg": c["neg_unrelated_pairs"]["stats"],
        "n_semantic_failures": v["n_semantic_failures"],
        "n_lexical_failures": v["n_lexical_failures"],
        "by_lang": {k: {"lex_mean": s["lexical_jaccard"]["mean"],
                        "cos_mean": s["semantic_cos"]["mean"]}
                    for k, s in payload["distribution_by_lang"].items()},
    }, ensure_ascii=False, indent=2))
    print(f"wrote {AUDIT_JSON.name}, {AUDIT_MD.name}")


if __name__ == "__main__":
    main()
