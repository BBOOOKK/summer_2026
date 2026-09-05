#!/usr/bin/env python3
"""Save three purposefully selected, report-ready error-case records.

Each image is passed to YOLO.predict separately. The resulting evidence is
descriptive: the cases were selected after the aggregate test evaluation and
must not be used to estimate an error rate or to replace the 650-image AP run.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import ultralytics
from ultralytics import YOLO


CLASS_NAMES = ["mouse", "keyboard", "laptop", "cup", "headphones"]
IOU_MATCH_THRESHOLD = 0.50
CASE_SPECS = (
    {
        "order": 1,
        "source_id": "6eb03384f25d3f01",
        "case_type": "false_negative_no_detection",
        "short_label": "Headphones missed",
        "output_stem": "01_headphones_missed_gt_vs_prediction",
        "selection_reason": (
            "Purposefully selected headphones example with no prediction at the "
            "fixed confidence threshold."
        ),
        "visual_review": "Headphones are visibly present; no accepted prediction is produced.",
    },
    {
        "order": 2,
        "source_id": "0378fe468292e979",
        "case_type": "correct_class_localization_below_iou50",
        "short_label": "Localization mismatch",
        "output_stem": "02_headphones_localization_gt_vs_prediction",
        "selection_reason": (
            "Purposefully selected example with the correct headphones class but "
            "a box overlap below IoU 0.50."
        ),
        "visual_review": (
            "The predicted class is correct, but its extent differs from the "
            "provider reference box."
        ),
    },
    {
        "order": 3,
        "source_id": "34da803c6cae973c",
        "case_type": "spurious_cup_false_positive_with_headphones_detection",
        "short_label": "Spurious cup prediction",
        "output_stem": "03_spurious_cup_gt_vs_prediction",
        "selection_reason": (
            "Purposefully selected example containing a high-confidence cup "
            "prediction in addition to a headphones prediction."
        ),
        "visual_review": (
            "No cup is visible in the image; the cup box is a false positive "
            "relative to the provider ground truth and direct visual inspection."
        ),
    },
)


def parse_args() -> argparse.Namespace:
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        type=Path,
        default=project / "models/experiment1_1000self_4000public_v1/best.pt",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=project / "datasets/experiment1_1000self_4000public_v1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project / "outputs/errors/experiment1_1000self_4000public_v1_holdout",
    )
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.50)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--device", default="mps")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def project_relative(
    path: Path,
    project: Path,
    *,
    resolve_symlinks: bool = False,
) -> str:
    candidate = path.resolve() if resolve_symlinks else path.absolute()
    try:
        return candidate.relative_to(project.resolve()).as_posix()
    except ValueError:
        return str(candidate)


def read_manifest(dataset: Path) -> dict[str, dict[str, str]]:
    wanted = {case["source_id"] for case in CASE_SPECS}
    with (dataset / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        selected = {
            row["source_id"]: row
            for row in csv.DictReader(handle)
            if row["source_id"] in wanted
        }
    missing = sorted(wanted - selected.keys())
    if missing:
        raise RuntimeError(f"source IDs missing from manifest: {missing}")
    for source_id, row in selected.items():
        if row["split"] != "test" or row["source_type"] != "open_images_v7":
            raise RuntimeError(f"{source_id} is not an Open Images test item: {row}")
    return selected


def read_ground_truth(label_path: Path, width: int, height: int) -> list[dict[str, Any]]:
    ground_truth: list[dict[str, Any]] = []
    for index, line in enumerate(label_path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise RuntimeError(f"invalid YOLO label in {label_path}: {line}")
        class_id = int(fields[0])
        xc, yc, box_width, box_height = (float(value) for value in fields[1:])
        x1 = (xc - box_width / 2.0) * width
        y1 = (yc - box_height / 2.0) * height
        x2 = (xc + box_width / 2.0) * width
        y2 = (yc + box_height / 2.0) * height
        ground_truth.append(
            {
                "box_index": index,
                "class_id": class_id,
                "class_name": CLASS_NAMES[class_id],
                "confidence": None,
                "bbox_xyxy_px": [x1, y1, x2, y2],
                "bbox_yolo_normalized": [xc, yc, box_width, box_height],
            }
        )
    return ground_truth


def prediction_records(result: Any, width: int, height: int) -> list[dict[str, Any]]:
    predictions: list[dict[str, Any]] = []
    if result.boxes is None:
        return predictions
    for index, box in enumerate(result.boxes):
        class_id = int(box.cls.item())
        confidence = float(box.conf.item())
        x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
        predictions.append(
            {
                "box_index": index,
                "class_id": class_id,
                "class_name": str(result.names[class_id]),
                "confidence": confidence,
                "bbox_xyxy_px": [x1, y1, x2, y2],
                "bbox_yolo_normalized": [
                    ((x1 + x2) / 2.0) / width,
                    ((y1 + y2) / 2.0) / height,
                    (x2 - x1) / width,
                    (y2 - y1) / height,
                ],
            }
        )
    return predictions


def box_iou(first: list[float], second: list[float]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0.0 else 0.0


def evaluate_boxes(
    ground_truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    pairs: list[dict[str, Any]] = []
    candidate_matches: list[tuple[float, int, int]] = []
    for prediction in predictions:
        all_ious: list[float] = []
        same_class_ious: list[tuple[float, int]] = []
        for truth in ground_truth:
            iou = box_iou(prediction["bbox_xyxy_px"], truth["bbox_xyxy_px"])
            class_match = prediction["class_id"] == truth["class_id"]
            pairs.append(
                {
                    "prediction_index": prediction["box_index"],
                    "prediction_class_id": prediction["class_id"],
                    "prediction_class_name": prediction["class_name"],
                    "prediction_confidence": prediction["confidence"],
                    "ground_truth_index": truth["box_index"],
                    "ground_truth_class_id": truth["class_id"],
                    "ground_truth_class_name": truth["class_name"],
                    "class_match": class_match,
                    "iou": iou,
                }
            )
            all_ious.append(iou)
            if class_match:
                same_class_ious.append((iou, truth["box_index"]))
                if iou >= IOU_MATCH_THRESHOLD:
                    candidate_matches.append(
                        (iou, prediction["box_index"], truth["box_index"])
                    )
        prediction["max_iou_any_ground_truth"] = max(all_ious, default=0.0)
        prediction["max_iou_same_class_ground_truth"] = max(
            (item[0] for item in same_class_ious), default=0.0
        )
        prediction["best_same_class_ground_truth_index"] = (
            max(same_class_ious)[1] if same_class_ious else None
        )

    matched_predictions: dict[int, int] = {}
    matched_ground_truth: dict[int, int] = {}
    for _, prediction_index, truth_index in sorted(candidate_matches, reverse=True):
        if (
            prediction_index not in matched_predictions
            and truth_index not in matched_ground_truth
        ):
            matched_predictions[prediction_index] = truth_index
            matched_ground_truth[truth_index] = prediction_index

    for prediction in predictions:
        index = prediction["box_index"]
        prediction["matched_ground_truth_index_iou50"] = matched_predictions.get(index)
        if index in matched_predictions:
            prediction["evaluation_label_iou50"] = "true_positive"
        elif prediction["best_same_class_ground_truth_index"] is not None:
            prediction["evaluation_label_iou50"] = "localization_or_duplicate_false_positive"
        else:
            prediction["evaluation_label_iou50"] = "wrong_class_false_positive"

    for truth in ground_truth:
        index = truth["box_index"]
        relevant_pairs = [pair for pair in pairs if pair["ground_truth_index"] == index]
        truth["max_iou_any_prediction"] = max(
            (pair["iou"] for pair in relevant_pairs), default=0.0
        )
        truth["max_iou_same_class_prediction"] = max(
            (
                pair["iou"]
                for pair in relevant_pairs
                if pair["class_match"]
            ),
            default=0.0,
        )
        truth["matched_prediction_index_iou50"] = matched_ground_truth.get(index)
        truth["evaluation_label_iou50"] = (
            "matched_true_positive"
            if index in matched_ground_truth
            else "false_negative"
        )

    summary = {
        "true_positives_iou50": len(matched_predictions),
        "false_positives_iou50": len(predictions) - len(matched_predictions),
        "false_negatives_iou50": len(ground_truth) - len(matched_ground_truth),
    }
    return pairs, summary


def draw_text_box(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    color: tuple[int, int, int],
    font_scale: float,
    thickness: int,
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    (text_width, text_height), baseline = cv2.getTextSize(
        text, font, font_scale, thickness
    )
    x, y = origin
    x = max(0, min(x, image.shape[1] - text_width - 8))
    y = max(text_height + 8, min(y, image.shape[0] - baseline - 4))
    cv2.rectangle(
        image,
        (x, y - text_height - 8),
        (x + text_width + 8, y + baseline + 4),
        color,
        -1,
    )
    cv2.putText(
        image,
        text,
        (x + 4, y - 3),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def draw_box(
    image: np.ndarray,
    bbox: list[float],
    label: str,
    color: tuple[int, int, int],
    y_offset: int,
    font_scale: float,
    thickness: int,
    label_stack_index: int,
) -> None:
    x1, y1, x2, y2 = bbox
    x1_i = max(0, min(image.shape[1] - 1, int(round(x1))))
    y1_i = max(y_offset, min(image.shape[0] - 1, int(round(y1)) + y_offset))
    x2_i = max(0, min(image.shape[1] - 1, int(round(x2))))
    y2_i = max(y_offset, min(image.shape[0] - 1, int(round(y2)) + y_offset))
    cv2.rectangle(image, (x1_i, y1_i), (x2_i, y2_i), color, thickness)
    if y1_i - 5 > y_offset + 20:
        label_y = y1_i - 5
    else:
        stack_spacing = max(30, int(round(38 * font_scale)))
        label_y = y1_i + 28 + label_stack_index * stack_spacing
    draw_text_box(
        image,
        label,
        (x1_i, label_y),
        color,
        font_scale,
        max(1, thickness - 1),
    )


def make_panel(
    image: np.ndarray,
    title: str,
    entries: list[dict[str, Any]],
    is_ground_truth: bool,
    confidence_threshold: float,
) -> np.ndarray:
    height, width = image.shape[:2]
    header_height = max(52, int(round(height * 0.10)))
    panel = np.full((height + header_height, width, 3), 255, dtype=np.uint8)
    panel[header_height:, :] = image
    panel[:header_height, :] = (35, 35, 35)
    font_scale = max(0.62, min(0.95, width / 1200.0))
    thickness = max(2, int(round(min(width, height) / 300.0)))
    cv2.putText(
        panel,
        title,
        (16, int(header_height * 0.68)),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        max(2, thickness),
        cv2.LINE_AA,
    )

    if not entries and not is_ground_truth:
        draw_text_box(
            panel,
            f"NO PREDICTION >= {confidence_threshold:.2f}",
            (16, header_height + 38),
            (0, 0, 210),
            font_scale,
            max(1, thickness - 1),
        )
        return panel

    for entry_position, entry in enumerate(entries):
        if is_ground_truth:
            color = (40, 170, 40)
            label = f"GT {entry['class_name']}"
        else:
            evaluation = entry["evaluation_label_iou50"]
            if evaluation == "true_positive":
                color = (200, 160, 0)
            elif evaluation == "localization_or_duplicate_false_positive":
                color = (0, 130, 230)
            else:
                color = (0, 0, 220)
            label = (
                f"PRED {entry['class_name']} {entry['confidence']:.3f} | "
                f"same-class IoU {entry['max_iou_same_class_ground_truth']:.3f}"
            )
        draw_box(
            panel,
            entry["bbox_xyxy_px"],
            label,
            color,
            header_height,
            font_scale,
            thickness,
            entry_position,
        )
    return panel


def save_comparison_image(
    image: np.ndarray,
    ground_truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    spec: dict[str, Any],
    output_path: Path,
    confidence_threshold: float,
) -> None:
    truth_panel = make_panel(
        image,
        "PROVIDER GROUND TRUTH",
        ground_truth,
        True,
        confidence_threshold,
    )
    prediction_panel = make_panel(
        image,
        "MODEL PREDICTIONS",
        predictions,
        False,
        confidence_threshold,
    )
    gap = np.full((truth_panel.shape[0], 12, 3), 255, dtype=np.uint8)
    body = np.concatenate((truth_panel, gap, prediction_panel), axis=1)
    footer_height = 76
    footer = np.full((footer_height, body.shape[1], 3), 245, dtype=np.uint8)
    font_scale = max(0.55, min(0.80, image.shape[1] / 1500.0))
    cv2.putText(
        footer,
        f"{spec['short_label']} | source ID {spec['source_id']}",
        (16, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (25, 25, 25),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        footer,
        "Green: provider GT | Cyan: IoU>=0.50 match | Orange: localization mismatch | Red: other prediction",
        (16, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        max(0.46, font_scale * 0.80),
        (40, 40, 40),
        1,
        cv2.LINE_AA,
    )
    comparison = np.concatenate((body, footer), axis=0)
    if not cv2.imwrite(
        str(output_path),
        comparison,
        [cv2.IMWRITE_JPEG_QUALITY, 95],
    ):
        raise RuntimeError(f"failed to save {output_path}")


def validate_case_expectations(case: dict[str, Any]) -> None:
    source_id = case["source_id"]
    predictions = case["predictions"]
    if source_id == "6eb03384f25d3f01":
        if predictions:
            raise RuntimeError("expected no accepted prediction for 6eb03384f25d3f01")
    elif source_id == "0378fe468292e979":
        same_class_iou = max(
            (
                prediction["max_iou_same_class_ground_truth"]
                for prediction in predictions
                if prediction["class_name"] == "headphones"
            ),
            default=0.0,
        )
        if not 0.44 <= same_class_iou < 0.50:
            raise RuntimeError(
                f"unexpected localization-case IoU for {source_id}: {same_class_iou:.6f}"
            )
    elif source_id == "34da803c6cae973c":
        names = {prediction["class_name"] for prediction in predictions}
        if not {"cup", "headphones"}.issubset(names):
            raise RuntimeError(f"expected cup and headphones predictions for {source_id}: {names}")


def csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.6f}"
    return value


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key)) for key in fieldnames})


def main() -> int:
    args = parse_args()
    project = Path(__file__).resolve().parents[1]
    model_path = args.model.expanduser().resolve()
    dataset = args.dataset.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    if not dataset.is_dir():
        raise FileNotFoundError(dataset)
    if args.device == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS requested but unavailable")
    output.mkdir(parents=True, exist_ok=True)

    np.random.seed(0)
    torch.manual_seed(0)
    manifest = read_manifest(dataset)
    model = YOLO(str(model_path))
    model_names = [str(model.names[index]) for index in range(len(model.names))]
    if model_names != CLASS_NAMES:
        raise RuntimeError(f"unexpected model class map: {model_names}")

    evidence: dict[str, Any] = {
        "schema_version": "1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "generator": {
            "script_path": project_relative(Path(__file__), project),
            "script_sha256": sha256(Path(__file__)),
        },
        "scope": {
            "selection": (
                "Three purposefully selected qualitative cases from the public portion "
                "of the existing 650-image test split."
            ),
            "statistical_interpretation": (
                "The cases are not randomly sampled and must not be used to estimate "
                "an overall error rate."
            ),
            "aggregate_evaluation_impact": (
                "None. Saving these records does not modify the frozen 650-image AP "
                "evaluation, its labels, the checkpoint, or any training state."
            ),
            "training_impact": "No retraining or parameter update is performed.",
            "iou_analysis": (
                "The per-box IoU records are descriptive at an IoU 0.50 matching "
                "threshold and do not reimplement or replace Ultralytics AP."
            ),
        },
        "inference_configuration": {
            "model_path": project_relative(model_path, project),
            "model_sha256": sha256(model_path),
            "model_size_bytes": model_path.stat().st_size,
            "class_names": CLASS_NAMES,
            "imgsz": args.imgsz,
            "confidence_threshold": args.conf,
            "nms_iou_threshold": args.iou,
            "device": args.device,
            "half": False,
            "prediction_unit": "one image per model.predict call; no list batch",
        },
        "dataset_record": {
            "dataset_path": project_relative(dataset, project),
            "manifest_path": project_relative(dataset / "manifest.csv", project),
            "manifest_sha256": sha256(dataset / "manifest.csv"),
            "selected_split": "test",
            "selected_source_type": "open_images_v7",
        },
        "software_environment": {
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "ultralytics": ultralytics.__version__,
            "opencv": cv2.__version__,
            "mps_available": bool(torch.backends.mps.is_available()),
        },
        "cases": [],
    }
    summary_rows: list[dict[str, Any]] = []
    box_rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []

    for spec in CASE_SPECS:
        row = manifest[spec["source_id"]]
        image_path = dataset / "images" / "test" / row["file"]
        label_path = dataset / "labels" / "test" / Path(row["file"]).with_suffix(".txt")
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"cannot decode {image_path}")
        height, width = image.shape[:2]
        ground_truth = read_ground_truth(label_path, width, height)

        # Deliberately keep one call per source image. Passing the three paths as a
        # list would change the requested execution boundary.
        result = model.predict(
            str(image_path),
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            device=args.device,
            verbose=False,
        )[0]
        predictions = prediction_records(result, width, height)
        pairwise, match_summary = evaluate_boxes(ground_truth, predictions)
        annotated_path = output / f"{spec['output_stem']}.jpg"
        save_comparison_image(
            image,
            ground_truth,
            predictions,
            spec,
            annotated_path,
            args.conf,
        )
        case = {
            "case_order": spec["order"],
            "source_id": spec["source_id"],
            "source_type": row["source_type"],
            "source_split": row["source_split"],
            "dataset_split": row["split"],
            "source_url": row["source_url"],
            "manifest_file": row["file"],
            "manifest_label_count": int(row["label_count"]),
            "manifest_classes": row["classes"].split("|"),
            "case_type": spec["case_type"],
            "selection_reason": spec["selection_reason"],
            "visual_review": spec["visual_review"],
            "image_path": project_relative(image_path, project),
            "annotation_path": project_relative(label_path, project),
            "resolved_image_source_path": project_relative(
                image_path, project, resolve_symlinks=True
            ),
            "resolved_annotation_source_path": project_relative(
                label_path, project, resolve_symlinks=True
            ),
            "comparison_image_path": project_relative(annotated_path, project),
            "comparison_image_sha256": sha256(annotated_path),
            "image_width_px": width,
            "image_height_px": height,
            "image_sha256": sha256(image_path),
            "annotation_sha256": sha256(label_path),
            "ground_truth": ground_truth,
            "predictions": predictions,
            "pairwise_iou": pairwise,
            "iou50_summary": match_summary,
        }
        validate_case_expectations(case)
        evidence["cases"].append(case)

        max_same_class_iou = max(
            (
                prediction["max_iou_same_class_ground_truth"]
                for prediction in predictions
            ),
            default=0.0,
        )
        top_prediction = (
            max(predictions, key=lambda prediction: prediction["confidence"])
            if predictions
            else None
        )
        summary_rows.append(
            {
                "case_order": spec["order"],
                "source_id": spec["source_id"],
                "case_type": spec["case_type"],
                "source_type": row["source_type"],
                "dataset_split": row["split"],
                "source_url": row["source_url"],
                "image_path": case["image_path"],
                "annotation_path": case["annotation_path"],
                "image_width_px": width,
                "image_height_px": height,
                "ground_truth_count": len(ground_truth),
                "prediction_count": len(predictions),
                **match_summary,
                "max_same_class_iou": max_same_class_iou,
                "top_prediction_class": (
                    top_prediction["class_name"] if top_prediction else ""
                ),
                "top_prediction_confidence": (
                    top_prediction["confidence"] if top_prediction else None
                ),
                "model_sha256": evidence["inference_configuration"]["model_sha256"],
                "image_sha256": case["image_sha256"],
                "annotation_sha256": case["annotation_sha256"],
                "comparison_image": case["comparison_image_path"],
                "comparison_image_sha256": case["comparison_image_sha256"],
                "selection_reason": spec["selection_reason"],
                "visual_review": spec["visual_review"],
            }
        )

        for truth in ground_truth:
            box_rows.append(
                {
                    "case_order": spec["order"],
                    "source_id": spec["source_id"],
                    "record_kind": "ground_truth",
                    "box_index": truth["box_index"],
                    "class_id": truth["class_id"],
                    "class_name": truth["class_name"],
                    "confidence": None,
                    "x1_px": truth["bbox_xyxy_px"][0],
                    "y1_px": truth["bbox_xyxy_px"][1],
                    "x2_px": truth["bbox_xyxy_px"][2],
                    "y2_px": truth["bbox_xyxy_px"][3],
                    "x_center_normalized": truth["bbox_yolo_normalized"][0],
                    "y_center_normalized": truth["bbox_yolo_normalized"][1],
                    "width_normalized": truth["bbox_yolo_normalized"][2],
                    "height_normalized": truth["bbox_yolo_normalized"][3],
                    "evaluation_label_iou50": truth["evaluation_label_iou50"],
                    "max_iou_any_counterpart": truth["max_iou_any_prediction"],
                    "max_iou_same_class_counterpart": truth[
                        "max_iou_same_class_prediction"
                    ],
                    "matched_counterpart_index_iou50": truth[
                        "matched_prediction_index_iou50"
                    ],
                }
            )
        for prediction in predictions:
            box_rows.append(
                {
                    "case_order": spec["order"],
                    "source_id": spec["source_id"],
                    "record_kind": "prediction",
                    "box_index": prediction["box_index"],
                    "class_id": prediction["class_id"],
                    "class_name": prediction["class_name"],
                    "confidence": prediction["confidence"],
                    "x1_px": prediction["bbox_xyxy_px"][0],
                    "y1_px": prediction["bbox_xyxy_px"][1],
                    "x2_px": prediction["bbox_xyxy_px"][2],
                    "y2_px": prediction["bbox_xyxy_px"][3],
                    "x_center_normalized": prediction["bbox_yolo_normalized"][0],
                    "y_center_normalized": prediction["bbox_yolo_normalized"][1],
                    "width_normalized": prediction["bbox_yolo_normalized"][2],
                    "height_normalized": prediction["bbox_yolo_normalized"][3],
                    "evaluation_label_iou50": prediction["evaluation_label_iou50"],
                    "max_iou_any_counterpart": prediction[
                        "max_iou_any_ground_truth"
                    ],
                    "max_iou_same_class_counterpart": prediction[
                        "max_iou_same_class_ground_truth"
                    ],
                    "matched_counterpart_index_iou50": prediction[
                        "matched_ground_truth_index_iou50"
                    ],
                }
            )
        for pair in pairwise:
            pair_rows.append(
                {
                    "case_order": spec["order"],
                    "source_id": spec["source_id"],
                    **pair,
                }
            )

    evidence_path = output / "error_case_evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    write_csv(
        output / "case_summary.csv",
        [
            "case_order",
            "source_id",
            "case_type",
            "source_type",
            "dataset_split",
            "source_url",
            "image_path",
            "annotation_path",
            "image_width_px",
            "image_height_px",
            "ground_truth_count",
            "prediction_count",
            "true_positives_iou50",
            "false_positives_iou50",
            "false_negatives_iou50",
            "max_same_class_iou",
            "top_prediction_class",
            "top_prediction_confidence",
            "model_sha256",
            "image_sha256",
            "annotation_sha256",
            "comparison_image",
            "comparison_image_sha256",
            "selection_reason",
            "visual_review",
        ],
        summary_rows,
    )
    write_csv(
        output / "boxes.csv",
        [
            "case_order",
            "source_id",
            "record_kind",
            "box_index",
            "class_id",
            "class_name",
            "confidence",
            "x1_px",
            "y1_px",
            "x2_px",
            "y2_px",
            "x_center_normalized",
            "y_center_normalized",
            "width_normalized",
            "height_normalized",
            "evaluation_label_iou50",
            "max_iou_any_counterpart",
            "max_iou_same_class_counterpart",
            "matched_counterpart_index_iou50",
        ],
        box_rows,
    )
    write_csv(
        output / "pairwise_iou.csv",
        [
            "case_order",
            "source_id",
            "prediction_index",
            "prediction_class_id",
            "prediction_class_name",
            "prediction_confidence",
            "ground_truth_index",
            "ground_truth_class_id",
            "ground_truth_class_name",
            "class_match",
            "iou",
        ],
        pair_rows,
    )
    print(f"Saved {len(evidence['cases'])} cases to {output}")
    for case in evidence["cases"]:
        predictions = case["predictions"]
        description = ", ".join(
            f"{item['class_name']}={item['confidence']:.6f}, "
            f"same-class IoU={item['max_iou_same_class_ground_truth']:.6f}"
            for item in predictions
        )
        print(f"{case['source_id']}: {description or 'no accepted prediction'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
