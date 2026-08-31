#!/usr/bin/env python3
"""Build a provenance-aware 5,000-image P05 expansion from Open Images V7.

The original 500-image P05 dataset is preserved as a frozen baseline. Public
images and labels are placed in a separate versioned dataset, with Open Images
train/validation/test splits kept separate to avoid evaluation leakage.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import random
import re
import shutil
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image


CLASS_NAMES = ["mouse", "keyboard", "laptop", "cup", "headphones"]
CLASS_ID = {name: index for index, name in enumerate(CLASS_NAMES)}
MIDS = {
    "/m/020lf": "mouse",
    "/m/01m2v": "keyboard",
    "/m/01c648": "laptop",
    "/m/02p5f1q": "cup",
    "/m/01b7fy": "headphones",
}
DISTRACTOR_MIDS = {
    "/m/02522": "computer monitor",
    "/m/04dr76w": "bottle",
    "/m/04kkgm": "bowl",
    "/m/050k8": "mobile phone",
    "/m/0bh9flk": "tablet computer",
    "/m/0qjjc": "remote control",
    "/m/01y9k5": "desk",
}
ANNOTATION_URLS = {
    "train": "https://storage.googleapis.com/openimages/v6/oidv6-train-annotations-bbox.csv",
}
S3_TEMPLATE = "https://open-images-dataset.s3.amazonaws.com/{split}/{image_id}.jpg"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
DEFAULT_SEED = 20260831
PUBLIC_IMAGE_BLACKLIST = {
    "14ecfd20e8c4ac7f",  # near-duplicate of test/608d813c31750c8b
}
TARGET_COUNTS = {
    "train": {"positive": 3600, "negative": 0},
    "val": {"positive": 276, "negative": 0},
    "test": {"positive": 624, "negative": 0},
}


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    workspace = project.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=workspace / "data")
    parser.add_argument("--baseline-manifest", type=Path, default=project / "splits/split_manifest.csv")
    parser.add_argument("--openimages-work", type=Path, default=workspace / "work/openimages")
    parser.add_argument("--output", type=Path, default=project / "datasets/p05_expanded_v1")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Keep a partial output and verify/skip completed JPEGs")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--skip-train-scan", action="store_true")
    return parser.parse_args()


def stable_value(seed: int, *parts: str) -> str:
    return hashlib.sha256((str(seed) + ":" + ":".join(parts)).encode()).hexdigest()


def reservoir_add(pool: list[dict], item: dict, seen: int, limit: int, rng: random.Random) -> None:
    if len(pool) < limit:
        pool.append(item)
        return
    index = rng.randrange(seen)
    if index < limit:
        pool[index] = item


def sane_box(box: dict) -> bool:
    width = box["xmax"] - box["xmin"]
    height = box["ymax"] - box["ymin"]
    return 0.0003 <= width * height <= 0.98 and width > 0 and height > 0


def row_to_box(row: dict[str, str]) -> dict | None:
    if row["LabelName"] not in MIDS:
        return None
    if row.get("IsDepiction", "0") == "1" or row.get("IsGroupOf", "0") == "1":
        return None
    box = {
        "class": MIDS[row["LabelName"]],
        "xmin": float(row["XMin"]),
        "xmax": float(row["XMax"]),
        "ymin": float(row["YMin"]),
        "ymax": float(row["YMax"]),
        "occluded": int(row.get("IsOccluded", 0)),
        "truncated": int(row.get("IsTruncated", 0)),
    }
    return box if sane_box(box) else None


def scan_annotation_rows(
    rows: Iterable[dict[str, str]], split: str, seed: int, progress_every: int = 1_000_000
) -> tuple[list[dict], list[dict], int]:
    """Reservoir-sample relevant images from an ImageID-sorted annotation stream."""
    rng = random.Random(seed + {"train": 1, "validation": 2, "test": 3}[split])
    positive_pools: dict[str, list[dict]] = {name: [] for name in CLASS_NAMES}
    positive_seen: Counter[str] = Counter()
    negative_pool: list[dict] = []
    negative_seen = 0
    current_id: str | None = None
    current_boxes: list[dict] = []
    current_distractors: set[str] = set()

    def finish_image() -> None:
        nonlocal negative_seen
        if current_id is None:
            return
        if current_boxes:
            classes = sorted({box["class"] for box in current_boxes})
            primary = min(classes, key=lambda name: (positive_seen[name], name))
            positive_seen[primary] += 1
            item = {
                "split": split,
                "image_id": current_id,
                "primary_class": primary,
                "boxes": list(current_boxes),
                "distractors": sorted(current_distractors),
            }
            reservoir_add(positive_pools[primary], item, positive_seen[primary], 5000, rng)
        elif current_distractors:
            negative_seen += 1
            item = {
                "split": split,
                "image_id": current_id,
                "primary_class": "NEG",
                "boxes": [],
                "distractors": sorted(current_distractors),
            }
            reservoir_add(negative_pool, item, negative_seen, 4000, rng)

    row_count = 0
    for row_count, row in enumerate(rows, 1):
        image_id = row["ImageID"]
        if current_id is None:
            current_id = image_id
        elif image_id != current_id:
            finish_image()
            current_id = image_id
            current_boxes = []
            current_distractors = set()
        box = row_to_box(row)
        if box is not None:
            current_boxes.append(box)
        distractor = DISTRACTOR_MIDS.get(row["LabelName"])
        if distractor and row.get("IsDepiction", "0") != "1":
            current_distractors.add(distractor)
        if progress_every and row_count % progress_every == 0:
            kept = sum(len(pool) for pool in positive_pools.values())
            print(f"[SCAN] {split}: rows={row_count:,} positive_pool={kept:,} negative_pool={len(negative_pool):,}", flush=True)
    finish_image()
    positives = [item for name in CLASS_NAMES for item in positive_pools[name]]
    return positives, negative_pool, row_count


def scan_train(work: Path, seed: int) -> tuple[Path, Path]:
    positive_path = work / "train_target_candidates.jsonl"
    negative_path = work / "train_negative_candidates.jsonl"
    if positive_path.is_file() and negative_path.is_file():
        print(f"[SCAN] Reusing cached train candidates: {positive_path}")
        return positive_path, negative_path
    local_csv = work / "oidv6-train-annotations-bbox.csv"
    if local_csv.is_file():
        print(f"[SCAN] Reading resumable local annotation file: {local_csv}")
        with local_csv.open(encoding="utf-8", newline="") as handle:
            positives, negatives, row_count = scan_annotation_rows(csv.DictReader(handle), "train", seed)
    else:
        url = ANNOTATION_URLS["train"]
        print(f"[SCAN] Streaming Open Images train annotations: {url}")
        print("[SCAN] Tip: for unstable networks, download it with curl -C - to", local_csv)
        with requests.get(url, stream=True, timeout=(30, 300)) as response:
            response.raise_for_status()
            response.raw.decode_content = True
            text = io.TextIOWrapper(response.raw, encoding="utf-8", newline="")
            positives, negatives, row_count = scan_annotation_rows(csv.DictReader(text), "train", seed)
    write_jsonl(positive_path, positives)
    write_jsonl(negative_path, negatives)
    print(f"[SCAN] train complete: rows={row_count:,}, positives={len(positives):,}, negatives={len(negatives):,}")
    return positive_path, negative_path


def scan_local_split(work: Path, split: str, seed: int) -> tuple[Path, Path]:
    source_name = "validation" if split == "val" else "test"
    csv_path = work / f"{source_name}-annotations-bbox.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"Missing Open Images annotations: {csv_path}")
    positive_path = work / f"{source_name}_target_candidates.jsonl"
    negative_path = work / f"{source_name}_negative_candidates.jsonl"
    if positive_path.is_file() and negative_path.is_file():
        return positive_path, negative_path
    with csv_path.open(encoding="utf-8", newline="") as handle:
        positives, negatives, row_count = scan_annotation_rows(
            csv.DictReader(handle), source_name, seed, progress_every=500_000
        )
    write_jsonl(positive_path, positives)
    write_jsonl(negative_path, negatives)
    print(f"[SCAN] {source_name}: rows={row_count:,}, positives={len(positives):,}, negatives={len(negatives):,}")
    return positive_path, negative_path


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    with temp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temp.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def cache_path(work: Path, item: dict) -> Path:
    source_split = "validation" if item["split"] == "val" else item["split"]
    return work / "images" / f"{source_split}_{item['image_id']}.jpg"


def select_candidates(
    positives: list[dict], negatives: list[dict], split: str, work: Path, seed: int,
    excluded_ids: set[str],
) -> list[dict]:
    positives = [item for item in positives if item["image_id"] not in excluded_ids]
    negatives = [item for item in negatives if item["image_id"] not in excluded_ids]
    positive_target = TARGET_COUNTS[split]["positive"]
    negative_target = TARGET_COUNTS[split]["negative"]
    quota = positive_target // len(CLASS_NAMES)
    remainder = positive_target % len(CLASS_NAMES)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in positives:
        grouped[item["primary_class"]].append(item)
    selected: list[dict] = []
    selected_ids: set[str] = set()
    for index, name in enumerate(CLASS_NAMES):
        need = quota + (1 if index < remainder else 0)
        pool = sorted(
            grouped[name],
            key=lambda item: (
                not cache_path(work, item).is_file(),
                stable_value(seed, split, name, item["image_id"]),
            ),
        )
        # Rare classes (especially computer mouse) may not meet an equal quota.
        # Keep every available rare-class candidate, then fill the image quota
        # from the remaining pools without duplicating images.
        for item in pool[: min(need, len(pool))]:
            if item["image_id"] not in selected_ids:
                selected.append(item)
                selected_ids.add(item["image_id"])
    if len(selected) < positive_target:
        extras = sorted(
            (item for item in positives if item["image_id"] not in selected_ids),
            key=lambda item: (not cache_path(work, item).is_file(), stable_value(seed, split, "extra", item["image_id"])),
        )
        selected.extend(extras[: positive_target - len(selected)])
    negative_pool = sorted(
        negatives,
        key=lambda item: (not cache_path(work, item).is_file(), stable_value(seed, split, "NEG", item["image_id"])),
    )
    if len(negative_pool) < negative_target:
        raise RuntimeError(f"{split} has only {len(negative_pool)} negative candidates; need {negative_target}")
    selected.extend(negative_pool[:negative_target])
    if len(selected) != positive_target + negative_target:
        raise RuntimeError(f"selection count mismatch for {split}: {len(selected)}")
    return selected


def verify_jpeg(path: Path) -> bool:
    try:
        if path.stat().st_size < 1000:
            return False
        with Image.open(path) as image:
            image.verify()
        return True
    except Exception:
        return False


def download_one(item: dict, destination: Path, work: Path) -> Path:
    source_split = "validation" if item["split"] == "val" else item["split"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    cached = cache_path(work, item)
    if cached.is_file() and verify_jpeg(cached):
        if not destination.exists():
            try:
                os.link(cached, destination)
            except OSError:
                shutil.copy2(cached, destination)
        return destination
    if destination.is_file() and verify_jpeg(destination):
        return destination
    url = S3_TEMPLATE.format(split=source_split, image_id=item["image_id"])
    temp = destination.with_suffix(".jpg.part")
    for attempt in range(4):
        try:
            with requests.get(url, timeout=(20, 90)) as response:
                response.raise_for_status()
                temp.write_bytes(response.content)
            if not verify_jpeg(temp):
                raise ValueError("invalid JPEG")
            temp.replace(destination)
            return destination
        except Exception as exc:
            temp.unlink(missing_ok=True)
            if attempt == 3:
                raise RuntimeError(f"download failed: {url}: {exc}") from exc
    raise AssertionError("unreachable")


def download_selected(selected: dict[str, list[dict]], output: Path, work: Path, workers: int) -> None:
    jobs: list[tuple[dict, Path]] = []
    for split, items in selected.items():
        for item in items:
            source_split = "validation" if split == "val" else split
            destination = output / "sources/openimages" / source_split / f"{item['image_id']}.jpg"
            jobs.append((item, destination))
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download_one, item, path, work): (item, path) for item, path in jobs}
        for index, future in enumerate(as_completed(futures), 1):
            item, _ = futures[future]
            try:
                future.result()
            except Exception as exc:
                failures.append((item, str(exc)))
            if index % 100 == 0 or index == len(jobs):
                print(f"[DOWNLOAD] {index}/{len(jobs)} complete; failures={len(failures)}", flush=True)
    if failures:
        preview = "\n".join(error for _, error in failures[:10])
        raise RuntimeError(f"{len(failures)} downloads failed:\n{preview}")


def safe_link(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve() == source.resolve():
            return
        destination.unlink()
    elif destination.exists():
        raise FileExistsError(f"Refusing to overwrite: {destination}")
    destination.symlink_to(os.path.relpath(source.resolve(), destination.parent.resolve()))


def write_yolo_label(path: Path, boxes: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for box in boxes:
        width = box["xmax"] - box["xmin"]
        height = box["ymax"] - box["ymin"]
        x_center = (box["xmin"] + box["xmax"]) / 2
        y_center = (box["ymin"] + box["ymax"]) / 2
        lines.append(f"{CLASS_ID[box['class']]} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def add_baseline(output: Path, baseline: Path, manifest_path: Path, rows: list[dict]) -> None:
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    for item in manifest:
        split = item["split"]
        source_image = (manifest_path.parent.parent / item["image"]).resolve()
        source_label = (manifest_path.parent.parent / item["label"]).resolve()
        name = "base_" + source_image.name
        image_link = output / "images" / split / name
        label_link = output / "labels" / split / Path(name).with_suffix(".txt")
        safe_link(source_image, image_link)
        safe_link(source_label, label_link)
        labels = [line for line in source_label.read_text().splitlines() if line.strip()]
        rows.append({
            "split": split,
            "file": name,
            "source_type": "p05_baseline_mixed",
            "source_split": split,
            "source_id": source_image.stem,
            "source_url": "",
            "label_count": len(labels),
            "classes": ";".join(sorted({CLASS_NAMES[int(line.split()[0])] for line in labels})),
        })


def add_public(output: Path, selected: dict[str, list[dict]], rows: list[dict]) -> None:
    for split, items in selected.items():
        source_split = "validation" if split == "val" else split
        for item in items:
            name = f"oi_{source_split}_{item['image_id']}.jpg"
            source_image = output / "sources/openimages" / source_split / f"{item['image_id']}.jpg"
            image_link = output / "images" / split / name
            label = output / "labels" / split / Path(name).with_suffix(".txt")
            safe_link(source_image, image_link)
            write_yolo_label(label, item["boxes"])
            rows.append({
                "split": split,
                "file": name,
                "source_type": "open_images_v7",
                "source_split": source_split,
                "source_id": item["image_id"],
                "source_url": S3_TEMPLATE.format(split=source_split, image_id=item["image_id"]),
                "label_count": len(item["boxes"]),
                "classes": ";".join(sorted({box["class"] for box in item["boxes"]})),
            })


def baseline_openimages_ids(baseline: Path) -> set[str]:
    provenance_path = baseline / "provenance.json"
    if not provenance_path.is_file():
        return set()
    result = set()
    for row in json.loads(provenance_path.read_text()):
        if row.get("source", {}).get("type") != "open_images_v7":
            continue
        match = re.search(r"[0-9a-f]{16}", json.dumps(row["source"]))
        if match:
            result.add(match.group(0))
    return result


def remove_stale_public_links(output: Path, selected: dict[str, list[dict]]) -> None:
    expected: dict[str, set[str]] = {}
    for split, items in selected.items():
        expected[split] = {
            f"oi_{'validation' if split == 'val' else split}_{item['image_id']}"
            for item in items
        }
    for split in ("train", "val", "test"):
        for folder, suffix in ((output / "images" / split, ".jpg"), (output / "labels" / split, ".txt")):
            if not folder.is_dir():
                continue
            for path in folder.glob(f"oi_*{suffix}"):
                if path.stem not in expected[split]:
                    path.unlink()


def write_metadata(output: Path, rows: list[dict], selected: dict[str, list[dict]]) -> None:
    manifest = output / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["split"], row["file"])))
    (output / "classes.txt").write_text("\n".join(CLASS_NAMES) + "\n", encoding="utf-8")
    (output / "dataset.yaml").write_text(
        "train: images/train\nval: images/val\ntest: images/test\n\nnc: 5\nnames:\n"
        + "\n".join(f"  {index}: {name}" for index, name in enumerate(CLASS_NAMES))
        + "\n",
        encoding="utf-8",
    )
    split_counts = Counter(row["split"] for row in rows)
    source_counts = Counter(row["source_type"] for row in rows)
    class_counts: Counter[str] = Counter()
    empty = 0
    for row in rows:
        if not row["classes"]:
            empty += 1
        for name in filter(None, row["classes"].split(";")):
            class_counts[name] += 1
    report = {
        "status": "BUILT_NOT_HUMAN_REVIEWED",
        "total_images": len(rows),
        "split_counts": dict(split_counts),
        "source_counts": dict(source_counts),
        "images_containing_class": dict(class_counts),
        "empty_labels": empty,
        "target_total": 5000,
        "public_selection": {split: len(items) for split, items in selected.items()},
        "limitations": [
            "Open Images boxes are converted automatically and have not yet received full per-image human review.",
            "The frozen baseline is mixed-source and includes generated images; provenance is preserved.",
            "Real handheld white-mouse captures from the deployment camera are still required for domain-specific fine-tuning.",
        ],
    }
    (output / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# P05 expanded v1\n\n"
        "This version contains exactly 5,000 images: the frozen 500-image P05 baseline plus "
        "4,500 Open Images V7 images. Open Images train/validation/test boundaries are retained.\n\n"
        "The public labels are automatic conversions of Open Images bounding boxes and require visual QA "
        "before a final training claim. Synthetic images from the original baseline remain identifiable in "
        "its provenance; they are not described as real photos.\n\n"
        "Open Images documentation: https://storage.googleapis.com/openimages/web/download_v7.html\n"
        "Per-image source IDs and URLs are recorded in manifest.csv.\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    baseline = args.baseline.expanduser().resolve()
    work = args.openimages_work.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not baseline.is_dir() or not args.baseline_manifest.is_file():
        raise FileNotFoundError("baseline dataset or split manifest is missing")
    work.mkdir(parents=True, exist_ok=True)
    paths = {}
    if not args.skip_train_scan:
        paths["train"] = scan_train(work, args.seed)
    else:
        paths["train"] = (work / "train_target_candidates.jsonl", work / "train_negative_candidates.jsonl")
    paths["val"] = scan_local_split(work, "val", args.seed)
    paths["test"] = scan_local_split(work, "test", args.seed)
    if args.scan_only:
        return 0
    selected = {}
    baseline_ids = baseline_openimages_ids(baseline)
    excluded_ids = baseline_ids | PUBLIC_IMAGE_BLACKLIST
    print(
        f"[SELECT] excluding {len(baseline_ids)} baseline Open Images IDs "
        f"and {len(PUBLIC_IMAGE_BLACKLIST)} QA-blacklisted IDs"
    )
    for split, (positive_path, negative_path) in paths.items():
        positives = read_jsonl(positive_path)
        negatives = read_jsonl(negative_path)
        selected[split] = select_candidates(positives, negatives, split, work, args.seed, excluded_ids)
        print(f"[SELECT] {split}: {len(selected[split])}")
    if output.exists():
        if args.resume:
            pass
        elif not args.force:
            raise FileExistsError(f"Output exists; use --force: {output}")
        elif output.name != "p05_expanded_v1":
            raise ValueError(f"Refusing to replace unexpected output: {output}")
        else:
            shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "selected_openimages.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    download_selected(selected, output, work, args.workers)
    remove_stale_public_links(output, selected)
    rows: list[dict] = []
    add_baseline(output, baseline, args.baseline_manifest.resolve(), rows)
    add_public(output, selected, rows)
    write_metadata(output, rows, selected)
    if len(rows) != 5000:
        raise RuntimeError(f"expected 5000 images, built {len(rows)}")
    print(f"[DONE] Built {len(rows)} images at {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[STOP] interrupted; cached scan/download progress is preserved", file=sys.stderr)
        raise SystemExit(130)
