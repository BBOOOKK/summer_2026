#!/usr/bin/env python3
"""Audit P05 expanded data and render a mouse-focused YOLO contact sheet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


CLASS_NAMES = ["mouse", "keyboard", "laptop", "cup", "headphones"]
COLORS = ["#ff3b30", "#00a7e1", "#34c759", "#ff9500", "#af52de"]


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=project / "datasets/p05_expanded_v1")
    parser.add_argument("--contact-count", type=int, default=120)
    return parser.parse_args()


def dhash(image: Image.Image) -> int:
    resized = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(resized.get_flattened_data())
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | int(pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return value


def parse_label(path: Path) -> list[tuple[int, float, float, float, float]]:
    result = []
    for line in path.read_text().splitlines():
        if line.strip():
            class_id, xc, yc, width, height = line.split()
            result.append((int(class_id), float(xc), float(yc), float(width), float(height)))
    return result


def draw_thumbnail(image_path: Path, label_path: Path, width: int, height: int) -> Image.Image:
    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    original_width, original_height = image.size
    scale = min(width / original_width, height / original_height)
    resized_width = max(1, round(original_width * scale))
    resized_height = max(1, round(original_height * scale))
    image = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), "#202124")
    offset_x = (width - resized_width) // 2
    offset_y = (height - resized_height) // 2
    canvas.paste(image, (offset_x, offset_y))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=13)
    for class_id, xc, yc, box_width, box_height in parse_label(label_path):
        x1 = offset_x + (xc - box_width / 2) * resized_width
        y1 = offset_y + (yc - box_height / 2) * resized_height
        x2 = offset_x + (xc + box_width / 2) * resized_width
        y2 = offset_y + (yc + box_height / 2) * resized_height
        draw.rectangle((x1, y1, x2, y2), outline=COLORS[class_id], width=3)
        draw.text((x1 + 2, max(offset_y, y1 - 15)), CLASS_NAMES[class_id], fill=COLORS[class_id], font=font)
    return canvas


def render_mouse_contact(dataset: Path, candidates: list[Path], count: int) -> Path:
    candidates = sorted(candidates, key=lambda path: hashlib.sha256(path.name.encode()).hexdigest())[:count]
    columns, thumb_width, thumb_height, label_height = 6, 260, 190, 24
    rows = (len(candidates) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + label_height)), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=13)
    for index, image_path in enumerate(candidates):
        split = image_path.parent.name
        label_path = dataset / "labels" / split / image_path.with_suffix(".txt").name
        thumb = draw_thumbnail(image_path, label_path, thumb_width, thumb_height)
        column, row = index % columns, index // columns
        x, y = column * thumb_width, row * (thumb_height + label_height)
        sheet.paste(thumb, (x, y))
        draw.text((x + 4, y + thumb_height + 4), image_path.stem[:38], fill="black", font=font)
    output = dataset / "qa/mouse_contact_sheet.jpg"
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)
    return output


def main() -> int:
    args = parse_args()
    dataset = args.dataset.resolve()
    manifest = list(csv.DictReader((dataset / "manifest.csv").open()))
    errors: list[str] = []
    corrupt: list[str] = []
    small_images: list[str] = []
    hashes: dict[str, Path] = {}
    exact_duplicates: list[tuple[str, str]] = []
    perceptual: list[tuple[Path, str, int, float]] = []
    class_boxes: Counter[int] = Counter()
    small_boxes: Counter[int] = Counter()
    mouse_images: list[Path] = []
    dimensions: Counter[str] = Counter()

    images = sorted((dataset / "images").glob("*/*.jpg"))
    if len(images) != 5000:
        errors.append(f"expected 5000 images, found {len(images)}")
    for index, image_path in enumerate(images, 1):
        split = image_path.parent.name
        label_path = dataset / "labels" / split / image_path.with_suffix(".txt").name
        try:
            raw_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            if raw_hash in hashes:
                exact_duplicates.append((str(hashes[raw_hash]), str(image_path)))
            else:
                hashes[raw_hash] = image_path
            with Image.open(image_path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                width, height = image.size
                image_hash = dhash(image)
            if width < 200 or height < 200:
                small_images.append(str(image_path))
            dimensions[f"{width}x{height}"] += 1
            perceptual.append((image_path, split, image_hash, width / height))
        except Exception as exc:
            corrupt.append(f"{image_path}: {exc}")
            continue
        boxes = parse_label(label_path)
        has_mouse = False
        for class_id, _, _, box_width, box_height in boxes:
            class_boxes[class_id] += 1
            if box_width * box_height < 0.005:
                small_boxes[class_id] += 1
            has_mouse |= class_id == 0
        if has_mouse and image_path.name.startswith("oi_"):
            mouse_images.append(image_path)
        if index % 1000 == 0:
            print(f"[AUDIT] decoded {index}/{len(images)}", flush=True)

    # dHash distance <= 1 is only a review candidate, not an automatic failure.
    cross_split_near: list[dict] = []
    for left_index, left in enumerate(perceptual):
        for right in perceptual[left_index + 1 :]:
            if left[1] == right[1] or abs(left[3] - right[3]) > 0.005:
                continue
            distance = (left[2] ^ right[2]).bit_count()
            if distance <= 1:
                cross_split_near.append({"left": str(left[0]), "right": str(right[0]), "distance": distance})
                if len(cross_split_near) >= 200:
                    break
        if len(cross_split_near) >= 200:
            break

    duplicate_sources = [
        {"source_type": key[0], "source_id": key[1], "count": count}
        for key, count in Counter((row["source_type"], row["source_id"]) for row in manifest).items()
        if count > 1
    ]
    if corrupt:
        errors.append(f"corrupt images: {len(corrupt)}")
    if exact_duplicates:
        errors.append(f"exact duplicate images: {len(exact_duplicates)}")
    if duplicate_sources:
        errors.append(f"duplicate source IDs: {len(duplicate_sources)}")
    contact_path = render_mouse_contact(dataset, mouse_images, args.contact_count)
    report = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "image_count": len(images),
        "manifest_count": len(manifest),
        "corrupt_images": corrupt,
        "images_below_200px": small_images,
        "exact_file_duplicates": exact_duplicates,
        "duplicate_source_ids": duplicate_sources,
        "cross_split_dhash_distance_le_1_review_candidates": cross_split_near,
        "box_counts": {CLASS_NAMES[key]: value for key, value in sorted(class_boxes.items())},
        "small_box_counts_area_below_0_005": {CLASS_NAMES[key]: value for key, value in sorted(small_boxes.items())},
        "mouse_public_image_count": len(mouse_images),
        "mouse_contact_sheet": str(contact_path),
        "most_common_dimensions": dimensions.most_common(20),
        "review_boundary": "Contact sheet is an engineering sample; public annotations still require full human review before a formal ground-truth claim.",
    }
    report_path = dataset / "qa/expanded_quality_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "image_count", "box_counts", "mouse_public_image_count")}, ensure_ascii=False, indent=2))
    print(f"[AUDIT] report: {report_path}")
    print(f"[AUDIT] contact sheet: {contact_path}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
