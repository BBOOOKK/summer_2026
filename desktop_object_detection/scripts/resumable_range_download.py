#!/usr/bin/env python3
"""Download a large HTTP object with parallel byte ranges and prefix resume."""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--chunk-mib", type=int, default=128)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    response = requests.head(args.url, timeout=30)
    response.raise_for_status()
    total = int(response.headers["Content-Length"])
    state_path = args.output.with_suffix(args.output.suffix + ".ranges.json")
    saved_state = json.loads(state_path.read_text()) if state_path.is_file() else None
    existing = int(saved_state["prefix_bytes"]) if saved_state else (args.output.stat().st_size if args.output.exists() else 0)
    if existing > total:
        raise ValueError(f"existing file is larger than remote object: {existing} > {total}")
    if existing == total and saved_state is None:
        print(f"[DONE] already complete: {args.output} ({total:,} bytes)")
        return 0
    file_descriptor = os.open(args.output, os.O_RDWR | os.O_CREAT)
    os.ftruncate(file_descriptor, total)
    chunk_size = args.chunk_mib * 1024 * 1024
    ranges = []
    start = existing
    while start < total:
        end = min(total - 1, start + chunk_size - 1)
        ranges.append((start, end))
        start = end + 1
    completed_ranges = {tuple(item) for item in (saved_state or {}).get("completed_ranges", [])}
    ranges = [item for item in ranges if item not in completed_ranges]
    state = {
        "url": args.url,
        "total_bytes": total,
        "prefix_bytes": existing,
        "completed_ranges": [list(item) for item in sorted(completed_ranges)],
    }

    def save_state() -> None:
        temp = state_path.with_suffix(state_path.suffix + ".part")
        temp.write_text(json.dumps(state, indent=2) + "\n")
        temp.replace(state_path)

    save_state()
    completed = 0
    completed_lock = threading.Lock()
    started = time.monotonic()

    def download(byte_range: tuple[int, int]) -> int:
        start, end = byte_range
        expected = end - start + 1
        for attempt in range(6):
            position = start
            try:
                with requests.get(
                    args.url,
                    headers={"Range": f"bytes={start}-{end}"},
                    stream=True,
                    timeout=(30, 180),
                ) as result:
                    if result.status_code != 206:
                        raise RuntimeError(f"server ignored range: HTTP {result.status_code}")
                    for data in result.iter_content(chunk_size=1024 * 1024):
                        if data:
                            os.pwrite(file_descriptor, data, position)
                            position += len(data)
                if position - start != expected:
                    raise IOError(f"short range {start}-{end}: {position - start}/{expected}")
                return expected
            except Exception:
                if attempt == 5:
                    raise
                time.sleep(min(2 ** attempt, 10))
        raise AssertionError("unreachable")

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(download, item): item for item in ranges}
            for future in as_completed(futures):
                size = future.result()
                with completed_lock:
                    completed += size
                    completed_ranges.add(futures[future])
                    state["completed_ranges"] = [list(item) for item in sorted(completed_ranges)]
                    save_state()
                    elapsed = max(time.monotonic() - started, 0.001)
                    done = existing + completed
                    rate = completed / elapsed / (1024 * 1024)
                    print(f"[DOWNLOAD] {done / total:6.1%} {done:,}/{total:,} bytes, {rate:.1f} MiB/s", flush=True)
    finally:
        os.close(file_descriptor)
    state_path.unlink(missing_ok=True)
    print(f"[DONE] {args.output} ({total:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
