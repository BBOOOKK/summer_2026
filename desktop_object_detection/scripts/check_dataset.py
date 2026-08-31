#!/usr/bin/env python3
"""Validate a YOLO detection dataset and write a machine-readable report."""

from __future__ import annotations

import argparse
from pathlib import Path

from dataset_utils import report_dict, save_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="Dataset YAML")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/evaluation/dataset_check_report.json"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = report_dict(args.data)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 2
    save_json(report, args.output)
    print(f"Status: {report['status']}")
    print(f"Classes: {len(report['names'])} - {list(report['names'].values())}")
    for split, stats in report["splits"].items():
        print(
            f"{split}: images={stats['image_count']} labels={stats['label_count']} "
            f"empty={stats['empty_labels']} objects={stats['object_count']}"
        )
    print(f"Class counts: {report['class_counts']}")
    print(f"Report: {args.output.resolve()}")
    if report["errors"]:
        print(f"Errors: {len(report['errors'])}")
        for error in report["errors"][:20]:
            print(f"  - {error}")
        if len(report["errors"]) > 20:
            print(f"  ... {len(report['errors']) - 20} more in report")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

