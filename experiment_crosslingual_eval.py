#!/usr/bin/env python3
"""TASK D (D1) — Korean cross-lingual track: KO-original vs KO-translated vs EN.

Background: the corpus is 100% English, so BM25 cannot lexically match Korean
queries (R@10=0). This script tests whether HUMAN-translating the 5 evaluable
Korean queries into English recovers retrieval performance, and compares that
against multilingual dense / hybrid retrieval that can bridge languages directly.

Three tracks are evaluated on the SAME validated labels (exact full eCFR codes):
  - KO-original : the Korean query as written
  - KO-translated: the human English translation (data/crosslingual_translations.json)
  - EN-original : the queries that were already in English

For each track we run BM25 / Dense / Hybrid (min-max alpha blend), reusing the
exact retrieval code from run_experiments.py / evaluate_validated_queries.py so
numbers stay consistent with existing outputs.

NO external API is used. Translations are manual; dense embedding runs locally.
This is consistent with the information-minimization theme of the project.

CAVEAT: the Korean evaluable sample is only 5. Results are TRENDS, not
statistically robust conclusions. Sample expansion is needed. Labels are
corpus-text-grounded category labels, NOT legal determinations.

Outputs: output/crosslingual_eval.json, output/crosslingual_eval.md
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from run_experiments import BM25, build_doc_text

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

CORPUS_PATH = DATA_DIR / "corpus" / "combined.json"
QUERIES_PATH = DATA_DIR / "external_consultation_queries_validated.json"
TRANSLATIONS_PATH = DATA_DIR / "crosslingual_translations.json"
JSON_PATH = OUT_DIR / "crosslingual_eval.json"
MD_PATH = OUT_DIR / "crosslingual_eval.md"

MODE = "minimal_text"
DENSE_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
ALPHAS = [1.0, 0.5, 0.0]  # 1.0 = pure BM25, 0.5 = hybrid, 0.0 = pure dense


def minmax(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def build_tracks(queries, translations):
    """Build three evaluation tracks from the validated, non-excluded queries."""
    scored = [q for q in queries if not q["excluded_from_metrics"]]
    ko = [q for q in scored if q["lang"] == "ko"]
    en = [q for q in scored if q["lang"] == "en"]

    ko_original = [{"id": q["id"], "text": q["query"], "labels": set(q["validated_labels"])}
                   for q in ko]
    ko_translated = []
    for q in ko:
        t = translations.get(q["id"])
        if t is None:
            raise KeyError(f"missing translation for {q['id']}")
        ko_translated.append({"id": q["id"], "text": t, "labels": set(q["validated_labels"])})
    en_original = [{"id": q["id"], "text": q["query"], "labels": set(q["validated_labels"])}
                   for q in en]

    return {
        "KO-original": ko_original,
        "KO-translated": ko_translated,
        "EN-original": en_original,
    }


def eval_track(track_items, index, codes, model, doc_emb):
    """Return per-alpha recall@10 for one track."""
    if not track_items:
        return {f"alpha={a}": {"recall@10": None, "n": 0} for a in ALPHAS}

    q_emb = model.encode([it["text"] for it in track_items], batch_size=64,
                         normalize_embeddings=True, show_progress_bar=False).astype(np.float32)

    results = {a: [] for a in ALPHAS}
    per_query = []
    for qi, it in enumerate(track_items):
        labels = it["labels"]
        bm = minmax(index.scores(it["text"]))
        dn = minmax(doc_emb @ q_emb[qi])
        rec = {"id": it["id"], "by_alpha": {}}
        for a in ALPHAS:
            blended = a * bm + (1 - a) * dn
            ranked = np.argsort(-blended)
            top10 = [codes[i] for i in ranked[:10]]
            rank = next((r + 1 for r, c in enumerate(top10) if c in labels), None)
            hit = int(rank is not None)
            results[a].append(hit)
            rec["by_alpha"][f"alpha={a}"] = {"hit@10": hit, "rank": rank, "top3": top10[:3]}
        per_query.append(rec)

    summary = {}
    for a in ALPHAS:
        n = len(results[a]) or 1
        summary[f"alpha={a}"] = {
            "recall@10": round(sum(results[a]) / n, 4),
            "n": len(results[a]),
        }
    return summary, per_query


def main() -> None:
    from sentence_transformers import SentenceTransformer

    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    payload = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    translations = json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))["translations"]

    docs = [build_doc_text(e, MODE) for e in corpus]
    codes = [e["code"] for e in corpus]
    index = BM25(docs)

    model = SentenceTransformer(DENSE_MODEL)
    doc_emb = model.encode(docs, batch_size=64, normalize_embeddings=True,
                           show_progress_bar=False).astype(np.float32)

    tracks = build_tracks(payload["queries"], translations)

    track_summaries = {}
    track_per_query = {}
    for name, items in tracks.items():
        summary, per_query = eval_track(items, index, codes, model, doc_emb)
        track_summaries[name] = summary
        track_per_query[name] = per_query

    out = {
        "meta": {
            "experiment": "crosslingual_ko_translation (TASK D / D1)",
            "mode": MODE,
            "dense_model": DENSE_MODEL,
            "alphas": ALPHAS,
            "translation_method": "manual (human), no external API",
            "ko_sample_size": len(tracks["KO-original"]),
            "en_sample_size": len(tracks["EN-original"]),
            "label_nature": payload["meta"]["label_nature"],
            "caveat": "Korean sample is only 5; results are trends, not robust. Sample expansion needed.",
        },
        "summary": track_summaries,
        "per_query": track_per_query,
    }
    JSON_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Markdown report ---
    lines = [
        "# TASK D (D1) — 한국어 cross-lingual: KO-원문 vs KO-번역 vs EN",
        "",
        f"- 질의셋: `{QUERIES_PATH.name}` (검증 라벨, exact full eCFR code 매칭)",
        f"- 번역: 사람 수동 번역 (외부 API 미사용) — `{TRANSLATIONS_PATH.name}`",
        f"- Dense: {DENSE_MODEL} (로컬 실행)",
        f"- 표본: 한국어 {out['meta']['ko_sample_size']}개 / 영어 {out['meta']['en_sample_size']}개",
        "- **주의: 한국어 표본 5개로 매우 작음. 아래는 '경향'이며 통계적 결론 아님. 표본 확대 필요.**",
        "- 라벨: 코퍼스 텍스트 근거 카테고리 라벨. 법적 판정 아님, 전문가 검증 아님.",
        "",
        "## R@10 by track and retriever",
        "",
        "| track | BM25 (α=1.0) | Hybrid (α=0.5) | Dense (α=0.0) |",
        "|---|---:|---:|---:|",
    ]
    for name in ["KO-original", "KO-translated", "EN-original"]:
        s = track_summaries[name]
        def fmt(a):
            v = s[f"alpha={a}"]["recall@10"]
            return f"{v:.4f}" if v is not None else "-"
        lines.append(f"| {name} | {fmt(1.0)} | {fmt(0.5)} | {fmt(0.0)} |")

    lines += [
        "",
        "## 해석 (경향)",
        "",
        "- **KO-원문 + BM25**: 코퍼스가 100% 영어라 한국어 어휘 매칭이 구조적으로 불가능하다.",
        "- **KO-번역 + BM25**: 한국어를 영어로 번역하면 BM25가 다시 어휘 매칭을 시도할 수 있다.",
        "  번역이 BM25 경로에서 한국어 0점을 어느 정도 회복시키는지가 핵심 관찰점.",
        "- **다국어 Dense/Hybrid**: 번역 없이도 한국어 질의와 영어 코퍼스를 같은 의미 공간에",
        "  임베딩하여 cross-lingual 매칭을 시도한다.",
        "- **EN-원문**: 영어 질의의 기준선. KO-번역이 EN-원문에 얼마나 근접하는지 비교.",
        "",
        "## 한계",
        "",
        "- 한국어 평가 표본이 5개뿐이라 1개 적중이 R@10을 0.20씩 움직인다. 절대값보다",
        "  track 간 상대 경향으로만 해석해야 하며, 표본 확대가 후속 과제다.",
        "- 번역 품질에 결과가 의존한다(사람 1인 번역). 다수 번역자/역번역 검증이 필요하다.",
        "- 라벨은 코퍼스 텍스트 근거 카테고리 라벨이며 법적·전문가 판정이 아니다.",
        "",
    ]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(track_summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()