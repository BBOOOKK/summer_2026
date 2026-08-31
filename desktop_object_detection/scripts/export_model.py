#!/usr/bin/env python3
"""Export a trained YOLO model to ONNX or TensorRT engine."""

from __future__ import annotations

import argparse
from pathlib import Path

from runtime_utils import choose_device, project_root


def parse_args() -> argparse.Namespace:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=root / "models/best.pt")
    parser.add_argument("--format", choices=["onnx", "engine"], required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--half", action="store_true")
    parser.add_argument("--dynamic", action="store_true")
    parser.add_argument("--simplify", action="store_true")
    parser.add_argument("--workspace", type=float, default=4.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.model.is_file():
        print(f"[ERROR] Model not found: {args.model}")
        return 2
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] ultralytics is not installed")
        return 2
    device = choose_device(args.device)
    if args.format == "engine" and device == "cpu":
        print("[ERROR] TensorRT export requires an NVIDIA CUDA environment; run this on Jetson")
        return 2
    export_args: dict[str, object] = {
        "format": args.format,
        "imgsz": args.imgsz,
        "device": device,
    }
    if args.format == "onnx":
        export_args.update(dynamic=args.dynamic, simplify=args.simplify)
    else:
        export_args.update(dynamic=args.dynamic, workspace=args.workspace)
        if args.half:
            export_args["half"] = True
    exported = YOLO(str(args.model.resolve())).export(**export_args)
    print(f"[INFO] Exported model: {exported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
