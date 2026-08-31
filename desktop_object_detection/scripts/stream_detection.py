#!/usr/bin/env python3
"""Shared OpenCV stream loop for camera and video entry points."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import cv2

from runtime_utils import (
    DetectionCsv,
    annotate_result,
    boxes_as_rows,
    choose_device,
    make_writer,
    open_capture,
    precision_kwargs,
    timestamp_slug,
)


def run_stream(args: Any, window_name: str) -> int:
    if not args.model.is_file():
        print(f"[ERROR] Model not found: {args.model}")
        return 2
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] ultralytics is not installed")
        return 2
    try:
        capture = open_capture(str(args.source))
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 2
    device = choose_device(args.device)
    precision = precision_kwargs(args.half, device, args.model)
    output = args.output.resolve()
    video_dir = output / "videos"
    image_dir = output / "images"
    log_dir = output / "logs"
    for directory in (video_dir, image_dir, log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    slug = timestamp_slug()
    csv_path = log_dir / f"detections_{slug}.csv"
    video_path = video_dir / f"detection_{slug}.mp4"
    writer = None
    model = YOLO(str(args.model.resolve()))
    print(f"[INFO] Model loaded: {args.model}")
    print(f"[INFO] Device: {device}")
    print(f"[INFO] Source opened: {args.source}")
    print(f"[INFO] Image size: {args.imgsz}")
    print(f"[INFO] Confidence threshold: {args.conf}")
    frame_id = 0
    smoothed_fps = 0.0
    try:
        with DetectionCsv(csv_path) as detection_csv:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                started = time.perf_counter()
                result = model.predict(
                    source=frame,
                    imgsz=args.imgsz,
                    conf=args.conf,
                    iou=args.iou,
                    device=device,
                    verbose=False,
                    **precision,
                )[0]
                elapsed = max(time.perf_counter() - started, 1e-9)
                instant_fps = 1.0 / elapsed
                smoothed_fps = instant_fps if frame_id == 0 else 0.9 * smoothed_fps + 0.1 * instant_fps
                annotated = annotate_result(result, smoothed_fps)
                now = time.time()
                detection_csv.write(boxes_as_rows(result, frame_id, now))
                if args.save_video:
                    if writer is None:
                        writer = make_writer(video_path, capture, (annotated.shape[1], annotated.shape[0]))
                    writer.write(annotated)
                if args.show:
                    cv2.imshow(window_name, annotated)
                    key = cv2.waitKey(1) & 0xFF
                    if key in (27, ord("q")):
                        break
                    if key == ord("s"):
                        screenshot = image_dir / f"screenshot_{slug}_{frame_id:06d}.jpg"
                        cv2.imwrite(str(screenshot), annotated)
                        print(f"[INFO] Screenshot: {screenshot}")
                frame_id += 1
    except KeyboardInterrupt:
        print("[INFO] Interrupted")
    finally:
        capture.release()
        if writer is not None:
            writer.release()
        if args.show:
            cv2.destroyAllWindows()
    print(f"[INFO] Frames: {frame_id}")
    print(f"[INFO] Average FPS (smoothed final): {smoothed_fps:.2f}")
    print(f"[INFO] Detection CSV: {csv_path}")
    if args.save_video:
        print(f"[INFO] Video: {video_path}")
    return 0
