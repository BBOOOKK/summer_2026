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
2. 安装系统 OpenCV/ROS2：`sudo apt install python3-opencv ros-$ROS_DISTRO-cv-bridge ros-$ROS_DISTRO-sensor-msgs ros-$ROS_DISTRO-rqt-image-view`。
3. 在不覆盖 CUDA PyTorch 的前提下安装 Ultralytics、PyYAML、pandas。

```bash
python3 -m pip install ultralytics PyYAML pandas
```

## 复制仓库与 PyTorch 推理

克隆或复制整个 `summer_2026` 仓库，避免 `configs/test_samples.csv` 所引用的仓库级数据路径失效。进入 `desktop_object_detection` 后确认：

```bash
ls -lh models/experiment1_1000self_4000public_v1/best.pt
python scripts/detect_camera.py --model models/experiment1_1000self_4000public_v1/best.pt --camera 0 --device 0 --half --save-video
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

## 可选 TensorRT 导出

Engine 与 Jetson 的 TensorRT 版本和硬件架构绑定，应在目标设备本地导出：

```bash
python scripts/export_model.py --model models/experiment1_1000self_4000public_v1/best.pt --format engine --imgsz 640 --device 0 --half
mv models/experiment1_1000self_4000public_v1/best.engine models/experiment1_1000self_4000public_v1/best_fp16.engine 2>/dev/null || true
python scripts/detect_camera.py --model models/experiment1_1000self_4000public_v1/best_fp16.engine --camera 0 --device 0 --save-video
```

若导出文件生成在权重旁边但名称不同，以命令实际输出路径为准。

## FPS 验收

```bash
sudo nvpmodel -m 0
python scripts/benchmark.py \
  --model models/experiment1_1000self_4000public_v1/best.pt \
  --source 0 --device 0 --half --imgsz 640 \
  --conf 0.5 --iou 0.45 \
  --warmup-frames 20 --test-frames 200 \
  --requirement-fps 5 \
  --output outputs/benchmark/jetson_orin_nx_camera.csv
```

本次验收使用 `MAXN_SUPER`、动态调频且未启用 `jetson_clocks`，PyTorch FP16 平均预测调用速率为 38.534 FPS。若启用固定频率或改用 TensorRT，应另存结果，不能与该次测量混写。测试时记录 Jetson 型号、功耗模式、推理后端及摄像头格式，并保持场景一致。

## FPS 低于 5 的优化顺序

1. 使用 YOLO11n；若兼容性问题明显则用 YOLOv8n。
2. 确认实际使用 CUDA，而不是 CPU。
3. 对 `.pt` 使用 FP16。
4. 在 Jetson 本机导出并使用 TensorRT FP16 Engine。
5. 依次将 `imgsz` 从 640 调至 512、416，每步都重新测试正确率。
6. 运行 `detect_camera.py` 时可使用 `--no-show` 降低显示开销；`benchmark.py` 本身不显示窗口。
7. 通过摄像头驱动或 `v4l2-ctl` 调整输入分辨率；当前检测 CLI 没有 `--width` 或 `--height` 参数。

不要只为速度盲目降低分辨率；每次优化后重新运行 20 样本测试，确保正确率仍 ≥ 80%。

## ROS2

按 `docs/ROS2_GUIDE.md` 编译。Jetson 若存在多个 Python 环境，确保 `colcon`、`rclpy`、Ultralytics 和 CUDA PyTorch 位于同一个可见环境。
