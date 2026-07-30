#!/usr/bin/env python3
"""Shared retrieval + statistics core.

Single source of truth for the pieces that the audit found were duplicated,
divergent, or subtly wrong across the experiment scripts:

1. **Deterministic ranking.** `np.argsort(-scores)` returns the sort
   implementation's tie order. When a query's score vector is all zeros (which
   happens for 44 of the 45 Korean queries against the 100%-English corpus,
   because BM25 has no in-vocabulary overlap at all) the "ranking" was really
   just corpus array order, so `top10` was corpus rows 0-9 and a gold label
   sitting in row 4 counted as a hit. `rank_indices` breaks ties by ascending
   corpus index so results are reproducible across numpy versions, and
   `retrieve` treats a no-signal query as an empty result set instead.

2. **Index text vs returned text.** `build_doc_text` was used simultaneously as
   the BM25/dense index input *and* as the definition of how much information
   the service discloses. That conflated a retrieval-quality manipulation with
   an exposure manipulation. They are separate arguments here.

3. **Exposure accounting.** The old `exposure_for_entry` returned the identical
   expression for `minimal_text` and `minimal_no_code`, so the two modes had
   byte-identical exposure for every corpus entry even though the strings
   actually returned differ by the control code. Exposure is now *derived* from
   `returned_text`, so the two definitions cannot drift apart again.

4. **Statistics.** Paired bootstrap, exact McNemar, TOST equivalence testing
   (the old code declared "no significant loss" whenever a CI happened to
   include zero, which is accepting the null, not demonstrating equivalence),
   Clopper-Pearson intervals for absolute rates, and Holm correction.

Nothing here changes the BM25 scoring math -- `BM25` is byte-equivalent to the
original implementation so the synthetic-set results (the paper's most robust
claim) reproduce unchanged.
"""

from __future__ import annotations

import math
import re
from statistics import mean
from typing import Iterable, Sequence

import numpy as np

# --------------------------------------------------------------------------
# text handling (canonical copies -- run_experiments imports these)
# --------------------------------------------------------------------------

CONTROL_CODE_RE = re.compile(
    r"\b(?:ECCN-)?[0-9][A-EY][0-9]{3}[A-Za-z]?(?:\.[A-Za-z0-9]+)*\b"
    r"|\b[0-9]\.[A-E](?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?(?:\.[a-z])?(?:\.[0-9]+)?\b",
    re.I,
)


def tokenize(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z0-9가-힣]+", text or "")]


def first_sentence(text: str, max_chars: int = 260) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    parts = re.split(r"(?<=[.;])\s+", text)
    candidate = parts[0] if parts else text
    if len(candidate) < 80 and len(parts) > 1:
        candidate = " ".join(parts[:2])
    return candidate[:max_chars].strip()


def route_text(entry: dict) -> str:
    flags = ", ".join(entry.get("review_flags", [])) or "none"
    return f"{entry.get('control_system')} | {entry.get('official_route')} | flags={flags}"


# --------------------------------------------------------------------------
# index text vs returned text
# --------------------------------------------------------------------------

MODES = ("full_text", "minimal_text", "minimal_no_code", "route_only")


def index_text(entry: dict, mode: str) -> str:
    """Text placed into the retrieval index (BM25 tokens / dense embedding)."""
    code = entry.get("code", "")
    text = entry.get("text", "")
    if mode == "full_text":
        return f"{code} {text}"
    if mode == "minimal_text":
        return f"{code} {first_sentence(text)}"
    if mode == "minimal_no_code":
        return first_sentence(text)
    if mode == "route_only":
        return route_text(entry)
    raise ValueError(f"unknown mode: {mode}")


def returned_text(entry: dict, mode: str) -> str:
    """Text the service hands back to the caller for a retrieved entry.

    Identical in form to `index_text` -- but a separate function so an
    experiment can index one way and disclose another (e.g. index the first
    sentence *with* the control code for retrieval quality, but return it
    *without* the code to disclose less).
    """
    return index_text(entry, mode)


def exposure_chars(entry: dict, mode: str) -> int:
    """Disclosure proxy: characters actually returned. Derived, never hardcoded."""
    return len(returned_text(entry, mode))


def legacy_exposure_chars(entry: dict, mode: str) -> int:
    """The pre-fix definition, kept only so audits can quantify the difference.

    Bug: `minimal_text` and `minimal_no_code` return the same expression, so the
    control code was never counted and the two modes were indistinguishable.
    """
    if mode == "full_text":
        return len(entry.get("text", ""))
    if mode in ("minimal_text", "minimal_no_code"):
        return len(first_sentence(entry.get("text", "")))
    if mode == "route_only":
        return len(route_text(entry))
    return 0


# --------------------------------------------------------------------------
# BM25 (math unchanged from the original implementation)
# --------------------------------------------------------------------------


class BM25:
    def __init__(self, corpus_texts: list[str]):
        self.tokens = [tokenize(t) for t in corpus_texts]
        self.N = len(self.tokens)
        self.avgdl = mean(len(t) for t in self.tokens) or 1.0
        self.k1 = 1.2
        self.b = 0.75
        df: dict[str, int] = {}
        for toks in self.tokens:
            for token in set(toks):
                df[token] = df.get(token, 0) + 1
        self.idf = {
            token: math.log((self.N - freq + 0.5) / (freq + 0.5) + 1)
            for token, freq in df.items()
        }
        self._tf = []
        for doc_tokens in self.tokens:
            tf: dict[str, int] = {}
            for token in doc_tokens:
                tf[token] = tf.get(token, 0) + 1
            self._tf.append(tf)

    def scores(self, query: str) -> np.ndarray:
        q_tokens = tokenize(query)
        out = np.zeros(self.N, dtype=float)
        known = [t for t in q_tokens if t in self.idf]
        if not known:
            return out
        for idx in range(self.N):
            tf = self._tf[idx]
            dl = len(self.tokens[idx])
            score = 0.0
            for token in known:
                freq = tf.get(token, 0)
                denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                if denom:
                    score += self.idf[token] * freq * (self.k1 + 1) / denom
            out[idx] = score
        return out

    def vocabulary_overlap(self, query: str) -> int:
        """How many distinct query tokens exist in the index vocabulary."""
        return len({t for t in tokenize(query) if t in self.idf})


# --------------------------------------------------------------------------
# deterministic ranking
# --------------------------------------------------------------------------


def rank_indices(scores: np.ndarray) -> np.ndarray:
    """Descending score, ties broken by ascending corpus index.

    Reproducible across numpy versions and sort kinds, unlike `np.argsort(-s)`.
    """
    s = np.asarray(scores, dtype=float)
    return np.lexsort((np.arange(s.shape[0]), -s))


def has_signal(scores: np.ndarray, eps: float = 1e-12) -> bool:
    """True if the retriever produced any non-zero evidence for this query."""
    s = np.asarray(scores, dtype=float)
    return bool(s.size and float(s.max()) > eps)


def retrieve(scores: np.ndarray, k: int = 10, *, zero_is_failure: bool = True) -> list[int]:
    """Top-k corpus indices. A no-signal query returns [] (retrieval failure).

    `zero_is_failure=False` reproduces the old permissive behaviour where an
    all-zero score vector still yielded k documents (corpus order).
    """
    if zero_is_failure and not has_signal(scores):
        return []
    return list(rank_indices(scores)[:k])


def minmax(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    lo, hi = float(x.min()), float(x.max())
    if hi - lo < 1e-12:
        return np.zeros_like(x)
    return (x - lo) / (hi - lo)


def blend(bm: np.ndarray, dn: np.ndarray, alpha: float) -> np.ndarray:
    """alpha * BM25 + (1 - alpha) * dense, on per-query min-max normalised scores.

    Normalisation is applied to the full corpus score vector before any top-k
    truncation, so the two components are on comparable scales.
    """
    return alpha * np.asarray(bm, dtype=float) + (1.0 - alpha) * np.asarray(dn, dtype=float)


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------


def paired_bootstrap_ci(
    diffs: Sequence[float], *, iters: int = 20000, seed: int = 20260626, conf: float = 0.95
) -> dict:
    """Percentile bootstrap CI for the mean of paired per-query differences."""
    arr = np.asarray(list(diffs), dtype=float)
    n = arr.shape[0]
    if n == 0:
        return {"mean": 0.0, "ci": [0.0, 0.0], "n": 0, "iters": iters, "seed": seed}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(iters, n))
    draws = arr[idx].mean(axis=1)
    lo = (1.0 - conf) / 2.0
    return {
        "mean": round(float(arr.mean()), 4),
        "ci": [round(float(np.quantile(draws, lo)), 4),
               round(float(np.quantile(draws, 1.0 - lo)), 4)],
        "n": int(n),
        "iters": iters,
        "seed": seed,
        "boot_se": round(float(draws.std(ddof=1)), 4),
    }


def sig(x: float, digits: int = 6) -> float:
    """Round to significant figures, not decimal places.

    p-values here reach 1e-9; `round(p, 10)` would silently flatten them.
    """
    if x == 0 or not math.isfinite(x):
        return float(x)
    return float(f"%.{digits}g" % x)


def _binom_sf_ge(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) for X ~ Binomial(n, p), computed exactly."""
    if n == 0:
        return 1.0
    total = 0.0
    for i in range(k, n + 1):
        total += math.comb(n, i) * (p ** i) * ((1 - p) ** (n - i))
    return min(1.0, total)


def exact_mcnemar(a: Sequence[int], b: Sequence[int]) -> dict:
    """Exact McNemar / sign test on paired binary outcomes (a vs b).

    `wins`   = queries where a hit and b missed
    `losses` = queries where b hit and a missed
    `ties`   = queries where both agree (uninformative for the test)
    """
    a = list(a)
    b = list(b)
    wins = sum(1 for x, y in zip(a, b) if x > y)
    losses = sum(1 for x, y in zip(a, b) if y > x)
    ties = len(a) - wins - losses
    disc = wins + losses
    if disc == 0:
        p_two = 1.0
        p_one = 1.0
    else:
        # one-sided alternative: "a beats b", i.e. wins are over-represented
        p_one = _binom_sf_ge(wins, disc, 0.5)
        p_two = min(1.0, 2.0 * _binom_sf_ge(max(wins, losses), disc, 0.5))
    return {
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "discordant": disc,
        "p_two_sided_exact": sig(p_two),
        "p_one_sided_exact": sig(p_one),
    }


def tost_paired(diffs: Sequence[float], delta: float, *, iters: int = 20000,
                seed: int = 20260626) -> dict:
    """Two one-sided tests for equivalence of paired outcomes.

    H0_lower: true mean difference <= -delta   (a is worse than b by >= delta)
    H0_upper: true mean difference >= +delta
    Equivalence is claimed only if BOTH are rejected, i.e. max(p) < alpha.

    `delta` must be chosen and justified *before* looking at the data; that is
    the whole point. Reporting "the CI included zero" is not equivalence.
    """
    arr = np.asarray(list(diffs), dtype=float)
    n = arr.shape[0]
    if n < 2:
        return {"delta": delta, "n": int(n), "conclusive": False,
                "reason": "n too small for an equivalence test"}
    m = float(arr.mean())
    se = float(arr.std(ddof=1) / math.sqrt(n))
    if se == 0.0:
        p_lower = 0.0 if m > -delta else 1.0
        p_upper = 0.0 if m < delta else 1.0
    else:
        # normal approximation on the mean of paired differences
        z_lower = (m + delta) / se
        z_upper = (delta - m) / se
        p_lower = 0.5 * math.erfc(z_lower / math.sqrt(2))
        p_upper = 0.5 * math.erfc(z_upper / math.sqrt(2))
    p_max = max(p_lower, p_upper)
    # bootstrap CI as a second, distribution-free view of the same question
    boot = paired_bootstrap_ci(arr, iters=iters, seed=seed, conf=0.90)  # 90% CI == TOST at 5%
    ci90 = boot["ci"]
    return {
        "delta": delta,
        "n": int(n),
        "mean_diff": round(m, 4),
        "se": round(se, 4),
        "p_lower": sig(p_lower),
        "p_upper": sig(p_upper),
        "p_max": sig(p_max),
        "equivalent_at_0.05": bool(p_max < 0.05),
        "ci90_bootstrap": ci90,
        "ci90_within_margin": bool(-delta < ci90[0] and ci90[1] < delta),
    }


def required_n_for_equivalence(diffs: Sequence[float], delta: float,
                               power: float = 0.80) -> int | None:
    """Approximate paired sample size needed to establish equivalence at margin delta.

    Uses the observed SD and observed mean difference. Returns None when the
    observed effect is already outside the margin (no n would help).
    """
    arr = np.asarray(list(diffs), dtype=float)
    if arr.shape[0] < 2:
        return None
    sd = float(arr.std(ddof=1))
    m = abs(float(arr.mean()))
    if sd == 0.0 or m >= delta:
        return None
    z_a = 1.6448536269514722   # one-sided 5%
    z_b = 0.8416212335729143   # 80% power
    n = ((z_a + z_b) * sd / (delta - m)) ** 2
    return int(math.ceil(n))


def clopper_pearson(k: int, n: int, conf: float = 0.95) -> list[float]:
    """Exact binomial CI for an absolute rate such as R@10 = k/n."""
    if n == 0:
        return [0.0, 0.0]
    alpha = 1.0 - conf
    lo = 0.0 if k == 0 else _beta_ppf(alpha / 2, k, n - k + 1)
    hi = 1.0 if k == n else _beta_ppf(1 - alpha / 2, k + 1, n - k)
    return [round(lo, 4), round(hi, 4)]


def _beta_ppf(p: float, a: float, b: float) -> float:
    """Inverse regularised incomplete beta via bisection (no scipy dependency)."""
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b) by continued fraction."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
    f, c, d = 1.0, 1.0, 0.0
    for i in range(0, 300):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
        else:
            num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        f *= c * d
        if abs(1.0 - c * d) < 1e-12:
            break
    result = front * (f - 1.0)
    if x > (a + 1) / (a + b + 2):
        return 1.0 - _betainc(b, a, 1 - x)
    return min(1.0, max(0.0, result))


def holm(pvals: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    """Holm-Bonferroni step-down correction over a family of comparisons."""
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    k = len(items)
    out: dict[str, dict] = {}
    rejected_so_far = True
    for i, (name, p) in enumerate(items):
        adj = min(1.0, p * (k - i))
        if i > 0:
            prev = out[items[i - 1][0]]["p_adjusted"]
            adj = max(adj, prev)   # enforce monotonicity
        rejected_so_far = rejected_so_far and adj < alpha
        out[name] = {
            "p_raw": round(p, 10),
            "p_adjusted": round(adj, 10),
            "significant_at_0.05": bool(rejected_so_far),
            "family_size": k,
        }
    return out


# --------------------------------------------------------------------------
# reproducibility metadata
# --------------------------------------------------------------------------


def env_meta(extra: dict | None = None) -> dict:
    """Record everything needed to reproduce a run bit-for-bit."""
    meta: dict = {"numpy": np.__version__}
    try:
        import platform
        meta["python"] = platform.python_version()
        meta["platform"] = platform.platform()
    except Exception:
        pass
    try:
        import torch
        meta["torch"] = torch.__version__
    except Exception:
        meta["torch"] = None
    try:
        import sentence_transformers
        meta["sentence_transformers"] = sentence_transformers.__version__
    except Exception:
        meta["sentence_transformers"] = None
    if extra:
        meta.update(extra)
    return meta


def rate_with_ci(hits: Iterable[int], conf: float = 0.95) -> dict:
    """Absolute rate plus exact binomial CI -- for reporting R@10 honestly."""
    h = [int(x) for x in hits]
    n = len(h)
    k = sum(h)
    return {
        "k": k,
        "n": n,
        "rate": round(k / n, 4) if n else 0.0,
        "ci95": clopper_pearson(k, n, conf),
    }
