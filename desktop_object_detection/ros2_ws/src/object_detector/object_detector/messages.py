"""JSON message builders for ROS2 object-detection results."""

from __future__ import annotations

import json
from typing import Any


def result_to_message(result: Any, timestamp: float, frame_id: int, fps: float) -> str:
    detections: list[dict[str, Any]] = []
    if result.boxes is not None:
        for box in result.boxes:
            class_id = int(box.cls.item())
            confidence = float(box.conf.item())
            x1, y1, x2, y2 = (float(value) for value in box.xyxy[0].tolist())
            detections.append(
                {
                    "class_id": class_id,
                    "class_name": str(result.names[class_id]),
                    "confidence": confidence,
                    "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                }
            )
    return json.dumps(
        {
            "timestamp": timestamp,
            "frame_id": frame_id,
            "fps": fps,
            "detections": detections,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )

