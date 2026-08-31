#!/usr/bin/env python3
"""Evaluate a YOLO model and export overall and per-class metrics."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from runtime_utils import choose_device, json_dump, project_root


def parse_args() -> argparse.Namespace:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=root / "configs/dataset.yaml")
    parser.add_argument("--model", type=Path, default=root / "models/best.pt")
    parser.add_argument("--split", choices=["val", "test"], default="test")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--output", type=Path, default=root / "outputs/evaluation")
    return parser.parse_args()


def value_at(values: object, index: int) -> float:
    try:
        return float(values[index])  # type: ignore[index]
    except (IndexError, TypeError):
        return float("nan")


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
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(args.model.resolve()))
    metrics = model.val(
        data=str(args.data.resolve()),
        split=args.split,
        imgsz=args.imgsz,
        batch=args.batch,
        device=choose_device(args.device),
        project=str(output / "runs"),
        name=f"{args.model.stem}_{args.split}",
        plots=True,
    )
    rows: list[dict[str, object]] = []
    box = metrics.box
    rows.append({
        "scope": "overall",
        "class_id": "all",
        "class_name": "all",
        "precision": float(box.mp),
        "recall": float(box.mr),
        "mAP50": float(box.map50),
        "mAP50-95": float(box.map),
    })
    names = metrics.names
    class_ids = list(getattr(box, "ap_class_index", range(len(names))))
    for index, class_id_raw in enumerate(class_ids):
        class_id = int(class_id_raw)
        rows.append({
            "scope": "class",
            "class_id": class_id,
            "class_name": names[class_id],
            "precision": value_at(box.p, index),
            "recall": value_at(box.r, index),
            "mAP50": value_at(box.ap50, index),
            "mAP50-95": value_at(box.maps, class_id),
        })
    csv_path = output / "evaluation_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    json_dump({"model": str(args.model), "split": args.split, "metrics": rows}, output / "evaluation_results.json")
    print(f"Precision: {box.mp:.4f}")
    print(f"Recall: {box.mr:.4f}")
    print(f"mAP@0.5: {box.map50:.4f}")
    print(f"mAP@0.5:0.95: {box.map:.4f}")
    print(f"Results: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

