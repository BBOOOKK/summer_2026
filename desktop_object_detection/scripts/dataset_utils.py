#!/usr/bin/env python3
"""Shared dataset configuration and validation helpers."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


@dataclass
class SplitStats:
    split: str
    image_count: int = 0
    label_count: int = 0
    empty_labels: int = 0
    object_count: int = 0
    class_counts: dict[int, int] = field(default_factory=dict)
    missing_labels: list[str] = field(default_factory=list)
    orphan_labels: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"YAML file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def normalize_names(raw: Any) -> dict[int, str]:
    if isinstance(raw, list):
        return {index: str(name) for index, name in enumerate(raw)}
    if isinstance(raw, dict):
        try:
            return {int(index): str(name) for index, name in raw.items()}
        except (TypeError, ValueError) as exc:
            raise ValueError("Dataset names keys must be integer class IDs") from exc
    raise ValueError("Dataset YAML must define names as a list or mapping")


def resolve_dataset_path(config_path: Path, value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = config_path.parent / candidate
    return candidate.resolve()


def split_image_paths(config_path: Path, config: dict[str, Any], split: str) -> list[Path]:
    value = config.get(split)
    if value in (None, ""):
        return []
    values = value if isinstance(value, list) else [value]
    paths: list[Path] = []
    for item in values:
        source = resolve_dataset_path(config_path, item)
        if source.is_dir():
            paths.extend(
                path.absolute()
                for path in source.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            )
        elif source.is_file() and source.suffix.lower() == ".txt":
            for line in source.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                image = Path(line).expanduser()
                if not image.is_absolute():
                    image = source.parent / image
                paths.append(image.absolute())
        elif source.is_file() and source.suffix.lower() in IMAGE_SUFFIXES:
            paths.append(source.absolute())
        else:
            raise FileNotFoundError(f"Invalid {split} dataset path: {source}")
    return sorted(dict.fromkeys(paths))


def image_to_label_path(image_path: Path) -> Path:
    parts = list(image_path.parts)
    indices = [index for index, part in enumerate(parts) if part == "images"]
    if not indices:
        raise ValueError(f"Image path does not contain an 'images' directory: {image_path}")
    parts[indices[-1]] = "labels"
    return Path(*parts).with_suffix(".txt")


def parse_label(path: Path, names: dict[int, str]) -> tuple[Counter[int], list[str]]:
    counts: Counter[int] = Counter()
    errors: list[str] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 5:
            errors.append(f"{path}:{line_number}: expected 5 columns, got {len(fields)}")
            continue
        try:
            class_id = int(fields[0])
            coords = [float(value) for value in fields[1:]]
        except ValueError:
            errors.append(f"{path}:{line_number}: non-numeric label value")
            continue
        if class_id not in names:
            errors.append(f"{path}:{line_number}: class_id {class_id} not declared in names")
        if any(not 0.0 <= value <= 1.0 for value in coords):
            errors.append(f"{path}:{line_number}: coordinates outside [0, 1]")
        if coords[2] <= 0.0 or coords[3] <= 0.0:
            errors.append(f"{path}:{line_number}: width and height must be > 0")
        counts[class_id] += 1
    return counts, errors


def inspect_split(
    split: str,
    images: Iterable[Path],
    names: dict[int, str],
) -> SplitStats:
    image_list = list(images)
    stats = SplitStats(split=split, image_count=len(image_list))
    expected_labels: set[Path] = set()
    class_counts: Counter[int] = Counter()
    label_dirs: set[Path] = set()
    for image in image_list:
        try:
            label = image_to_label_path(image)
        except ValueError as exc:
            stats.errors.append(str(exc))
            continue
        expected_labels.add(label)
        label_dirs.add(label.parent)
        if not label.is_file():
            stats.missing_labels.append(str(label))
            continue
        stats.label_count += 1
        if label.stat().st_size == 0 or not label.read_text(encoding="utf-8").strip():
            stats.empty_labels += 1
        counts, errors = parse_label(label, names)
        class_counts.update(counts)
        stats.errors.extend(errors)
    all_labels: set[Path] = set()
    for label_dir in label_dirs:
        if label_dir.is_dir():
            all_labels.update(path.absolute() for path in label_dir.glob("*.txt"))
    stats.orphan_labels = sorted(str(path) for path in all_labels - expected_labels)
    stats.class_counts = dict(sorted(class_counts.items()))
    stats.object_count = sum(class_counts.values())
    return stats


def report_dict(config_path: Path) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_yaml(config_path)
    names = normalize_names(config.get("names"))
    if len(names) < 2:
        raise ValueError(f"At least 2 classes are required, found {len(names)}")
    declared_nc = config.get("nc")
    config_errors: list[str] = []
    if declared_nc is not None and int(declared_nc) != len(names):
        config_errors.append(f"nc={declared_nc} does not match len(names)={len(names)}")

    splits: dict[str, SplitStats] = {}
    seen_images: dict[Path, str] = {}
    overlap: list[str] = []
    for split in ("train", "val", "test"):
        images = split_image_paths(config_path, config, split)
        for image in images:
            if image in seen_images:
                overlap.append(f"{image}: {seen_images[image]} and {split}")
            else:
                seen_images[image] = split
        splits[split] = inspect_split(split, images, names)

    totals = {
        "images": sum(item.image_count for item in splits.values()),
        "labels": sum(item.label_count for item in splits.values()),
        "empty_labels": sum(item.empty_labels for item in splits.values()),
        "objects": sum(item.object_count for item in splits.values()),
    }
    total_class_counts: Counter[int] = Counter()
    for item in splits.values():
        total_class_counts.update(item.class_counts)
    errors = list(config_errors)
    if overlap:
        errors.extend(f"split overlap: {entry}" for entry in overlap)
    for item in splits.values():
        errors.extend(item.errors)
        errors.extend(f"missing label: {entry}" for entry in item.missing_labels)
        errors.extend(f"orphan label: {entry}" for entry in item.orphan_labels)
    return {
        "status": "PASS" if not errors else "FAIL",
        "config": str(config_path),
        "names": names,
        "splits": {name: asdict(item) for name, item in splits.items()},
        "totals": totals,
        "class_counts": dict(sorted(total_class_counts.items())),
        "errors": errors,
    }


def save_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
