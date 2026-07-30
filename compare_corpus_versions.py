#!/usr/bin/env python3
"""Measure what adopting combined_v2.json would actually change.

"Every number changes" is an assumption worth testing before it drives a
decision. Two structural facts suggest the impact is narrower than it looks:

  1. The gold labels are all eCFR codes, and v2 leaves eCFR byte-identical
     (637 entries, 105,567 chars). So the *answer* documents do not move at all.
     Only the distractor pool (Wassenaar + SCOMET) gets richer.
  2. The headline condition indexes `minimal_text`, which is `first_sentence`
     capped at 260 characters. Recovering truncated body text changes the tail
     of a document, not its first sentence -- unless the entry's *beginning* was
     mis-parsed (fake entries, absorbed annexes, footer contamination).

If both hold, adopting v2 makes the benchmark harder in an honest direction
(richer distractors against unchanged answers) while leaving most of the
headline machinery intact. This script measures it instead of assuming it.

    python compare_corpus_versions.py            # BM25 only, seconds
    python compare_corpus_versions.py --dense    # + MiniLM dense/hybrid

Outputs: output/corpus_version_comparison.{json,md}
"""

from __future__ import annotations

import argparse
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
JSON_PATH = OUT_DIR / "corpus_version_comparison.json"
MD_PATH = OUT_DIR / "corpus_version_comparison.md"

INDEX_MODE = "minimal_text"
PRIMARY_ALPHA = 0.5
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SEED = 20260626


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def eval_bm25(corpus: list[dict], queries: list[dict]) -> list[int]:
    docs = [rc.index_text(e, INDEX_MODE) for e in corpus]
    codes = [e["code"] for e in corpus]
    index = rc.BM25(docs)
    out = []
    for q in queries:
        top10 = rc.retrieve(index.scores(q["query"]), 10)
        labels = set(q["validated_labels"])
        out.append(int(any(codes[i] in labels for i in top10)))
    return out


def eval_dense(corpus: list[dict], queries: list[dict]) -> dict[str, list[int]]:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(DENSE_MODEL)
    docs = [rc.index_text(e, INDEX_MODE) for e in corpus]
    codes = [e["code"] for e in corpus]
    index = rc.BM25(docs)
    demb = model.encode(docs, batch_size=32, normalize_embeddings=True,
                        show_progress_bar=False).astype(np.float32)
    qemb = model.encode([q["query"] for q in queries], batch_size=32,
                        normalize_embeddings=True, show_progress_bar=False).astype(np.float32)
    res = {"dense": [], f"hybrid_{PRIMARY_ALPHA}": []}
    for qi, q in enumerate(queries):
        bm = rc.minmax(index.scores(q["query"]))
        dn = rc.minmax(demb @ qemb[qi])
        labels = set(q["validated_labels"])
        for name, a in (("dense", 0.0), (f"hybrid_{PRIMARY_ALPHA}", PRIMARY_ALPHA)):
            top10 = list(rc.rank_indices(rc.blend(bm, dn, a))[:10])
            res[name].append(int(any(codes[i] in labels for i in top10)))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dense", action="store_true", help="also run MiniLM (a few minutes)")
    args = ap.parse_args()

    if not V2.exists():
        raise SystemExit(f"{V2} 없음 — build_corpus_clean.py --v2 를 먼저 실행")
    c1, c2 = load(V1), load(V2)
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    langs = [q["lang"] for q in queries]
    gold_codes = {lbl for q in queries for lbl in q["validated_labels"]}

    def by_src(c):
        d: dict[str, dict] = {}
        for e in c:
            s = d.setdefault(e["source"], {"n": 0, "chars": 0})
            s["n"] += 1
            s["chars"] += len(e.get("text", ""))
        return d

    m1, m2 = {e["code"]: e for e in c1}, {e["code"]: e for e in c2}

    # do the gold documents move at all?
    gold_present_v1 = sorted(g for g in gold_codes if g in m1)
    gold_present_v2 = sorted(g for g in gold_codes if g in m2)
    gold_text_changed = [g for g in gold_present_v1 if g in m2
                         and m1[g].get("text") != m2[g].get("text")]
    gold_first_sentence_changed = [
        g for g in gold_present_v1 if g in m2
        and rc.index_text(m1[g], INDEX_MODE) != rc.index_text(m2[g], INDEX_MODE)]
    gold_missing_in_v2 = [g for g in gold_present_v1 if g not in m2]

    # how much of the *indexed* text actually moves?
    shared = set(m1) & set(m2)
    idx_changed = [c for c in shared
                   if rc.index_text(m1[c], INDEX_MODE) != rc.index_text(m2[c], INDEX_MODE)]
    full_changed = [c for c in shared if m1[c].get("text") != m2[c].get("text")]

    # retrieval impact
    h1 = {"BM25": eval_bm25(c1, queries)}
    h2 = {"BM25": eval_bm25(c2, queries)}
    if args.dense:
        print("encoding v1 ...", flush=True)
        h1.update(eval_dense(c1, queries))
        print("encoding v2 ...", flush=True)
        h2.update(eval_dense(c2, queries))

    retrieval = {}
    for name in h1:
        a, b = h2[name], h1[name]        # a = v2, b = v1
        diffs = [x - y for x, y in zip(a, b)]
        sub = {}
        for lang in (None, "en", "ko"):
            tag = lang or "overall"
            va = [x for x, lg in zip(a, langs) if lang is None or lg == lang]
            vb = [x for x, lg in zip(b, langs) if lang is None or lg == lang]
            sub[tag] = {"v1": rc.rate_with_ci(vb), "v2": rc.rate_with_ci(va),
                        "delta": round(sum(va) / len(va) - sum(vb) / len(vb), 4)}
        retrieval[name] = {
            "by_subgroup": sub,
            "paired_bootstrap": rc.paired_bootstrap_ci(diffs, seed=SEED),
            "mcnemar": rc.exact_mcnemar(a, b),
            "flipped_to_hit": [queries[i]["id"] for i, d in enumerate(diffs) if d > 0],
            "flipped_to_miss": [queries[i]["id"] for i, d in enumerate(diffs) if d < 0],
        }

    out = {
        "env": rc.env_meta({"seed": SEED, "index_mode": INDEX_MODE, "dense_run": args.dense}),
        "composition": {
            "v1": {"total": len(c1), "by_source": by_src(c1)},
            "v2": {"total": len(c2), "by_source": by_src(c2)},
        },
        "gold_documents": {
            "note": "정답 라벨은 전부 eCFR. v2에서 eCFR이 무변경이면 정답 문서는 움직이지 않는다.",
            "gold_codes": len(gold_codes),
            "present_v1": len(gold_present_v1),
            "present_v2": len(gold_present_v2),
            "missing_in_v2": gold_missing_in_v2,
            "full_text_changed": gold_text_changed,
            "indexed_text_changed": gold_first_sentence_changed,
        },
        "text_movement": {
            "shared_codes": len(shared),
            "only_in_v1": sorted(set(m1) - set(m2)),
            "only_in_v2": sorted(set(m2) - set(m1)),
            f"indexed_{INDEX_MODE}_changed": len(idx_changed),
            "full_text_changed": len(full_changed),
            "indexed_changed_examples": idx_changed[:15],
        },
        "retrieval_impact": retrieval,
    }
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    MD_PATH.write_text(render(out), encoding="utf-8")
    print(json.dumps({
        "gold_docs_moved": {
            "missing": len(gold_missing_in_v2),
            "full_text_changed": len(gold_text_changed),
            "indexed_changed": len(gold_first_sentence_changed),
        },
        "indexed_text_changed_of_shared": f"{len(idx_changed)}/{len(shared)}",
        "retrieval": {k: {"v1": v["by_subgroup"]["overall"]["v1"]["rate"],
                          "v2": v["by_subgroup"]["overall"]["v2"]["rate"],
                          "delta": v["by_subgroup"]["overall"]["delta"],
                          "wins/losses": f"{v['mcnemar']['wins']}/{v['mcnemar']['losses']}"}
                      for k, v in retrieval.items()},
    }, ensure_ascii=False, indent=2))


def render(o: dict) -> str:
    c = o["composition"]
    g = o["gold_documents"]
    t = o["text_movement"]
    L = ["# 코퍼스 v1 → v2 교체 영향 측정", "",
         f"색인 모드 `{o['env']['index_mode']}` / 검증셋 n=71 / seed {o['env']['seed']}", "",
         "## 1. 구성", "", "| 소스 | v1 건수 | v2 건수 | v1 문자 | v2 문자 | 문자 증감 |",
         "|---|---:|---:|---:|---:|---:|"]
    for s in sorted(set(c["v1"]["by_source"]) | set(c["v2"]["by_source"])):
        a = c["v1"]["by_source"].get(s, {"n": 0, "chars": 0})
        b = c["v2"]["by_source"].get(s, {"n": 0, "chars": 0})
        pct = (b["chars"] - a["chars"]) / a["chars"] * 100 if a["chars"] else 0
        L.append(f"| {s} | {a['n']} | {b['n']} | {a['chars']:,} | {b['chars']:,} | {pct:+.1f}% |")
    L += [f"| **합계** | **{c['v1']['total']}** | **{c['v2']['total']}** | | | |", "",
          "## 2. 정답 문서는 움직였는가", "",
          f"- 검증셋 정답 코드 {g['gold_codes']}개 (전부 eCFR)",
          f"- v1 존재 {g['present_v1']} / v2 존재 {g['present_v2']} / **v2에서 사라진 정답 {len(g['missing_in_v2'])}개**",
          f"- 본문이 바뀐 정답 문서: **{len(g['full_text_changed'])}개**",
          f"- 색인 텍스트가 바뀐 정답 문서: **{len(g['indexed_text_changed'])}개**", ""]
    if not g["full_text_changed"] and not g["missing_in_v2"]:
        L += ["> **정답 문서는 한 건도 움직이지 않았다.** v2가 바꾼 것은 방해 문서(Wassenaar·SCOMET)뿐이다.",
              "> 즉 교체는 정답을 그대로 둔 채 방해 문서를 풍부하게 만든다 — 벤치마크가",
              "> 정직한 방향으로 **어려워진다**. v1의 파싱 결함이 과제를 쉽게 만들고 있었다는 뜻이다.", ""]
    L += ["## 3. 색인 텍스트 이동량", "",
          f"- 양쪽에 공통인 코드 {t['shared_codes']}개 중 **색인 텍스트가 바뀐 것 "
          f"{t[f'indexed_{o[chr(39)+chr(39)] if False else INDEX_MODE}_changed']}개**"
          if False else
          f"- 양쪽에 공통인 코드 {t['shared_codes']}개 중 "
          f"**색인 텍스트가 바뀐 것 {t[f'indexed_{INDEX_MODE}_changed']}개**",
          f"- 본문 전체가 바뀐 것 {t['full_text_changed']}개",
          f"- v1에만 있는 코드 {len(t['only_in_v1'])}개 / v2에만 있는 코드 {len(t['only_in_v2'])}개", "",
          "## 4. 검색 성능 영향 (v2 − v1)", "",
          "| 검색기 | v1 R@10 | v2 R@10 | 차이 | 95% CI | 승/패/무 | exact p |",
          "|---|---:|---:|---:|---|---:|---:|"]
    for name, r in o["retrieval_impact"].items():
        s = r["by_subgroup"]["overall"]
        b = r["paired_bootstrap"]
        mc = r["mcnemar"]
        L.append(f"| {name} | {s['v1']['rate']:.4f} | {s['v2']['rate']:.4f} | "
                 f"{s['delta']:+.4f} | [{b['ci'][0]:+.4f}, {b['ci'][1]:+.4f}] | "
                 f"{mc['wins']}/{mc['losses']}/{mc['ties']} | {mc['p_two_sided_exact']:.3g} |")
    L += ["", "### 언어별", "", "| 검색기 | 영어 v1→v2 | 한국어 v1→v2 |", "|---|---|---|"]
    for name, r in o["retrieval_impact"].items():
        e, k = r["by_subgroup"]["en"], r["by_subgroup"]["ko"]
        L.append(f"| {name} | {e['v1']['rate']:.4f} → {e['v2']['rate']:.4f} ({e['delta']:+.4f}) | "
                 f"{k['v1']['rate']:.4f} → {k['v2']['rate']:.4f} ({k['delta']:+.4f}) |")
    L += ["", "## 5. 해석 주의", "",
          "- 이 비교는 검증셋(n=71)·색인 `minimal_text` 한정이다. `full_text` 조건은 본문 "
          "총량이 크게 늘어 영향이 더 크다. **확인 필요.**",
          "- 합성셋(주장 1)은 코퍼스 본문에서 파생되므로 v2 채택 시 쿼리 자체를 재생성해야 한다.",
          "- v2 자체도 사람 검수를 받지 않았다. 파서 교정이 새 오류를 넣지 않았다는 보장은 "
          "`tests/test_corpus.py`의 회귀 검증 범위까지다.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
