#!/usr/bin/env python3
"""Run real-time YOLO detection from an OpenCV camera source."""

from __future__ import annotations

import argparse
from pathlib import Path

from runtime_utils import load_detector_config, project_root, resolve_path
from stream_detection import run_stream


def parse_args() -> argparse.Namespace:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=root / "configs/detector.yaml")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--camera", dest="source")
    parser.add_argument("--imgsz", type=int)
    parser.add_argument("--conf", type=float)
    parser.add_argument("--iou", type=float)
    parser.add_argument("--device")
    parser.add_argument("--half", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--save-video", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--show", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config = load_detector_config(args.config)
    args.model = args.model or resolve_path(config.get("model_path", "models/best.pt"))
    args.source = args.source if args.source is not None else str(config.get("camera_id", 0))
    args.imgsz = args.imgsz or int(config.get("imgsz", 640))
    args.conf = args.conf if args.conf is not None else float(config.get("confidence_threshold", 0.5))
    args.iou = args.iou if args.iou is not None else float(config.get("iou_threshold", 0.45))
    args.device = args.device or str(config.get("device", "auto"))
    args.half = bool(config.get("half", True)) if args.half is None else args.half
    args.save_video = bool(config.get("save_video", False)) if args.save_video is None else args.save_video
    args.output = args.output or resolve_path(config.get("output_dir", "outputs"))
    return args


def main() -> int:
    return run_stream(parse_args(), "P05 Camera Detection")


if __name__ == "__main__":
    raise SystemExit(main())

