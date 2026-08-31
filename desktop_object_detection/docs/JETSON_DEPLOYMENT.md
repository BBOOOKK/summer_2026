# Jetson 部署指南

## 环境检查

```bash
cat /etc/nv_tegra_release
nvcc --version
nvidia-smi 2>/dev/null || tegrastats
python3 --version
python3 -c "import torch; print(torch.__version__, torch.cuda.is_available())"
python3 -c "import cv2; print(cv2.__version__)"
echo $ROS_DISTRO
```

1. 安装与 JetPack 对应的 NVIDIA PyTorch wheel。
2. 安装系统 OpenCV/ROS2：`sudo apt install python3-opencv ros-$ROS_DISTRO-cv-bridge ros-$ROS_DISTRO-sensor-msgs`。
3. 在不覆盖 CUDA PyTorch 的前提下安装 Ultralytics、PyYAML、pandas。

```bash
python3 -m pip install ultralytics PyYAML pandas
```

## 复制模型与 PyTorch 推理

把整个 `desktop_object_detection` 目录复制到 Jetson，确认：

```bash
ls -lh models/best.pt
python scripts/detect_camera.py --model models/best.pt --camera 0 --device 0 --half --save-video
```

摄像头检查：

```bash
v4l2-ctl --list-devices
python3 - <<'PY'
import cv2
cap = cv2.VideoCapture(0)
print("opened:", cap.isOpened())
cap.release()
PY
```

## TensorRT

Engine 与 Jetson 的 TensorRT 版本和硬件架构绑定，应在目标设备本地导出：

```bash
python scripts/export_model.py --model models/best.pt --format engine --imgsz 640 --device 0 --half
mv models/best.engine models/best_fp16.engine 2>/dev/null || true
python scripts/detect_camera.py --model models/best_fp16.engine --camera 0 --device 0 --save-video
```

若导出文件生成在权重旁边但名称不同，以命令实际输出路径为准。

## FPS 验收

```bash
sudo nvpmodel -m 0
sudo jetson_clocks
python scripts/benchmark.py --model models/best_fp16.engine --source 0 --device 0 --imgsz 640 --warmup-frames 20 --test-frames 200
```

记录 Jetson 型号、电源模式、推理后端和温度。测试时保持同一摄像头分辨率与场景。

## FPS 低于 5 的优化顺序

1. 使用 YOLO11n；若兼容性问题明显则用 YOLOv8n。
2. 确认实际使用 CUDA，而不是 CPU。
3. 对 `.pt` 使用 FP16。
4. 在 Jetson 本机导出并使用 TensorRT FP16 Engine。
5. 依次将 `imgsz` 从 640 调至 512、416，每步都重新测试正确率。
6. 使用 `--no-show` 降低显示开销。
7. 将摄像头输入分辨率降到 1280×720 或 640×480。

不要只为速度盲目降低分辨率；每次优化后重新运行 20 样本测试，确保正确率仍 ≥ 80%。

## ROS2

按 `docs/ROS2_GUIDE.md` 编译。Jetson 若存在多个 Python 环境，确保 `colcon`、`rclpy`、Ultralytics 和 CUDA PyTorch 位于同一个可见环境。

