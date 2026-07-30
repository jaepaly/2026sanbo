#!/usr/bin/env python3
"""논문용 figure 생성 — 검증셋 n=71 기준으로 재작성.

정정 내역 (감사 항목 M9-B / M14-D5):

1. **stale 데이터 소스 교체.**
   - `fig_validated_retriever`는 `output/validated_eval.json`(n=13, hybrid R@10
     0.2308)을 읽고 있었다. 논문 헤드라인은 n=71의 0.578이다. 이제
     `output/validated_suite.json`(없으면 `..._smoke.json`)을 읽는다.
   - `fig_exposure_recall`은 `output/experiment_logs.json`, 즉 **자기참조 합성셋**을
     읽고 있었다. 논문은 "합성셋이 아니라 검증셋으로 입증"이라고 주장한다. 이제
     합성 / 검증 2패널로 분리해 둘을 나란히 놓고, 어느 쪽이 자기참조인지 그림
     안에 명시한다.

2. **오차막대 추가.** 이전 판은 점값만 찍었다. 이제
   - 절대율(R@10)에는 Clopper-Pearson 정확 이항구간,
   - 짝지음 차이(예: hybrid - BM25)에는 paired bootstrap 95% CI를 쓴다.
   두 구간은 다른 질문에 답하므로 그림 안에 어느 쪽인지 표시한다.

3. **fig_embedding_robustness 신설.** 모델 교체에도 dense 성분의 우위가 유지되는지
   보여주는 그림이 없었다.

4. **`docs/figures/fig1~3.png` 폐기 결정.** 세 PNG는 생성 코드가 저장소에 없고
   README·PAPER·docs에서 참조 0건이다. 재생성이 불가능하므로 **폐기**로 판단한다
   (여기서 대체 생성하지 않는다). 근거와 결정은 README.md '그림' 절에 남겼다.
   파일 자체는 감사 목적으로 삭제하지 않는다.

렌더러: matplotlib (이전 판은 Pillow로 축·눈금을 직접 그렸다). 한글 라벨은 Windows의
'Malgun Gothic'을 쓰고, 폰트가 없으면 영문 라벨로 폴백하며 그 사실을 stdout에 출력한다.
DPI 200.

새 검색·임베딩·외부 API 호출은 하지 않는다(기존 output/*.json만 읽는다).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

import retrieval_core as rc

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"

DPI = 200
SEED = 20260626
BOOTSTRAP_ITERS = 20000

BLUE = "#4C78A8"
ORANGE = "#F58518"
GREEN = "#54A24B"
PURPLE = "#B279A2"
RED = "#D62728"
GRAY = "#666666"

# 한국어 우선 폰트 후보 (Windows 기본 → 대체 → 폴백)
KOREAN_FONTS = ["Malgun Gothic", "NanumGothic", "Hancom Gothic", "Gulim", "Batang"]
KOREAN_OK = False
CHOSEN_FONT = None


def setup_font() -> None:
    """한글 폰트를 등록한다. 없으면 KOREAN_OK=False로 두고 영문 라벨로 폴백한다."""
    global KOREAN_OK, CHOSEN_FONT
    available = {f.name for f in fm.fontManager.ttflist}
    for name in KOREAN_FONTS:
        if name in available:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            KOREAN_OK = True
            CHOSEN_FONT = name
            return
    plt.rcParams["axes.unicode_minus"] = False
    KOREAN_OK = False
    CHOSEN_FONT = plt.rcParams["font.family"][0] if plt.rcParams["font.family"] else "default"
    print(
        "[font] 한글 폰트를 찾지 못했다 (후보: %s). 라벨을 영문으로 폴백한다. "
        "현재 폰트=%s" % (", ".join(KOREAN_FONTS), CHOSEN_FONT)
    )


def T(ko: str, en: str) -> str:
    """한글 폰트가 있으면 한국어, 없으면 영문 라벨."""
    return ko if KOREAN_OK else en


def load_json(name: str) -> dict | None:
    path = OUT_DIR / name
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def validated_source() -> tuple[dict, str, bool]:
    """검증셋 통합 산출물. 본실행 파일이 없으면 smoke로 대체하고 그림에 표시한다."""
    data = load_json("validated_suite.json")
    if data is not None:
        return data, "output/validated_suite.json", False
    data = load_json("validated_suite_smoke.json")
    if data is None:
        raise FileNotFoundError(
            "output/validated_suite.json / validated_suite_smoke.json 둘 다 없다."
        )
    return data, "output/validated_suite_smoke.json", True


def smoke_banner(fig, is_smoke: bool) -> None:
    if not is_smoke:
        return
    fig.text(
        0.5, 0.005,
        T("※ 단일 모델 smoke 산출물(validated_suite_smoke.json) 기준 — 3모델 본실행 후 재생성 필요",
          "NOTE: single-model smoke output; regenerate after the full 3-model run"),
        ha="center", va="bottom", fontsize=8, color=RED,
    )


def save(fig, name: str) -> str:
    fig.savefig(OUT_DIR / name, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return name


def cp_err(rates: list[float], cis: list[list[float]]) -> np.ndarray:
    """errorbar용 비대칭 오차 (2, n) 배열."""
    lo = [max(0.0, r - c[0]) for r, c in zip(rates, cis)]
    hi = [max(0.0, c[1] - r) for r, c in zip(rates, cis)]
    return np.array([lo, hi])


def subgroup(vec: list[int], langs: list[str], lang: str | None) -> list[int]:
    return [h for h, lg in zip(vec, langs) if lang is None or lg == lang]


# --------------------------------------------------------------------------
# (a) 검증셋 검색기 비교 — n=71
# --------------------------------------------------------------------------


def fig_validated_retriever() -> str:
    data, src, is_smoke = validated_source()
    meta = data["meta"]
    langs = data["langs"]
    model = meta["primary_model"]
    imode = "minimal_text" if "minimal_text" in meta["index_modes"] else meta["index_modes"][0]
    hits = data["hit_vectors"][model][imode]

    order = ["BM25", "hybrid_0.7", "hybrid_0.5", "hybrid_0.3", "dense"]
    order = [k for k in order if k in hits]
    n, n_en, n_ko = meta["n"], meta["n_en"], meta["n_ko"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 6.2),
                                   gridspec_kw={"width_ratios": [1.35, 1]})

    # --- 좌: 절대 R@10 (Clopper-Pearson)
    groups = [
        (T(f"전체 n={n}", f"Overall n={n}"), None, BLUE),
        (T(f"영어 n={n_en}", f"EN n={n_en}"), "en", ORANGE),
        (T(f"한국어 n={n_ko}", f"KO n={n_ko}"), "ko", GREEN),
    ]
    x = np.arange(len(order))
    width = 0.26
    for gi, (label, lang, color) in enumerate(groups):
        rates, cis = [], []
        for retr in order:
            r = rc.rate_with_ci(subgroup(hits[retr], langs, lang))
            rates.append(r["rate"])
            cis.append(r["ci95"])
        pos = x + (gi - 1) * width
        ax1.bar(pos, rates, width, label=label, color=color, edgecolor="white", linewidth=0.6)
        ax1.errorbar(pos, rates, yerr=cp_err(rates, cis), fmt="none",
                     ecolor="#333333", elinewidth=1.1, capsize=3)
        for px, rv in zip(pos, rates):
            ax1.text(px, rv + 0.022, f"{rv:.3f}", ha="center", va="bottom", fontsize=7.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(order, fontsize=9)
    ax1.set_ylim(0, 1.0)
    ax1.set_ylabel(T("R@10", "Recall@10"))
    ax1.set_title(T("절대 R@10 — 오차막대 = Clopper-Pearson 95% 정확 이항구간",
                    "Absolute R@10 — error bars = Clopper-Pearson exact 95% CI"),
                  fontsize=10.5)
    ax1.legend(fontsize=8.5, loc="upper left")
    ax1.grid(axis="y", alpha=0.3, linewidth=0.6)
    ax1.set_axisbelow(True)

    # --- 우: 짝지음 차이 (paired bootstrap)
    contrasts = [
        ("hybrid_0.5", "BM25", T("hybrid(α0.5) - BM25", "hybrid(a0.5) - BM25")),
        ("dense", "BM25", T("dense - BM25", "dense - BM25")),
        ("hybrid_0.5", "dense", T("hybrid(α0.5) - dense", "hybrid(a0.5) - dense")),
    ]
    rows, ylabels, colors = [], [], []
    for lang, lcolor in [(None, BLUE), ("en", ORANGE), ("ko", GREEN)]:
        tag = T({None: "전체", "en": "영어", "ko": "한국어"}[lang],
                {None: "all", "en": "EN", "ko": "KO"}[lang])
        for treat, base, cname in contrasts:
            a = subgroup(hits[treat], langs, lang)
            b = subgroup(hits[base], langs, lang)
            diffs = [p - q for p, q in zip(a, b)]
            boot = rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERS, seed=SEED)
            mc = rc.exact_mcnemar(a, b)
            rows.append((boot["mean"], boot["ci"], mc))
            ylabels.append(f"{cname} [{tag}]")
            colors.append(lcolor)

    ypos = np.arange(len(rows))[::-1]
    for yp, (mean, ci, mc), color in zip(ypos, rows, colors):
        ax2.errorbar([mean], [yp],
                     xerr=[[max(0.0, mean - ci[0])], [max(0.0, ci[1] - mean)]],
                     fmt="o", color=color, ecolor=color, elinewidth=1.6,
                     capsize=4, markersize=6)
        star = "*" if mc["p_two_sided_exact"] < 0.05 else ""
        ax2.text(ci[1] + 0.02, yp,
                 f"{mean:+.3f}  {mc['wins']}/{mc['losses']}/{mc['ties']}  "
                 f"p={mc['p_two_sided_exact']:.2g}{star}",
                 va="center", fontsize=7.5)
    ax2.axvline(0, color="#333333", linewidth=1.0, linestyle="--")
    ax2.set_yticks(ypos)
    ax2.set_yticklabels(ylabels, fontsize=8)
    ax2.set_xlim(-0.25, 1.05)
    ax2.set_xlabel(T("R@10 평균차 (짝지음)", "Paired mean difference in R@10"))
    ax2.set_title(T("짝지음 차이 — 오차막대 = paired bootstrap 95% CI\n"
                    "숫자 = 평균차, 승/패/무, exact McNemar 양측 p (*p<0.05)",
                    "Paired difference — error bars = paired bootstrap 95% CI\n"
                    "labels = mean diff, wins/losses/ties, exact McNemar two-sided p"),
                  fontsize=10.5)
    ax2.grid(axis="x", alpha=0.3, linewidth=0.6)
    ax2.set_axisbelow(True)

    fig.suptitle(
        T(f"검증셋 검색기 비교 (n={n}: 영어 {n_en} / 한국어 {n_ko})",
          f"Validated set: retriever comparison (n={n}: EN {n_en} / KO {n_ko})"),
        fontsize=14, y=1.0,
    )
    fig.text(0.5, 0.955,
             T(f"source={src} | 색인={imode} | dense={model} | "
               f"bootstrap {BOOTSTRAP_ITERS:,}회, seed {SEED} | "
               "라벨=코퍼스 텍스트 근거 카테고리 라벨(법적 판정 아님)",
               f"source={src} | index={imode} | dense={model} | "
               f"bootstrap {BOOTSTRAP_ITERS:,}, seed {SEED} | "
               "labels are corpus-text-grounded, not legal determinations"),
             ha="center", va="top", fontsize=8, color=GRAY)
    fig.tight_layout(rect=(0, 0.02, 1, 0.945))
    smoke_banner(fig, is_smoke)
    return save(fig, "fig_validated_retriever.png")


# --------------------------------------------------------------------------
# (b) 노출-성능 frontier — 합성(자기참조) vs 검증셋 2패널
# --------------------------------------------------------------------------


def fig_exposure_recall() -> str:
    logs = load_json("experiment_logs.json")
    data, src, is_smoke = validated_source()
    meta = data["meta"]
    model = meta["primary_model"]
    langs = data["langs"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 6.4))

    # --- 좌: 합성 자기참조 셋
    conds = ["route_only", "minimal_no_code", "minimal_text", "full_text"]
    conds = [c for c in conds if c in logs["metrics"]]
    colors = {"route_only": PURPLE, "minimal_no_code": BLUE,
              "minimal_text": ORANGE, "full_text": GREEN}
    pts = [(c, logs["metrics"][c]["exposure@10"], logs["metrics"][c]["recall@10"],
            logs["metrics"][c]["recall@10_ci95"]) for c in conds]
    pts.sort(key=lambda p: p[1])
    ax1.plot([p[1] for p in pts], [p[2] for p in pts], "-", color="#999999", linewidth=1.4, zorder=1)
    # 라벨이 겹치지 않게 위/아래로 번갈아 배치한다 (minimal_* 두 점이 거의 같은 위치)
    offsets = [(12, 14), (12, 14), (12, -34), (12, 10)]
    for i, (cond, exp, rec, ci) in enumerate(pts):
        ax1.errorbar([exp], [rec], yerr=[[max(0, rec - ci[0])], [max(0, ci[1] - rec)]],
                     fmt="o", color=colors[cond], markersize=9, capsize=4,
                     ecolor=colors[cond], elinewidth=1.4, zorder=3)
        ax1.annotate(f"{cond}\n{exp:.0f} / {rec:.4f}", (exp, rec),
                     textcoords="offset points", xytext=offsets[i % len(offsets)],
                     fontsize=8, color=colors[cond])
    ax1.set_xlabel(T("평균 노출량@10 (반환 문자 수)", "Mean exposure@10 (returned characters)"))
    ax1.set_ylabel(T("R@10", "Recall@10"))
    ax1.set_xlim(0, max(p[1] for p in pts) * 1.35)
    ax1.set_ylim(-0.05, 1.15)
    ax1.set_title(T("(A) 합성셋 — 자기참조 재검색 조건 (일반화 금지)\n"
                    f"source=output/experiment_logs.json, n={logs['test_query_count']}",
                    "(A) Synthetic set - SELF-RETRIEVAL condition (do not generalise)\n"
                    f"source=output/experiment_logs.json, n={logs['test_query_count']}"),
                  fontsize=10.5)
    ax1.grid(alpha=0.3, linewidth=0.6)
    ax1.set_axisbelow(True)

    # --- 우: 검증셋 (색인 모드 × 반환 모드)
    exp10 = data["exposure_at10"]
    hits = data["hit_vectors"][model]
    retr = "hybrid_0.5" if "hybrid_0.5" in hits[meta["index_modes"][0]] else "dense"
    imodes = meta["index_modes"]
    rmodes = meta["return_modes"]
    marker_by_rmode = {"full_text": "o", "minimal_text": "s", "minimal_no_code": "^"}
    color_by_imode = {"full_text": GREEN, "minimal_text": ORANGE, "minimal_no_code": BLUE}

    for imode in imodes:
        r = rc.rate_with_ci(hits[imode][retr])
        xs, ys = [], []
        for rmode in rmodes:
            exp = exp10[imode][f"return={rmode}"]
            xs.append(exp)
            ys.append(r["rate"])
            diagonal = (rmode == imode)
            ax2.errorbar([exp], [r["rate"]],
                         yerr=[[max(0, r["rate"] - r["ci95"][0])],
                               [max(0, r["ci95"][1] - r["rate"])]],
                         fmt=marker_by_rmode[rmode], color=color_by_imode[imode],
                         markersize=10 if diagonal else 8,
                         markerfacecolor=color_by_imode[imode] if diagonal else "white",
                         markeredgecolor=color_by_imode[imode], markeredgewidth=1.6,
                         capsize=3, ecolor=color_by_imode[imode], elinewidth=1.2, zorder=3)
        # 같은 색인 모드는 R@10이 동일하다 (반환량만 바뀌므로 랭킹 불변)
        ax2.plot(xs, ys, ":", color=color_by_imode[imode], linewidth=1.2, zorder=1)

    # 핵심 화살표: 색인=full_text 유지, 반환만 축소 → 노출 급감, R@10 불변
    if "full_text" in imodes and "minimal_no_code" in rmodes:
        x0 = exp10["full_text"]["return=full_text"]
        x1 = exp10["full_text"]["return=minimal_no_code"]
        y0 = rc.rate_with_ci(hits["full_text"][retr])["rate"]
        cut = 100 * (x0 - x1) / x0
        ax2.annotate("", xy=(x1, y0), xytext=(x0, y0),
                     arrowprops=dict(arrowstyle="->", color=RED, linewidth=1.8))
        ax2.text((x0 + x1) / 2, y0 + 0.035,
                 T(f"반환량만 축소: {x0:.0f}→{x1:.0f}자 ({cut:.1f}% 감소), R@10 불변",
                   f"return-only cut: {x0:.0f}->{x1:.0f} chars ({cut:.1f}%), R@10 unchanged"),
                 ha="center", fontsize=8.5, color=RED)

    handles = [plt.Line2D([], [], marker="o", linestyle="", color=color_by_imode[m],
                          label=T(f"색인={m}", f"index={m}")) for m in imodes]
    handles += [plt.Line2D([], [], marker=marker_by_rmode[m], linestyle="", color="#444444",
                           markerfacecolor="white",
                           label=T(f"반환={m}", f"return={m}")) for m in rmodes]
    ax2.legend(handles=handles, fontsize=7.5, loc="lower right", ncol=2)
    ax2.set_xlabel(T("평균 노출량@10 (반환 문자 수)", "Mean exposure@10 (returned characters)"))
    ax2.set_ylabel(T("R@10", "Recall@10"))
    ax2.set_ylim(-0.05, 1.08)
    ax2.set_title(T(f"(B) 검증셋 n={meta['n']} — 색인 모드 × 반환 모드 ({retr})\n"
                    f"source={src} | 오차막대 = Clopper-Pearson 95% CI",
                    f"(B) Validated set n={meta['n']} - index mode x return mode ({retr})\n"
                    f"source={src} | error bars = Clopper-Pearson 95% CI"),
                  fontsize=10.5)
    ax2.grid(alpha=0.3, linewidth=0.6)
    ax2.set_axisbelow(True)

    fig.suptitle(T("노출-성능 frontier: 합성(자기참조) vs 검증셋",
                   "Exposure-recall frontier: synthetic (self-retrieval) vs validated"),
                 fontsize=14)
    fig.text(0.5, 0.945,
             T("비용은 '색인 축소'에서만 발생한다. 같은 색인 모드 안에서 반환량만 줄이면 랭킹이 "
               "바뀌지 않으므로 R@10은 그대로다(점선).",
               "Cost comes only from shrinking the INDEX. Within one index mode, cutting the "
               "returned text does not change the ranking, so R@10 is unchanged (dotted line)."),
             ha="center", va="top", fontsize=8, color=GRAY)
    fig.tight_layout(rect=(0, 0.02, 1, 0.935))
    smoke_banner(fig, is_smoke)
    return save(fig, "fig_exposure_recall.png")


# --------------------------------------------------------------------------
# (c) 임베딩 robustness — 신설
# --------------------------------------------------------------------------


def fig_embedding_robustness() -> str:
    data, src, is_smoke = validated_source()
    meta = data["meta"]
    langs = data["langs"]
    imode = "minimal_text" if "minimal_text" in meta["index_modes"] else meta["index_modes"][0]
    models = [m for m in meta["dense_models"] if m in data["hit_vectors"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.5, 5.8),
                                   gridspec_kw={"width_ratios": [1.15, 1]})

    # --- 좌: 모델별 R@10 (BM25 / dense / hybrid), 전체
    series = [("BM25", BLUE), ("dense", ORANGE), ("hybrid_0.5", GREEN)]
    x = np.arange(len(models))
    width = 0.26 if len(models) > 1 else 0.16
    ax1.set_xlim(-0.5, len(models) - 0.5)
    for si, (retr, color) in enumerate(series):
        rates, cis = [], []
        for mk in models:
            vec = data["hit_vectors"][mk][imode].get(retr)
            r = rc.rate_with_ci(vec) if vec else {"rate": 0.0, "ci95": [0.0, 0.0]}
            rates.append(r["rate"])
            cis.append(r["ci95"])
        pos = x + (si - 1) * width
        ax1.bar(pos, rates, width, color=color, label=retr, edgecolor="white", linewidth=0.6)
        ax1.errorbar(pos, rates, yerr=cp_err(rates, cis), fmt="none",
                     ecolor="#333333", elinewidth=1.1, capsize=3)
        for px, rv in zip(pos, rates):
            ax1.text(px, rv + 0.02, f"{rv:.3f}", ha="center", va="bottom", fontsize=8)
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, fontsize=9)
    ax1.set_ylim(0, 1.0)
    ax1.set_ylabel(T("R@10 (전체)", "Recall@10 (overall)"))
    ax1.set_title(T("dense 모델별 R@10 — 오차막대 = Clopper-Pearson 95% CI",
                    "R@10 by dense model - error bars = Clopper-Pearson 95% CI"),
                  fontsize=10.5)
    ax1.legend(fontsize=8.5, loc="upper left")
    ax1.grid(axis="y", alpha=0.3, linewidth=0.6)
    ax1.set_axisbelow(True)

    # --- 우: 모델별 (hybrid - BM25) 짝지음 차이, 전체/영어/한국어
    ylabels, rows, colors = [], [], []
    for mk in models:
        h = data["hit_vectors"][mk][imode]
        for lang, color in [(None, BLUE), ("en", ORANGE), ("ko", GREEN)]:
            tag = T({None: "전체", "en": "영어", "ko": "한국어"}[lang],
                    {None: "all", "en": "EN", "ko": "KO"}[lang])
            a = subgroup(h.get("hybrid_0.5") or h["dense"], langs, lang)
            b = subgroup(h["BM25"], langs, lang)
            diffs = [p - q for p, q in zip(a, b)]
            boot = rc.paired_bootstrap_ci(diffs, iters=BOOTSTRAP_ITERS, seed=SEED)
            mc = rc.exact_mcnemar(a, b)
            rows.append((boot["mean"], boot["ci"], mc))
            ylabels.append(f"{mk} [{tag}]")
            colors.append(color)

    ypos = np.arange(len(rows))[::-1]
    for yp, (mean, ci, mc), color in zip(ypos, rows, colors):
        ax2.errorbar([mean], [yp],
                     xerr=[[max(0.0, mean - ci[0])], [max(0.0, ci[1] - mean)]],
                     fmt="o", color=color, ecolor=color, elinewidth=1.6,
                     capsize=4, markersize=6)
        star = "*" if mc["p_two_sided_exact"] < 0.05 else ""
        ax2.text(ci[1] + 0.015, yp,
                 f"{mean:+.3f}  {mc['wins']}/{mc['losses']}  p={mc['p_two_sided_exact']:.2g}{star}",
                 va="center", fontsize=7.5)
    ax2.axvline(0, color="#333333", linewidth=1.0, linestyle="--")
    ax2.set_yticks(ypos)
    ax2.set_yticklabels(ylabels, fontsize=8)
    ax2.set_xlim(-0.15, 1.0)
    ax2.set_xlabel(T("hybrid(α0.5) - BM25 평균차 (짝지음)",
                     "hybrid(a0.5) - BM25 paired mean difference"))
    ax2.set_title(T("오차막대 = paired bootstrap 95% CI\n숫자 = 평균차, 승/패, exact McNemar p",
                    "error bars = paired bootstrap 95% CI\nlabels = mean diff, wins/losses, "
                    "exact McNemar p"),
                  fontsize=10.5)
    ax2.grid(axis="x", alpha=0.3, linewidth=0.6)
    ax2.set_axisbelow(True)

    fig.suptitle(T(f"임베딩 robustness (검증셋 n={meta['n']}, 색인={imode})",
                   f"Embedding robustness (validated n={meta['n']}, index={imode})"),
                 fontsize=14)
    note = T(f"source={src} | 모델 {len(models)}개 | bootstrap {BOOTSTRAP_ITERS:,}회, seed {SEED}",
             f"source={src} | {len(models)} model(s) | bootstrap {BOOTSTRAP_ITERS:,}, seed {SEED}")
    if len(models) < 2:
        note += T("  ← 모델이 1개뿐이므로 robustness 주장 불가 (확인 필요)",
                  "  <- only one model: no robustness claim can be made (TO VERIFY)")
    fig.text(0.5, 0.94, note, ha="center", va="top", fontsize=8,
             color=RED if len(models) < 2 else GRAY)
    fig.tight_layout(rect=(0, 0.02, 1, 0.93))
    smoke_banner(fig, is_smoke)
    return save(fig, "fig_embedding_robustness.png")


# --------------------------------------------------------------------------
# (d) 자기참조 의존성 (paraphrase gap)
# --------------------------------------------------------------------------


def fig_paraphrase_gap() -> str | None:
    data = load_json("paraphrase_gap.json")
    if data is None:
        print("[skip] output/paraphrase_gap.json 없음")
        return None
    n = data["query_count"]
    fig, ax = plt.subplots(figsize=(9.5, 6.0))
    for mode, color in [("minimal_text", BLUE), ("full_text", ORANGE)]:
        rows = data["results"][mode]["summary"]
        xs = [r["n_removed_high_idf_shared_terms"] for r in rows]
        ys = [r["recall@10"] for r in rows]
        if "recall@10_ci95" in rows[0]:
            cis = [r["recall@10_ci95"] for r in rows]
            ax.errorbar(xs, ys, yerr=cp_err(ys, cis), fmt="o-", color=color,
                        label=mode, capsize=3, elinewidth=1.1, markersize=6)
        else:
            ax.plot(xs, ys, "o-", color=color, label=mode, markersize=6)
        for xv, yv in zip(xs, ys):
            ax.annotate(f"{yv:.4f}", (xv, yv), textcoords="offset points",
                        xytext=(0, 9), ha="center", fontsize=7.5, color=color)
        legacy_key = "recall@10_legacy_zero_permissive"
        if legacy_key in rows[0]:
            ax.plot(xs, [r[legacy_key] for r in rows], "--", color=color, alpha=0.45,
                    linewidth=1.2,
                    label=T(f"{mode} (정정 전 정의)", f"{mode} (pre-fix definition)"))
    ax.set_xlabel(T("제거한 고-IDF 공유토큰 수 N", "N removed high-IDF shared terms"))
    ax.set_ylabel(T("R@10", "Recall@10"))
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(fontsize=8.5)
    ax.set_title(T(f"자기참조 의존성: 어휘 격차에 따른 R@10 붕괴 (합성셋 n={n})",
                   f"Self-retrieval dependency under vocabulary gap (synthetic n={n})"),
                 fontsize=12.5)
    fig.text(0.5, 0.005,
             T("source=output/paraphrase_gap.json | 오차막대 = Clopper-Pearson 95% CI | "
               "점선 = 전점수 0 질의에 코퍼스 앞머리를 부여한 정정 전 정의",
               "source=output/paraphrase_gap.json | error bars = Clopper-Pearson 95% CI | "
               "dashed = pre-fix definition that awarded corpus-order rows to zero-score queries"),
             ha="center", va="bottom", fontsize=8, color=GRAY)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return save(fig, "fig_paraphrase_gap.png")


# --------------------------------------------------------------------------
# (e) 합성셋 alpha 스윕
# --------------------------------------------------------------------------


def fig_retriever_alpha() -> str | None:
    data = load_json("retriever_compare.json")
    if data is None:
        print("[skip] output/retriever_compare.json 없음")
        return None
    alphas = sorted(data["alphas"])
    levels = data["ablation_levels"]
    n = data["query_count"]
    fig, ax = plt.subplots(figsize=(9.5, 6.0))
    colors = [BLUE, ORANGE, GREEN, PURPLE]
    for i, level in enumerate(levels):
        row = data["results"]["summary"][str(level)]
        ys = [row[f"alpha={a}"]["recall@10"] for a in alphas]
        color = colors[i % len(colors)]
        if "recall@10_ci95" in row[f"alpha={alphas[0]}"]:
            cis = [row[f"alpha={a}"]["recall@10_ci95"] for a in alphas]
            ax.errorbar(alphas, ys, yerr=cp_err(ys, cis), fmt="o-", color=color,
                        label=f"N={level}", capsize=3, elinewidth=1.0, markersize=5)
        else:
            ax.plot(alphas, ys, "o-", color=color, label=f"N={level}", markersize=5)
        for xv, yv in zip(alphas, ys):
            ax.annotate(f"{yv:.3f}", (xv, yv), textcoords="offset points",
                        xytext=(0, 8 if i % 2 == 0 else -13), ha="center",
                        fontsize=7, color=color)
    ax.set_xlabel(T("alpha (1.0 = BM25 단독, 0.0 = dense 단독)",
                    "alpha (1.0 = BM25 only, 0.0 = dense only)"))
    ax.set_ylabel(T("R@10", "Recall@10"))
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.3, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.legend(fontsize=8.5, title=T("어휘격차 N", "vocab gap N"))
    ax.set_title(T(f"합성셋: alpha별 R@10 (n={n}, 어휘격차별)",
                   f"Synthetic set: R@10 by alpha (n={n}, per vocabulary gap)"),
                 fontsize=12.5)
    fig.text(0.5, 0.005,
             T("source=output/retriever_compare.json | 오차막대 = Clopper-Pearson 95% CI | "
               "BM25와 dense는 동일한 ablation 텍스트를 입력받는다(입력 비대칭 정정 후)",
               "source=output/retriever_compare.json | error bars = Clopper-Pearson 95% CI | "
               "BM25 and dense receive the identical ablated text (input asymmetry fixed)"),
             ha="center", va="bottom", fontsize=8, color=GRAY)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    return save(fig, "fig_retriever_alpha.png")


# --------------------------------------------------------------------------


def main() -> None:
    setup_font()
    created = []
    for fn in (fig_validated_retriever, fig_exposure_recall, fig_embedding_robustness,
               fig_paraphrase_gap, fig_retriever_alpha):
        name = fn()
        if name:
            created.append(name)
    _, src, is_smoke = validated_source()
    print(json.dumps({
        "renderer": "matplotlib",
        "font": CHOSEN_FONT,
        "korean_labels": KOREAN_OK,
        "dpi": DPI,
        "validated_source": src,
        "validated_source_is_smoke": is_smoke,
        "created": created,
        "deprecated_not_regenerated": [
            "docs/figures/fig1_scope_decomposition.png",
            "docs/figures/fig2_privacy_utility_map.png",
            "docs/figures/fig3_scenario_scope.png",
        ],
        "deprecation_reason": "생성 코드가 저장소에 없고 참조 0건. 재현 불가하므로 폐기 결정 "
                             "(README.md '그림' 절에 기록). 파일은 감사용으로 삭제하지 않음.",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
