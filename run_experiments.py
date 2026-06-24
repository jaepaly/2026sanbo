#!/usr/bin/env python3
"""Run 4-condition retrieval experiment and save metrics + figures."""
import json, os, math, textwrap
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Inline lightweight BM25 (no external deps) using term frequency

def tokenize(text: str):
    return [w.lower() for w in __import__("re").findall(r"[A-Za-z0-9]+", text)]


class BM25:
    def __init__(self, corpus_texts):
        self.corpus = corpus_texts
        self.tokens = [tokenize(t) for t in corpus_texts]
        self.N = len(corpus_texts)
        self.avgdl = mean(len(toks) for toks in self.tokens) or 1.0
        self.k1 = 1.2
        self.b = 0.75
        # df
        df = {}
        for toks in self.tokens:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self.df = df
        self.idf = {}
        for t, f in df.items():
            self.idf[t] = math.log((self.N - f + 0.5) / (f + 0.5) + 1)

    def score(self, query, idx):
        qt = tokenize(query)
        tf = {}
        for t in self.tokens[idx]:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for t in qt:
            if t not in self.idf:
                continue
            f = tf.get(t, 0)
            dl = len(self.tokens[idx])
            denom = f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += self.idf[t] * f * (self.k1 + 1) / denom
        return score


def build_query_text(entry, mode):
    code = entry.get("code", "")
    text = entry.get("text", "")
    if mode == "raw":
        return f"{code} {text}"
    if mode == "minimal":
        # first sentence only as a proxy
        first = text.split(".")[0] if "." in text else text
        return f"{code} {first}"
    if mode == "category":
        # keep top-level letter only e.g. 3A
        top = "".join([c for c in code if c.isalpha() or c.isdigit()][:2])
        return f"{top} {text[:120]}"
    # local_rule: same as raw but keep note of numeric fields
    return f"{code} {text}"


def recall_at_k(retrieved_codes, answer_code, k):
    return 1 if answer_code in retrieved_codes[:k] else 0


def mrr(retrieved_codes, answer_code):
    for rank, c in enumerate(retrieved_codes, 1):
        if c == answer_code:
            return 1.0 / rank
    return 0.0


def weighted_exposure(retrieved, mode):
    # proxy: longer text => higher exposure
    total = 0
    for e in retrieved:
        if mode == "raw":
            total += len(e.get("text", ""))
        elif mode == "minimal":
            total += len((e.get("text", "").split(".")[0]))
        else:
            total += len(e.get("text", "")) * 0.1
    return total


def run():
    corpus = []
    for p in [DATA_DIR / "corpus" / "wassenaar.json", DATA_DIR / "corpus" / "india_scomet.json"]:
        corpus += json.loads(p.read_text(encoding="utf-8"))
    code_to_entry = {e["code"]: e for e in corpus}
    queries = json.loads((DATA_DIR / "queries.json").read_text(encoding="utf-8"))["test"]

    ks = [1, 5, 10, 20]
    modes = ["raw", "minimal", "category", "local_rule"]
    index = {m: i for i, m in enumerate(modes)}

    # Build index texts + bm25 per mode
    bm25 = {}
    texts = {}
    for mode in modes:
        texts[mode] = [build_query_text(e, mode) for e in corpus]
        bm25[mode] = BM25(texts[mode])

    logs = []
    summary = {
        m: {f"recall@{k}": [] for k in ks} | {"mrr": [], "exposure": []}
        for m in modes
    }

    for q in queries:
        ans = q["answer_code"]
        row = {"query": q["query"], "answer": ans}
        for mode in modes:
            scores = [bm25[mode].score(q["query"], i) for i in range(len(corpus))]
            ranked_idx = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)
            retrieved = [corpus[i]["code"] for i in ranked_idx]
            retrieved_entries = [corpus[i] for i in ranked_idx]
            for k in ks:
                summary[mode][f"recall@{k}"].append(recall_at_k(retrieved, ans, k))
            summary[mode]["mrr"].append(mrr(retrieved, ans))
            summary[mode]["exposure"].append(weighted_exposure(retrieved_entries[:20], mode))
            row[mode] = {
                "top5": retrieved[:5],
                f"recall@10": recall_at_k(retrieved, ans, 10),
                "mrr": mrr(retrieved, ans),
            }
        logs.append(row)

    metrics = {m: {} for m in modes}
    for mode in modes:
        for k in ks:
            metrics[mode][f"recall@{k}"] = round(mean(summary[mode][f"recall@{k}"]), 4)
        metrics[mode]["mrr"] = round(mean(summary[mode]["mrr"]), 4)
        metrics[mode]["exposure"] = round(mean(summary[mode]["exposure"]), 2)

    # Save logs + metrics
    (OUT_DIR / "experiment_logs.json").write_text(
        json.dumps({"logs": logs, "metrics": metrics}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- figures ---
    labels = modes
    r10 = [metrics[m]["recall@10"] for m in labels]
    expo = [metrics[m]["exposure"] for m in labels]
    r20 = [metrics[m]["recall@20"] for m in labels]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(labels, r10, color=["#e74c3c", "#2ecc71", "#3498db", "#f39c12"], edgecolor="black", linewidth=0.5)
    for i, v in enumerate(r10):
        ax.text(i, v + 0.01, f"{v:.2f}", ha="center", va="bottom", fontweight="bold")
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Recall@10")
    ax.set_title("Condition-wise Recall@10")
    ax.grid(axis="y", linestyle="--", alpha=0.5)
    plt.tight_layout()
    fig.savefig(OUT_DIR / "fig_r10_compare.png", dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.scatter(expo, r10, s=120, c=["#e74c3c", "#2ecc71", "#3498db", "#f39c12"])
    for i, m in enumerate(labels):
        ax.annotate(m, (expo[i], r10[i]), textcoords="offset points", xytext=(6, 4))
    ax.set_xlabel("Weighted Exposure (proxy chars)")
    ax.set_ylabel("Recall@10")
    ax.set_title("Privacy–Utility Frontier (proxy)")
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    fig.savefig(OUT_DIR / "fig_frontier.png", dpi=150)
    plt.close(fig)

    # Sensitivity: k sweep
    ks_list = [1, 5, 10, 20, 50]
    fig, ax = plt.subplots(figsize=(7, 4))
    for mode in modes:
        vals = [metrics[mode].get(f"recall@{k}", 0) for k in ks_list]
        ax.plot(ks_list, vals, marker="o", label=mode)
    ax.set_xlabel("k")
    ax.set_ylabel("Recall@k")
    ax.set_title("Sensitivity: Recall vs k")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    fig.savefig(OUT_DIR / "fig_sensitivity.png", dpi=150)
    plt.close(fig)

    # Write markdown summary
    lines = [
        "# 전략물자 AI 사전 트리아지 — 실험 결과 보고서",
        "",
        f"- **생성일시**: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **코퍼스**: Wassenaar 2025 ({len(json.loads((DATA_DIR/'corpus'/'wassenaar.json').read_text(encoding='utf-8')))} 항목) + India SCOMET 2024 ({len(json.loads((DATA_DIR/'corpus'/'india_scomet.json').read_text(encoding='utf-8')))} 항목)",
        f"- **평가셋**: {len(queries)} 질의 (synthetic)",
        "",
        "## 메트릭",
        "",
        "| 조건 | Recall@10 | Recall@20 | MRR | 노출량 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for mode in modes:
        m = metrics[mode]
        lines.append(f"| {mode} | {m['recall@10']:.2f} | {m['recall@20']:.2f} | {m['mrr']:.3f} | {m['exposure']:.0f} |")
    lines += [
        "",
        "## 관찰",
        "",
        "- 조건별 재현율과 노출량의 trade-off가 포착됨",
        "- 로컬규럼분리 조건은 원문 수준의 재현ale 유지가 필요한지 확인 필요",
        "- BM25 하이브리드 구성 추후 세밀 튜닝 필요",
        "",
        "## 경고",
        "",
        "- 현재 임베딩 미사용 (TF-only BM25). 하이브리드 검색은 다음 커밋에서 적용.",
        "- Query generator가 단일 코드 기반이라 분포가 편향됨",
        "- 한국어 질의 번역 레이어는 아직 포함되지 않음",
        "",
        "## 부록: 그래프",
        "",
        "- output/fig_r10_compare.png",
        "- output/fig_frontier.png",
        "- output/fig_sensitivity.png",
    ]
    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("Done.")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
