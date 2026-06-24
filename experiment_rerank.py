#!/usr/bin/env python3
"""Rerank experiment: cross-encoder on top of hybrid retrieval (minimal mode)."""
import json, math, re
from pathlib import Path
import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer
from statistics import mean

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

ALPHA = 0.8

# ---- BM25 + tokenize copied from run_experiments_v3.py ----
def tokenize(text: str):
    return [w.lower() for w in re.findall(r"[A-Za-z0-9]+", text)]

class BM25:
    def __init__(self, corpus_texts):
        self.corpus = corpus_texts
        self.tokens = [tokenize(t) for t in corpus_texts]
        self.N = len(corpus_texts)
        self.avgdl = mean(len(toks) for toks in self.tokens) or 1.0
        self.k1, self.b = 1.2, 0.75
        df = {}
        for toks in self.tokens:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log((self.N - f + 0.5) / (f + 0.5) + 1) for t, f in df.items()}

    def score(self, query, idx):
        qt = tokenize(query)
        tf = {}
        for t in self.tokens[idx]:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in qt:
            if t not in self.idf:
                continue
            f = tf.get(t, 0)
            dl = len(self.tokens[idx])
            s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s
# ----------------------------------------------------------

# Load data
corpus = json.loads((DATA_DIR / "corpus" / "combined.json").read_text(encoding="utf-8"))
all_queries = json.loads((DATA_DIR / "queries.json").read_text(encoding="utf-8"))
test_q = all_queries.get("test", [])[:75]

# Build minimal-text corpus
minimal_texts = []
for e in corpus:
    code = e.get("code", "")
    text = e.get("text", "")
    first = text.split(".")[0] if "." in text else text[:200]
    minimal_texts.append(f"{code} {first}")

bm25 = BM25(minimal_texts)
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
emb = model.encode(minimal_texts, normalize_embeddings=True, batch_size=64)

ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=256)

def hybrid_search(query, top_k=20):
    bm_scores = np.array([bm25.score(query, i) for i in range(len(corpus))])
    qv = model.encode(query, normalize_embeddings=True)
    de_scores = emb @ qv
    fused = ALPHA * bm_scores + (1 - ALPHA) * de_scores
    idx = np.argsort(fused)[::-1][:top_k]
    return idx

rerank = {"recall@1": [], "recall@5": [], "recall@10": []}
for q in test_q:
    ans = q["answer_code"]
    top_idx = hybrid_search(q["query"], top_k=20)
    candidates = [(q["query"], corpus[i]["text"][:300]) for i in top_idx]
    ce_scores = ce.predict(candidates)
    order = np.argsort(ce_scores)[::-1][:20]
    codes = [corpus[top_idx[i]]["code"] for i in order]
    rerank["recall@1"].append(1 if codes[0] == ans else 0)
    rerank["recall@5"].append(1 if ans in codes[:5] else 0)
    rerank["recall@10"].append(1 if ans in codes[:10] else 0)

out = {k: float(np.mean(v)) for k, v in rerank.items()}
print("Rerank (cross-encoder on minimal top-20, ALPHA=0.8):")
for k, v in out.items():
    print(f"  {k}: {v:.4f}")
(OUT_DIR / "rerank_results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
