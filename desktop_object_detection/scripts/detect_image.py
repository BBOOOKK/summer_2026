#!/usr/bin/env python3
"""Run YOLO on one image and save an annotated image plus detection CSV."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from runtime_utils import (
    DetectionCsv,
    annotate_result,
    boxes_as_rows,
    choose_device,
    precision_kwargs,
    project_root,
    timestamp_slug,
)


def parse_args() -> argparse.Namespace:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=root / "models/best.pt")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.5)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--half", action="store_true")
    parser.add_argument("--output", type=Path, default=root / "outputs/images")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.model.is_file():
        print(f"[ERROR] Model not found: {args.model}")
        return 2
    if not args.source.is_file():
        print(f"[ERROR] Input image not found: {args.source}")
        return 2
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] ultralytics is not installed")
        return 2
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    device = choose_device(args.device)
    model = YOLO(str(args.model.resolve()))
    timestamp = time.time()
    result = model.predict(
        source=str(args.source.resolve()),
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        device=device,
        verbose=False,
        **precision_kwargs(args.half, device, args.model),
    )[0]
    slug = timestamp_slug()
    image_path = output / f"{args.source.stem}_{slug}.jpg"
    csv_path = output / f"{args.source.stem}_{slug}.csv"
    if not cv2.imwrite(str(image_path), annotate_result(result)):
        print(f"[ERROR] Failed to save image: {image_path}")
        return 1
    with DetectionCsv(csv_path) as detection_csv:
        detection_csv.write(boxes_as_rows(result, 0, timestamp))
    print(f"[INFO] Detections: {len(result.boxes)}")
    print(f"[INFO] Image: {image_path}")
    print(f"[INFO] CSV: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
