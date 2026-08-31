#!/usr/bin/env python3
"""Train an Ultralytics YOLO detector and copy best/last weights to models/."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from runtime_utils import choose_device, project_root


def parse_args() -> argparse.Namespace:
    root = project_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=root / "configs/dataset.yaml")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--project", type=Path, default=root / "outputs/training")
    parser.add_argument("--name", default="yolo11n_p05")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=root / "models",
        help="Where best.pt and last.pt are copied after training",
    )
    parser.add_argument("--patience", type=int, default=25)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def copy_weights(save_dir: Path, destination: Path) -> None:
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("best.pt", "last.pt"):
        source = save_dir / "weights" / name
        if source.is_file():
            shutil.copy2(source, destination / name)
            print(f"[INFO] Saved: {destination / name}")


def main() -> int:
    args = parse_args()
    try:
        from ultralytics import YOLO
    except ImportError:
        print("[ERROR] ultralytics is not installed. Run: pip install -r requirements.txt")
        return 2
    data = args.data.expanduser().resolve()
    if not data.is_file():
        print(f"[ERROR] Dataset YAML not found: {data}")
        return 2
    device = choose_device(args.device)
    print(f"[INFO] Model: {args.model}")
    print(f"[INFO] Dataset: {data}")
    print(f"[INFO] Device: {device}")
    model = YOLO(args.model)
    try:
        results = model.train(
            data=str(data),
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            device=device,
            workers=args.workers,
            project=str(args.project.resolve()),
            name=args.name,
            patience=args.patience,
            plots=True,
            resume=args.resume,
            degrees=5.0,
            translate=0.10,
            scale=0.30,
            fliplr=0.5,
            mosaic=0.5,
            mixup=0.0,
            close_mosaic=10,
            verbose=True,
        )
    except KeyboardInterrupt:
        candidates = sorted(
            args.project.resolve().glob(f"{args.name}*"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            copy_weights(candidates[0], args.models_dir)
            print(f"[INFO] Training interrupted; retained weights from {candidates[0]}")
        return 130
    save_dir = Path(results.save_dir)
    copy_weights(save_dir, args.models_dir)
    print(f"[INFO] Training artifacts: {save_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
