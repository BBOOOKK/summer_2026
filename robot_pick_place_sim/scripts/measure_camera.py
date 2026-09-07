#!/usr/bin/env python3
"""Measure delivered camera frames, not encoded/duplicated video frames."""
import argparse
import json
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rclpy.init()
    node = Node('camera_performance_probe')
    samples = []
    dimensions = []

    def receive(msg):
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        samples.append((time.monotonic(), stamp))
        dimensions[:] = [msg.width, msg.height]

    subscription = node.create_subscription(
        Image, '/demo_camera/image', receive, qos_profile_sensor_data)
    start = time.monotonic()
    while time.monotonic() - start < args.seconds:
        rclpy.spin_once(node, timeout_sec=0.2)
    result = {'received_frames': len(samples), 'resolution': dimensions,
              'requested_wall_seconds': args.seconds}
    if len(samples) > 1:
        wall = samples[-1][0] - samples[0][0]
        sim = samples[-1][1] - samples[0][1]
        gaps = sorted(b[0] - a[0] for a, b in zip(samples, samples[1:]))
        result.update(wall_span_seconds=wall, sim_span_seconds=sim,
                      delivered_wall_fps=(len(samples)-1)/wall,
                      delivered_sim_fps=(len(samples)-1)/sim if sim > 0 else None,
                      camera_stamp_real_time_factor=sim/wall,
                      wall_gap_p95_seconds=gaps[min(len(gaps)-1, int(len(gaps)*.95))],
                      duplicate_stamps=sum(a[1] == b[1] for a,b in zip(samples,samples[1:])))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2), flush=True)
    node.destroy_subscription(subscription)
    node.destroy_node()
    rclpy.shutdown()
    if len(samples) < 2:
        raise SystemExit('Insufficient camera frames; not a valid performance measurement')


if __name__ == '__main__':
    main()
