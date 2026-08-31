# 完整运行指南

以下命令均从 `desktop_object_detection` 目录执行，除非章节另有说明。

## 1. Python 环境

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Jetson 上先按 JetPack 版本安装 NVIDIA 提供的 PyTorch，再安装 requirements；不要让 pip 覆盖 Jetson CUDA 版 PyTorch。

## 2. 数据集配置与划分

当前验收数据集为 `datasets/experiment1_1000self_4000public_v1/`。它包含 1,000 张自主采集来源素材（10 张独立实拍 + 990 张可追溯增强）和 4,000 张 Open Images V7 图片。重新构建命令：

```bash
python scripts/build_target_dataset.py
```

构建脚本默认拒绝覆盖已存在的数据集。检查当前数据与来源口径：

```bash
python scripts/check_dataset.py --data datasets/experiment1_1000self_4000public_v1/dataset.yaml
python scripts/audit_expanded_dataset.py --dataset datasets/experiment1_1000self_4000public_v1 --provenance-only
```

## 3. 数据集检查

```bash
python scripts/check_dataset.py --data datasets/experiment1_1000self_4000public_v1/dataset.yaml
```

报告：`outputs/evaluation/dataset_check_report.json`。退出码 0 为 PASS。

## 4. 模型训练

```bash
python scripts/train.py \
  --data datasets/experiment1_1000self_4000public_v1/dataset.yaml \
  --model models/expanded_v1/best.pt \
  --epochs 12 \
  --batch 32 \
  --imgsz 640 \
  --device 0 \
  --workers 4 \
  --project outputs/training \
  --name experiment1_1000self_4000public_v1 \
  --models-dir models/experiment1_1000self_4000public_v1
```

CPU 可用 `--device cpu`；Apple Silicon 可尝试 `--device mps`。训练完成后权重位于 `models/experiment1_1000self_4000public_v1/`。

## 5. 模型评估

```bash
python scripts/evaluate.py --data datasets/experiment1_1000self_4000public_v1/dataset.yaml --model models/experiment1_1000self_4000public_v1/best.pt --split test --device 0
```

本次验收结果位于 `outputs/evaluation/experiment1_1000self_4000public_v1_test/`，含整体与每类别 Precision、Recall、mAP50、mAP50-95。

## 6. 图片测试

```bash
python scripts/detect_image.py --model models/experiment1_1000self_4000public_v1/best.pt --source /path/to/image.jpg --device 0 --half
```

## 7. 视频测试

```bash
python scripts/detect_video.py --model models/experiment1_1000self_4000public_v1/best.pt --source /path/to/input.mp4 --device 0 --half --save-video
```

无桌面显示时加 `--no-show`。

## 8. USB 摄像头测试

```bash
python scripts/detect_camera.py --model models/experiment1_1000self_4000public_v1/best.pt --camera 0 --device 0 --half --save-video
```

按 `s` 保存截图，按 `q` 或 ESC 退出。参数也可集中修改 `configs/detector.yaml`。

## 9. 模型导出

ONNX 可在训练机导出：

```bash
python -m pip install "onnx>=1.12,<2" onnxruntime "onnxslim>=0.1.82"
python scripts/export_model.py --model models/experiment1_1000self_4000public_v1/best.pt --format onnx --imgsz 640 --simplify
```

TensorRT Engine 必须在目标 Jetson 上导出，以匹配其 TensorRT/CUDA/架构：

```bash
python scripts/export_model.py --model models/experiment1_1000self_4000public_v1/best.pt --format engine --imgsz 640 --device 0 --half --workspace 4
```

## 10. FPS 测试

```bash
python scripts/benchmark.py \
  --model models/experiment1_1000self_4000public_v1/best.engine \
  --source 0 \
  --imgsz 640 \
  --device 0 \
  --warmup-frames 20 \
  --test-frames 200
```

平均端到端 FPS ≥ 5 才输出 PASS。也可用视频文件替代摄像头，使不同模型对比可复现。

## 11. 20 个物体测试

先人工检查并按实际独立样本修改 `configs/test_samples.csv`。字段固定为 `sample_id,image_path,ground_truth_class`，必须正好 20 行。

```bash
python scripts/test_20_objects.py --model models/experiment1_1000self_4000public_v1/best.pt --samples configs/test_samples.csv --device 0 --half
```

多目标 GT 用 `mouse|cup` 表示；程序要求所有列出的 GT 类别均被检测到。正确率 ≥ 80% 才 PASS，错误图与 CSV 自动保存。

## 12. ROS2 编译和节点运行

```bash
cd ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
colcon build --symlink-install
source install/setup.bash
ros2 run object_detector detector_node \
  --ros-args \
  -p model_path:=$(pwd)/../models/experiment1_1000self_4000public_v1/best.engine \
  -p source_mode:=camera \
  -p camera_id:=0 \
  -p device:=0 \
  -p half:=true
```

另开终端：

```bash
cd ros2_ws
source /opt/ros/$ROS_DISTRO/setup.bash
source install/setup.bash
ros2 topic echo /object_detection/result
ros2 topic hz /object_detection/result
```

图像输入模式：

```bash
ros2 run object_detector detector_node --ros-args \
  -p model_path:=$(pwd)/../models/experiment1_1000self_4000public_v1/best.pt \
  -p source_mode:=topic \
  -p input_topic:=/camera/image_raw
```
