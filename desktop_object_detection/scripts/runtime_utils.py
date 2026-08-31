#!/usr/bin/env python3
"""Runtime helpers shared by training and inference entry points."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any, Iterable

import cv2
import yaml


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_detector_config(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Detector config not found: {path}")
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise ValueError("Detector config root must be a mapping")
    return config


def resolve_path(value: str | Path, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base or project_root()) / path
    return path.resolve()


def choose_device(requested: str) -> str | int:
    requested = str(requested).strip().lower()
    if requested not in {"", "auto"}:
        return int(requested) if requested.isdigit() else requested
    try:
        import torch

        if torch.cuda.is_available():
            return 0
    except ImportError:
        pass
    return "cpu"


def use_half(requested: bool, device: str | int, model_path: Path) -> bool:
    if model_path.suffix.lower() == ".engine":
        return False
    return bool(requested and (isinstance(device, int) or str(device).startswith("cuda")))


def precision_kwargs(requested_half: bool, device: str | int, model_path: Path) -> dict[str, bool]:
    """Only pass the legacy half flag when FP16 was explicitly requested and is usable."""
    return {"half": True} if use_half(requested_half, device, model_path) else {}


def timestamp_slug() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def boxes_as_rows(result: Any, frame_id: int, timestamp: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if result.boxes is None:
        return rows
    names = result.names
    for box in result.boxes:
        class_id = int(box.cls.item())
        confidence = float(box.conf.item())
        x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
        rows.append({
            "timestamp": f"{timestamp:.6f}",
            "frame_id": frame_id,
            "class_id": class_id,
            "class_name": str(names[class_id]),
            "confidence": f"{confidence:.6f}",
            "x1": f"{x1:.2f}",
            "y1": f"{y1:.2f}",
            "x2": f"{x2:.2f}",
            "y2": f"{y2:.2f}",
        })
    return rows


CSV_FIELDS = [
    "timestamp",
    "frame_id",
    "class_id",
    "class_name",
    "confidence",
    "x1",
    "y1",
    "x2",
    "y2",
]


class DetectionCsv:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.handle = path.open("w", encoding="utf-8", newline="")
        self.writer = csv.DictWriter(self.handle, fieldnames=CSV_FIELDS)
        self.writer.writeheader()

    def write(self, rows: Iterable[dict[str, Any]]) -> None:
        self.writer.writerows(rows)
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()

    def __enter__(self) -> "DetectionCsv":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def annotate_result(result: Any, fps: float | None = None) -> Any:
    frame = result.plot()
    if fps is not None:
        cv2.rectangle(frame, (8, 8), (175, 42), (0, 0, 0), -1)
        cv2.putText(
            frame,
            f"FPS: {fps:.1f}",
            (16, 33),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
    return frame


def open_capture(source: str) -> cv2.VideoCapture:
    parsed: str | int = int(source) if str(source).isdigit() else source
    capture = cv2.VideoCapture(parsed)
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open camera/video source: {source}")
    return capture


def make_writer(path: Path, capture: cv2.VideoCapture, fallback_size: tuple[int, int]) -> cv2.VideoWriter:
    path.parent.mkdir(parents=True, exist_ok=True)
    fps = capture.get(cv2.CAP_PROP_FPS)
    if fps <= 0 or fps > 240:
        fps = 20.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or fallback_size[0]
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or fallback_size[1]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Unable to create output video: {path}")
    return writer


def json_dump(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
