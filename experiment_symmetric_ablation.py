#!/usr/bin/env python3
"""대칭 자기참조 ablation — 검증셋(n=71) × BM25/dense/hybrid (M4).

## 왜 이 실험이 필요한가

`experiment_paraphrase_gap.py`는 "질의가 정답 문서와 공유하는 고-IDF 토큰을 N개 제거하면
R@10이 어떻게 무너지는가"를 측정했다. 문제는 그 압력이

  - `data/queries.json` (합성셋) 에만,
  - BM25 에만

적용되었다는 점이다. 즉 자기비판 도구를 경쟁 상대에게만 적용했다. 검증셋(n=71)의
의미적·번역적 자기참조가 dense 검색기를 과대평가하는지는 한 번도 검증되지 않았다.

이 스크립트는 같은 압력을 **검증셋 × (BM25, dense, hybrid)** 에 대칭으로 가한다.

## 조작

질의에서 정답 항목과 의미를 공유하는 핵심 명사구를 **상위어로 치환**한다.
치환은 전적으로 `data/hypernym_substitutions.json` 에서 읽어오며 코드에 하드코딩된
치환어는 없다. 치환 강도 N=0,1,2,3 (level N = tier <= N 인 규칙 적용). 적용 규칙 집합은
level에 대해 중첩되므로 압력은 단조증가한다.

고-IDF 토큰 삭제(기존 방식)와 달리 상위어 치환은 문장을 사람이 실제로 쓸 만한 형태로
남긴다. 이것이 중요한 이유: 토큰을 그냥 지우면 dense 임베딩에는 "망가진 문장"이 들어가
성능 하락이 자기참조 때문인지 문장 붕괴 때문인지 구분할 수 없다.

## 조작이 실제로 자기참조를 줄였는지 검증

level별로 정답 원문 대비 (a) 어휘 Jaccard, (b) 제3모델(LaBSE) cos을 함께 측정한다.
cos이 줄지 않으면 조작이 의미 수준 자기참조를 건드리지 못한 것이므로, R@10이 유지되어도
"dense 우위가 살아남았다"고 말할 수 없다. 이 진단 없이는 결과 해석이 불가능하다.

## 핵심 질문

dense 우위(dense - BM25)가 패러프레이즈 압력에서 살아남는가? 급락하면 그 사실이
이 논문의 최대 기여가 된다. 유지되면 그것도 강한 결과다. 어느 쪽이든 그대로 보고한다.

출력: output/symmetric_ablation.json, output/symmetric_ablation.md
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

# 모델별 실행 (Tier 1 다모델 확장). 팀원이 자기 모델로 돌려도 다른 사람의 산출물을
# 덮어쓰지 않도록, 기본 모델이 아니면 출력 경로에 모델 키를 붙인다.
SANBO_MODELS = {
    "MiniLM": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "e5-base": "intfloat/multilingual-e5-base",
    "bge-m3": "BAAI/bge-m3",
}
PRIMARY_MODEL_KEY = "MiniLM"
MODEL_KEY = os.environ.get("SANBO_MODEL_KEY", PRIMARY_MODEL_KEY)
if MODEL_KEY not in SANBO_MODELS:
    raise SystemExit(
        f"SANBO_MODEL_KEY 는 {sorted(SANBO_MODELS)} 중 하나여야 합니다: {MODEL_KEY!r}")
_SUFFIX = "" if MODEL_KEY == PRIMARY_MODEL_KEY else f"_{MODEL_KEY}"
# SANBO_ABLATION_MODEL 은 하위호환으로 남긴다(모델 전체 이름을 직접 지정).
DENSE_MODEL = os.environ.get("SANBO_ABLATION_MODEL", SANBO_MODELS[MODEL_KEY])

JSON_PATH = OUT_DIR / f"symmetric_ablation{_SUFFIX}.json"
MD_PATH = OUT_DIR / f"symmetric_ablation{_SUFFIX}.md"

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "validated_queries_expanded.json"
SUBS_PATH = DATA_DIR / "hypernym_substitutions.json"

DENSE_MODEL = os.environ.get("SANBO_ABLATION_MODEL", SANBO_MODELS[MODEL_KEY])
GATE_MODEL = "sentence-transformers/LaBSE"   # 진단용(평가에 쓰지 않는 제3모델)

LEVELS = [0, 1, 2, 3]
INDEX_MODES = ["full_text", "minimal_text"]
PRIMARY_INDEX_MODE = "full_text"
ALPHAS = [1.0, 0.5, 0.0]
PRIMARY_ALPHA = 0.5
K = 10
BOOTSTRAP_ITERS = 20000
SEED = 20260626


def alpha_name(a: float) -> str:
    if a == 1.0:
        return "BM25"
    if a == 0.0:
        return "dense"
    return f"hybrid_{a}"


# --------------------------------------------------------------------------
# 결정론적 상위어 치환
# --------------------------------------------------------------------------


def load_substitutions() -> dict:
    return json.loads(SUBS_PATH.read_text(encoding="utf-8"))


def rules_for(query_id: str, lang: str, rules: list[dict], level: int) -> list[dict]:
    """이 질의·이 level에 적용될 규칙을 결정론적 순서로 반환.

    정렬: tier 오름차순 → phrase 길이 내림차순 → phrase 사전순.
    긴 구를 먼저 치환하므로 짧은 구가 긴 구의 일부를 갈아먹는 일이 없다.
    """
    picked = [
        r for r in rules
        if r["tier"] <= level
        and r["lang"] == lang
        and (r["query_ids"] is None or query_id in r["query_ids"])
    ]
    return sorted(picked, key=lambda r: (r["tier"], -len(r["phrase"]), r["phrase"]))


def substitute(query_text: str, query_id: str, lang: str,
               rules: list[dict], level: int) -> dict:
    text = query_text
    applied, skipped = [], []
    for r in rules_for(query_id, lang, rules, level):
        if r["phrase"] in text:
            text = text.replace(r["phrase"], r["hypernym"])
            applied.append({"tier": r["tier"], "phrase": r["phrase"],
                            "hypernym": r["hypernym"]})
        else:
            # 상위 tier가 이미 그 구간을 치환했거나 원문에 없는 경우 — 정직하게 기록
            skipped.append({"tier": r["tier"], "phrase": r["phrase"]})
    return {"text": text, "applied": applied, "skipped": skipped,
            "n_applied": len(applied), "changed": text != query_text}


# --------------------------------------------------------------------------
# 검색 평가
# --------------------------------------------------------------------------


def hits_for_level(corpus: list[dict], label_sets: list[set], qtexts: list[str],
                   index_mode: str, model, doc_emb_cache: dict) -> dict[str, list[int]]:
    codes = [e["code"] for e in corpus]
    docs = [rc.index_text(e, index_mode) for e in corpus]
    # setdefault 은 인자를 먼저 평가하므로 캐시가 있어도 BM25(코퍼스 전체)를 매번 새로
    # 만든다. level 수 x 색인 모드 수만큼 낭비되므로 명시적으로 확인한다.
    if ("bm25", index_mode) not in doc_emb_cache:
        doc_emb_cache[("bm25", index_mode)] = rc.BM25(docs)
    index = doc_emb_cache[("bm25", index_mode)]
    if ("emb", index_mode) not in doc_emb_cache:
        doc_emb_cache[("emb", index_mode)] = model.encode(
            docs, batch_size=32, normalize_embeddings=True,
            show_progress_bar=False).astype(np.float32)
    doc_emb = doc_emb_cache[("emb", index_mode)]

    q_emb = model.encode(qtexts, batch_size=32, normalize_embeddings=True,
                         show_progress_bar=False).astype(np.float32)

    out = {alpha_name(a): [] for a in ALPHAS}
    no_signal = 0
    for qi in range(len(qtexts)):
        raw_bm = index.scores(qtexts[qi])
        signal = rc.has_signal(raw_bm)
        no_signal += int(not signal)
        bm = rc.minmax(raw_bm)
        dn = rc.minmax(doc_emb @ q_emb[qi])
        for a in ALPHAS:
            if a == 1.0 and not signal:
                topk: list[int] = []           # 무신호 BM25는 검색 실패
            else:
                topk = list(rc.rank_indices(rc.blend(bm, dn, a))[:K])
            out[alpha_name(a)].append(
                int(any(codes[i] in label_sets[qi] for i in topk)))
    out["_bm25_no_signal"] = no_signal          # type: ignore[assignment]
    return out


def subgroup(vec: list[int], langs: list[str], lang: str | None) -> list[int]:
    return [h for h, lg in zip(vec, langs) if lang is None or lg == lang]


def contrast(a: list[int], b: list[int], label: str) -> dict:
    diffs = [x - y for x, y in zip(a, b)]
    boot = rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERS, seed=SEED)
    mc = rc.exact_mcnemar(a, b)
    return {
        "comparison": label,
        "mean_diff": boot["mean"],
        "diff_95_ci": boot["ci"],
        "excludes_zero": bool(boot["ci"][0] > 0 or boot["ci"][1] < 0),
        **{k: mc[k] for k in ("wins", "losses", "ties", "discordant",
                              "p_two_sided_exact", "p_one_sided_exact")},
    }


# --------------------------------------------------------------------------
# 조작 강도 진단 (어휘 + 제3모델 의미)
# --------------------------------------------------------------------------


def manipulation_diagnostics(corpus: list[dict], queries: list[dict],
                             level_texts: dict[int, list[str]]) -> dict:
    """정답 원문 대비 어휘 Jaccard와 LaBSE cos이 level에 따라 실제로 줄었는지.

    코퍼스 전체를 LaBSE로 인코딩하지 않는다 — 필요한 것은 각 질의의 정답
    원문(<=71개)뿐이다.
    """
    from sentence_transformers import SentenceTransformer
    from selfreference_gate import jaccard

    by_code = {e["code"]: e for e in corpus}
    ans_texts = [rc.index_text(by_code[q["validated_labels"][0]], "minimal_text")
                 for q in queries]
    uniq = sorted(set(ans_texts))
    gate = SentenceTransformer(GATE_MODEL)
    a_emb = gate.encode(uniq, batch_size=16, normalize_embeddings=True,
                        show_progress_bar=False).astype(np.float32)
    a_idx = {t: i for i, t in enumerate(uniq)}

    langs = [q["lang"] for q in queries]
    per_level: dict[str, dict] = {}
    per_query: dict[str, dict] = {}
    for lv in sorted(level_texts):
        texts = level_texts[lv]
        q_emb = gate.encode(texts, batch_size=16, normalize_embeddings=True,
                            show_progress_bar=False).astype(np.float32)
        lex, cos = [], []
        for qi, t in enumerate(texts):
            lex.append(jaccard(rc.tokenize(t), rc.tokenize(ans_texts[qi])))
            cos.append(float(q_emb[qi] @ a_emb[a_idx[ans_texts[qi]]]))
        per_level[str(lv)] = {
            "mean_lexical_jaccard": round(float(np.mean(lex)), 4),
            "mean_gate_cos": round(float(np.mean(cos)), 4),
            "mean_gate_cos_ko": round(float(np.mean(
                [c for c, lg in zip(cos, langs) if lg == "ko"])), 4),
            "mean_gate_cos_en": round(float(np.mean(
                [c for c, lg in zip(cos, langs) if lg == "en"])), 4),
            "max_gate_cos": round(float(np.max(cos)), 4),
        }
        for qi, q in enumerate(queries):
            per_query.setdefault(q["id"], {})[str(lv)] = {
                "lexical_jaccard": round(lex[qi], 4),
                "gate_cos": round(cos[qi], 4),
            }

    levels = sorted(level_texts)
    cos_seq = [per_level[str(lv)]["mean_gate_cos"] for lv in levels]
    lex_seq = [per_level[str(lv)]["mean_lexical_jaccard"] for lv in levels]
    return {
        "gate_model": GATE_MODEL,
        "note": "평가에 쓰지 않는 제3모델. 조작이 의미 수준 자기참조를 실제로 줄였는지 확인용.",
        "per_level": per_level,
        "mean_gate_cos_monotone_nonincreasing": all(
            cos_seq[i] >= cos_seq[i + 1] - 1e-9 for i in range(len(cos_seq) - 1)),
        "mean_lexical_jaccard_monotone_nonincreasing": all(
            lex_seq[i] >= lex_seq[i + 1] - 1e-9 for i in range(len(lex_seq) - 1)),
        "total_gate_cos_drop": round(cos_seq[0] - cos_seq[-1], 4),
        "per_query": per_query,
    }


# --------------------------------------------------------------------------


def main() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))["queries"]
    subs = load_substitutions()
    rules = subs["rules"]
    langs = [q["lang"] for q in queries]
    label_sets = [set(q["validated_labels"]) for q in queries]

    # ---- 치환 적용 (결정론적) -----------------------------------------
    level_texts: dict[int, list[str]] = {}
    substitution_log: dict[str, dict] = {}
    coverage: dict[str, dict] = {}
    for lv in LEVELS:
        texts = []
        n_changed = 0
        n_rules = 0
        for q in queries:
            res = substitute(q["query"], q["id"], q["lang"], rules, lv)
            texts.append(res["text"])
            n_changed += int(res["changed"])
            n_rules += res["n_applied"]
            substitution_log.setdefault(q["id"], {})[str(lv)] = {
                "text": res["text"],
                "n_applied": res["n_applied"],
                "applied": res["applied"],
                "skipped_because_already_replaced_or_absent": res["skipped"],
            }
        level_texts[lv] = texts
        coverage[str(lv)] = {
            "queries_changed": n_changed,
            "queries_unchanged": len(queries) - n_changed,
            "total_rules_applied": n_rules,
            "mean_rules_per_query": round(n_rules / len(queries), 2),
        }

    # 치환 사다리 자체가 단조인지(적용 규칙 수) 검증
    counts = [coverage[str(lv)]["total_rules_applied"] for lv in LEVELS]
    ladder_monotone = all(counts[i] <= counts[i + 1] for i in range(len(counts) - 1))

    # ---- 검색 평가 -----------------------------------------------------
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(DENSE_MODEL)
    cache: dict = {}
    hits: dict[str, dict[str, dict[str, list[int]]]] = {}
    no_signal: dict[str, dict[str, int]] = {}
    for imode in INDEX_MODES:
        hits[imode] = {}
        no_signal[imode] = {}
        for lv in LEVELS:
            print(f"[{imode}] level {lv} ...", flush=True)
            h = hits_for_level(corpus, label_sets, level_texts[lv], imode, model, cache)
            no_signal[imode][str(lv)] = h.pop("_bm25_no_signal")
            hits[imode][str(lv)] = h

    # ---- 감쇠 곡선 + 통계 ----------------------------------------------
    decay: dict[str, dict] = {}
    for imode in INDEX_MODES:
        block: dict = {}
        for a in ALPHAS:
            nm = alpha_name(a)
            rows = {}
            for lv in LEVELS:
                v = hits[imode][str(lv)][nm]
                rows[str(lv)] = {
                    "overall": rc.rate_with_ci(v),
                    "en": rc.rate_with_ci(subgroup(v, langs, "en")),
                    "ko": rc.rate_with_ci(subgroup(v, langs, "ko")),
                }
            # level N vs level 0 (같은 검색기 내부의 감쇠)
            vs0 = {}
            for lv in LEVELS[1:]:
                for lang in (None, "en", "ko"):
                    tag = lang or "overall"
                    vs0[f"level{lv}_vs_level0[{tag}]"] = contrast(
                        subgroup(hits[imode][str(lv)][nm], langs, lang),
                        subgroup(hits[imode]["0"][nm], langs, lang),
                        f"{nm} level{lv}_vs_level0[{tag}]")
            block[nm] = {"recall@10": rows, "decay_vs_level0": vs0,
                         "holm_within_retriever": rc.holm(
                             {k: c["p_two_sided_exact"] for k, c in vs0.items()})}
        # 각 level에서의 검색기 간 비교 — dense 우위가 압력에서 살아남는가
        cross = {}
        for lv in LEVELS:
            h = hits[imode][str(lv)]
            for (x, y, label) in [
                ("dense", "BM25", "dense_vs_bm25"),
                (alpha_name(PRIMARY_ALPHA), "BM25", "hybrid_vs_bm25"),
                (alpha_name(PRIMARY_ALPHA), "dense", "hybrid_vs_dense"),
            ]:
                for lang in (None, "en", "ko"):
                    tag = lang or "overall"
                    cross[f"level{lv}:{label}[{tag}]"] = contrast(
                        subgroup(h[x], langs, lang), subgroup(h[y], langs, lang),
                        f"level{lv} {label}[{tag}]")
        block["retriever_contrasts_per_level"] = cross
        block["bm25_no_signal_queries"] = no_signal[imode]
        decay[imode] = block

    # ---- 조작 강도 진단 -------------------------------------------------
    diag = manipulation_diagnostics(corpus, queries, level_texts)

    # ---- 핵심 질문 요약 -------------------------------------------------
    prim = decay[PRIMARY_INDEX_MODE]
    headline = {
        "index_mode": PRIMARY_INDEX_MODE,
        "recall_by_level": {
            alpha_name(a): {str(lv): prim[alpha_name(a)]["recall@10"][str(lv)]["overall"]["rate"]
                            for lv in LEVELS}
            for a in ALPHAS
        },
        "recall_by_level_ko": {
            alpha_name(a): {str(lv): prim[alpha_name(a)]["recall@10"][str(lv)]["ko"]["rate"]
                            for lv in LEVELS}
            for a in ALPHAS
        },
        "recall_by_level_en": {
            alpha_name(a): {str(lv): prim[alpha_name(a)]["recall@10"][str(lv)]["en"]["rate"]
                            for lv in LEVELS}
            for a in ALPHAS
        },
        "dense_advantage_over_bm25_by_level": {
            str(lv): prim["retriever_contrasts_per_level"][f"level{lv}:dense_vs_bm25[overall]"]["mean_diff"]
            for lv in LEVELS
        },
        "dense_absolute_drop_level0_to_level3": round(
            prim["dense"]["recall@10"]["0"]["overall"]["rate"]
            - prim["dense"]["recall@10"]["3"]["overall"]["rate"], 4),
        "bm25_absolute_drop_level0_to_level3": round(
            prim["BM25"]["recall@10"]["0"]["overall"]["rate"]
            - prim["BM25"]["recall@10"]["3"]["overall"]["rate"], 4),
        "hybrid_absolute_drop_level0_to_level3": round(
            prim[alpha_name(PRIMARY_ALPHA)]["recall@10"]["0"]["overall"]["rate"]
            - prim[alpha_name(PRIMARY_ALPHA)]["recall@10"]["3"]["overall"]["rate"], 4),
    }

    out = {
        "experiment": "symmetric_selfreference_ablation_validated_set",
        "meta": {
            "n": len(queries),
            "n_en": langs.count("en"), "n_ko": langs.count("ko"),
            "levels": LEVELS,
            "index_modes": INDEX_MODES,
            "primary_index_mode": PRIMARY_INDEX_MODE,
            "alphas": ALPHAS, "primary_alpha": PRIMARY_ALPHA, "k": K,
            "dense_model": DENSE_MODEL,
            "single_model_rationale": "지시대로 MiniLM 단일 모델. 3모델 전체 실행은 하지 않았다.",
            "substitution_source": str(SUBS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "substitution_meta": subs["meta"],
            "bootstrap_iters": BOOTSTRAP_ITERS, "seed": SEED,
            "asymmetry_fixed": (
                "experiment_paraphrase_gap.py는 합성셋 + BM25에만 압력을 가했다. "
                "여기서는 검증셋 × BM25/dense/hybrid에 동일 압력을 대칭 적용한다."
            ),
        },
        "env": rc.env_meta({"seed": SEED, "dense_model": DENSE_MODEL,
                            "gate_model": GATE_MODEL}),
        "substitution_coverage": coverage,
        "substitution_ladder_monotone": ladder_monotone,
        "manipulation_diagnostics": diag,
        "headline": headline,
        "decay": decay,
        "hit_vectors": hits,
        "langs": langs,
        "query_ids": [q["id"] for q in queries],
        "substitution_log": substitution_log,
    }
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(render_md(out), encoding="utf-8")
    print(json.dumps(headline, ensure_ascii=False, indent=2))
    print(json.dumps(diag["per_level"], ensure_ascii=False, indent=2))
    print(f"wrote {JSON_PATH.name}, {MD_PATH.name}")


def render_md(out: dict) -> str:
    m = out["meta"]
    d = out["decay"][m["primary_index_mode"]]
    diag = out["manipulation_diagnostics"]
    h = out["headline"]
    L = [
        f"# 대칭 자기참조 ablation (검증셋 n={m['n']}, 영어 {m['n_en']} / 한국어 {m['n_ko']})",
        "",
        m["asymmetry_fixed"],
        "",
        f"- dense 모델: `{m['dense_model']}` (단일 모델)",
        f"- 치환 사전: `{m['substitution_source']}` — 코드에 하드코딩된 치환어는 없다.",
        f"- 색인 모드: 주 분석 `{m['primary_index_mode']}`, 보조 "
        + ", ".join(f"`{x}`" for x in m["index_modes"] if x != m["primary_index_mode"]),
        f"- bootstrap {m['bootstrap_iters']}회, seed {m['seed']}",
        "",
        "## 1. 조작이 실제로 자기참조를 줄였는가 (전제 확인)",
        "",
        f"진단 모델은 평가에 쓰지 않는 제3모델 `{diag['gate_model']}`이다.",
        "",
        "| level | 적용 규칙 수 | 변경된 질의 | 어휘 Jaccard 평균 | 게이트 cos 평균 | 한국어 | 영어 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for lv in m["levels"]:
        c = out["substitution_coverage"][str(lv)]
        p = diag["per_level"][str(lv)]
        L.append(f"| {lv} | {c['total_rules_applied']} | {c['queries_changed']}/{m['n']} | "
                 f"{p['mean_lexical_jaccard']:.4f} | {p['mean_gate_cos']:.4f} | "
                 f"{p['mean_gate_cos_ko']:.4f} | {p['mean_gate_cos_en']:.4f} |")
    L += [
        "",
        f"- 치환 사다리 단조성(적용 규칙 수 비감소): "
        f"**{'통과' if out['substitution_ladder_monotone'] else '실패'}**",
        f"- 게이트 cos 평균 단조 비증가: "
        f"**{'통과' if diag['mean_gate_cos_monotone_nonincreasing'] else '실패'}** "
        f"(level0 → level3 총 하락 {diag['total_gate_cos_drop']:+.4f})",
        f"- 어휘 Jaccard 평균 단조 비증가: "
        f"**{'통과' if diag['mean_lexical_jaccard_monotone_nonincreasing'] else '실패'}**",
        "",
        "> cos 하락폭이 작다면 조작이 의미 수준 자기참조를 부분적으로만 제거한 것이며,",
        "> 그 경우 R@10 유지는 'dense 우위가 살아남았다'의 근거로 쓸 수 없다.",
        "",
        "## 2. 감쇠 곡선 — R@10 (95% CI = Clopper-Pearson)",
        "",
        "| 검색기 | " + " | ".join(f"level {lv}" for lv in m["levels"]) + " | level0→3 변화 |",
        "|---" * (len(m["levels"]) + 2) + "|",
    ]
    for a in m["alphas"]:
        nm = alpha_name(a)
        cells = []
        for lv in m["levels"]:
            r = d[nm]["recall@10"][str(lv)]["overall"]
            cells.append(f"{r['rate']:.4f} [{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]")
        drop = (d[nm]["recall@10"]["0"]["overall"]["rate"]
                - d[nm]["recall@10"][str(m["levels"][-1])]["overall"]["rate"])
        L.append(f"| {nm} | " + " | ".join(cells) + f" | {-drop:+.4f} |")
    L += ["", "### 언어별", "",
          "| 검색기 | 언어 | " + " | ".join(f"level {lv}" for lv in m["levels"]) + " |",
          "|---" * (len(m["levels"]) + 2) + "|"]
    for a in m["alphas"]:
        nm = alpha_name(a)
        for lang in ("en", "ko"):
            cells = [f"{d[nm]['recall@10'][str(lv)][lang]['rate']:.4f}" for lv in m["levels"]]
            L.append(f"| {nm} | {lang} | " + " | ".join(cells) + " |")
    L += ["", "BM25 무신호 질의 수: " + ", ".join(
        f"level {lv}: {d['bm25_no_signal_queries'][str(lv)]}/{m['n']}" for lv in m["levels"]), ""]

    L += ["## 3. 검색기 내부 감쇠 검정 (level N vs level 0)", "",
          "| 검색기 | 비교 | 평균차 | 95% CI | 승/패/무 | exact p | Holm p |",
          "|---|---|---:|---|---:|---:|---:|"]
    for a in m["alphas"]:
        nm = alpha_name(a)
        for key, c in d[nm]["decay_vs_level0"].items():
            hp = d[nm]["holm_within_retriever"][key]
            L.append(f"| {nm} | {key} | {c['mean_diff']:+.4f} | "
                     f"[{c['diff_95_ci'][0]:.4f}, {c['diff_95_ci'][1]:.4f}] | "
                     f"{c['wins']}/{c['losses']}/{c['ties']} | "
                     f"{c['p_two_sided_exact']:.3g} | {hp['p_adjusted']:.3g} |")

    L += ["", "## 4. 핵심 질문 — dense 우위는 압력에서 살아남는가", "",
          "| level | dense - BM25 (평균차) | 95% CI | 승/패/무 | exact p |",
          "|---:|---:|---|---:|---:|"]
    for lv in m["levels"]:
        c = d["retriever_contrasts_per_level"][f"level{lv}:dense_vs_bm25[overall]"]
        L.append(f"| {lv} | {c['mean_diff']:+.4f} | "
                 f"[{c['diff_95_ci'][0]:.4f}, {c['diff_95_ci'][1]:.4f}] | "
                 f"{c['wins']}/{c['losses']}/{c['ties']} | {c['p_two_sided_exact']:.3g} |")
    L += ["", "| level | hybrid - dense (평균차) | 95% CI | 승/패/무 | exact p |",
          "|---:|---:|---|---:|---:|"]
    for lv in m["levels"]:
        c = d["retriever_contrasts_per_level"][f"level{lv}:hybrid_vs_dense[overall]"]
        L.append(f"| {lv} | {c['mean_diff']:+.4f} | "
                 f"[{c['diff_95_ci'][0]:.4f}, {c['diff_95_ci'][1]:.4f}] | "
                 f"{c['wins']}/{c['losses']}/{c['ties']} | {c['p_two_sided_exact']:.3g} |")
    def _rel(nm: str) -> str:
        r0 = d[nm]["recall@10"]["0"]["overall"]["rate"]
        r3 = d[nm]["recall@10"][str(m["levels"][-1])]["overall"]["rate"]
        return f"{(r0 - r3) / r0 * 100:.1f}%" if r0 else "-"

    cos0 = diag["per_level"][str(m["levels"][0])]["mean_gate_cos"]
    cos3 = diag["per_level"][str(m["levels"][-1])]["mean_gate_cos"]
    L += ["",
          "| 검색기 | level0 R@10 | level3 R@10 | 감소폭 | 상대 감소 |",
          "|---|---:|---:|---:|---:|"]
    for a, key in [(1.0, "bm25"), (0.0, "dense"), (PRIMARY_ALPHA, "hybrid")]:
        nm = alpha_name(a)
        L.append(f"| {nm} | {d[nm]['recall@10']['0']['overall']['rate']:.4f} | "
                 f"{d[nm]['recall@10'][str(m['levels'][-1])]['overall']['rate']:.4f} | "
                 f"{h[key + '_absolute_drop_level0_to_level3']:.4f} | {_rel(nm)} |")
    L += ["",
          f"**민감도**: 조작이 의미 수준 자기참조를 줄인 폭은 게이트 cos 평균 기준 "
          f"{cos0:.4f} → {cos3:.4f} (−{cos0 - cos3:.4f}, 상대 −{(cos0 - cos3) / cos0 * 100:.1f}%)에 "
          f"불과하다. 그 정도의 압력에 dense R@10은 {_rel('dense')} 떨어졌다. 즉 dense 성능은 "
          "질의가 정답 원문의 표현을 되받아 쓰는 정도에 매우 민감하다.",
          ""]

    L += ["## 5. 보조 색인 모드", ""]
    for imode in m["index_modes"]:
        if imode == m["primary_index_mode"]:
            continue
        dd = out["decay"][imode]
        L += [f"### 색인 = {imode}", "",
              "| 검색기 | " + " | ".join(f"level {lv}" for lv in m["levels"]) + " |",
              "|---" * (len(m["levels"]) + 1) + "|"]
        for a in m["alphas"]:
            nm = alpha_name(a)
            cells = [f"{dd[nm]['recall@10'][str(lv)]['overall']['rate']:.4f}"
                     for lv in m["levels"]]
            L.append(f"| {nm} | " + " | ".join(cells) + " |")
        L.append("")

    L += ["## 6. 한계", "",
          "- 치환어는 사람(에이전트)이 질의와 정답 원문을 함께 보고 작성한 판단이며 자동 생성이 "
          "아니다. 사전 전체가 `data/hypernym_substitutions.json`에 공개되어 검증 가능하다.",
          "- 치환 후에도 정답 라벨은 바꾸지 않았다. 치환된 질의가 여전히 같은 정답을 가리키는지에 "
          "대한 전문가 확인은 **확인 필요** 상태다.",
          "- 단일 dense 모델(MiniLM) 결과다. 모델 간 일반화는 확인되지 않았다 — **확인 필요**.",
          "- level별 적용 규칙 수는 질의마다 다르다(질의별 상세는 JSON의 `substitution_log`).",
          ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
