#!/usr/bin/env python3
"""Record the real Gazebo presentation camera with task-state overlays."""

import argparse
import json
from pathlib import Path
import time

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String


STAGES = [
    'OPEN_GRIPPER', 'HOME', 'ABOVE_PICK', 'DESCEND_PICK', 'GRASP',
    'ATTACH_OBJECT', 'GRASP_CONFIRMED', 'LIFT_OBJECT', 'ABOVE_PLACE',
    'DESCEND_PLACE', 'DETACH_OBJECT', 'RELEASE', 'RETREAT',
    'RETURN_HOME', 'SUCCEEDED',
]

DISPLAY = {
    'OPEN_GRIPPER': 'Open gripper',
    'HOME': 'Return to home',
    'ABOVE_PICK': 'Move above pickup A',
    'DESCEND_PICK': 'Descend to target',
    'GRASP': 'Close gripper',
    'ATTACH_OBJECT': 'Verify physical contact',
    'GRASP_CONFIRMED': 'Grasp confirmed',
    'LIFT_OBJECT': 'Lift to safe height',
    'ABOVE_PLACE': 'Transfer above placement B',
    'DESCEND_PLACE': 'Descend to placement B',
    'DETACH_OBJECT': 'Release physical joint',
    'RELEASE': 'Open gripper',
    'RETREAT': 'Retreat to safe height',
    'RETURN_HOME': 'Return to home',
    'SUCCEEDED': 'Task completed safely',
    'SAFE_STOP': 'SAFE STOP',
}


class DemoRecorder(Node):
    def __init__(self, output, fps, timeout):
        super().__init__('fortress_demo_recorder')
        self.output = output
        self.fps = fps
        self.timeout = timeout
        self.bridge = CvBridge()
        self.state = 'WAITING'
        self.detail = 'Waiting for task start'
        self.started = False
        self.finished_at = None
        self.started_at = time.monotonic()
        self.writer = None
        self.first_frame = None
        self.last_frame = None
        self.frame_count = 0
        self.create_subscription(String, '/pick_place/state', self.on_state, 20)
        self.create_subscription(
            Image, '/demo_camera/image', self.on_image, qos_profile_sensor_data)
        self.create_timer(0.2, self.check_done)

    def on_state(self, message):
        try:
            payload = json.loads(message.data)
        except (json.JSONDecodeError, AttributeError):
            return
        self.state = str(payload.get('state', 'UNKNOWN'))
        self.detail = str(payload.get('detail', ''))
        if self.state in STAGES or self.state == 'SAFE_STOP':
            self.started = True
        if self.state in ('SUCCEEDED', 'SAFE_STOP') and self.finished_at is None:
            self.finished_at = time.monotonic()

    def on_image(self, message):
        if not self.started:
            return
        frame = self.bridge.imgmsg_to_cv2(message, 'bgr8')
        frame = self.decorate(frame)
        if self.writer is None:
            height, width = frame.shape[:2]
            self.output.parent.mkdir(parents=True, exist_ok=True)
            self.writer = cv2.VideoWriter(
                str(self.output), cv2.VideoWriter_fourcc(*'mp4v'),
                self.fps, (width, height))
            if not self.writer.isOpened():
                raise RuntimeError(f'cannot open video writer: {self.output}')
            self.first_frame = frame.copy()
            for _ in range(round(self.fps * 1.2)):
                self.writer.write(frame)
                self.frame_count += 1
        self.writer.write(frame)
        self.last_frame = frame.copy()
        self.frame_count += 1

    def decorate(self, frame):
        height, width = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (24, 22), (width - 24, 116), (14, 20, 30), -1)
        cv2.addWeighted(overlay, 0.78, frame, 0.22, 0, frame)
        cv2.putText(
            frame, 'mechArm 270  |  Gazebo Fortress + MoveIt 2',
            (48, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.82, (245, 248, 252), 2,
            cv2.LINE_AA)
        label = DISPLAY.get(self.state, self.state.replace('_', ' ').title())
        color = (91, 220, 140) if self.state == 'SUCCEEDED' else (76, 190, 255)
        if self.state == 'SAFE_STOP':
            color = (64, 80, 255)
        cv2.putText(
            frame, label, (48, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.72,
            color, 2, cv2.LINE_AA)

        cv2.putText(frame, 'A  PICK', (525, 558), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (82, 235, 128), 2, cv2.LINE_AA)
        cv2.putText(frame, 'B  PLACE', (330, 402), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 170, 72), 2, cv2.LINE_AA)

        bar_left, bar_right, bar_y = 48, width - 48, height - 38
        cv2.line(frame, (bar_left, bar_y), (bar_right, bar_y),
                 (74, 84, 99), 8, cv2.LINE_AA)
        try:
            stage_index = STAGES.index(self.state)
        except ValueError:
            stage_index = 0
        progress = stage_index / (len(STAGES) - 1)
        cv2.line(frame, (bar_left, bar_y),
                 (int(bar_left + (bar_right - bar_left) * progress), bar_y),
                 color, 8, cv2.LINE_AA)
        cv2.putText(
            frame, 'contact-gated grasp  |  collision monitor active',
            (48, height - 58), cv2.FONT_HERSHEY_SIMPLEX, 0.50,
            (238, 242, 247), 1, cv2.LINE_AA)
        return frame

    def check_done(self):
        now = time.monotonic()
        if now - self.started_at > self.timeout:
            self.stop('recording timeout')
        elif self.finished_at is not None and now - self.finished_at > 2.0:
            self.stop(self.state)

    def stop(self, reason):
        if self.writer is not None:
            if self.last_frame is not None:
                for _ in range(round(self.fps * 1.8)):
                    self.writer.write(self.last_frame)
                    self.frame_count += 1
            self.writer.release()
            self.writer = None
        print(json.dumps({
            'output': str(self.output), 'frames': self.frame_count,
            'fps': self.fps, 'terminal_state': reason,
        }), flush=True)
        rclpy.shutdown()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fps', type=float, default=10.0)
    parser.add_argument('--timeout', type=float, default=180.0)
    args = parser.parse_args()
    rclpy.init()
    node = DemoRecorder(args.output, args.fps, args.timeout)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.stop('interrupted')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
