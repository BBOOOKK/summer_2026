"""ROS2 YOLO detector node supporting USB camera and Image-topic input."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .messages import result_to_message

try:
    from cv_bridge import CvBridge
except ImportError:  # handled with a clear error if topic mode/image publishing is used
    CvBridge = None  # type: ignore[assignment,misc]


class ObjectDetectorNode(Node):
    def __init__(self) -> None:
        super().__init__("object_detector")
        self.declare_parameter("model_path", "models/best.pt")
        self.declare_parameter("source_mode", "camera")
        self.declare_parameter("camera_id", 0)
        self.declare_parameter("input_topic", "/camera/image_raw")
        self.declare_parameter("confidence_threshold", 0.5)
        self.declare_parameter("iou_threshold", 0.45)
        self.declare_parameter("imgsz", 640)
        self.declare_parameter("device", "auto")
        self.declare_parameter("half", True)
        self.declare_parameter("publish_image", True)
        self.declare_parameter("save_video", False)
        self.declare_parameter("output_dir", "outputs/videos")

        self.model_path = Path(str(self.get_parameter("model_path").value)).expanduser().resolve()
        self.source_mode = str(self.get_parameter("source_mode").value).lower()
        self.camera_id = int(self.get_parameter("camera_id").value)
        self.input_topic = str(self.get_parameter("input_topic").value)
        self.confidence = float(self.get_parameter("confidence_threshold").value)
        self.iou = float(self.get_parameter("iou_threshold").value)
        self.imgsz = int(self.get_parameter("imgsz").value)
        self.device = self._choose_device(str(self.get_parameter("device").value))
        self.half = bool(self.get_parameter("half").value) and self.device != "cpu"
        self.publish_image = bool(self.get_parameter("publish_image").value)
        self.save_video = bool(self.get_parameter("save_video").value)
        self.output_dir = Path(str(self.get_parameter("output_dir").value)).expanduser().resolve()

        if not self.model_path.is_file():
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("ultralytics is not installed in the ROS2 Python environment") from exc
        if (self.publish_image or self.source_mode == "topic") and CvBridge is None:
            raise RuntimeError("cv_bridge is required for topic mode or publish_image=true")

        self.model = YOLO(str(self.model_path))
        self.bridge = CvBridge() if CvBridge is not None else None
        self.result_publisher = self.create_publisher(String, "/object_detection/result", 10)
        self.image_publisher = self.create_publisher(Image, "/object_detection/image", 2)
        self.capture: cv2.VideoCapture | None = None
        self.video_writer: cv2.VideoWriter | None = None
        self.frame_id = 0
        self.fps = 0.0

        if self.source_mode == "camera":
            self.capture = cv2.VideoCapture(self.camera_id)
            if not self.capture.isOpened():
                raise RuntimeError(f"Unable to open camera {self.camera_id}")
            self.create_timer(0.001, self._camera_tick)
            self.get_logger().info(f"Camera opened: {self.camera_id}")
        elif self.source_mode == "topic":
            self.create_subscription(Image, self.input_topic, self._image_callback, 2)
            self.get_logger().info(f"Subscribed: {self.input_topic}")
        else:
            raise ValueError("source_mode must be 'camera' or 'topic'")

        self.get_logger().info(f"Model loaded: {self.model_path}")
        self.get_logger().info(f"Device: {self.device}")
        self.get_logger().info(f"Image size: {self.imgsz}")
        self.get_logger().info(f"Confidence threshold: {self.confidence}")
        self.get_logger().info("ROS2 publishers initialized")

    @staticmethod
    def _choose_device(requested: str) -> str | int:
        if requested.lower() not in {"", "auto"}:
            return int(requested) if requested.isdigit() else requested
        try:
            import torch

            if torch.cuda.is_available():
                return 0
        except ImportError:
            pass
        return "cpu"

    def _camera_tick(self) -> None:
        if self.capture is None:
            return
        ok, frame = self.capture.read()
        if ok:
            self._process_frame(frame)

    def _image_callback(self, message: Image) -> None:
        if self.bridge is None:
            return
        try:
            frame = self.bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
        except Exception as exc:  # cv_bridge exposes different exception types by ROS version
            self.get_logger().error(f"Image conversion failed: {exc}")
            return
        self._process_frame(frame)

    def _process_frame(self, frame: Any) -> None:
        started = time.perf_counter()
        result = self.model.predict(
            frame,
            imgsz=self.imgsz,
            conf=self.confidence,
            iou=self.iou,
            device=self.device,
            verbose=False,
            **({"half": True} if self.half else {}),
        )[0]
        elapsed = max(time.perf_counter() - started, 1e-9)
        instantaneous = 1.0 / elapsed
        self.fps = instantaneous if self.frame_id == 0 else 0.9 * self.fps + 0.1 * instantaneous
        timestamp = self.get_clock().now().nanoseconds / 1e9

        result_message = String()
        result_message.data = result_to_message(result, timestamp, self.frame_id, self.fps)
        self.result_publisher.publish(result_message)

        annotated = result.plot()
        cv2.rectangle(annotated, (8, 8), (175, 42), (0, 0, 0), -1)
        cv2.putText(annotated, f"FPS: {self.fps:.1f}", (16, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        if self.publish_image and self.bridge is not None:
            image_message = self.bridge.cv2_to_imgmsg(annotated, encoding="bgr8")
            image_message.header.stamp = self.get_clock().now().to_msg()
            image_message.header.frame_id = "object_detector"
            self.image_publisher.publish(image_message)
        if self.save_video:
            self._write_video(annotated)

        self.frame_id += 1
        if self.frame_id % 100 == 0:
            self.get_logger().info(f"Average FPS: {self.fps:.1f}")

    def _write_video(self, frame: Any) -> None:
        if self.video_writer is None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"ros2_detection_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
            height, width = frame.shape[:2]
            self.video_writer = cv2.VideoWriter(
                str(path), cv2.VideoWriter_fourcc(*"mp4v"), 20.0, (width, height)
            )
            if not self.video_writer.isOpened():
                raise RuntimeError(f"Unable to create output video: {path}")
            self.get_logger().info(f"Saving video: {path}")
        self.video_writer.write(frame)

    def destroy_node(self) -> bool:
        if self.capture is not None:
            self.capture.release()
        if self.video_writer is not None:
            self.video_writer.release()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node: ObjectDetectorNode | None = None
    try:
        node = ObjectDetectorNode()
        rclpy.spin(node)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        if node is not None:
            node.get_logger().fatal(str(exc))
        else:
            print(f"[FATAL] {exc}")
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
