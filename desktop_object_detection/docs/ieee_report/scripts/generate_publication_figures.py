#!/usr/bin/env python3
"""Generate compact, publication-size figures for the A4 experiment report."""

from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import Color, HexColor, black, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


REPORT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = REPORT_DIR.parents[1]
OUTPUT_DIR = REPORT_DIR / "figures"
DATASET_DIR = PROJECT_DIR / "datasets/experiment1_1000self_4000public_v1"
TRAIN_DIR = PROJECT_DIR / "outputs/training/experiment1_1000self_4000public_v1"
TEST_DIR = (
    PROJECT_DIR
    / "outputs/evaluation/experiment1_1000self_4000public_v1_test/runs/best_test-2"
)

PT = 72.0
PAGE_WIDTH = 7.16 * PT
CLASS_NAMES = ["mouse", "keyboard", "laptop", "cup", "headphones"]
CLASS_COLORS = [
    HexColor("#0072B2"),
    HexColor("#D55E00"),
    HexColor("#009E73"),
    HexColor("#CC79A7"),
    HexColor("#E69F00"),
]
NORMAL_FONT = "ReportSans"
BOLD_FONT = "ReportSansBold"


def first_existing(paths: list[str]) -> Path:
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file():
            return path
    raise FileNotFoundError(f"No embeddable figure font found in: {paths}")


pdfmetrics.registerFont(
    TTFont(
        NORMAL_FONT,
        str(
            first_existing(
                [
                    "/System/Library/Fonts/Supplemental/Arial.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                ]
            )
        ),
    )
)
pdfmetrics.registerFont(
    TTFont(
        BOLD_FONT,
        str(
            first_existing(
                [
                    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                ]
            )
        ),
    )
)


def draw_fitted_image(
    pdf: canvas.Canvas,
    image_path: Path,
    label_path: Path,
    x: float,
    y: float,
    width: float,
    height: float,
    panel_label: str,
) -> None:
    with Image.open(image_path) as image:
        image_width, image_height = image.size
    scale = min(width / image_width, height / image_height)
    draw_width = image_width * scale
    draw_height = image_height * scale
    left = x + (width - draw_width) / 2
    bottom = y + (height - draw_height) / 2

    pdf.drawImage(
        ImageReader(str(image_path)),
        left,
        bottom,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )
    pdf.setStrokeColor(HexColor("#444444"))
    pdf.setLineWidth(0.45)
    pdf.rect(left, bottom, draw_width, draw_height, stroke=1, fill=0)

    for raw_line in label_path.read_text(encoding="utf-8").splitlines():
        fields = raw_line.split()
        if len(fields) != 5:
            continue
        class_id = int(fields[0])
        xc, yc, box_width, box_height = map(float, fields[1:])
        box_x = left + (xc - box_width / 2) * draw_width
        box_y = bottom + (1 - yc - box_height / 2) * draw_height
        box_w = box_width * draw_width
        box_h = box_height * draw_height
        color = CLASS_COLORS[class_id]
        pdf.setStrokeColor(color)
        pdf.setLineWidth(1.2)
        pdf.rect(box_x, box_y, box_w, box_h, stroke=1, fill=0)

        label = CLASS_NAMES[class_id]
        font_size = 5.5
        label_width = pdf.stringWidth(label, BOLD_FONT, font_size) + 3.5
        label_x = min(max(box_x, left), left + draw_width - label_width)
        label_y = min(box_y + box_h - font_size - 1, bottom + draw_height - font_size - 1)
        label_y = max(label_y, bottom)
        pdf.setFillColor(color)
        pdf.rect(label_x, label_y, label_width, font_size + 1.8, stroke=0, fill=1)
        pdf.setFillColor(white)
        pdf.setFont(BOLD_FONT, font_size)
        pdf.drawString(label_x + 1.7, label_y + 1.2, label)

    panel_width = pdf.stringWidth(panel_label, BOLD_FONT, 7) + 5
    panel_x = left + draw_width - panel_width - 2
    panel_y = bottom + draw_height - 10
    pdf.setFillColor(Color(0, 0, 0, alpha=0.72))
    pdf.rect(panel_x, panel_y, panel_width, 9, stroke=0, fill=1)
    pdf.setFillColor(white)
    pdf.setFont(BOLD_FONT, 7)
    pdf.drawString(panel_x + 2.5, panel_y + 1.3, panel_label)


def generate_sample_pairs() -> None:
    pairs = [
        ("train", "self_IMG_8382_v000", "self_IMG_8382_v031"),
        ("train", "self_IMG_8252_v000", "self_IMG_8252_v019"),
        ("train", "self_IMG_8304_v000", "self_IMG_8304_v084"),
        ("test", "self_IMG_8306_v000", "self_IMG_8306_v091"),
    ]
    output = OUTPUT_DIR / "self_augmentation_examples.pdf"
    page_height = 3.34 * PT
    pdf = canvas.Canvas(
        str(output),
        pagesize=(PAGE_WIDTH, page_height),
        pageCompression=1,
        initialFontName=NORMAL_FONT,
        invariant=1,
    )

    left_margin = 35
    right_margin = 4
    top_margin = 15
    bottom_margin = 4
    column_gap = 5
    row_gap = 5
    usable_width = PAGE_WIDTH - left_margin - right_margin
    tile_width = (usable_width - 3 * column_gap) / 4
    tile_height = (page_height - top_margin - bottom_margin - row_gap) / 2

    pdf.setFont(NORMAL_FONT, 7)
    pdf.setFillColor(black)
    pdf.saveState()
    pdf.translate(10, bottom_margin + tile_height * 1.5 + row_gap)
    pdf.rotate(90)
    pdf.drawCentredString(0, 0, "Base")
    pdf.restoreState()
    pdf.saveState()
    pdf.translate(10, bottom_margin + tile_height / 2)
    pdf.rotate(90)
    pdf.drawCentredString(0, 0, "Derived")
    pdf.restoreState()

    for column, (split, base_stem, derived_stem) in enumerate(pairs):
        x = left_margin + column * (tile_width + column_gap)
        for row, stem in enumerate((base_stem, derived_stem)):
            y = bottom_margin + (1 - row) * (tile_height + row_gap)
            image_path = DATASET_DIR / "images" / split / f"{stem}.jpg"
            label_path = DATASET_DIR / "labels" / split / f"{stem}.txt"
            letter = chr(ord("a") + row * len(pairs) + column)
            draw_fitted_image(
                pdf,
                image_path,
                label_path,
                x,
                y,
                tile_width,
                tile_height,
                f"({letter})",
            )

    pdf.showPage()
    pdf.save()


def read_training_rows() -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with (TRAIN_DIR / "results.csv").open(encoding="utf-8", newline="") as handle:
        for raw in csv.DictReader(handle):
            rows.append({key: float(value) for key, value in raw.items()})
    return rows


def nice_ticks(minimum: float, maximum: float, count: int = 4) -> list[float]:
    if math.isclose(minimum, maximum):
        return [minimum]
    return [minimum + index * (maximum - minimum) / (count - 1) for index in range(count)]


def draw_line_panel(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    series: list[tuple[str, list[float], Color]],
    epochs: list[float],
) -> None:
    plot_left = x + 29
    plot_bottom = y + 19
    plot_width = width - 36
    plot_height = height - 35
    all_values = [value for _, values, _ in series for value in values]
    minimum = min(all_values)
    maximum = max(all_values)
    padding = max((maximum - minimum) * 0.10, 0.005)
    minimum -= padding
    maximum += padding

    pdf.setFillColor(black)
    pdf.setFont(BOLD_FONT, 7.5)
    pdf.drawString(x + 3, y + height - 10, title)
    pdf.setStrokeColor(HexColor("#777777"))
    pdf.setLineWidth(0.45)
    pdf.line(plot_left, plot_bottom, plot_left, plot_bottom + plot_height)
    pdf.line(plot_left, plot_bottom, plot_left + plot_width, plot_bottom)

    pdf.setFont(NORMAL_FONT, 5.5)
    for tick in nice_ticks(minimum, maximum):
        py = plot_bottom + (tick - minimum) / (maximum - minimum) * plot_height
        pdf.setStrokeColor(HexColor("#E2E2E2"))
        pdf.line(plot_left, py, plot_left + plot_width, py)
        pdf.setFillColor(HexColor("#333333"))
        pdf.drawRightString(plot_left - 3, py - 2, f"{tick:.2f}")

    for tick in (1, 6, 12):
        px = plot_left + (tick - epochs[0]) / (epochs[-1] - epochs[0]) * plot_width
        pdf.setFillColor(HexColor("#333333"))
        pdf.drawCentredString(px, plot_bottom - 8, str(tick))
    pdf.drawCentredString(plot_left + plot_width / 2, y + 2, "Epoch")

    for label, values, color in series:
        points: list[tuple[float, float]] = []
        for epoch, value in zip(epochs, values):
            px = plot_left + (epoch - epochs[0]) / (epochs[-1] - epochs[0]) * plot_width
            py = plot_bottom + (value - minimum) / (maximum - minimum) * plot_height
            points.append((px, py))
        pdf.setStrokeColor(color)
        pdf.setFillColor(color)
        pdf.setLineWidth(1.15)
        path = pdf.beginPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        pdf.drawPath(path, stroke=1, fill=0)
        for px, py in points:
            pdf.circle(px, py, 1.25, stroke=0, fill=1)

    legend_x = plot_left + 4
    legend_y = plot_bottom + plot_height - 7
    pdf.setFont(NORMAL_FONT, 5.4)
    for label, _, color in series:
        pdf.setStrokeColor(color)
        pdf.setLineWidth(1.3)
        pdf.line(legend_x, legend_y, legend_x + 9, legend_y)
        pdf.setFillColor(black)
        pdf.drawString(legend_x + 12, legend_y - 2, label)
        legend_y -= 8


def generate_training_curves() -> None:
    rows = read_training_rows()
    epochs = [row["epoch"] for row in rows]
    blue = HexColor("#0072B2")
    orange = HexColor("#D55E00")
    green = HexColor("#009E73")
    purple = HexColor("#CC79A7")
    output = OUTPUT_DIR / "training_curves.pdf"
    page_height = 3.12 * PT
    pdf = canvas.Canvas(
        str(output),
        pagesize=(PAGE_WIDTH, page_height),
        pageCompression=1,
        initialFontName=NORMAL_FONT,
        invariant=1,
    )

    margin_x = 5
    margin_y = 5
    gap_x = 8
    gap_y = 7
    panel_width = (PAGE_WIDTH - 2 * margin_x - gap_x) / 2
    panel_height = (page_height - 2 * margin_y - gap_y) / 2
    panels = [
        (
            "(a) Training loss",
            [
                ("box", [row["train/box_loss"] for row in rows], blue),
                ("cls", [row["train/cls_loss"] for row in rows], orange),
                ("dfl", [row["train/dfl_loss"] for row in rows], green),
            ],
        ),
        (
            "(b) Validation loss",
            [
                ("box", [row["val/box_loss"] for row in rows], blue),
                ("cls", [row["val/cls_loss"] for row in rows], orange),
                ("dfl", [row["val/dfl_loss"] for row in rows], green),
            ],
        ),
        (
            "(c) Validation precision and recall",
            [
                ("precision", [row["metrics/precision(B)"] for row in rows], blue),
                ("recall", [row["metrics/recall(B)"] for row in rows], orange),
            ],
        ),
        (
            "(d) Validation mean average precision",
            [
                ("mAP@0.5", [row["metrics/mAP50(B)"] for row in rows], green),
                ("mAP@0.5:0.95", [row["metrics/mAP50-95(B)"] for row in rows], purple),
            ],
        ),
    ]
    for index, (title, series) in enumerate(panels):
        column = index % 2
        row = 1 - index // 2
        x = margin_x + column * (panel_width + gap_x)
        y = margin_y + row * (panel_height + gap_y)
        draw_line_panel(pdf, x, y, panel_width, panel_height, title, series, epochs)

    pdf.showPage()
    pdf.save()


def heat_color(value: float) -> Color:
    low = (0.96, 0.98, 1.0)
    high = (0.03, 0.23, 0.48)
    weight = math.sqrt(max(0.0, min(1.0, value)))
    return Color(*(low[index] + (high[index] - low[index]) * weight for index in range(3)))


def generate_confusion_matrix() -> None:
    source = TEST_DIR / "confusion_matrix_normalized.png"
    expected_hash = "9c6df7e794170bd355bed9dc014d09f311bb45a7e48eced541744a8bc913fa99"
    actual_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise RuntimeError("The saved test-set confusion matrix has changed; update the plotted values.")

    # Values are the two-decimal annotations in the verified Ultralytics test artifact above.
    values = [
        [0.93, 0.00, 0.00, 0.01, 0.00, 0.09],
        [0.00, 0.89, 0.02, 0.00, 0.00, 0.39],
        [0.01, 0.00, 0.82, 0.00, 0.00, 0.15],
        [0.00, 0.00, 0.00, 0.78, 0.00, 0.15],
        [0.03, 0.00, 0.00, 0.00, 0.67, 0.21],
        [0.03, 0.10, 0.17, 0.22, 0.32, 0.00],
    ]
    labels = CLASS_NAMES + ["background"]
    page_width = 3.45 * PT
    page_height = 3.18 * PT
    pdf = canvas.Canvas(
        str(OUTPUT_DIR / "test_confusion_matrix.pdf"),
        pagesize=(page_width, page_height),
        pageCompression=1,
        initialFontName=NORMAL_FONT,
        invariant=1,
    )
    left = 61
    bottom = 58
    cell = 25.8
    matrix_size = 6 * cell

    for row in range(6):
        for column in range(6):
            value = values[row][column]
            x = left + column * cell
            y = bottom + (5 - row) * cell
            pdf.setFillColor(heat_color(value))
            pdf.setStrokeColor(white)
            pdf.setLineWidth(0.55)
            pdf.rect(x, y, cell, cell, stroke=1, fill=1)
            if value > 0:
                pdf.setFillColor(white if value >= 0.55 else black)
                pdf.setFont(NORMAL_FONT, 6.4)
                pdf.drawCentredString(x + cell / 2, y + cell / 2 - 2.2, f"{value:.2f}")

    pdf.setFillColor(black)
    pdf.setFont(NORMAL_FONT, 6.5)
    for row, label in enumerate(labels):
        y = bottom + (5 - row) * cell + cell / 2 - 2.2
        pdf.drawRightString(left - 5, y, label)
    for column, label in enumerate(labels):
        x = left + column * cell + cell / 2
        pdf.saveState()
        pdf.translate(x + 2, bottom - 5)
        pdf.rotate(55)
        pdf.drawRightString(0, 0, label)
        pdf.restoreState()

    pdf.setFont(BOLD_FONT, 7)
    pdf.drawCentredString(left + matrix_size / 2, 5, "True class")
    pdf.saveState()
    pdf.translate(10, bottom + matrix_size / 2)
    pdf.rotate(90)
    pdf.drawCentredString(0, 0, "Predicted class")
    pdf.restoreState()

    bar_x = left + matrix_size + 10
    bar_width = 8
    segments = 80
    for index in range(segments):
        value = index / (segments - 1)
        pdf.setFillColor(heat_color(value))
        pdf.rect(
            bar_x,
            bottom + index * matrix_size / segments,
            bar_width,
            matrix_size / segments + 0.2,
            stroke=0,
            fill=1,
        )
    pdf.setFillColor(black)
    pdf.setFont(NORMAL_FONT, 5.5)
    for value in (0.0, 0.5, 1.0):
        y = bottom + value * matrix_size
        pdf.drawString(bar_x + bar_width + 2, y - 2, f"{value:.1f}")

    pdf.showPage()
    pdf.save()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_sample_pairs()
    generate_training_curves()
    generate_confusion_matrix()
    for path in sorted(OUTPUT_DIR.glob("*.pdf")):
        print(path.relative_to(PROJECT_DIR))


if __name__ == "__main__":
    main()
