#!/usr/bin/env python3
"""
Compare multiple embedding models for export control retrieval.
"""
import json, math, re, time
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"

# Load corpus and queries
corpus = json.loads((DATA_DIR / "corpus" / "combined.json").read_text(encoding="utf-8"))
queries_data = json.loads((DATA_DIR / "queries.json").read_text(encoding="utf-8"))
test_q = queries_data["test"]
print(f"Loaded {len(corpus)} corpus items, {len(test_q)} test queries")

# Models to compare (small/fast to download)
MODELS = {
    "minilm": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "mpnet": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    "all-Mini": "sentence-transformers/all-MiniLM-L12-v2",
    "bge": "BAAI/bge-m3",
}

def tokenize(text):
    return [w.lower() for w in re.findall(r"[A-Za-z0-9]+", text)]

class BM25:
    def __init__(self, corpus_texts):
        self.corpus = corpus_texts
        self.tokens = [tokenize(t) for t in corpus_texts]
        self.N = len(corpus_texts)
        self.avgdl = sum(len(toks) for toks in self.tokens) / max(self.N, 1)
        self.k1, self.b = 1.2, 0.75
        df = {}
        for toks in self.tokens:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log((self.N - f + 0.5) / (f + 0.5) + 1) for t, f in df.items()}

    def get_scores(self, query_tokens):
        scores = np.zeros(self.N)
        for idx, doc_tokens in enumerate(self.tokens):
            tf = {}
            for t in doc_tokens:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for t in query_tokens:
                if t not in self.idf:
                    continue
                f = tf.get(t, 0)
                dl = len(doc_tokens)
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores[idx] = s
        return scores

texts = [c["code"] + " " + c["text"] for c in corpus]
codes = [c["code"] for c in corpus]
bm25 = BM25(texts)

# Evaluate each model
from sklearn.metrics import ndcg_score
results = {}

for name, model_name in MODELS.items():
    print(f"\nLoading {name}: {model_name}")
    t0 = time.time()
    model = SentenceTransformer(model_name)
    load_time = time.time() - t0
    print(f"  Loaded in {load_time:.1f}s")

    # Precompute embeddings
    t0 = time.time()
    embs = model.encode(texts, batch_size=32, show_progress_bar=True, normalize_embeddings=True)
    embs_time = time.time() - t0
    print(f"  Embeddings computed in {embs_time:.1f}s, shape={embs.shape}")

    # Hybrid search with ALPHA=0.8
    ALPHA = 0.8
    r10s, r20s, mrrs, dcgs, exposures = [], [], [], [], []
    for q in test_q:
        ans = q["answer_code"]
        qtokens = tokenize(q["query"])
        bm_scores = bm25.get_scores(qtokens)
        bm_scores = bm_scores / (bm_scores.max() or 1)
        qv = model.encode(q["query"], show_progress_bar=False, normalize_embeddings=True)
        cos = embs @ qv
        score = ALPHA * bm_scores + (1 - ALPHA) * cos
        ranked = np.argsort(-score)
        retrieved = [codes[i] for i in ranked]
        top10 = retrieved[:10]
        r10 = 1 if ans in top10 else 0
        r20 = 1 if ans in retrieved[:20] else 0
        # MRR
        try:
            rank = top10.index(ans) + 1
            mrr = 1.0 / rank
        except ValueError:
            mrr = 0.0
        # nDCG@10 (binary relevance)
        rel = [1 if c == ans else 0 for c in retrieved[:10]]
        dcg = sum(r / math.log2(i+2) for i, r in enumerate(rel))
        ideal = [1] + [0]*9
        idcg = sum(r / math.log2(i+2) for i, r in enumerate(ideal))
        ndcg = dcg / (idcg or 1)
        # Exposure (characters retrieved)
        exp = sum(len(corpus[i]["text"]) for i in ranked[:20])
        r10s.append(r10)
        r20s.append(r20)
        mrrs.append(mrr)
        dcgs.append(ndcg)
        exposures.append(exp)

    results[name] = {
        "model": model_name,
        "R@10": round(np.mean(r10s), 4),
        "R@20": round(np.mean(r20s), 4),
        "MRR": round(np.mean(mrrs), 4),
        "nDCG@10": round(np.mean(dcgs), 4),
        "exposure": round(np.mean(exposures), 2),
        "load_time_s": round(load_time, 1),
        "embed_time_s": round(embs_time, 1),
    }
    print(f"  Results: {results[name]}")

# Save results
(OUT_DIR / "embedding_comparison.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
print("\n=== Summary ===")
for name, r in results.items():
    print(f"{name}: R@10={r['R@10']}, R@20={r['R@20']}, MRR={r['MRR']}, nDCG@10={r['nDCG@10']}, expo={r['exposure']}")
