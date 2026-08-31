#!/usr/bin/env python3
"""Run the course 20-object recognition-accuracy test and save error cases."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import cv2

from runtime_utils import annotate_result, choose_device, precision_kwargs, project_root


RESULT_FIELDS = [
    "sample_id",
    "image_path",
    "ground_truth",
    "prediction",
    "confidence",
    "correct",
]
ERROR_FIELDS = ["image", "ground_truth", "prediction", "confidence", "error_type"]


def parse_args() -> argparse.Namespace:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=root / "models/best.pt")
    parser.add_argument("--samples", type=Path, default=root / "configs/test_samples.csv")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.5)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--half", action="store_true")
    parser.add_argument("--low-confidence", type=float, default=0.6)
    parser.add_argument("--output", type=Path, default=root / "outputs/evaluation/20_object_test_results.csv")
    parser.add_argument("--errors", type=Path, default=root / "outputs/errors")
    return parser.parse_args()


def parse_ground_truth(value: str) -> set[str]:
    return {item.strip() for item in value.replace(";", "|").split("|") if item.strip()}


def label_error(frame: Any, gt: str, prediction: str, confidence: float) -> Any:
    lines = [f"GT: {gt}", f"Pred: {prediction}", f"Confidence: {confidence:.3f}"]
    y = 30
    for line in lines:
        cv2.putText(frame, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
        y += 28
    return frame


def main() -> int:
    args = parse_args()
    if not args.model.is_file():
        print(f"[ERROR] Model not found: {args.model}")
        return 2
    if not args.samples.is_file():
        print(f"[ERROR] Sample CSV not found: {args.samples}")
        return 2
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] ultralytics is not installed")
        return 2
    with args.samples.open("r", encoding="utf-8-sig", newline="") as handle:
        samples = list(csv.DictReader(handle))
    required = {"sample_id", "image_path", "ground_truth_class"}
    if not samples or not required.issubset(samples[0]):
        print(f"[ERROR] Sample CSV requires columns: {sorted(required)}")
        return 2
    if len(samples) != 20:
        print(f"[ERROR] Exactly 20 samples are required, found {len(samples)}")
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.errors.mkdir(parents=True, exist_ok=True)
    device = choose_device(args.device)
    model = YOLO(str(args.model.resolve()))
    results_rows: list[dict[str, object]] = []
    error_rows: list[dict[str, object]] = []
    correct_count = 0
    for sample in samples:
        image_path = Path(sample["image_path"]).expanduser()
        if not image_path.is_absolute():
            image_path = args.samples.parent / image_path
        image_path = image_path.resolve()
        if not image_path.is_file():
            print(f"[ERROR] Test image not found: {image_path}")
            return 2
        result = model.predict(
            str(image_path),
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            device=device,
            verbose=False,
            **precision_kwargs(args.half, device, args.model),
        )[0]
        detections: list[tuple[str, float]] = []
        if result.boxes is not None:
            for box in result.boxes:
                class_id = int(box.cls.item())
                detections.append((str(result.names[class_id]), float(box.conf.item())))
        detections.sort(key=lambda item: item[1], reverse=True)
        predicted_classes = {name for name, _ in detections}
        gt_classes = parse_ground_truth(sample["ground_truth_class"])
        prediction = detections[0][0] if detections else "none"
        confidence = detections[0][1] if detections else 0.0
        if gt_classes == {"none"}:
            correct = not detections
        elif len(gt_classes) == 1:
            # A single-target sample is classified by its highest-confidence detection.
            correct = prediction in gt_classes
        else:
            # For multi-object rows, every listed GT class must appear at least once.
            correct = bool(gt_classes) and gt_classes.issubset(predicted_classes)
        correct_count += int(correct)
        results_rows.append({
            "sample_id": sample["sample_id"],
            "image_path": str(image_path),
            "ground_truth": "|".join(sorted(gt_classes)),
            "prediction": prediction,
            "confidence": f"{confidence:.6f}",
            "correct": str(correct).lower(),
        })
        error_type = ""
        if gt_classes == {"none"} and detections:
            error_type = "false_positive"
        elif not detections:
            error_type = "missed_detection"
        elif not correct:
            error_type = "misclassification"
        elif confidence < args.low_confidence:
            error_type = "low_confidence"
        if error_type:
            annotated = label_error(annotate_result(result), "|".join(sorted(gt_classes)), prediction, confidence)
            error_path = args.errors / f"{sample['sample_id']}_{error_type}.jpg"
            cv2.imwrite(str(error_path), annotated)
            error_rows.append({
                "image": str(error_path),
                "ground_truth": "|".join(sorted(gt_classes)),
                "prediction": prediction,
                "confidence": f"{confidence:.6f}",
                "error_type": error_type,
            })
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(results_rows)
    errors_csv = args.errors / "error_cases.csv"
    with errors_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ERROR_FIELDS)
        writer.writeheader()
        writer.writerows(error_rows)
    total = len(samples)
    wrong = total - correct_count
    accuracy = correct_count / total * 100.0
    status = "PASS" if accuracy >= 80.0 else "FAIL"
    print(f"Total: {total}")
    print(f"Correct: {correct_count}")
    print(f"Wrong: {wrong}")
    print(f"Accuracy: {accuracy:.2f}%")
    print("Requirement: >= 80%")
    print(f"Result: {status}")
    print(f"Results: {args.output.resolve()}")
    print(f"Error cases: {errors_csv.resolve()}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
