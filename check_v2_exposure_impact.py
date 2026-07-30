#!/usr/bin/env python3
"""Does adopting combined_v2.json move the exposure figures, not just recall?

`compare_corpus_versions.py` showed recall@10 is identical for all 71 validated
queries under all three retrievers. That is a statement about hit/miss only. The
exposure headline (4043 -> 1820 chars, 55.0%) is a sum over the *documents* in
the top-10, so it can move even when every hit/miss verdict is unchanged: a
non-gold document swapping places, or a Wassenaar/SCOMET entry whose recovered
body text is now longer, changes the character count without changing recall.

This checks the stronger property -- are the top-10 index *sets* identical -- and
measures exposure@10 under both corpus versions, so the adoption manual can state
which paper numbers need updating instead of guessing.

    python check_v2_exposure_impact.py

Outputs: output/v2_exposure_impact.{json,md}
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT_DIR = ROOT / "output"
V1 = DATA / "corpus" / "combined.json"
V2 = DATA / "corpus" / "combined_v2.json"
QUERIES = DATA / "validated_queries_expanded.json"
JSON_PATH = OUT_DIR / "v2_exposure_impact.json"
MD_PATH = OUT_DIR / "v2_exposure_impact.md"

INDEX_MODES = ["full_text", "minimal_text", "minimal_no_code"]
RETURN_MODES = ["full_text", "minimal_text", "minimal_no_code"]
PRIMARY_ALPHA = 0.5
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SEED = 20260626


def run(corpus: list[dict], queries: list[dict], model) -> dict:
    """top-10 code sequences and exposure@10 per index mode, hybrid ranking."""
    codes = [e["code"] for e in corpus]
    qtexts = [q["query"] for q in queries]
    qemb = model.encode(qtexts, batch_size=32, normalize_embeddings=True,
                        show_progress_bar=False).astype(np.float32)
    out = {}
    for imode in INDEX_MODES:
        docs = [rc.index_text(e, imode) for e in corpus]
        index = rc.BM25(docs)
        demb = model.encode(docs, batch_size=32, normalize_embeddings=True,
                            show_progress_bar=False).astype(np.float32)
        top10s, exp = [], {r: [] for r in RETURN_MODES}
        for qi in range(len(queries)):
            bm = rc.minmax(index.scores(qtexts[qi]))
            dn = rc.minmax(demb @ qemb[qi])
            idx = list(rc.rank_indices(rc.blend(bm, dn, PRIMARY_ALPHA))[:10])
            top10s.append([codes[i] for i in idx])
            for r in RETURN_MODES:
                exp[r].append(sum(rc.exposure_chars(corpus[i], r) for i in idx))
        out[imode] = {
            "top10_codes": top10s,
            "exposure_at10": {r: round(float(np.mean(exp[r])), 1) for r in RETURN_MODES},
        }
    return out


def main() -> None:
    from sentence_transformers import SentenceTransformer
    corpus1, corpus2 = json.loads(V1.read_text(encoding="utf-8")), json.loads(V2.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    model = SentenceTransformer(DENSE_MODEL)

    print("v1 ...", flush=True)
    a = run(corpus1, queries, model)
    print("v2 ...", flush=True)
    b = run(corpus2, queries, model)

    per_mode = {}
    for imode in INDEX_MODES:
        t1, t2 = a[imode]["top10_codes"], b[imode]["top10_codes"]
        identical_seq = sum(1 for x, y in zip(t1, t2) if x == y)
        identical_set = sum(1 for x, y in zip(t1, t2) if set(x) == set(y))
        changed = [{"query_id": queries[i]["id"],
                    "only_v1": sorted(set(t1[i]) - set(t2[i])),
                    "only_v2": sorted(set(t2[i]) - set(t1[i]))}
                   for i in range(len(queries)) if set(t1[i]) != set(t2[i])]
        e1, e2 = a[imode]["exposure_at10"], b[imode]["exposure_at10"]
        per_mode[imode] = {
            "top10_sequence_identical": f"{identical_seq}/{len(queries)}",
            "top10_set_identical": f"{identical_set}/{len(queries)}",
            "queries_with_set_change": changed,
            "exposure_at10_v1": e1,
            "exposure_at10_v2": e2,
            "exposure_delta": {r: round(e2[r] - e1[r], 1) for r in RETURN_MODES},
            "exposure_delta_pct": {
                r: (round(100 * (e2[r] - e1[r]) / e1[r], 2) if e1[r] else 0.0)
                for r in RETURN_MODES},
        }

    # the headline: index=full_text, return=minimal_text vs baseline full/full
    def cut(block):
        base = block["full_text"]["exposure_at10"]["full_text"]
        best = block["full_text"]["exposure_at10"]["minimal_text"]
        return round(100 * (base - best) / base, 1)

    headline = {
        "definition": "색인=full_text 고정, 반환 full_text -> minimal_text 노출 감소율 "
                      "(실사용 가능한 최적 운용점)",
        "v1_pct": cut(a), "v2_pct": cut(b),
        "v1_chars": [a["full_text"]["exposure_at10"]["full_text"],
                     a["full_text"]["exposure_at10"]["minimal_text"]],
        "v2_chars": [b["full_text"]["exposure_at10"]["full_text"],
                     b["full_text"]["exposure_at10"]["minimal_text"]],
    }

    out = {
        "question": "코퍼스 v2 채택이 recall 말고 노출량 수치를 움직이는가",
        "env": rc.env_meta({"seed": SEED, "dense_model": DENSE_MODEL}),
        "per_index_mode": per_mode,
        "headline_exposure_cut": headline,
        "conclusion": conclude(per_mode, headline),
    }
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(render(out), encoding="utf-8")
    print(json.dumps({"headline": headline,
                      "per_mode": {k: {"set_identical": v["top10_set_identical"],
                                       "exposure_delta": v["exposure_delta"]}
                                   for k, v in per_mode.items()},
                      "conclusion": out["conclusion"]}, ensure_ascii=False, indent=2))


def conclude(per_mode: dict, headline: dict) -> dict:
    n_changed = sum(len(v["queries_with_set_change"]) for v in per_mode.values())
    worst = max(abs(d) for v in per_mode.values() for d in v["exposure_delta"].values())
    worst_pct = max(abs(d) for v in per_mode.values() for d in v["exposure_delta_pct"].values())
    cut_moved = abs(headline["v2_pct"] - headline["v1_pct"])
    if n_changed == 0 and worst < 1.0:
        label = "no_change"
        text = ("top-10 문서 집합이 전부 동일하고 노출량@10도 움직이지 않았다. "
                "검증셋 관련 논문 수치(4.3·4.5 표, 초록의 노출 감소율)는 그대로 쓸 수 있다.")
    elif cut_moved < 0.5:
        label = "negligible"
        text = (f"top-10 집합이 {n_changed}개 질의에서 달라졌고 노출량@10이 최대 {worst:.1f}자"
                f"({worst_pct:.2f}%) 움직였으나, 헤드라인 감소율은 {cut_moved:.2f}%p 변화로 "
                "표기 자리수 안이다. 4.5 표의 절대 문자수만 갱신하면 된다.")
    else:
        label = "must_update"
        text = (f"헤드라인 노출 감소율이 {headline['v1_pct']:.1f}% -> {headline['v2_pct']:.1f}% "
                f"({cut_moved:.1f}%p) 바뀐다. 4.5 표와 초록·결론의 감소율을 반드시 갱신해야 하고, "
                "검증셋 통합 실행(3모델)도 다시 돌려야 한다.")
    return {"label": label, "text": text,
            "queries_with_top10_set_change": n_changed,
            "max_exposure_delta_chars": worst,
            "headline_cut_shift_pp": round(cut_moved, 2)}


def render(o: dict) -> str:
    h = o["headline_exposure_cut"]
    c = o["conclusion"]
    L = [f"# 코퍼스 v2 채택의 노출량 영향", "",
         f"**질문.** {o['question']}", "",
         "`compare_corpus_versions.py`는 적중 여부(recall)만 비교했다. 노출량@10은 top-10에 "
         "든 **문서들의** 반환 문자 수 합이므로, 적중 판정이 전부 같아도 문서 집합이 바뀌면 "
         "움직인다. 이 스크립트가 그 강한 성질을 확인한다.", "",
         "## top-10 집합 동일성과 노출량", "",
         "| 색인 모드 | 순서까지 동일 | 집합 동일 | 노출량@10 v1 → v2 (반환=minimal_text) | 변화 |",
         "|---|---:|---:|---|---:|"]
    for im, v in o["per_index_mode"].items():
        e1 = v["exposure_at10_v1"]["minimal_text"]
        e2 = v["exposure_at10_v2"]["minimal_text"]
        L.append(f"| {im} | {v['top10_sequence_identical']} | {v['top10_set_identical']} | "
                 f"{e1:.1f} → {e2:.1f} | {v['exposure_delta']['minimal_text']:+.1f}자 |")
    L += ["", "## 헤드라인 노출 감소율", "",
          f"{h['definition']}", "",
          f"- v1: {h['v1_chars'][0]:.1f} → {h['v1_chars'][1]:.1f} = **{h['v1_pct']:.1f}%**",
          f"- v2: {h['v2_chars'][0]:.1f} → {h['v2_chars'][1]:.1f} = **{h['v2_pct']:.1f}%**", "",
          "## 판정", "", f"**{c['label']}**", "", c["text"], "",
          f"- top-10 집합이 달라진 질의 {c['queries_with_top10_set_change']}건",
          f"- 노출량@10 최대 변화 {c['max_exposure_delta_chars']:.1f}자",
          f"- 헤드라인 감소율 이동 {c['headline_cut_shift_pp']:.2f}%p", ""]
    changed = [(im, q) for im, v in o["per_index_mode"].items()
               for q in v["queries_with_set_change"]]
    if changed:
        L += ["## top-10 집합이 바뀐 질의", "", "| 색인 | 질의 | v1에만 | v2에만 |", "|---|---|---|---|"]
        for im, q in changed[:25]:
            L.append(f"| {im} | {q['query_id']} | {', '.join(q['only_v1']) or '-'} | "
                     f"{', '.join(q['only_v2']) or '-'} |")
        L.append("")
    return "\n".join(L)


if __name__ == "__main__":
    main()
