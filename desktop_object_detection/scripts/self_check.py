#!/usr/bin/env python3
"""Run a repository-level completion audit without requiring Jetson or ROS2."""

from __future__ import annotations

import argparse
import csv
import json
import py_compile
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from dataset_utils import report_dict
from runtime_utils import project_root


PUBLIC_SCRIPTS = [
    "prepare_dataset.py",
    "check_dataset.py",
    "train.py",
    "evaluate.py",
    "export_model.py",
    "detect_image.py",
    "detect_video.py",
    "detect_camera.py",
    "benchmark.py",
    "test_20_objects.py",
]

REQUIRED_FILES = [
    "README.md",
    "requirements.txt",
    "configs/dataset.yaml",
    "configs/detector.yaml",
    "configs/test_samples.csv",
    "docs/RUN_GUIDE.md",
    "docs/JETSON_DEPLOYMENT.md",
    "docs/ROS2_GUIDE.md",
    "docs/EXPERIMENT_REPORT_TEMPLATE.md",
    "docs/EXPERIMENT_REPORT.md",
    "models/best.pt",
    "models/best.onnx",
    "outputs/evaluation/evaluation_results.csv",
    "outputs/evaluation/20_object_test_results.csv",
    "outputs/errors/error_cases.csv",
    "outputs/benchmark/benchmark_local_mps.csv",
    "ros2_ws/src/object_detector/package.xml",
    "ros2_ws/src/object_detector/setup.py",
    "ros2_ws/src/object_detector/setup.cfg",
    "ros2_ws/src/object_detector/resource/object_detector",
    "ros2_ws/src/object_detector/object_detector/detector_node.py",
    "ros2_ws/src/object_detector/object_detector/messages.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=project_root() / "outputs/evaluation/project_self_check.json",
    )
    return parser.parse_args()


def add(checks: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "status": "PASS" if passed else "FAIL", "detail": detail})


def main() -> int:
    args = parse_args()
    root = project_root()
    checks: list[dict[str, Any]] = []

    missing = [item for item in REQUIRED_FILES if not (root / item).is_file()]
    add(checks, "required_files", not missing, "all present" if not missing else f"missing: {missing}")

    syntax_errors: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {"build", "install", ".venv"} for part in path.parts):
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            syntax_errors.append(str(exc))
    add(checks, "python_syntax", not syntax_errors, "all Python files compile" if not syntax_errors else "; ".join(syntax_errors))

    help_errors: list[str] = []
    for name in PUBLIC_SCRIPTS:
        completed = subprocess.run(
            [sys.executable, str(root / "scripts" / name), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0:
            help_errors.append(f"{name}: {completed.stderr.strip()}")
    add(checks, "cli_entrypoints", not help_errors, "all --help commands pass" if not help_errors else "; ".join(help_errors))

    dataset = report_dict(root / "configs/dataset.yaml")
    add(
        checks,
        "dataset",
        dataset["status"] == "PASS" and dataset["totals"]["images"] == 500,
        f"status={dataset['status']} totals={dataset['totals']}",
    )

    with (root / "outputs/evaluation/evaluation_results.csv").open("r", encoding="utf-8", newline="") as handle:
        evaluation = next(csv.DictReader(handle))
    add(
        checks,
        "evaluation_metrics",
        evaluation.get("scope") == "overall" and float(evaluation["mAP50"]) > 0,
        f"precision={evaluation['precision']} recall={evaluation['recall']} mAP50={evaluation['mAP50']}",
    )

    with (root / "outputs/evaluation/20_object_test_results.csv").open("r", encoding="utf-8", newline="") as handle:
        test_rows = list(csv.DictReader(handle))
    correct = sum(row["correct"].lower() == "true" for row in test_rows)
    accuracy = correct / len(test_rows) * 100.0 if test_rows else 0.0
    add(checks, "twenty_object_test", len(test_rows) == 20 and accuracy >= 80.0, f"{correct}/20 = {accuracy:.2f}%")

    videos = [path for path in (root / "outputs/videos").glob("*.mp4") if path.stat().st_size > 0]
    add(checks, "result_video", bool(videos), f"{len(videos)} non-empty video(s)")

    error_csv = root / "outputs/errors/error_cases.csv"
    add(checks, "error_cases", error_csv.is_file(), str(error_csv))

    package_xml = root / "ros2_ws/src/object_detector/package.xml"
    try:
        package_name = ET.parse(package_xml).getroot().findtext("name")
        ros_ok = package_name == "object_detector"
    except ET.ParseError:
        ros_ok = False
        package_name = None
    node_text = (root / "ros2_ws/src/object_detector/object_detector/detector_node.py").read_text(encoding="utf-8")
    ros_ok = ros_ok and all(
        token in node_text
        for token in ("/object_detection/result", "/object_detection/image", "source_mode", "camera_id")
    )
    add(checks, "ros2_package_static", ros_ok, f"package={package_name}, required topics/parameters present")

    benchmark_rows = list(csv.DictReader((root / "outputs/benchmark/benchmark_local_mps.csv").open("r", encoding="utf-8")))
    local_fps = float(benchmark_rows[0]["average_fps"]) if benchmark_rows else 0.0
    add(checks, "benchmark_software_flow", local_fps >= 5.0, f"local MPS average_fps={local_fps:.3f}; not Jetson evidence")

    failed = [item for item in checks if item["status"] == "FAIL"]
    report = {
        "status": "PASS_WITH_HARDWARE_PENDING" if not failed else "FAIL",
        "checks": checks,
        "hardware_pending": [
            "Jetson camera and TensorRT benchmark >= 5 FPS",
            "ROS2 colcon build and live topic verification",
            "Jetson result video and screenshots",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Status: {report['status']}")
    for item in checks:
        print(f"[{item['status']}] {item['name']}: {item['detail']}")
    print(f"Report: {args.output.resolve()}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
