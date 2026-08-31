#!/usr/bin/env python3
"""Create a deterministic, non-copying YOLO train/val/test view of P05."""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
from collections import defaultdict
from pathlib import Path

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
SPLIT_RATIOS = (("train", 0.70), ("val", 0.20), ("test", 0.10))
CLASS_CODES = {
    "MOU": "mouse",
    "KEY": "keyboard",
    "LAP": "laptop",
    "CUP": "cup",
    "HDP": "headphones",
}


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    workspace = project.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, default=workspace / "data/raw/P05")
    parser.add_argument("--labels", type=Path, default=workspace / "data/annotated/labels/P05")
    parser.add_argument("--output", type=Path, default=project / "dataset_view")
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--force", action="store_true", help="Rebuild existing symlink view")
    return parser.parse_args()


def scene_key(path: Path) -> str:
    parts = path.stem.split("_")
    if len(parts) != 4:
        raise ValueError(f"Unexpected P05 filename: {path.name}")
    return f"{parts[1]}_{parts[2]}"


def stable_order(paths: list[Path], seed: int) -> list[Path]:
    return sorted(
        paths,
        key=lambda path: hashlib.sha256(f"{seed}:{path.name}".encode()).hexdigest(),
    )


def allocate(paths: list[Path], seed: int) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        groups[scene_key(path)].append(path)
    result: dict[str, list[Path]] = {name: [] for name, _ in SPLIT_RATIOS}
    for key in sorted(groups):
        ordered = stable_order(groups[key], seed)
        count = len(ordered)
        train_end = int(count * 0.70)
        val_end = train_end + int(count * 0.20)
        # Ensure every non-empty split receives an example when a group is large enough.
        if count >= 10:
            train_end = max(train_end, 1)
            val_end = max(val_end, train_end + 1)
            val_end = min(val_end, count - 1)
        result["train"].extend(ordered[:train_end])
        result["val"].extend(ordered[train_end:val_end])
        result["test"].extend(ordered[val_end:])
    return result


def safe_link(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve() == source.resolve():
            return
        destination.unlink()
    elif destination.exists():
        raise FileExistsError(f"Refusing to overwrite non-symlink: {destination}")
    destination.symlink_to(os.path.relpath(source.resolve(), destination.parent.resolve()))


def main() -> int:
    args = parse_args()
    images_root = args.images.resolve()
    labels_root = args.labels.resolve()
    output = args.output.resolve()
    if not images_root.is_dir() or not labels_root.is_dir():
        raise FileNotFoundError("P05 image or label source directory is missing")
    if args.force and output.exists():
        if output.name != "dataset_view":
            raise ValueError(f"Refusing to remove unexpected output directory: {output}")
        shutil.rmtree(output)

    images = sorted(
        path for path in images_root.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not images:
        raise RuntimeError(f"No images found under {images_root}")
    assigned = allocate(images, args.seed)
    manifest_rows: list[dict[str, str]] = []
    for split, split_images in assigned.items():
        for image in sorted(split_images):
            relative = image.relative_to(images_root)
            label = labels_root / relative.with_suffix(".txt")
            if not label.is_file():
                raise FileNotFoundError(f"Missing label for {image}: {label}")
            image_link = output / "images" / split / relative
            label_link = output / "labels" / split / relative.with_suffix(".txt")
            safe_link(image, image_link)
            safe_link(label, label_link)
            manifest_rows.append({
                "split": split,
                "image": str(image_link.relative_to(output.parent)),
                "label": str(label_link.relative_to(output.parent)),
                "scene_key": scene_key(image),
            })

    manifest = output.parent / "splits/split_manifest.csv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["split", "image", "label", "scene_key"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    test_samples = output.parent / "configs/test_samples.csv"
    candidates: dict[str, list[Path]] = defaultdict(list)
    for image in sorted(assigned["test"]):
        code = image.stem.split("_")[2]
        if code in CLASS_CODES:
            candidates[code].append(image)
    sample_rows: list[dict[str, str]] = []
    for code, class_name in CLASS_CODES.items():
        selected = candidates[code][:4]
        if len(selected) < 4:
            raise RuntimeError(f"Test split has fewer than 4 single-target samples for {class_name}")
        for image in selected:
            relative = image.relative_to(images_root)
            linked = output / "images/test" / relative
            sample_rows.append({
                "sample_id": f"sample_{len(sample_rows) + 1:02d}",
                "image_path": os.path.relpath(linked, test_samples.parent),
                "ground_truth_class": class_name,
            })
    with test_samples.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sample_id", "image_path", "ground_truth_class"],
        )
        writer.writeheader()
        writer.writerows(sample_rows)
    print(f"Prepared {len(images)} images without copying source data")
    for split, split_images in assigned.items():
        print(f"  {split}: {len(split_images)}")
    print(f"Manifest: {manifest}")
    print(f"20-object template: {test_samples}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
