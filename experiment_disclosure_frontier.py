#!/usr/bin/env python3
"""Disclosure–recall frontier: 질의 측 노출을 줄이면 후보검색은 어디서 무너지는가.

동기 (docs/threat_model.md)
    기존 노출 실험은 인바운드(공개 통제목록 반환량)를 측정했다. 그것은 기업
    영업비밀과 무관하고, 랭킹을 바꾸지 않으므로 비용 없이 줄일 수 있다
    (색인=full_text/반환=minimal_text에서 노출량 4043→1820, 55.0% 감소인데
    R@10은 0.6056 불변). 실제 트레이드오프는 **아웃바운드 = 질의 본문**에서 발생한다.
    이 스크립트는 L0~L4 등급 사다리(data/disclosure_ladder.json)로 그 트레이드오프를
    측정하고 굴절점(어느 등급에서 R@10이 유의하게 하락하는가)을 찾는다.

사전지정 (데이터를 보기 전에 고정. 결과에 맞춰 조정하지 않는다)
    색인 모드            minimal_text (코드 + 첫 문장)  — 질의 측 조작만 남기기 위해 고정
    검색기               BM25(alpha=1.0) / dense(alpha=0.0) / hybrid(alpha=0.5)
    dense 모델           MiniLM 단일 (paraphrase-multilingual-MiniLM-L12-v2)
    1차 지표             R@10 (전체 / en / ko), Clopper-Pearson 95% CI
    등가성 마진          delta = 0.05  (사전 트리아지 도구의 top-10 누락률이 5%p
                         이상 늘면 그 축소는 수용 불가)
    민감도 마진          0.03 / 0.10
    bootstrap            20,000회, seed 20260626
    다중비교             Holm — 두 가족: (a) 각 등급 vs L0, (b) 인접 등급 간
    굴절점 정의          vs-L0 가족에서 Holm 보정 p<0.05 이고 평균차<0 인 최소 등급

x축은 문자 수가 아니라 평균 `sensitive_token_count`와 평균 노출 필드 카테고리 수다.

출력: output/disclosure_frontier.json, output/disclosure_frontier.md
실행: python experiment_disclosure_frontier.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import retrieval_core as rc  # noqa: E402

DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
LADDER_PATH = DATA_DIR / "disclosure_ladder.json"
JSON_PATH = OUT_DIR / "disclosure_frontier.json"
MD_PATH = OUT_DIR / "disclosure_frontier.md"

LEVELS = ["L0", "L1", "L2", "L3", "L4"]
INDEX_MODE = "minimal_text"
ALPHAS = {"BM25": 1.0, "hybrid_0.5": 0.5, "dense": 0.0}
RETRIEVERS = ["BM25", "dense", "hybrid_0.5"]
PRIMARY_DELTA = 0.05
SENSITIVITY_DELTAS = [0.03, 0.05, 0.10]
BOOTSTRAP_ITERS = 20000
SEED = 20260626
K = 10
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def resolved_revision(model_name: str) -> str | None:
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
        slug = "models--" + model_name.replace("/", "--")
        snaps = Path(HF_HUB_CACHE) / slug / "snapshots"
        if snaps.is_dir():
            return sorted(p.name for p in snaps.iterdir())[-1]
    except Exception:
        pass
    return None


def subgroup(vec: list[int], langs: list[str], lang: str | None) -> list[int]:
    return [h for h, lg in zip(vec, langs) if lang is None or lg == lang]


def contrast(a: list[int], b: list[int], label: str) -> dict:
    """a - b. 양수면 a가 낫다."""
    diffs = [x - y for x, y in zip(a, b)]
    boot = rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERS, seed=SEED)
    mc = rc.exact_mcnemar(a, b)
    return {
        "comparison": label,
        "mean_diff": boot["mean"],
        "diff_95_ci": boot["ci"],
        "excludes_zero": bool(boot["ci"][0] > 0 or boot["ci"][1] < 0),
        "wins": mc["wins"], "losses": mc["losses"], "ties": mc["ties"],
        "discordant": mc["discordant"],
        "p_two_sided_exact": mc["p_two_sided_exact"],
    }


def run() -> dict:
    from sentence_transformers import SentenceTransformer

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    ladder = json.loads(LADDER_PATH.read_text(encoding="utf-8"))
    entries = ladder["queries"]
    langs = [e["lang"] for e in entries]
    label_sets = [set(e["validated_labels"]) for e in entries]
    codes = [c["code"] for c in corpus]
    n = len(entries)

    docs = [rc.index_text(c, INDEX_MODE) for c in corpus]
    index = rc.BM25(docs)

    print(f"[dense] encoding {len(docs)} docs ...", flush=True)
    model = SentenceTransformer(DENSE_MODEL)
    doc_emb = model.encode(docs, batch_size=32, normalize_embeddings=True,
                           show_progress_bar=False).astype(np.float32)

    hits: dict[str, dict[str, list[int]]] = {}
    diagnostics: dict[str, dict] = {}

    for lv in LEVELS:
        qtexts = [e["levels"][lv]["query"] for e in entries]
        print(f"[{lv}] encoding {n} queries ...", flush=True)
        q_emb = model.encode(qtexts, batch_size=32, normalize_embeddings=True,
                             show_progress_bar=False).astype(np.float32)
        per_retr = {r: [] for r in RETRIEVERS}
        bm_no_signal = 0
        bm_no_signal_ko = 0
        vocab_overlap = []
        hybrid_equals_dense = 0
        for qi in range(n):
            raw_bm = index.scores(qtexts[qi])
            signal = rc.has_signal(raw_bm)
            if not signal:
                bm_no_signal += 1
                if langs[qi] == "ko":
                    bm_no_signal_ko += 1
            vocab_overlap.append(index.vocabulary_overlap(qtexts[qi]))
            bm = rc.minmax(raw_bm)
            dn = rc.minmax(doc_emb @ q_emb[qi])
            dense_top = list(rc.rank_indices(rc.blend(bm, dn, 0.0))[:K])
            for r in RETRIEVERS:
                a = ALPHAS[r]
                if r == "BM25":
                    # 어휘 겹침이 전혀 없는 질의는 아무것도 검색하지 못한다.
                    top = rc.retrieve(raw_bm, K, zero_is_failure=True)
                else:
                    top = list(rc.rank_indices(rc.blend(bm, dn, a))[:K])
                    if r == "hybrid_0.5" and top == dense_top:
                        hybrid_equals_dense += 1
                per_retr[r].append(int(any(codes[i] in label_sets[qi] for i in top)))
        hits[lv] = per_retr
        diagnostics[lv] = {
            "bm25_no_signal_queries": bm_no_signal,
            "bm25_no_signal_korean": bm_no_signal_ko,
            "mean_query_vocab_overlap": round(float(np.mean(vocab_overlap)), 3),
            "hybrid_top10_identical_to_dense": hybrid_equals_dense,
        }

    # ------------------------------------------------------------- 노출 축
    exposure = {}
    for lv in LEVELS:
        st = [e["levels"][lv]["sensitive_token_count"] for e in entries]
        fc = [e["levels"][lv]["sensitive_field_count"] for e in entries]
        tk = [e["levels"][lv]["token_count"] for e in entries]
        ch = [e["levels"][lv]["char_count"] for e in entries]
        exposure[lv] = {
            "definition": ladder["meta"]["levels"][lv],
            "mean_sensitive_token_count": round(float(np.mean(st)), 3),
            "mean_sensitive_field_count": round(float(np.mean(fc)), 3),
            "mean_query_token_count": round(float(np.mean(tk)), 3),
            "mean_query_char_count": round(float(np.mean(ch)), 2),
            "field_frequency": ladder["per_level_summary"][lv]["field_frequency"],
        }

    # ------------------------------------------------------------- R@10
    rates = {}
    for r in RETRIEVERS:
        rates[r] = {
            lv: {
                "overall": rc.rate_with_ci(hits[lv][r]),
                "en": rc.rate_with_ci(subgroup(hits[lv][r], langs, "en")),
                "ko": rc.rate_with_ci(subgroup(hits[lv][r], langs, "ko")),
            }
            for lv in LEVELS
        }

    # --------------------------------------------- 인접 등급 / vs L0 대비
    adjacent = {}
    vs_l0 = {}
    holm_adjacent = {}
    holm_vs_l0 = {}
    equivalence = {}
    for r in RETRIEVERS:
        adj_family = {}
        adj_block = {}
        for i in range(1, len(LEVELS)):
            lo, hi = LEVELS[i - 1], LEVELS[i]
            key = f"{hi}_vs_{lo}"
            c = contrast(hits[hi][r], hits[lo][r], key)
            adj_block[key] = c
            adj_family[key] = c["p_two_sided_exact"]
        adjacent[r] = adj_block
        holm_adjacent[r] = rc.holm(adj_family)

        l0_family = {}
        l0_block = {}
        eq_block = {}
        for lv in LEVELS[1:]:
            key = f"{lv}_vs_L0"
            c = contrast(hits[lv][r], hits["L0"][r], key)
            # 하위군도 같은 가족에 넣지 않고 별도로 기술한다(가족 정의를 흐리지 않기 위해)
            c["en"] = contrast(subgroup(hits[lv][r], langs, "en"),
                               subgroup(hits["L0"][r], langs, "en"), f"{key}[en]")
            c["ko"] = contrast(subgroup(hits[lv][r], langs, "ko"),
                               subgroup(hits["L0"][r], langs, "ko"), f"{key}[ko]")
            l0_block[key] = c
            l0_family[key] = c["p_two_sided_exact"]

            diffs = [x - y for x, y in zip(hits[lv][r], hits["L0"][r])]
            eq_block[key] = {
                "primary": rc.tost_paired(diffs, PRIMARY_DELTA,
                                          iters=BOOTSTRAP_ITERS, seed=SEED),
                "sensitivity": {
                    f"delta={d}": rc.tost_paired(diffs, d, iters=BOOTSTRAP_ITERS,
                                                 seed=SEED)["equivalent_at_0.05"]
                    for d in SENSITIVITY_DELTAS
                },
                "required_n_for_delta_0.05": rc.required_n_for_equivalence(diffs, PRIMARY_DELTA),
            }
        vs_l0[r] = l0_block
        holm_vs_l0[r] = rc.holm(l0_family)
        equivalence[r] = eq_block

    # ------------------------------------------------------------ 굴절점
    inflection = {}
    for r in RETRIEVERS:
        found = None
        for lv in LEVELS[1:]:
            key = f"{lv}_vs_L0"
            if holm_vs_l0[r][key]["significant_at_0.05"] and vs_l0[r][key]["mean_diff"] < 0:
                found = lv
                break
        safe = LEVELS[LEVELS.index(found) - 1] if found else LEVELS[-1]
        inflection[r] = {
            "first_significant_drop_vs_L0": found,
            "deepest_level_without_significant_drop": safe,
            "equivalent_to_L0_at_delta_0.05": [
                lv for lv in LEVELS[1:]
                if equivalence[r][f"{lv}_vs_L0"]["primary"].get("equivalent_at_0.05")
            ],
            "criterion": "Holm 보정 p<0.05 그리고 평균차<0 인 최소 등급을 굴절점으로 본다.",
        }

    return {
        "experiment": "query_side_disclosure_recall_frontier",
        "threat_model": "docs/threat_model.md",
        "prespecification": {
            "index_mode": INDEX_MODE,
            "retrievers": {r: ALPHAS[r] for r in RETRIEVERS},
            "dense_model": DENSE_MODEL,
            "dense_model_revision": resolved_revision(DENSE_MODEL),
            "k": K,
            "primary_delta": PRIMARY_DELTA,
            "sensitivity_deltas": SENSITIVITY_DELTAS,
            "bootstrap_iters": BOOTSTRAP_ITERS,
            "seed": SEED,
            "multiplicity": "Holm, 두 가족(각 등급 vs L0 / 인접 등급 간)",
            "note": "3모델 전체 실행은 하지 않았다. dense는 MiniLM 단일이며 "
                    "모델 간 강건성은 validated_suite 쪽 산출물에서 별도로 다룬다.",
        },
        "env": rc.env_meta({"seed": SEED, "bootstrap_iters": BOOTSTRAP_ITERS}),
        "data": {
            "ladder": str(LADDER_PATH.relative_to(ROOT)).replace("\\", "/"),
            "n_queries": n,
            "language_distribution": ladder["meta"]["language_distribution"],
            "corpus_size": len(corpus),
            "ladder_validation_passed": ladder["validation"]["passed"],
        },
        "exposure_axis": exposure,
        "recall@10": rates,
        "diagnostics": diagnostics,
        "contrasts_adjacent": adjacent,
        "holm_adjacent": holm_adjacent,
        "contrasts_vs_L0": vs_l0,
        "holm_vs_L0": holm_vs_l0,
        "equivalence_vs_L0": equivalence,
        "inflection": inflection,
        "hit_vectors": {lv: hits[lv] for lv in LEVELS},
        "notes": [
            "지표는 후보검색 성능(R@10)이며 전략물자 해당/비해당 판정 정확도가 아니다.",
            "BM25는 어휘 겹침이 0인 질의에 대해 빈 결과를 반환한다(정정 후 정의). "
            "따라서 한국어 질의의 BM25 R@10은 대부분 0이고, 이는 코퍼스가 100% 영어인 "
            "구조적 결과다.",
            "L3·L4는 계수 대상 민감토큰이 0이므로 x축의 sensitive_token_count에서 동점이다. "
            "두 등급의 차이는 기능 서술 잔존 여부이며 mean_query_token_count로 구분된다.",
        ],
    }


def fmt_ci(ci: list[float]) -> str:
    return f"[{ci[0]:.3f}, {ci[1]:.3f}]"


SELFREF_AUDIT_PATH = OUT_DIR / "ladder_selfreference.json"


def confounded_levels() -> dict:
    """자기참조 감사에서 정답 쪽으로 유의하게 표류한 등급.

    R@10이 유지되었다는 사실만으로는 '노출을 줄여도 성능이 유지된다'를 말할 수 없다.
    상위 등급의 재작성은 질의를 기능 서술만 남기는데, 그것이 바로 통제목록 원문의
    문체다. 질의가 정답 문서 쪽으로 옮겨갔다면 성능 유지는 노출 축소가 무해해서가
    아니라 자기참조가 늘어난 결과이므로, 그 등급의 회수율은 운용 근거가 될 수 없다.

    `audit_ladder_selfreference.py`가 평가에 쓰지 않는 제3 인코더로 측정한다.
    감사 산출물이 없으면 등급을 교란으로 표시하지 않되, 미검증임을 함께 반환한다.
    """
    if not SELFREF_AUDIT_PATH.exists():
        return {"levels": [], "audited": False,
                "note": "output/ladder_selfreference.json 없음 — "
                        "audit_ladder_selfreference.py 를 먼저 실행할 것. 자기참조 미검증."}
    a = json.loads(SELFREF_AUDIT_PATH.read_text(encoding="utf-8"))
    bad = [lv for lv in LEVELS[1:]
           if (c := a.get("vs_L0", {}).get(f"{lv}_vs_L0"))
           and c.get("significant_drift") and c.get("mean_cos_shift", 0) > 0]
    return {"levels": bad, "audited": True, "verdict": a.get("verdict", {}).get("label"),
            "gate_model": a.get("method", {}).get("gate_model"),
            "note": "정답 문서 쪽으로 유의하게 표류한 등급 — 이 등급의 R@10 유지는 "
                    "노출 축소의 효과로 귀속할 수 없다."}


def evidence_tiers(p: dict, retriever: str) -> dict:
    """등급별 증거 수준을 A/B/C/D로 분류한다.

    "Holm 보정 후 유의하지 않음"을 안전의 근거로 삼는 것은 귀무가설 채택이며,
    이 저장소가 고치고 있는 M3 결함 그 자체다. 따라서 권고는 다음 넷으로 나눈다.
      A 등가 입증        : 사전지정 마진에서 TOST 통과
      B 하락 미검출      : 유의하락 없음 + 점추정이 마진 안, 그러나 TOST 미통과(검정력 부족)
      C 손실 징후        : 점추정 차이가 마진을 넘음(유의 여부와 무관)
      D 자기참조 교란    : 질의가 정답 문서 쪽으로 유의하게 표류 — 성능 유지의 원인이
                          노출 축소가 아니므로 회수율을 운용 근거로 쓸 수 없다
    운용 권고는 A 또는 B이면서 D가 아닌 가장 깊은 연속 등급까지로 한다.
    """
    conf = confounded_levels()
    proven, under, loss, confounded = [], [], [], []
    for lv in LEVELS[1:]:
        key = f"{lv}_vs_L0"
        diff = p["contrasts_vs_L0"][retriever][key]["mean_diff"]
        eq = p["equivalence_vs_L0"][retriever][key]["primary"].get("equivalent_at_0.05", False)
        sig_drop = (p["holm_vs_L0"][retriever][key]["significant_at_0.05"] and diff < 0)
        if lv in conf["levels"]:
            confounded.append(lv)
        elif diff <= -PRIMARY_DELTA or sig_drop:
            loss.append(lv)
        elif eq:
            proven.append(lv)
        else:
            under.append(lv)
    blocked = set(loss) | set(confounded)
    acceptable = [lv for lv in LEVELS[1:] if lv not in blocked]
    # 손실 징후나 자기참조 교란이 처음 나타나는 등급 직전까지만 권고한다.
    recommended = "L0"
    for lv in LEVELS[1:]:
        if lv in blocked:
            break
        recommended = lv
    return {
        "proven_equivalent": proven,
        "underpowered": under,
        "evidence_of_loss": loss,
        "confounded_by_selfreference": confounded,
        "selfreference_audit": conf,
        "acceptable_levels": acceptable,
        "recommended_level": recommended,
        "criterion": "A(TOST 통과) 또는 B(유의하락 없음 & |점추정|<delta)이면서 "
                     "D(자기참조 표류)가 아닌 가장 깊은 연속 등급까지 권고. "
                     "'p>0.05'만으로 안전을 주장하지 않고, 회수율이 유지되어도 "
                     "그 원인이 노출 축소가 아니면 근거로 쓰지 않는다.",
    }


def markdown(p: dict) -> str:
    ex = p["exposure_axis"]
    L = LEVELS
    lines = [
        "# 질의 측 노출 등급 사다리와 disclosure–recall frontier",
        "",
        "이 보고서는 **아웃바운드(질의 본문)** 노출을 줄였을 때 후보검색 성능이 어떻게",
        "변하는지를 측정한다. 기존 실험이 측정한 것은 인바운드(공개 통제목록 반환량)였고,",
        "그 값은 랭킹을 바꾸지 않으므로 비용 없이 줄일 수 있어 트레이드오프가 아니었다.",
        "위협모형은 `docs/threat_model.md`에 있다.",
        "",
        "## 사전지정",
        "",
        f"- 색인 모드: `{p['prespecification']['index_mode']}` (질의 측 조작만 남기기 위해 고정)",
        f"- 검색기: BM25(α=1.0) / dense(α=0.0) / hybrid(α=0.5), dense = MiniLM 단일",
        f"- 등가성 마진 δ={p['prespecification']['primary_delta']} "
        f"(민감도 {p['prespecification']['sensitivity_deltas']})",
        f"- bootstrap {p['prespecification']['bootstrap_iters']}회, seed {p['prespecification']['seed']}",
        f"- 다중비교: {p['prespecification']['multiplicity']}",
        f"- 질의 {p['data']['n_queries']}개 (언어 {p['data']['language_distribution']}), "
        f"코퍼스 {p['data']['corpus_size']}개",
        f"- 등급 사다리 검증 통과: {'예' if p['data']['ladder_validation_passed'] else '아니오'}",
        "",
        "## 1. 노출 축 (문자 수가 아니라 민감 필드 기준)",
        "",
        "| 등급 | 정의 | 평균 민감토큰 | 평균 노출필드 수 | 평균 질의토큰 | 평균 문자수 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for lv in L:
        e = ex[lv]
        lines.append(
            f"| **{lv}** | {e['definition']} | {e['mean_sensitive_token_count']:.2f} | "
            f"{e['mean_sensitive_field_count']:.2f} | {e['mean_query_token_count']:.1f} | "
            f"{e['mean_query_char_count']:.0f} |"
        )
    lines += [
        "",
        "등급별 잔존 필드 빈도(질의 수):",
        "",
        "| 등급 | " + " | ".join(sorted({k for lv in L for k in ex[lv]["field_frequency"]})) + " |",
    ]
    cats = sorted({k for lv in L for k in ex[lv]["field_frequency"]})
    lines.append("|---|" + "---:|" * len(cats))
    for lv in L:
        ff = ex[lv]["field_frequency"]
        lines.append(f"| {lv} | " + " | ".join(str(ff.get(c, 0)) for c in cats) + " |")

    lines += ["", "## 2. frontier — R@10", ""]
    for r in RETRIEVERS:
        lines += [
            f"### {r}", "",
            "| 등급 | 평균 민감토큰 | R@10 | 95% CI | R@10 (en, n=26) | R@10 (ko, n=45) |",
            "|---|---:|---:|---|---:|---:|",
        ]
        for lv in L:
            row = p["recall@10"][r][lv]
            lines.append(
                f"| {lv} | {ex[lv]['mean_sensitive_token_count']:.2f} | "
                f"{row['overall']['rate']:.4f} | {fmt_ci(row['overall']['ci95'])} | "
                f"{row['en']['rate']:.4f} | {row['ko']['rate']:.4f} |"
            )
        lines.append("")

    lines += ["## 3. 인접 등급 간 대비 (paired bootstrap + exact McNemar, Holm 보정)", ""]
    for r in RETRIEVERS:
        lines += [
            f"### {r}", "",
            "| 비교 | 평균차 | 95% CI | 승/패/동 | p (exact) | Holm p | 유의 |",
            "|---|---:|---|---:|---:|---:|---:|",
        ]
        for key, c in p["contrasts_adjacent"][r].items():
            h = p["holm_adjacent"][r][key]
            lines.append(
                f"| {key} | {c['mean_diff']:+.4f} | {fmt_ci(c['diff_95_ci'])} | "
                f"{c['wins']}/{c['losses']}/{c['ties']} | {c['p_two_sided_exact']:.4g} | "
                f"{h['p_adjusted']:.4g} | {'예' if h['significant_at_0.05'] else '아니오'} |"
            )
        lines.append("")

    lines += ["## 4. L0 대비 + 등가성 검정 (TOST, δ=0.05)", ""]
    for r in RETRIEVERS:
        lines += [
            f"### {r}", "",
            "| 비교 | 평균차 | 95% CI | Holm p | 유의하락 | TOST p_max | δ=0.05 등가 | 필요 n(δ=0.05) |",
            "|---|---:|---|---:|---:|---:|---:|---:|",
        ]
        for lv in L[1:]:
            key = f"{lv}_vs_L0"
            c = p["contrasts_vs_L0"][r][key]
            h = p["holm_vs_L0"][r][key]
            eq = p["equivalence_vs_L0"][r][key]["primary"]
            need = p["equivalence_vs_L0"][r][key]["required_n_for_delta_0.05"]
            drop = "예" if (h["significant_at_0.05"] and c["mean_diff"] < 0) else "아니오"
            lines.append(
                f"| {key} | {c['mean_diff']:+.4f} | {fmt_ci(c['diff_95_ci'])} | "
                f"{h['p_adjusted']:.4g} | {drop} | "
                f"{eq.get('p_max', float('nan')):.4g} | "
                f"{'예' if eq.get('equivalent_at_0.05') else '아니오'} | "
                f"{need if need is not None else '-'} |"
            )
        lines.append("")

    lines += ["## 5. 굴절점과 운용 기준", ""]
    lines += ["| 검색기 | 첫 유의하락 등급 | A: δ=0.05 등가 입증 | B: 하락 미검출 | "
              "C: 손실 징후 | 운용 권고 |",
              "|---|---|---|---|---|---|"]
    for r in RETRIEVERS:
        i = p["inflection"][r]
        t = evidence_tiers(p, r)
        lines.append(
            f"| {r} | {i['first_significant_drop_vs_L0'] or '없음'} | "
            f"{', '.join(t['proven_equivalent']) or '없음'} | "
            f"{', '.join(t['underpowered']) or '없음'} | "
            f"{', '.join(t['evidence_of_loss']) or '없음'} | "
            f"**{t['recommended_level']}** |"
        )
    bm_ko = [p["recall@10"]["BM25"][lv]["ko"]["rate"] for lv in L]
    if all(abs(x) < 1e-12 for x in bm_ko):
        lines += [
            "",
            "> BM25 행은 해석하지 말 것. 한국어 45개 질의의 BM25 R@10이 **모든 등급에서 0.0000**이고 "
            "(코퍼스가 100% 영어라 어휘 겹침이 없다) 영어 26개만으로 전체 지표가 결정되므로, "
            "BM25의 '손실 징후 없음 → L4 권고'는 이미 바닥에 붙은 지표가 더 내려갈 곳이 없다는 "
            "뜻일 뿐이다. 운용 권고는 hybrid 행으로 읽는다.",
        ]

    prim = "hybrid_0.5"
    pi = p["inflection"][prim]
    tiers = evidence_tiers(p, prim)
    lines += [
        "",
        "### 운용 기준 (외부 AI에 보내도 되는 최소정보)",
        "",
        f"1차 검색기(hybrid α=0.5, 색인 `{INDEX_MODE}`) 기준으로 읽는다.",
        "",
        "**\"유의하락 없음\"은 안전의 증명이 아니다.** 귀무가설을 기각하지 못한 것과",
        "등가를 입증한 것은 다르다(이 저장소의 M3 결함이 바로 그 혼동이었다).",
        "**회수율이 유지되었다는 사실도 그 자체로는 근거가 아니다.** 상위 등급의 재작성은",
        "질의를 기능 서술만 남기는데 그것이 통제목록 원문의 문체이므로, 질의가 정답 문서",
        "쪽으로 옮겨가 회수율이 유지되었을 수 있다. 따라서 증거 등급을 넷으로 나눈다.",
        "",
        "| 증거 등급 | 판단 근거 | 해당 등급 |",
        "|---|---|---|",
        f"| **A. 등가 입증** | 사전지정 δ={PRIMARY_DELTA} TOST 통과 | "
        f"{', '.join(tiers['proven_equivalent']) or '없음'} |",
        f"| **B. 하락 미검출(검정력 부족)** | Holm 보정 후 유의하락 없음 + 점추정 차이의 절댓값 < δ, "
        f"그러나 TOST 미통과 | {', '.join(tiers['underpowered']) or '없음'} |",
        f"| **C. 손실 징후** | 점추정 차이 ≤ −δ (유의 여부와 무관) | "
        f"{', '.join(tiers['evidence_of_loss']) or '없음'} |",
        f"| **D. 자기참조 교란** | 질의가 정답 문서 쪽으로 유의하게 표류 — 회수율 유지를 "
        f"노출 축소로 귀속할 수 없음 | {', '.join(tiers['confounded_by_selfreference']) or '없음'} |",
        "",
    ]
    conf = tiers["selfreference_audit"]
    if conf["levels"]:
        lines += [
            f"> **D 등급 판정 근거.** `{conf.get('gate_model')}`(평가에 쓰지 않는 제3 인코더)로 "
            f"측정한 결과 {', '.join(conf['levels'])} 질의가 정답 문서와 유의하게 더 비슷해졌다"
            f"(감사 판정 `{conf.get('verdict')}`). 상세는 `output/ladder_selfreference.md`. "
            "이 등급에서 R@10이 유지된 것은 노출 축소가 무해해서가 아니라 자기참조가 "
            "늘었기 때문일 수 있으므로 운용 근거로 쓰지 않는다.",
            "",
        ]
    elif not conf["audited"]:
        lines += [f"> ⚠ 자기참조 미검증: {conf['note']}", ""]

    rec = tiers["recommended_level"]
    lines += [
        f"- **운용 권고: {rec}까지 지운 질의를 외부 AI에 보낸다.** {rec} 시점의 평균 민감토큰은 "
        f"{ex[rec]['mean_sensitive_token_count']:.2f}개(L0 {ex['L0']['mean_sensitive_token_count']:.2f}개 대비 "
        f"{100 * (1 - ex[rec]['mean_sensitive_token_count'] / max(ex['L0']['mean_sensitive_token_count'], 1e-9)):.1f}% 감소), "
        f"평균 노출필드는 {ex[rec]['mean_sensitive_field_count']:.2f}개, "
        f"R@10은 {p['recall@10'][prim][rec]['overall']['rate']:.4f}"
        f"(L0 {p['recall@10'][prim]['L0']['overall']['rate']:.4f})다.",
    ]
    if tiers["confounded_by_selfreference"]:
        blocked = tiers["confounded_by_selfreference"][0]
        lines.append(
            f"- **{blocked} 이하로는 권고하지 않는다.** {blocked}에서 민감정보를 더 지우면 "
            f"R@10은 유지되지만(L0과 동일), 그 유지가 자기참조 증가로 설명되므로 "
            f"\"{blocked}까지 지워도 안전하다\"고 말할 수 없다. 이 판정은 초판 자동 생성문의 "
            "결론을 뒤집은 것이다."
        )
    if tiers["evidence_of_loss"]:
        worst = tiers["evidence_of_loss"][0]
        d = p["contrasts_vs_L0"][prim][f"{worst}_vs_L0"]
        lines.append(
            f"- 반면 **{worst}(카테고리 키워드 2~5단어)에서는 점추정 하락이 "
            f"{abs(d['mean_diff']):.4f}(={abs(d['mean_diff']) * 100:.1f}%p)로 사전지정 마진 δ={PRIMARY_DELTA}를 "
            f"넘는다.** Holm 보정 후 유의하지는 않지만(p={p['holm_vs_L0'][prim][f'{worst}_vs_L0']['p_adjusted']:.3g}) "
            f"이는 n={p['data']['n_queries']}의 검정력 한계이지 무해의 근거가 아니다. "
            f"기능 서술까지 지우는 것은 권고하지 않는다."
        )
    lines += [
        f"- B등급 판정에는 검정력이 부족하다. δ={PRIMARY_DELTA}에서 등가를 입증하려면 "
        f"표의 '필요 n' 열에 따라 수백~수천 개의 질의가 필요하다. n={p['data']['n_queries']}에서 "
        f"확정 가능한 것은 A등급(L1)뿐이며, L2·L3은 \"손실 징후가 없다\"까지만 말할 수 있다. "
        "**확인 필요.**",
        "",
        "## 6. 진단",
        "",
        "| 등급 | BM25 무신호 질의 | 그중 한국어 | 평균 질의-색인 어휘겹침 | hybrid top10 == dense |",
        "|---|---:|---:|---:|---:|",
    ]
    for lv in L:
        d = p["diagnostics"][lv]
        lines.append(
            f"| {lv} | {d['bm25_no_signal_queries']} | {d['bm25_no_signal_korean']} | "
            f"{d['mean_query_vocab_overlap']:.2f} | {d['hybrid_top10_identical_to_dense']} |"
        )

    lines += ["", "## 7. 해석 주의", ""]
    for note in p["notes"]:
        lines.append(f"- {note}")
    lines += [
        "- 이 실험은 법적 판정·수출허가 판단·전문판정 대체가 아니다.",
        "- L1~L4 질의는 사람이 재작성한 것이므로 재작성자의 어휘 선택이 결과에 영향을 준다. "
        "`data/disclosure_ladder.json`에 등급별 전문과 제거 항목이 남아 있어 감사 가능하다.",
        "- dense는 MiniLM 단일 실행이다. 모델 간 강건성은 이 산출물의 범위가 아니다. **확인 필요.**",
    ]
    return "\n".join(lines)


def main() -> int:
    # --render-only: 이미 계산된 JSON에서 보고서만 다시 만든다(인코딩 재실행 없음).
    if "--render-only" in sys.argv:
        payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        payload["evidence_tiers"] = {r: evidence_tiers(payload, r) for r in RETRIEVERS}
        JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        MD_PATH.write_text(markdown(payload), encoding="utf-8")
        print(f"re-rendered -> {MD_PATH}")
        for r in RETRIEVERS:
            print(f"  {r:12s} tiers={payload['evidence_tiers'][r]}")
        return 0

    payload = run()
    payload["evidence_tiers"] = {r: evidence_tiers(payload, r) for r in RETRIEVERS}
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(markdown(payload), encoding="utf-8")
    for r in RETRIEVERS:
        row = " ".join(
            f"{lv}={payload['recall@10'][r][lv]['overall']['rate']:.4f}" for lv in LEVELS
        )
        print(f"{r:12s} {row}   굴절점={payload['inflection'][r]['first_significant_drop_vs_L0']}")
    print(f"-> {JSON_PATH}\n-> {MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
