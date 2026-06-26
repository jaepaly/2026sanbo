#!/usr/bin/env python3
"""Create TASK F figures from existing output/*.json files only.

The figures intentionally include source file names, sample sizes, and compact
value tables so the PNGs can be checked against the JSON without guessing.
No retrieval, embedding, reranking, or external API call is run here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"

BLUE = "#4C78A8"
ORANGE = "#F58518"
GREEN = "#54A24B"
PURPLE = "#B279A2"
GRAY = "#666666"
DARK = "#222222"
GRID = "#D9D9D9"


def load_json(name: str) -> dict:
    return json.loads((OUT_DIR / name).read_text(encoding="utf-8"))


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\malgunbd.ttf" if bold else r"C:\Windows\Fonts\malgun.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


FONT_TITLE = font(30, True)
FONT_SUBTITLE = font(18)
FONT_BODY = font(18)
FONT_SMALL = font(15)
FONT_TABLE = font(16)
FONT_TABLE_BOLD = font(16, True)


def fmt4(value: float) -> str:
    return f"{value:.4f}"


def fmt2(value: float) -> str:
    return f"{value:.2f}"


def scale(value: float, lo: float, hi: float, start: float, end: float) -> float:
    if abs(hi - lo) < 1e-12:
        return (start + end) / 2
    return start + (value - lo) * (end - start) / (hi - lo)


def draw_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str) -> None:
    draw.text((70, 35), title, fill=DARK, font=FONT_TITLE)
    draw.text((70, 76), subtitle, fill=GRAY, font=FONT_SUBTITLE)


def draw_axes(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    x_ticks: Iterable[float],
    y_ticks: Iterable[float],
    x_label: str,
    y_label: str,
) -> None:
    left, top, right, bottom = box
    for y in y_ticks:
        y_px = scale(y, y_min, y_max, bottom, top)
        draw.line((left, y_px, right, y_px), fill=GRID, width=1)
        draw.text((left - 62, y_px - 10), f"{y:.3f}" if y_max - y_min < 0.1 else f"{y:.2f}", fill=DARK, font=FONT_SMALL)
    for x in x_ticks:
        x_px = scale(x, x_min, x_max, left, right)
        draw.line((x_px, bottom, x_px, bottom + 7), fill=DARK, width=2)
        label = f"{x:g}"
        draw.text((x_px - 14, bottom + 12), label, fill=DARK, font=FONT_SMALL)
    draw.line((left, bottom, right, bottom), fill=DARK, width=2)
    draw.line((left, top, left, bottom), fill=DARK, width=2)
    draw.text(((left + right) // 2 - 120, bottom + 45), x_label, fill=DARK, font=FONT_BODY)
    draw.text((left, top - 30), y_label, fill=DARK, font=FONT_BODY)


def draw_value_label(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, color: str, offset: tuple[int, int]) -> None:
    x, y = xy
    dx, dy = offset
    pos = (x + dx, y + dy)
    bbox = draw.textbbox(pos, text, font=FONT_SMALL)
    pad = 3
    draw.rectangle((bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad), fill="white")
    draw.text(pos, text, fill=color, font=FONT_SMALL)


def draw_legend(draw: ImageDraw.ImageDraw, x: int, y: int, items: list[tuple[str, str]]) -> None:
    for idx, (label, color) in enumerate(items):
        yy = y + idx * 30
        draw.line((x, yy + 10, x + 36, yy + 10), fill=color, width=5)
        draw.ellipse((x + 12, yy + 2, x + 24, yy + 14), fill=color)
        draw.text((x + 46, yy - 2), label, fill=DARK, font=FONT_BODY)


def draw_table(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    headers: list[str],
    rows: list[list[str]],
    widths: list[int],
    row_h: int = 34,
) -> None:
    total_w = sum(widths)
    draw.rectangle((x, y, x + total_w, y + row_h), fill="#F2F2F2", outline=DARK)
    xx = x
    for header, width in zip(headers, widths):
        draw.text((xx + 8, y + 8), header, fill=DARK, font=FONT_TABLE_BOLD)
        draw.line((xx, y, xx, y + row_h * (len(rows) + 1)), fill="#BDBDBD")
        xx += width
    draw.line((x + total_w, y, x + total_w, y + row_h * (len(rows) + 1)), fill="#BDBDBD")
    for ri, row in enumerate(rows):
        yy = y + row_h * (ri + 1)
        fill = "white" if ri % 2 == 0 else "#FAFAFA"
        draw.rectangle((x, yy, x + total_w, yy + row_h), fill=fill, outline="#E0E0E0")
        xx = x
        for cell, width in zip(row, widths):
            draw.text((xx + 8, yy + 8), cell, fill=DARK, font=FONT_TABLE)
            xx += width


def save_image(image: Image.Image, name: str) -> None:
    image.save(OUT_DIR / name, dpi=(200, 200))


def fig_paraphrase_gap() -> None:
    data = load_json("paraphrase_gap.json")
    rows_min = data["results"]["minimal_text"]["summary"]
    rows_full = data["results"]["full_text"]["summary"]
    xs = [r["n_removed_high_idf_shared_terms"] for r in rows_min]
    min_vals = [r["recall@10"] for r in rows_min]
    full_vals = [r["recall@10"] for r in rows_full]
    n = data["query_count"]

    image = Image.new("RGB", (1600, 1080), "white")
    draw = ImageDraw.Draw(image)
    draw_header(
        draw,
        "Self-Retrieval Dependency Under Vocabulary Gap",
        f"source=output/paraphrase_gap.json | evaluated queries n={n} | metric=Recall@10",
    )

    box = (100, 150, 1230, 675)
    x_min, x_max = -0.4, 10.4
    y_min, y_max = 0.38, 1.02
    draw_axes(draw, box, x_min, x_max, y_min, y_max, xs, [0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00], "Removed high-IDF shared terms (N)", "Recall@10")

    series = [("minimal_text", min_vals, BLUE, (8, 10)), ("full_text", full_vals, ORANGE, (8, -26))]
    for label, vals, color, offset in series:
        points = []
        for x, y in zip(xs, vals):
            px = scale(x, x_min, x_max, box[0], box[2])
            py = scale(y, y_min, y_max, box[3], box[1])
            points.append((px, py))
        draw.line(points, fill=color, width=4)
        for point, value in zip(points, vals):
            draw.ellipse((point[0] - 6, point[1] - 6, point[0] + 6, point[1] + 6), fill=color)
            draw_value_label(draw, point, fmt4(value), color, offset)
    draw_legend(draw, 1280, 170, [("minimal_text", BLUE), ("full_text", ORANGE)])

    table_rows = [[str(x), fmt4(m), fmt4(f)] for x, m, f in zip(xs, min_vals, full_vals)]
    draw.text((80, 735), "JSON values used in the plot", fill=DARK, font=FONT_BODY)
    draw_table(draw, 80, 770, ["N removed", "minimal_text R@10", "full_text R@10"], table_rows, [170, 260, 240])
    draw.text((80, 1015), "Note: This is a self-retrieval sensitivity analysis, not a legal determination.", fill=GRAY, font=FONT_SMALL)
    save_image(image, "fig_paraphrase_gap.png")


def fig_retriever_alpha() -> None:
    data = load_json("retriever_compare.json")
    alphas = sorted(data["alphas"])
    levels = data["ablation_levels"]
    n = data["query_count"]
    dense_model = data.get("dense_model", "")

    image = Image.new("RGB", (1700, 1120), "white")
    draw = ImageDraw.Draw(image)
    draw_header(
        draw,
        "Synthetic Set: Alpha vs Recall@10",
        f"source=output/retriever_compare.json | evaluated queries n={n} | alpha=0 Dense, alpha=1 BM25 | dense={dense_model}",
    )

    box = (100, 155, 1260, 675)
    x_min, x_max = -0.05, 1.05
    y_min, y_max = 0.20, 1.02
    draw_axes(draw, box, x_min, x_max, y_min, y_max, alphas, [0.20, 0.35, 0.50, 0.65, 0.80, 0.95, 1.00], "alpha", "Recall@10")

    colors = [BLUE, ORANGE, GREEN, PURPLE]
    legend_items = []
    table_rows: list[list[str]] = []
    for idx, level in enumerate(levels):
        row = data["results"]["summary"][str(level)]
        vals = [row[f"alpha={a}"]["recall@10"] for a in alphas]
        color = colors[idx % len(colors)]
        legend_items.append((f"N={level}", color))
        points = [(scale(a, x_min, x_max, box[0], box[2]), scale(v, y_min, y_max, box[3], box[1])) for a, v in zip(alphas, vals)]
        draw.line(points, fill=color, width=4)
        for point, value in zip(points, vals):
            draw.ellipse((point[0] - 6, point[1] - 6, point[0] + 6, point[1] + 6), fill=color)
            draw_value_label(draw, point, fmt4(value), color, (8, -24 if idx % 2 == 0 else 10))
        table_rows.append([str(level)] + [fmt4(v) for v in vals])
    draw_legend(draw, 1305, 175, legend_items)

    headers = ["N removed"] + [f"alpha={a:g}" for a in alphas]
    draw.text((80, 735), "JSON values used in the plot", fill=DARK, font=FONT_BODY)
    draw_table(draw, 80, 770, headers, table_rows, [150, 155, 155, 155, 155, 155])
    save_image(image, "fig_retriever_alpha.png")


def fig_exposure_recall() -> None:
    data = load_json("experiment_logs.json")
    n = data["test_query_count"]
    conditions = ["minimal_no_code", "minimal_text", "full_text"]
    colors = {"minimal_no_code": BLUE, "minimal_text": ORANGE, "full_text": GREEN}
    vals = [(c, data["metrics"][c]["exposure@10"], data["metrics"][c]["recall@10"]) for c in conditions]

    image = Image.new("RGB", (1550, 1050), "white")
    draw = ImageDraw.Draw(image)
    draw_header(
        draw,
        "Exposure-Recall Frontier",
        f"source=output/experiment_logs.json | test queries n={n} | x=mean exposure@10 chars, y=Recall@10",
    )

    box = (100, 155, 1170, 675)
    x_values = [x for _, x, _ in vals]
    x_min, x_max = min(x_values) - 250, max(x_values) + 300
    y_min, y_max = 0.975, 1.000
    draw_axes(draw, box, x_min, x_max, y_min, y_max, [1600, 2400, 3200, 4000, 4800], [0.975, 0.980, 0.985, 0.990, 0.995, 1.000], "Mean exposure@10 (characters)", "Recall@10")

    points = []
    label_offsets = {"minimal_no_code": (55, -70), "minimal_text": (55, 26), "full_text": (-250, -10)}
    for condition, exposure, recall in vals:
        point = (scale(exposure, x_min, x_max, box[0], box[2]), scale(recall, y_min, y_max, box[3], box[1]))
        points.append(point)
        color = colors[condition]
        draw.ellipse((point[0] - 11, point[1] - 11, point[0] + 11, point[1] + 11), fill=color)
        label = f"{condition}\nexposure={fmt2(exposure)}\nR@10={fmt4(recall)}"
        draw_value_label(draw, point, label, color, label_offsets[condition])
    draw.line(points, fill="#8A8A8A", width=3)

    table_rows = [[c, fmt2(exposure), fmt4(recall)] for c, exposure, recall in vals]
    draw.text((80, 735), "JSON values used in the plot", fill=DARK, font=FONT_BODY)
    draw_table(draw, 80, 770, ["condition", "exposure@10", "Recall@10"], table_rows, [250, 180, 180])
    save_image(image, "fig_exposure_recall.png")


def fig_validated_retriever() -> None:
    data = load_json("validated_eval.json")
    meta = data["meta"]
    alpha_order = ["alpha=1.0", "alpha=0.7", "alpha=0.5", "alpha=0.3", "alpha=0.0"]
    labels = {
        "alpha=1.0": "BM25\nalpha=1.0",
        "alpha=0.7": "Hybrid\nalpha=0.7",
        "alpha=0.5": "Hybrid\nalpha=0.5",
        "alpha=0.3": "Hybrid\nalpha=0.3",
        "alpha=0.0": "Dense\nalpha=0.0",
    }
    n_all = meta["evaluated_count"]
    n_excluded = meta["excluded_count"]
    n_en = data["summary"]["alpha=1.0"]["en_n"]
    n_ko = data["summary"]["alpha=1.0"]["ko_n"]

    image = Image.new("RGB", (1750, 1180), "white")
    draw = ImageDraw.Draw(image)
    draw_header(
        draw,
        "Validated Set: Recall@10 by Alpha",
        f"source=output/validated_eval.json | evaluated n={n_all} (EN n={n_en}, KO n={n_ko}) | excluded n={n_excluded}",
    )
    draw.text((70, 104), "matching=exact full-code equality; labels are corpus-text-grounded category labels, not legal determinations", fill=GRAY, font=FONT_SMALL)

    box = (100, 180, 1480, 690)
    y_min, y_max = 0.0, 0.30
    y_ticks = [0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
    left, top, right, bottom = box
    for y in y_ticks:
        y_px = scale(y, y_min, y_max, bottom, top)
        draw.line((left, y_px, right, y_px), fill=GRID, width=1)
        draw.text((left - 58, y_px - 10), f"{y:.2f}", fill=DARK, font=FONT_SMALL)
    draw.line((left, bottom, right, bottom), fill=DARK, width=2)
    draw.line((left, top, left, bottom), fill=DARK, width=2)
    draw.text((left, top - 30), "Recall@10", fill=DARK, font=FONT_BODY)
    draw.text(((left + right) // 2 - 80, bottom + 70), "Retriever / alpha", fill=DARK, font=FONT_BODY)

    group_w = (right - left) / len(alpha_order)
    bar_w = 48
    series = [("Overall n=13", "recall@10", BLUE), ("EN n=8", "en_recall@10", ORANGE), ("KO n=5", "ko_recall@10", GREEN)]
    for gi, alpha in enumerate(alpha_order):
        center = left + group_w * (gi + 0.5)
        label_lines = labels[alpha].split("\n")
        draw.text((center - 62, bottom + 15), label_lines[0], fill=DARK, font=FONT_SMALL)
        draw.text((center - 62, bottom + 38), label_lines[1], fill=DARK, font=FONT_SMALL)
        for si, (_, key, color) in enumerate(series):
            value = data["summary"][alpha][key]
            x0 = center + (si - 1) * (bar_w + 10) - bar_w / 2
            x1 = x0 + bar_w
            y0 = scale(value, y_min, y_max, bottom, top)
            draw.rectangle((x0, y0, x1, bottom), fill=color)
            draw.text((x0 - 2, y0 - 24), fmt4(value), fill=DARK, font=FONT_SMALL)
    draw_legend(draw, 1515, 200, [(s[0], s[2]) for s in series])

    table_rows = []
    for alpha in alpha_order:
        row = data["summary"][alpha]
        table_rows.append([alpha, labels[alpha].replace("\n", " "), fmt4(row["recall@10"]), fmt4(row["en_recall@10"]), fmt4(row["ko_recall@10"])])
    draw.text((80, 785), "JSON values used in the plot", fill=DARK, font=FONT_BODY)
    draw_table(draw, 80, 820, ["alpha", "retriever", "Overall R@10 (n=13)", "EN R@10 (n=8)", "KO R@10 (n=5)"], table_rows, [150, 210, 230, 200, 200])
    save_image(image, "fig_validated_retriever.png")


def save_figures() -> None:
    fig_paraphrase_gap()
    fig_retriever_alpha()
    fig_exposure_recall()
    fig_validated_retriever()


def main() -> None:
    save_figures()
    print(
        json.dumps(
            {
                "renderer": "Pillow detailed",
                "created": [
                    "fig_paraphrase_gap.png",
                    "fig_retriever_alpha.png",
                    "fig_exposure_recall.png",
                    "fig_validated_retriever.png",
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
