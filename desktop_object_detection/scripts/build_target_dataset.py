#!/usr/bin/env python3
"""Build the 1,000 self-collected-derived + 4,000 public-image dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


CLASS_NAMES = ["mouse", "keyboard", "laptop", "cup", "headphones"]
PUBLIC_SPLIT_QUOTAS = {"train": 3200, "val": 250, "test": 550}
SELF_SOURCE_SPLITS = {"train": 8, "val": 1, "test": 1}
OUTPUT_SIZE = (1280, 960)


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    workspace = project.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-data", type=Path, default=workspace / "data")
    parser.add_argument("--public-dataset", type=Path, default=project / "datasets/p05_expanded_v1")
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "datasets/experiment1_1000self_4000public_v1",
    )
    parser.add_argument("--seed", type=int, default=20260831)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_link(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.symlink_to(os.path.relpath(source.resolve(), destination.parent.resolve()))


def read_yolo(path: Path) -> list[tuple[int, float, float, float, float]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            class_id, xc, yc, width, height = line.split()
            rows.append((int(class_id), float(xc), float(yc), float(width), float(height)))
    return rows


def write_yolo(path: Path, boxes: list[tuple[int, float, float, float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{class_id} {xc:.6f} {yc:.6f} {width:.6f} {height:.6f}" for class_id, xc, yc, width, height in boxes]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def transform_boxes(
    boxes: list[tuple[int, float, float, float, float]],
    matrix: np.ndarray,
    flip: bool,
) -> list[tuple[int, float, float, float, float]]:
    width, height = OUTPUT_SIZE
    transformed = []
    for class_id, xc, yc, box_width, box_height in boxes:
        x1 = (xc - box_width / 2) * width
        y1 = (yc - box_height / 2) * height
        x2 = (xc + box_width / 2) * width
        y2 = (yc + box_height / 2) * height
        corners = np.array([[x1, y1, 1], [x2, y1, 1], [x2, y2, 1], [x1, y2, 1]], dtype=np.float32)
        warped = corners @ matrix.T
        if flip:
            warped[:, 0] = width - 1 - warped[:, 0]
        raw_x1, raw_y1 = warped[:, 0].min(), warped[:, 1].min()
        raw_x2, raw_y2 = warped[:, 0].max(), warped[:, 1].max()
        raw_area = max(1.0, (raw_x2 - raw_x1) * (raw_y2 - raw_y1))
        clipped_x1, clipped_y1 = max(0.0, raw_x1), max(0.0, raw_y1)
        clipped_x2, clipped_y2 = min(width - 1.0, raw_x2), min(height - 1.0, raw_y2)
        clipped_width = clipped_x2 - clipped_x1
        clipped_height = clipped_y2 - clipped_y1
        if clipped_width < 4 or clipped_height < 4 or clipped_width * clipped_height / raw_area < 0.40:
            continue
        transformed.append((
            class_id,
            ((clipped_x1 + clipped_x2) / 2) / width,
            ((clipped_y1 + clipped_y2) / 2) / height,
            clipped_width / width,
            clipped_height / height,
        ))
    return transformed


def augment(
    image: np.ndarray,
    boxes: list[tuple[int, float, float, float, float]],
    seed: int,
    identity: bool,
) -> tuple[np.ndarray, list[tuple[int, float, float, float, float]], dict]:
    width, height = OUTPUT_SIZE
    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    rng = np.random.default_rng(seed)
    if identity:
        angle, scale, tx, ty, flip = 0.0, 1.0, 0.0, 0.0, False
    else:
        angle = float(rng.uniform(-9.0, 9.0))
        scale = float(rng.uniform(0.88, 1.12))
        tx = float(rng.uniform(-0.07, 0.07) * width)
        ty = float(rng.uniform(-0.07, 0.07) * height)
        flip = bool(rng.random() < 0.5)
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, scale)
    matrix[0, 2] += tx
    matrix[1, 2] += ty
    warped = cv2.warpAffine(
        resized,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    if flip:
        warped = cv2.flip(warped, 1)
    transformed = transform_boxes(boxes, matrix, flip)
    if not transformed:
        raise RuntimeError("augmentation removed every target box")

    brightness = float(rng.uniform(0.82, 1.18)) if not identity else 1.0
    contrast = float(rng.uniform(0.86, 1.14)) if not identity else 1.0
    warped = cv2.convertScaleAbs(warped, alpha=contrast, beta=(brightness - 1.0) * 80.0)
    blur_kernel = 3 if (not identity and rng.random() < 0.18) else 0
    if blur_kernel:
        warped = cv2.GaussianBlur(warped, (blur_kernel, blur_kernel), 0)
    noise_sigma = float(rng.uniform(0, 5.0)) if not identity else 0.0
    if noise_sigma > 0.5:
        noise = rng.normal(0, noise_sigma, warped.shape).astype(np.int16)
        warped = np.clip(warped.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return warped, transformed, {
        "angle_deg": round(angle, 4),
        "scale": round(scale, 6),
        "translate_x_px": round(tx, 3),
        "translate_y_px": round(ty, 3),
        "horizontal_flip": flip,
        "brightness": round(brightness, 6),
        "contrast": round(contrast, 6),
        "blur_kernel": blur_kernel,
        "noise_sigma": round(noise_sigma, 6),
    }


def find_local_sources(base_data: Path) -> list[dict]:
    provenance = json.loads((base_data / "provenance.json").read_text(encoding="utf-8"))
    local_rows = sorted(
        (row for row in provenance if row.get("source", {}).get("type") == "local_capture"),
        key=lambda row: row["file"],
    )
    if len(local_rows) != 10:
        raise RuntimeError(f"expected 10 local source photos, found {len(local_rows)}")
    result = []
    for row in local_rows:
        image_matches = list((base_data / "raw/P05").rglob(row["file"]))
        label_name = Path(row["file"]).with_suffix(".txt").name
        label_matches = list((base_data / "annotated/labels/P05").rglob(label_name))
        if len(image_matches) != 1 or len(label_matches) != 1:
            raise RuntimeError(f"cannot resolve unique image/label for {row['file']}")
        result.append({"row": row, "image": image_matches[0], "label": label_matches[0]})
    return result


def assign_self_splits(sources: list[dict]) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    cursor = 0
    for split, count in SELF_SOURCE_SPLITS.items():
        result[split] = sources[cursor: cursor + count]
        cursor += count
    return result


def select_public_rows(manifest_path: Path, seed: int) -> dict[str, list[dict[str, str]]]:
    rows = list(csv.DictReader(manifest_path.open(encoding="utf-8", newline="")))
    public = [row for row in rows if row["source_type"] == "open_images_v7"]
    result = {}
    for split, quota in PUBLIC_SPLIT_QUOTAS.items():
        candidates = [row for row in public if row["split"] == split]
        ordered = sorted(
            candidates,
            key=lambda row: hashlib.sha256(f"{seed}:{row['source_id']}".encode()).hexdigest(),
        )
        if len(ordered) < quota:
            raise RuntimeError(f"public {split} has {len(ordered)}, needs {quota}")
        result[split] = ordered[:quota]
    return result


def build_self_images(output: Path, sources: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    manifest_rows: list[dict] = []
    provenance_rows: list[dict] = []
    for split, split_sources in assign_self_splits(sources).items():
        for source in split_sources:
            image = cv2.imread(str(source["image"]), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"failed to decode {source['image']}")
            boxes = read_yolo(source["label"])
            original_name = source["row"]["source"]["original_name"]
            source_digest = sha256(source["image"])
            for variant in range(100):
                variant_seed = int.from_bytes(
                    hashlib.sha256(f"{seed}:{original_name}:{variant}".encode()).digest()[:8],
                    "big",
                )
                augmented, new_boxes, transform = augment(image, boxes, variant_seed, identity=variant == 0)
                stem = f"self_{Path(original_name).stem}_v{variant:03d}"
                image_path = output / "images" / split / f"{stem}.jpg"
                label_path = output / "labels" / split / f"{stem}.txt"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                if not cv2.imwrite(str(image_path), augmented, [cv2.IMWRITE_JPEG_QUALITY, 90]):
                    raise RuntimeError(f"failed to write {image_path}")
                write_yolo(label_path, new_boxes)
                classes = sorted({CLASS_NAMES[item[0]] for item in new_boxes})
                manifest_rows.append({
                    "split": split,
                    "file": image_path.name,
                    "source_type": "self_collected_derived",
                    "source_split": split,
                    "source_id": original_name,
                    "source_url": "",
                    "label_count": str(len(new_boxes)),
                    "classes": "|".join(classes),
                })
                provenance_rows.append({
                    "file": image_path.name,
                    "split": split,
                    "source_type": "self_collected_derived",
                    "original_capture_name": original_name,
                    "original_dataset_file": source["row"]["file"],
                    "original_sha256": source_digest,
                    "variant": variant,
                    "transform": transform,
                    "label_count": len(new_boxes),
                    "classes": classes,
                })
    return manifest_rows, provenance_rows


def link_public_images(
    output: Path,
    public_dataset: Path,
    selected: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for split, split_rows in selected.items():
        for row in split_rows:
            image_source = public_dataset / "images" / split / row["file"]
            label_source = public_dataset / "labels" / split / Path(row["file"]).with_suffix(".txt")
            if not image_source.exists() or not label_source.exists():
                raise FileNotFoundError(f"missing public pair: {image_source}, {label_source}")
            safe_link(image_source.resolve(), output / "images" / split / row["file"])
            safe_link(label_source.resolve(), output / "labels" / split / label_source.name)
            rows.append(row)
    return rows


def write_metadata(output: Path, manifest_rows: list[dict], provenance_rows: list[dict]) -> None:
    fieldnames = ["split", "file", "source_type", "source_split", "source_id", "source_url", "label_count", "classes"]
    with (output / "manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(manifest_rows, key=lambda row: (row["split"], row["file"])))
    (output / "self_collected_provenance.json").write_text(
        json.dumps(provenance_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "dataset.yaml").write_text(
        "train: images/train\nval: images/val\ntest: images/test\n\nnc: 5\nnames:\n"
        + "".join(f"  {index}: {name}\n" for index, name in enumerate(CLASS_NAMES)),
        encoding="utf-8",
    )
    (output / "classes.txt").write_text("\n".join(CLASS_NAMES) + "\n", encoding="utf-8")


def verify(output: Path, manifest_rows: list[dict]) -> dict:
    counts = Counter(row["source_type"] for row in manifest_rows)
    split_counts = Counter(row["split"] for row in manifest_rows)
    images = sorted((output / "images").glob("*/*.jpg"))
    labels = sorted((output / "labels").glob("*/*.txt"))
    broken = [str(path) for path in images + labels if path.is_symlink() and not path.exists()]
    report = {
        "status": "PASS",
        "image_count": len(images),
        "label_count": len(labels),
        "source_counts": dict(counts),
        "split_counts": dict(split_counts),
        "self_original_capture_count": 10,
        "self_derived_count": counts["self_collected_derived"],
        "public_count": counts["open_images_v7"],
        "broken_links": broken,
        "disclosure": "1,000 self-collected-source images comprise 10 original captures and 990 deterministic derived augmentations, as authorized by the dataset owner; they are not 1,000 independent shutter events.",
    }
    if len(images) != 5000 or len(labels) != 5000:
        report["status"] = "FAIL"
    if counts != Counter({"self_collected_derived": 1000, "open_images_v7": 4000}):
        report["status"] = "FAIL"
    if broken:
        report["status"] = "FAIL"
    return report


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing dataset: {output}")
    output.mkdir(parents=True)
    sources = find_local_sources(args.base_data.resolve())
    self_rows, self_provenance = build_self_images(output, sources, args.seed)
    public_selected = select_public_rows(args.public_dataset.resolve() / "manifest.csv", args.seed)
    public_rows = link_public_images(output, args.public_dataset.resolve(), public_selected)
    manifest_rows = self_rows + public_rows
    write_metadata(output, manifest_rows, self_provenance)
    report = verify(output, manifest_rows)
    (output / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
