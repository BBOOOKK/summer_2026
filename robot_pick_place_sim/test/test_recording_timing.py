"""Exercise real recorder callback with irregular arrivals, without a simulator."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_sparse_camera_does_not_speed_up_playback(monkeypatch, tmp_path):
    pytest.importorskip('rclpy')
    path = Path(__file__).parents[1] / 'scripts' / 'record_fortress_demo.py'
    spec = importlib.util.spec_from_file_location('demo_recorder_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.rclpy.init()
    recorder = module.DemoRecorder(tmp_path / 'test.mp4', 10, 180)
    try:
        recorder.started = True
        frame = Mock(shape=(720, 1280, 3))
        recorder.bridge = Mock()
        recorder.bridge.imgmsg_to_cv2.return_value = frame
        recorder.decorate = lambda image: image
        writer = Mock()
        monkeypatch.setattr(module.cv2, 'VideoWriter', lambda *args: writer)
        for wall, sec in [(100., 1), (100.5, 2), (101., 3)]:
            monkeypatch.setattr(module.time, 'monotonic', lambda: wall)
            recorder.on_image(SimpleNamespace(header=SimpleNamespace(
                stamp=SimpleNamespace(sec=sec, nanosec=0))))
        # One second of wall-time coverage plus the final frame, not three
        # frames compressed to 0.3 seconds, nor undocumented title holds.
        assert recorder.frame_count == 11
        assert recorder.received_frames == 3
        assert recorder.repeated_frames == 8
    finally:
        recorder.destroy_node()
        module.rclpy.shutdown()
