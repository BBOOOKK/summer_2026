#!/usr/bin/env python3
"""Run YOLO on a video, with optional display and annotated video saving."""

from __future__ import annotations

import argparse
from pathlib import Path

from runtime_utils import project_root
from stream_detection import run_stream


def parse_args() -> argparse.Namespace:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=root / "models/best.pt")
    parser.add_argument("--source", required=True)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.5)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--half", action="store_true")
    parser.add_argument("--save-video", action="store_true")
    parser.add_argument("--show", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output", type=Path, default=root / "outputs")
    return parser.parse_args()


def main() -> int:
    return run_stream(parse_args(), "P05 Video Detection")


if __name__ == "__main__":
    raise SystemExit(main())

