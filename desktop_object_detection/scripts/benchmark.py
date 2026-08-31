#!/usr/bin/env python3
"""Benchmark end-to-end YOLO stream FPS against the 5 FPS requirement."""

from __future__ import annotations

import argparse
import csv
import statistics
import time
from pathlib import Path

from runtime_utils import choose_device, open_capture, precision_kwargs, project_root


def parse_args() -> argparse.Namespace:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=root / "models/best.pt")
    parser.add_argument("--source", default="0", help="Camera index or video path")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.5)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--half", action="store_true")
    parser.add_argument("--warmup-frames", type=int, default=20)
    parser.add_argument("--test-frames", type=int, default=200)
    parser.add_argument("--requirement-fps", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=root / "outputs/benchmark/benchmark.csv")
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
    try:
        capture = open_capture(args.source)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 2
    device = choose_device(args.device)
    precision = precision_kwargs(args.half, device, args.model)
    model = YOLO(str(args.model.resolve()))
    loop_times_ms: list[float] = []
    inference_times_ms: list[float] = []
    frame_index = 0
    try:
        while len(loop_times_ms) < args.test_frames:
            ok, frame = capture.read()
            if not ok:
                break
            started = time.perf_counter()
            result = model.predict(
                frame,
                imgsz=args.imgsz,
                conf=args.conf,
                iou=args.iou,
                device=device,
                verbose=False,
                **precision,
            )[0]
            loop_ms = (time.perf_counter() - started) * 1000.0
            if frame_index >= args.warmup_frames:
                loop_times_ms.append(loop_ms)
                inference_times_ms.append(float(result.speed.get("inference", loop_ms)))
            frame_index += 1
    finally:
        capture.release()
    if not loop_times_ms:
        print("[ERROR] No benchmark frames were processed after warmup")
        return 1
    fps_values = [1000.0 / value for value in loop_times_ms]
    average_loop_ms = statistics.fmean(loop_times_ms)
    average_inference_ms = statistics.fmean(inference_times_ms)
    average_fps = 1000.0 / average_loop_ms
    min_fps = min(fps_values)
    max_inference_ms = max(inference_times_ms)
    status = "PASS" if average_fps >= args.requirement_fps else "FAIL"
    row = {
        "model": str(args.model.resolve()),
        "device": device,
        "image_size": args.imgsz,
        "frames": len(loop_times_ms),
        "average_inference_ms": f"{average_inference_ms:.3f}",
        "average_end_to_end_ms": f"{average_loop_ms:.3f}",
        "average_fps": f"{average_fps:.3f}",
        "min_fps": f"{min_fps:.3f}",
        "max_inference_ms": f"{max_inference_ms:.3f}",
        "requirement_fps": f"{args.requirement_fps:.3f}",
        "result": status,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
    print(f"Model: {args.model}")
    print(f"Device: {device}")
    print(f"Image size: {args.imgsz}")
    print(f"Frames: {len(loop_times_ms)}")
    print(f"Average inference time: {average_inference_ms:.3f} ms")
    print(f"Average FPS: {average_fps:.3f}")
    print(f"Min FPS: {min_fps:.3f}")
    print(f"Maximum inference time: {max_inference_ms:.3f} ms")
    print(f"Requirement: >= {args.requirement_fps:.1f} FPS")
    print(status)
    print(f"CSV: {args.output.resolve()}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
