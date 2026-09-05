#!/usr/bin/env python3
"""Evaluate the Open Images portion of the fixed test split with ``model.val``.

This is a source-stratified analysis of the existing holdout, not a new or
independent test set.  The script verifies cohort membership from the frozen
manifest before inference and writes portable provenance and metric records.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from collections import Counter
from pathlib import Path

import yaml


CLASS_NAMES = ["mouse", "keyboard", "laptop", "cup", "headphones"]
EXPECTED_TOTAL_TEST_IMAGES = 650
EXPECTED_PUBLIC_TEST_IMAGES = 550
EXPECTED_SELF_TEST_IMAGES = 100
EXPECTED_PUBLIC_TEST_BOXES = 807


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=root / "datasets/experiment1_1000self_4000public_v1",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=root / "models/experiment1_1000self_4000public_v1/best.pt",
    )
    parser.add_argument(
        "--baseline-provenance",
        type=Path,
        default=root.parent / "data/provenance.json",
        help="Historical 500-image provenance used to audit duplicated Open Images IDs.",
    )
    parser.add_argument(
        "--expanded-manifest",
        type=Path,
        default=root / "datasets/p05_expanded_v1/manifest.csv",
        help="Historical initializer-dataset manifest used to verify source-split placement.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "outputs/evaluation/experiment1_1000self_4000public_v1_public_holdout",
    )
    parser.add_argument("--device", default="mps")
    parser.add_argument("--batch", type=int, default=4)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_to_project(path: Path, project: Path) -> str:
    # Use lexical absolute paths so provenance continues to name the frozen
    # dataset entry even when that entry is a symlink to a source archive.
    absolute_path = path.absolute()
    try:
        return absolute_path.relative_to(project.absolute()).as_posix()
    except ValueError:
        # The self-contained submission keeps the dataset, model, and historical
        # lineage records beside 03_program rather than below it.  Preserve a
        # usable run-local absolute path when an input lies outside project.
        return absolute_path.as_posix()


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_label_counts(path: Path) -> tuple[Counter[int], set[int]]:
    counts: Counter[int] = Counter()
    present: set[int] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        fields = raw.split()
        if len(fields) != 5:
            raise ValueError(f"invalid YOLO row in {path}: {raw!r}")
        class_id = int(fields[0])
        if class_id not in range(len(CLASS_NAMES)):
            raise ValueError(f"class id {class_id} outside 0..{len(CLASS_NAMES) - 1}: {path}")
        counts[class_id] += 1
        present.add(class_id)
    return counts, present


def validate_and_freeze_cohort(
    dataset: Path,
    project: Path,
    output: Path,
    baseline_provenance: Path,
    expanded_manifest: Path,
) -> tuple[list[dict[str, str]], dict, Path]:
    manifest_path = dataset / "manifest.csv"
    rows = read_manifest(manifest_path)
    test_rows = [row for row in rows if row["split"] == "test"]
    public_rows = sorted(
        (row for row in test_rows if row["source_type"] == "open_images_v7"),
        key=lambda row: row["file"],
    )
    self_rows = [row for row in test_rows if row["source_type"] == "self_collected_derived"]
    image_dir = dataset / "images/test"
    label_dir = dataset / "labels/test"
    test_files = {path.name for path in image_dir.iterdir() if path.is_file()}
    manifest_test_files = {row["file"] for row in test_rows}

    checks = {
        "manifest_test_images": len(test_rows),
        "filesystem_test_images": len(test_files),
        "public_test_images": len(public_rows),
        "self_derived_test_images": len(self_rows),
        "manifest_exactly_matches_test_directory": manifest_test_files == test_files,
        "public_source_split_counts": dict(Counter(row["source_split"] for row in public_rows)),
        "public_source_ids_unique": len({row["source_id"] for row in public_rows}) == len(public_rows),
    }
    expected = {
        "manifest_test_images": EXPECTED_TOTAL_TEST_IMAGES,
        "filesystem_test_images": EXPECTED_TOTAL_TEST_IMAGES,
        "public_test_images": EXPECTED_PUBLIC_TEST_IMAGES,
        "self_derived_test_images": EXPECTED_SELF_TEST_IMAGES,
    }
    for key, value in expected.items():
        if checks[key] != value:
            raise RuntimeError(f"cohort check failed: {key}={checks[key]!r}, expected {value!r}")
    if not checks["manifest_exactly_matches_test_directory"]:
        raise RuntimeError("test manifest filenames do not exactly match the test image directory")
    if checks["public_source_split_counts"] != {"test": EXPECTED_PUBLIC_TEST_IMAGES}:
        raise RuntimeError(f"public source split mismatch: {checks['public_source_split_counts']}")
    if not checks["public_source_ids_unique"]:
        raise RuntimeError("public test source IDs are not unique")

    class_instances: Counter[int] = Counter()
    class_images: Counter[int] = Counter()
    frozen_rows: list[dict[str, str]] = []
    for row in public_rows:
        image_path = image_dir / row["file"]
        label_path = label_dir / Path(row["file"]).with_suffix(".txt").name
        if not image_path.is_file() or not label_path.is_file():
            raise FileNotFoundError(f"missing public test pair: {image_path}, {label_path}")
        instance_counts, present = read_label_counts(label_path)
        actual_count = sum(instance_counts.values())
        if actual_count != int(row["label_count"]):
            raise RuntimeError(
                f"label count mismatch for {row['file']}: manifest={row['label_count']}, actual={actual_count}"
            )
        class_instances.update(instance_counts)
        class_images.update(present)
        frozen_rows.append(
            {
                "file": row["file"],
                "image_path": relative_to_project(image_path, project),
                "label_path": relative_to_project(label_path, project),
                "source_type": row["source_type"],
                "source_split": row["source_split"],
                "source_id": row["source_id"],
                "source_url": row["source_url"],
                "label_count": str(actual_count),
                "classes": row["classes"],
                "image_sha256": sha256(image_path),
                "label_sha256": sha256(label_path),
            }
        )

    box_count = sum(class_instances.values())
    if box_count != EXPECTED_PUBLIC_TEST_BOXES:
        raise RuntimeError(f"public test box count={box_count}, expected {EXPECTED_PUBLIC_TEST_BOXES}")

    baseline_rows = json.loads(baseline_provenance.read_text(encoding="utf-8"))
    baseline_openimages_ids = {
        row["source"]["image_id"]
        for row in baseline_rows
        if row.get("source", {}).get("type") == "open_images_v7"
    }
    all_current_public_ids = {
        row["source_id"] for row in rows if row["source_type"] == "open_images_v7"
    }
    holdout_ids = {row["source_id"] for row in public_rows}

    expanded_rows = read_manifest(expanded_manifest)
    expanded_by_id: dict[str, list[dict[str, str]]] = {}
    for row in expanded_rows:
        if row["source_type"] == "open_images_v7":
            expanded_by_id.setdefault(row["source_id"], []).append(row)
    missing_from_expanded = sorted(holdout_ids - expanded_by_id.keys())
    nonunique_in_expanded = sorted(source_id for source_id in holdout_ids if len(expanded_by_id[source_id]) != 1)
    non_test_in_expanded = sorted(
        source_id
        for source_id in holdout_ids
        if any(row["split"] != "test" for row in expanded_by_id.get(source_id, []))
    )
    overlap_all = sorted(all_current_public_ids & baseline_openimages_ids)
    overlap_holdout = sorted(holdout_ids & baseline_openimages_ids)
    if overlap_all or overlap_holdout:
        raise RuntimeError("historical baseline Open Images IDs overlap the current public cohort")
    if missing_from_expanded or nonunique_in_expanded or non_test_in_expanded:
        raise RuntimeError("initializer-manifest placement check failed for the public holdout")

    portable_manifest_path = output / "public_holdout_manifest.csv"
    with portable_manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(frozen_rows[0]))
        writer.writeheader()
        writer.writerows(frozen_rows)

    portable_list_path = output / "public_holdout_files.txt"
    portable_list_path.write_text(
        "\n".join(row["image_path"] for row in frozen_rows) + "\n",
        encoding="utf-8",
    )

    absolute_list_path = output / "evaluation_input_images.absolute.txt"
    absolute_list_path.write_text(
        # Keep the dataset-facing symlink path lexical. Path.resolve() would
        # dereference it into sources/openimages/, breaking YOLO's standard
        # images/ -> labels/ companion-path conversion.
        "\n".join(str((project / row["image_path"]).absolute()) for row in frozen_rows) + "\n",
        encoding="utf-8",
    )
    input_yaml_path = output / "evaluation_input.absolute.yaml"
    input_yaml_path.write_text(
        yaml.safe_dump(
            {
                "path": str(dataset.resolve()),
                "train": str((dataset / "images/train").resolve()),
                "val": str((dataset / "images/val").resolve()),
                "test": str(absolute_list_path.resolve()),
                "nc": len(CLASS_NAMES),
                "names": {index: name for index, name in enumerate(CLASS_NAMES)},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    cohort = {
        **checks,
        "public_test_boxes": box_count,
        "class_image_counts": {CLASS_NAMES[i]: class_images[i] for i in range(len(CLASS_NAMES))},
        "class_instance_counts": {CLASS_NAMES[i]: class_instances[i] for i in range(len(CLASS_NAMES))},
        "baseline_openimages_id_count": len(baseline_openimages_ids),
        "baseline_vs_all_current_public_overlap_count": len(overlap_all),
        "baseline_vs_public_holdout_overlap_count": len(overlap_holdout),
        "initializer_manifest_missing_count": len(missing_from_expanded),
        "initializer_manifest_nonunique_count": len(nonunique_in_expanded),
        "initializer_manifest_non_test_placement_count": len(non_test_in_expanded),
        "interpretation": (
            "The 550 images are exactly the Open Images V7 portion of the existing 650-image test split. "
            "They are a source-stratified analysis of a reused development holdout, not a new independent test set."
        ),
    }
    return frozen_rows, cohort, input_yaml_path


def main() -> int:
    args = parse_args()
    project = Path(__file__).resolve().parents[1]
    dataset = args.dataset.expanduser().resolve()
    model_path = args.model.expanduser().resolve()
    output = args.output.expanduser().resolve()
    baseline_provenance = args.baseline_provenance.expanduser().resolve()
    expanded_manifest = args.expanded_manifest.expanduser().resolve()

    required = [dataset / "manifest.csv", dataset / "dataset.yaml", model_path, baseline_provenance, expanded_manifest]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing required input(s): " + ", ".join(missing))
    if output.exists():
        raise FileExistsError(f"refusing to overwrite an existing evaluation directory: {output}")
    output.mkdir(parents=True)

    frozen_rows, cohort, input_yaml_path = validate_and_freeze_cohort(
        dataset,
        project,
        output,
        baseline_provenance,
        expanded_manifest,
    )

    import numpy as np
    import torch
    import ultralytics
    from ultralytics import YOLO
    from ultralytics.utils.metrics import smooth

    validation_args = {
        "data": str(input_yaml_path.resolve()),
        "split": "test",
        "imgsz": 640,
        "batch": args.batch,
        "device": args.device,
        "workers": 0,
        "conf": 0.001,
        "iou": 0.7,
        "max_det": 300,
        "agnostic_nms": False,
        "single_cls": False,
        "rect": True,
        "augment": False,
        "quantize": None,
        "plots": False,
        "save_json": False,
        "save_txt": False,
        "save_conf": False,
        "dnn": False,
        "verbose": True,
        "project": str(output / "runs"),
        "name": "public_holdout",
        "exist_ok": True,
    }

    test_cache_path = dataset / "labels/test.cache"
    cache_preexisted = test_cache_path.exists()
    model = YOLO(str(model_path))
    try:
        metrics = model.val(**validation_args)
    finally:
        if not cache_preexisted and test_cache_path.exists():
            test_cache_path.unlink()

    box = metrics.box
    measured_instances = int(np.asarray(metrics.nt_per_class).sum())
    if measured_instances != EXPECTED_PUBLIC_TEST_BOXES:
        raise RuntimeError(
            f"validator consumed {measured_instances} labeled instances, expected {EXPECTED_PUBLIC_TEST_BOXES}"
        )
    op_curve = smooth(box.f1_curve.mean(0), 0.1)
    operating_index = int(op_curve.argmax())
    operating_confidence = float(box.px[operating_index])

    class_instances = cohort["class_instance_counts"]
    class_images = cohort["class_image_counts"]
    rows: list[dict[str, object]] = [
        {
            "scope": "overall_macro",
            "class_id": "all",
            "class_name": "all",
            "images": len(frozen_rows),
            "instances": cohort["public_test_boxes"],
            "precision": float(box.mp),
            "recall": float(box.mr),
            "f1": float(np.mean(box.f1)),
            "mAP50": float(box.map50),
            "mAP50-95": float(box.map),
            "operating_confidence": operating_confidence,
        }
    ]
    for index, class_id_raw in enumerate(box.ap_class_index):
        class_id = int(class_id_raw)
        class_name = str(metrics.names[class_id])
        rows.append(
            {
                "scope": "class",
                "class_id": class_id,
                "class_name": class_name,
                "images": class_images[class_name],
                "instances": class_instances[class_name],
                "precision": float(box.p[index]),
                "recall": float(box.r[index]),
                "f1": float(box.f1[index]),
                "mAP50": float(box.ap50[index]),
                "mAP50-95": float(box.ap[index]),
                "operating_confidence": operating_confidence,
            }
        )

    results_csv = output / "evaluation_results.csv"
    with results_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    checkpoint_overrides = dict(model.overrides)
    for key in ("model", "data"):
        value = checkpoint_overrides.get(key)
        if value:
            try:
                checkpoint_overrides[key] = relative_to_project(Path(value), project)
            except (ValueError, OSError):
                checkpoint_overrides[key] = str(value)

    config = {
        "analysis_scope": "source-stratified Open Images V7 subset of the reused 650-image development holdout",
        "model": relative_to_project(model_path, project),
        "model_sha256": sha256(model_path),
        "model_size_bytes": model_path.stat().st_size,
        "checkpoint_overrides": checkpoint_overrides,
        "dataset": relative_to_project(dataset, project),
        "dataset_yaml_sha256": sha256(dataset / "dataset.yaml"),
        "dataset_manifest_sha256": sha256(dataset / "manifest.csv"),
        "portable_holdout_list": relative_to_project(output / "public_holdout_files.txt", project),
        "portable_holdout_list_sha256": sha256(output / "public_holdout_files.txt"),
        "public_holdout_manifest": relative_to_project(output / "public_holdout_manifest.csv", project),
        "public_holdout_manifest_sha256": sha256(output / "public_holdout_manifest.csv"),
        "evaluation_input_yaml": relative_to_project(input_yaml_path, project),
        "evaluation_input_yaml_sha256": sha256(input_yaml_path),
        "evaluation_input_image_list": relative_to_project(
            output / "evaluation_input_images.absolute.txt", project
        ),
        "evaluation_input_image_list_sha256": sha256(output / "evaluation_input_images.absolute.txt"),
        "software": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "ultralytics": ultralytics.__version__,
        },
        "resolved_validation_arguments": {
            **{key: value for key, value in validation_args.items() if key not in {"data", "project"}},
            "data": relative_to_project(input_yaml_path, project),
            "project": relative_to_project(output / "runs", project),
            "effective_precision": "FP32 on MPS (quantize=None)",
            "nms_multi_label": True,
        },
        "metric_definition": {
            "iou_thresholds_for_ap": [round(float(x), 2) for x in np.linspace(0.5, 0.95, 10)],
            "precision_recall_operating_point": (
                "One shared confidence index maximizing the smoothed mean F1 curve across represented classes; "
                "reported overall precision and recall are unweighted means across class values at that index."
            ),
            "operating_confidence": operating_confidence,
            "nms_candidate_confidence_floor": validation_args["conf"],
        },
    }
    results_json = output / "evaluation_results.json"
    results_json.write_text(
        json.dumps(
            {
                "configuration": config,
                "cohort": cohort,
                "metrics": rows,
                "speed_ms_per_image": {key: float(value) for key, value in metrics.speed.items()},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps({"output": str(output), "cohort": cohort, "metrics": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
