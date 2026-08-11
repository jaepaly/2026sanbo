#!/usr/bin/env python3
"""Consolidated, pre-registered evaluation of the validated query set (n=151).

Query set: `data/validated_queries_expanded.json`, 151 queries (42 English /
109 Korean). Corpus: `data/corpus/combined.json`, corpus v2 = 1,783 entries
(eCFR 637 + India SCOMET 578 + Wassenaar 568), 100% English.

Supersedes the overlapping logic in `evaluate_validated_queries.py`,
`build_expanded_validated.py`, `experiment_embedding_robustness.py` and
`experiment_exposure_frontier_validated.py`, all four of which reimplemented the
same pipeline with slightly different bugs. Closes these audit findings:

C1  Ranking was `np.argsort(-scores)`. For most Korean queries BM25 scores are
    identically zero (no in-vocabulary overlap with a 100%-English corpus), so
    "top-10" was corpus rows 0-9 and a gold label in row 4 scored as a hit. At
    n=151 the no-signal count is 95 of the 109 Korean queries at
    index=full_text and 96 of 109 at minimal_text / minimal_no_code; no English
    query is ever no-signal. (The n=71 edition reported 44 of 45 Korean.) The
    live counts are re-derived every run into
    `diagnostics[index_mode].bm25_no_signal_queries`. Ranking is now
    deterministic and a no-signal query retrieves nothing.

M1  `hybrid vs dense` was never tested at n=71 -- every reported comparison was
    against BM25 -- while the paper claims hybrid retrieval is what is needed.
    All three pairwise contrasts are now computed for every dense model, and the
    degenerate identity (when BM25 is all-zero, any alpha<1 ranks exactly like
    dense) is measured rather than assumed.

M2  The n=71 edition's headline "29 wins 0 losses" aggregated over both
    languages; 26 of those wins were Korean queries where BM25 returned nothing
    at all. At n=151 the same hybrid-vs-BM25 contrast (MiniLM) is 61 wins /
    1 loss at index=full_text, 57 of the wins Korean, and 54 / 0 at
    minimal_text, 51 of them Korean -- the aggregation problem is unchanged in
    kind, only larger. Subgroup contrasts with exact McNemar are now
    first-class output.

M3  Equivalence was declared whenever a CI happened to contain zero, which is
    accepting the null. A margin delta is pre-specified below, TOST is run, and
    the sample size needed for a tighter margin is reported.

M6  Exposure is now derived from the text actually returned, and index mode is
    separated from return mode, so `(index=minimal_text, return=minimal_no_code)`
    -- disclose less without degrading the index -- becomes measurable.

PRE-SPECIFICATION (fixed before running; do not tune to the result)
    Primary equivalence margin  delta = 0.05
        Rationale: the tool is a pre-screening aid whose output is a candidate
        list for a human reviewer. If cutting disclosure raises the miss rate at
        top-10 by 5 percentage points or more, the reduced disclosure is not
        acceptable. The remaining margins in SENSITIVITY_DELTAS below
        (0.03, 0.075, 0.10, 0.15) are reported as sensitivity only.
    Primary alpha for hybrid    0.5   (fixed in TASK E before this set existed)
    Bootstrap                   20,000 iterations, seed 20260626
    Multiplicity                Holm within each declared family

Outputs: output/validated_suite.json, output/validated_suite.md
"""

from __future__ import annotations

import json
import os
from itertools import product
from pathlib import Path

import numpy as np

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "validated_queries_expanded.json"
JSON_PATH = OUT_DIR / "validated_suite.json"
MD_PATH = OUT_DIR / "validated_suite.md"

INDEX_MODES = ["full_text", "minimal_text", "minimal_no_code"]
RETURN_MODES = ["full_text", "minimal_text", "minimal_no_code"]
ALPHAS = [1.0, 0.7, 0.5, 0.3, 0.0]
PRIMARY_ALPHA = 0.5
PRIMARY_DELTA = 0.05
SENSITIVITY_DELTAS = [0.03, 0.05, 0.075, 0.10, 0.15]
BOOTSTRAP_ITERS = 20000
SEED = 20260626

DENSE_MODELS = {
    "MiniLM": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "e5-base": "intfloat/multilingual-e5-base",
    "bge-m3": "BAAI/bge-m3",
}
PRIMARY_MODEL = "MiniLM"

# Smoke-test escape hatch: SANBO_MODELS=MiniLM runs one encoder so a code change
# can be validated in a minute instead of an hour. Full runs use all three.
if os.environ.get("SANBO_MODELS"):
    _keep = [k.strip() for k in os.environ["SANBO_MODELS"].split(",") if k.strip()]
    DENSE_MODELS = {k: v for k, v in DENSE_MODELS.items() if k in _keep}
    PRIMARY_MODEL = _keep[0]
    JSON_PATH = OUT_DIR / "validated_suite_smoke.json"
    MD_PATH = OUT_DIR / "validated_suite_smoke.md"


def resolved_revision(model_name: str) -> str | None:
    """Recover the exact HF commit sha a model resolved to, for the record."""
    try:
        from huggingface_hub import HfApi
        return HfApi().model_info(model_name).sha
    except Exception:
        try:
            from huggingface_hub.constants import HF_HUB_CACHE
            slug = "models--" + model_name.replace("/", "--")
            snaps = Path(HF_HUB_CACHE) / slug / "snapshots"
            if snaps.is_dir():
                return sorted(p.name for p in snaps.iterdir())[-1]
        except Exception:
            pass
    return None


def alpha_name(a: float) -> str:
    if a == 1.0:
        return "BM25"
    if a == 0.0:
        return "dense"
    return f"hybrid_{a}"


def run_model(model_key: str, corpus: list[dict], queries: list[dict]) -> dict:
    """Per-query hit@10 vectors for every (index_mode, alpha) pair."""
    from sentence_transformers import SentenceTransformer

    name = DENSE_MODELS[model_key]
    model = SentenceTransformer(name)
    codes = [e["code"] for e in corpus]
    qtexts = [q["query"] for q in queries]
    label_sets = [set(q["validated_labels"]) for q in queries]

    hits: dict[str, dict[str, list[int]]] = {}
    diagnostics: dict[str, dict] = {}
    exposure: dict[str, dict] = {}

    for imode in INDEX_MODES:
        docs = [rc.index_text(e, imode) for e in corpus]
        index = rc.BM25(docs)
        # 배치 크기는 임베딩 값에 영향을 주지 않는다(같은 문장 → 같은 벡터).
        # bge-m3 는 8GB VRAM 에서 batch 32 로 OOM 이 나므로 환경변수로 낮춘다.
        _bs = int(os.environ.get("SANBO_BATCH", "32"))
        doc_emb = model.encode(docs, batch_size=_bs, normalize_embeddings=True,
                               show_progress_bar=False).astype(np.float32)
        q_emb = model.encode(qtexts, batch_size=_bs, normalize_embeddings=True,
                             show_progress_bar=False).astype(np.float32)

        per_alpha = {alpha_name(a): [] for a in ALPHAS}
        bm25_no_signal = 0
        rank1_ties = 0
        dense_equals_hybrid = {alpha_name(a): 0 for a in ALPHAS if a not in (1.0, 0.0)}
        # exposure@10 follows this model's own ranking, so it belongs to the shard
        exp_sums = {rmode: [] for rmode in RETURN_MODES}
        exp_legacy: list[int] = []

        for qi in range(len(queries)):
            raw_bm = index.scores(qtexts[qi])
            signal = rc.has_signal(raw_bm)
            if not signal:
                bm25_no_signal += 1
            bm = rc.minmax(raw_bm)
            dn = rc.minmax(doc_emb @ q_emb[qi])

            dense_rank = rc.rank_indices(rc.blend(bm, dn, 0.0))
            for a in ALPHAS:
                scores = rc.blend(bm, dn, a)
                # BM25 alone with no lexical overlap retrieves nothing at all
                if a == 1.0 and not signal:
                    top10 = []
                else:
                    ranked = rc.rank_indices(scores)
                    top10 = list(ranked[:10])
                    if a not in (1.0, 0.0) and list(ranked[:10]) == list(dense_rank[:10]):
                        dense_equals_hybrid[alpha_name(a)] += 1
                per_alpha[alpha_name(a)].append(
                    int(any(codes[i] in label_sets[qi] for i in top10))
                )

            primary_scores = rc.blend(bm, dn, PRIMARY_ALPHA)
            top_scores = np.sort(primary_scores)[::-1]
            if top_scores.size > 1 and abs(top_scores[0] - top_scores[1]) < 1e-12:
                rank1_ties += 1
            top10_primary = list(rc.rank_indices(primary_scores)[:10])
            for rmode in RETURN_MODES:
                exp_sums[rmode].append(
                    sum(rc.exposure_chars(corpus[i], rmode) for i in top10_primary))
            exp_legacy.append(
                sum(rc.legacy_exposure_chars(corpus[i], imode) for i in top10_primary))

        hits[imode] = per_alpha
        exposure[imode] = {
            **{f"return={rmode}": round(float(np.mean(exp_sums[rmode])), 1)
               for rmode in RETURN_MODES},
            "legacy_definition": round(float(np.mean(exp_legacy)), 1),
        }
        diagnostics[imode] = {
            "bm25_no_signal_queries": bm25_no_signal,
            "rank1_ties_at_primary_alpha": rank1_ties,
            "hybrid_top10_identical_to_dense": dense_equals_hybrid,
            "distinct_index_texts": len(set(docs)),
        }

    return {
        "model_key": model_key,
        "model_name": name,
        "revision": resolved_revision(name),
        "hits": hits,
        "exposure_at10": exposure,
        "diagnostics": diagnostics,
        "env": rc.env_meta({"seed": SEED}),
        "query_ids": [q["id"] for q in queries],
        "langs": [q["lang"] for q in queries],
        "corpus_size": len(corpus),
    }


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


def analyze(per_model: dict[str, dict], corpus: list[dict], queries: list[dict],
            primary_model: str | None = None) -> dict:
    """All statistics, given already-computed per-model hit vectors.

    Separated from the encoding step so a teammate can run one encoder on their
    own machine (`run_model_shard.py`) and the shards can be merged here without
    re-encoding anything (`merge_shards.py`).
    """
    primary_model = primary_model or (PRIMARY_MODEL if PRIMARY_MODEL in per_model
                                      else sorted(per_model)[0])
    langs = [q["lang"] for q in queries]
    n, n_en, n_ko = len(queries), langs.count("en"), langs.count("ko")
    model_keys = list(per_model)

    # ---------------------------------------------------------------- exposure
    exposure = {}
    for imode, rmode in product(INDEX_MODES, RETURN_MODES):
        prim = per_model[primary_model]["hits"][imode][alpha_name(PRIMARY_ALPHA)]
        exposure[f"{imode}|{rmode}"] = {
            "index_mode": imode,
            "return_mode": rmode,
            "mean_returned_chars_per_doc": round(
                float(np.mean([rc.exposure_chars(e, rmode) for e in corpus])), 2),
            "hybrid_recall@10": rc.rate_with_ci(prim)["rate"],
        }
    # exposure@10 follows the ranking, so it is taken from the primary model's shard
    exposure_at10 = per_model[primary_model]["exposure_at10"]

    # ------------------------------------------------------- retriever contrasts
    retriever = {}
    for model_key, payload in per_model.items():
        block = {"revision": payload["revision"], "diagnostics": payload["diagnostics"]}
        for imode in INDEX_MODES:
            h = payload["hits"][imode]
            rates = {}
            for a in ALPHAS:
                nm = alpha_name(a)
                rates[nm] = {
                    "overall": rc.rate_with_ci(h[nm]),
                    "en": rc.rate_with_ci(subgroup(h[nm], langs, "en")),
                    "ko": rc.rate_with_ci(subgroup(h[nm], langs, "ko")),
                }
            prim = alpha_name(PRIMARY_ALPHA)
            contrasts = {}
            pfam = {}
            for lang in (None, "en", "ko"):
                tag = lang or "overall"
                for (x, y, label) in [
                    (prim, "BM25", "hybrid_vs_bm25"),
                    ("dense", "BM25", "dense_vs_bm25"),
                    (prim, "dense", "hybrid_vs_dense"),   # M1: never tested before
                ]:
                    c = contrast(subgroup(h[x], langs, lang), subgroup(h[y], langs, lang),
                                 f"{label}[{tag}]")
                    contrasts[f"{label}[{tag}]"] = c
                    pfam[f"{label}[{tag}]"] = c["p_two_sided_exact"]
            block[imode] = {
                "recall@10": rates,
                "contrasts": contrasts,
                "holm_within_index_mode": rc.holm(pfam),
            }
        retriever[model_key] = block

    # -------------------------------------------------- equivalence (disclosure)
    prim = alpha_name(PRIMARY_ALPHA)
    base = per_model[primary_model]["hits"]["full_text"][prim]
    equivalence = {}
    eq_pfam = {}
    for imode in INDEX_MODES:
        if imode == "full_text":
            continue
        for retr in (prim, "dense", "BM25"):
            a = per_model[primary_model]["hits"][imode][retr]
            b = per_model[primary_model]["hits"]["full_text"][retr]
            diffs = [x - y for x, y in zip(a, b)]
            key = f"{imode}_vs_full_text[{retr}]"
            mc = rc.exact_mcnemar(a, b)
            equivalence[key] = {
                "paired_bootstrap": rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERS, seed=SEED),
                "mcnemar": mc,
                "tost": {f"delta={d}": rc.tost_paired(diffs, d, iters=BOOTSTRAP_ITERS, seed=SEED)
                         for d in SENSITIVITY_DELTAS},
                "primary_delta": PRIMARY_DELTA,
                "equivalent_at_primary_delta": rc.tost_paired(
                    diffs, PRIMARY_DELTA, iters=BOOTSTRAP_ITERS, seed=SEED)["equivalent_at_0.05"],
                "n_required_for_primary_delta": rc.required_n_for_equivalence(diffs, PRIMARY_DELTA),
                "n_required_for_delta_0.03": rc.required_n_for_equivalence(diffs, 0.03),
            }
            eq_pfam[key] = mc["p_two_sided_exact"]
    equivalence_holm = rc.holm(eq_pfam)

    out = {
        "meta": {
            "n": n, "n_en": n_en, "n_ko": n_ko,
            "index_modes": INDEX_MODES, "return_modes": RETURN_MODES,
            "alphas": ALPHAS, "primary_alpha": PRIMARY_ALPHA,
            "primary_equivalence_delta": PRIMARY_DELTA,
            "sensitivity_deltas": SENSITIVITY_DELTAS,
            "dense_models": {k: per_model[k]["model_name"] for k in model_keys},
            "primary_model": primary_model,
            "model_revisions": {k: per_model[k]["revision"] for k in model_keys},
            "bootstrap_iters": BOOTSTRAP_ITERS, "seed": SEED,
            "label_nature": "corpus-text-grounded category labels (exact eCFR codes); "
                            "not legal or expert determinations",
            "prespecified": "delta, primary alpha, bootstrap settings and the Holm "
                            "families were fixed in this file before the run; "
                            "sensitivity deltas are reported as sensitivity only",
        },
        "env": rc.env_meta({"seed": SEED}),
        "retriever": retriever,
        "exposure_per_doc": exposure,
        "exposure_at10": exposure_at10,
        "equivalence": equivalence,
        "equivalence_holm": equivalence_holm,
        "hit_vectors": {
            mk: {im: per_model[mk]["hits"][im] for im in INDEX_MODES} for mk in model_keys
        },
        "langs": langs,
        "query_ids": [q["id"] for q in queries],
    }
    return out


def write_outputs(out: dict, json_path: Path = None, md_path: Path = None) -> None:
    json_path = json_path or JSON_PATH
    md_path = md_path or MD_PATH
    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_md(out), encoding="utf-8")
    print(f"\nwrote {json_path.name}, {md_path.name}")


def main() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))["queries"]

    per_model: dict[str, dict] = {}
    for key in DENSE_MODELS:
        print(f"[{key}] encoding ...", flush=True)
        per_model[key] = run_model(key, corpus, queries)

    write_outputs(analyze(per_model, corpus, queries))


def render_md(out: dict) -> str:
    m = out["meta"]
    L = [
        f"# 검증셋 통합 평가 (n={m['n']}, 영어 {m['n_en']} / 한국어 {m['n_ko']})",
        "",
        "사전지정: 등가성 마진 δ=%.2f, 기본 α=%.1f, bootstrap %d회(seed %d). "
        "민감도 δ는 민감도 분석으로만 보고한다."
        % (m["primary_equivalence_delta"], m["primary_alpha"], m["bootstrap_iters"], m["seed"]),
        "",
        "라벨: 코퍼스 텍스트 근거 카테고리 라벨(법적·전문가 판정 아님).",
        "",
        "## 1. 진단 — BM25가 애초에 아무 신호도 내지 못하는 질의",
        "",
        "| 색인 모드 | BM25 무신호 질의 | 고유 색인문서 | hybrid top-10 = dense top-10 (α=0.5) |",
        "|---|---:|---:|---:|",
    ]
    diag = out["retriever"][m["primary_model"]]["diagnostics"]
    for im in m["index_modes"]:
        d = diag[im]
        same = d["hybrid_top10_identical_to_dense"].get("hybrid_0.5", 0)
        L.append(f"| {im} | {d['bm25_no_signal_queries']}/{m['n']} | "
                 f"{d['distinct_index_texts']} | {same}/{m['n']} |")
    L += [
        "",
        "> 무신호 질의는 어휘 교집합이 0이어서 top-10을 만들 수 없다. 이전 코드는 이 경우",
        "> 코퍼스 배열 앞머리를 결과로 집계했다.",
        "",
        "## 2. R@10 (95% CI = Clopper-Pearson)",
        "",
    ]
    for mk in m["dense_models"]:
        blk = out["retriever"][mk]
        L += [f"### {mk} (revision `{blk['revision']}`)", "",
              "| 색인 | retriever | 전체 R@10 | 95% CI | 영어 | 한국어 |",
              "|---|---|---:|---|---:|---:|"]
        for im in m["index_modes"]:
            for a in m["alphas"]:
                nm = alpha_name(a)
                r = blk[im]["recall@10"][nm]
                L.append(f"| {im} | {nm} | {r['overall']['rate']:.4f} | "
                         f"[{r['overall']['ci95'][0]:.3f}, {r['overall']['ci95'][1]:.3f}] | "
                         f"{r['en']['rate']:.4f} | {r['ko']['rate']:.4f} |")
        L.append("")

    L += ["## 3. 검색기 비교 (paired bootstrap + exact McNemar, Holm 보정)", "",
          "| 모델 | 색인 | 비교 | 평균차 | 95% CI | 승/패/무 | exact p | Holm p |",
          "|---|---|---|---:|---|---:|---:|---:|"]
    for mk in m["dense_models"]:
        for im in m["index_modes"]:
            blk = out["retriever"][mk][im]
            for key, c in blk["contrasts"].items():
                h = blk["holm_within_index_mode"][key]
                L.append(f"| {mk} | {im} | {key} | {c['mean_diff']:+.4f} | "
                         f"[{c['diff_95_ci'][0]:.4f}, {c['diff_95_ci'][1]:.4f}] | "
                         f"{c['wins']}/{c['losses']}/{c['ties']} | "
                         f"{c['p_two_sided_exact']:.3g} | {h['p_adjusted']:.3g} |")
    L += ["", "> `hybrid_vs_dense`는 기존 산출물에 한 번도 없던 비교다. BM25 점수가 항등 0인",
          "> 무신호 질의에서는 α<1의 랭킹이 dense와 수학적으로 동일하므로 그 질의들에서는",
          "> 승/패가 생길 수 없다(1절의 무신호 질의 수 = hybrid top-10 = dense top-10 건수).",
          "> n=71 판에서는 한국어 무신호가 45개 중 44개여서 한국어 승/패가 0/0으로 나왔으나,",
          "> n=151에서는 신호가 있는 한국어 질의가 남아 있어(109개 중 13~14개) 한국어에서도",
          "> 소수의 승/패가 나올 수 있다 — 다만 결론은 그대로다. 즉 '하이브리드가 필요하다'가",
          "> 아니라 'dense 성분이 필요하다'가 데이터가 지지하는 진술이다.", ""]

    L += ["## 4. 노출량@10 — 색인 모드 × 반환 모드", "",
          "| 색인 모드 | " + " | ".join(f"반환={r}" for r in m["return_modes"]) + " | 정정 전 정의 |",
          "|---" * (len(m["return_modes"]) + 2) + "|"]
    for im in m["index_modes"]:
        e = out["exposure_at10"][im]
        cells = " | ".join(f"{e[f'return={r}']:.0f}" for r in m["return_modes"])
        L.append(f"| {im} | {cells} | {e['legacy_definition']:.0f} |")
    L += ["", "> 정정 전 정의는 `minimal_text`와 `minimal_no_code`에 동일한 값을 부여했다.",
          "> 대각선이 아닌 칸(예: 색인=minimal_text, 반환=minimal_no_code)은 색인 품질을",
          "> 유지하면서 반환량만 줄이는 조건이며, 기존 설계로는 측정할 수 없었다.", ""]

    L += ["## 5. 정보최소화 등가성 검정 (TOST)", "",
          f"사전지정 마진 δ={m['primary_equivalence_delta']}. 'CI가 0을 포함' 은 등가성의 근거가 아니다.",
          "",
          "| 비교 | 평균차 | 95% CI | 승/패/무 | exact p | δ=0.05 등가? | δ=0.05 필요 n | δ=0.03 필요 n |",
          "|---|---:|---|---:|---:|---|---:|---:|"]
    for key, eq in out["equivalence"].items():
        b = eq["paired_bootstrap"]
        mc = eq["mcnemar"]
        t = eq["tost"]["delta=0.05"]
        L.append(f"| {key} | {b['mean']:+.4f} | [{b['ci'][0]:.4f}, {b['ci'][1]:.4f}] | "
                 f"{mc['wins']}/{mc['losses']}/{mc['ties']} | {mc['p_two_sided_exact']:.3g} | "
                 f"{'예' if t['equivalent_at_0.05'] else '**아니오**'} | "
                 f"{eq['n_required_for_primary_delta'] or '-'} | "
                 f"{eq['n_required_for_delta_0.03'] or '-'} |")
    L += ["", "### 마진별 민감도 (p_max, δ가 클수록 통과하기 쉬움)", "",
          "| 비교 | " + " | ".join(f"δ={d}" for d in m["sensitivity_deltas"]) + " |",
          "|---" * (len(m["sensitivity_deltas"]) + 1) + "|"]
    for key, eq in out["equivalence"].items():
        cells = []
        for d in m["sensitivity_deltas"]:
            t = eq["tost"][f"delta={d}"]
            mark = "" if t["equivalent_at_0.05"] else ""
            cells.append(f"{t['p_max']:.3g}{mark}")
        L.append(f"| {key} | " + " | ".join(cells) + " |")
    L += ["", "> p_max < 0.05 이면 해당 마진에서 등가(비열등)로 볼 수 있다. 표본이 작으면",
          "> 좁은 마진은 원리상 통과할 수 없으므로 '필요 n' 열을 함께 읽어야 한다.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
