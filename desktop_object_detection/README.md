# 桌面物体目标检测与 ROS2 实时识别系统

实验目标：使用 YOLO 完成不少于两类桌面物体的实时识别，并部署到 Jetson，通过 ROS2 发布识别结果。

本工程使用 5 类目标：`mouse`、`keyboard`、`laptop`、`cup`、`headphones`。

## 当前验收版数据集（1,000 + 4,000）

当前数据位于 `datasets/experiment1_1000self_4000public_v1/`，总计恰好 5,000 张：

- 自主采集来源素材 1,000 张：10 张原始实拍照片，每张生成 1 个等尺寸版本和 99 个确定性增强版本。增强包括小角度旋转、缩放、平移、翻转、亮度/对比度、轻微模糊和噪声，框同步变换。
- 公开数据 4,000 张：来自 Open Images V7，保留官方 train/validation/test 边界及逐图来源 ID。
- 划分：train 4,000、val 350、test 650。10 个实拍母图按 8/1/1 分组，任何母图及其增强版本只进入一个集合，避免跨集合泄漏。
- 自主采集母图只覆盖 `mouse`、`keyboard`、`laptop`；`cup` 和 `headphones` 样本来自公开数据。
- 逐图追溯：`manifest.csv`；实拍母图 SHA256 和增强参数：`self_collected_provenance.json`；独立检查：`qa/dataset_check_report.json` 和 `qa/expanded_quality_report.json`。

口径说明：这里的 1,000 张是经数据集所有者确认的“实拍来源素材”，其中 10 张为独立拍摄、990 张为实拍照片衍生增强。它们不能表述为 1,000 次独立拍摄；课程验收时应保留这一区分。

## 历史扩充版数据集

`datasets/p05_expanded_v1/` 是旧版 500 张 P05 混合基线加 4,500 张公开图的历史快照。其基线包含生成图，因此不作为当前 1,000 + 4,000 口径的数据集。

- 划分：train 3,947、val 376、test 677。
- 目标框：mouse 965、keyboard 1,720、laptop 2,238、cup 1,739、headphones 1,151。
- 空标签仅保留原 P05 中人工复核的 50 张；公开图中“没有目标框”的图片不作为负样本，以免把漏标目标当背景训练。
- 自动质量报告：`datasets/p05_expanded_v1/dataset_check_report.json` 和 `datasets/p05_expanded_v1/qa/expanded_quality_report.json`。
- 鼠标抽样标框联系表：`datasets/p05_expanded_v1/qa/mouse_contact_sheet.jpg`。

双击 `训练扩充模型.command` 可从当前 `models/best.pt` 开始微调；新权重写入 `models/expanded_v1/`，不会覆盖当前摄像头模型。公开框已经完成格式、完整性、重复和抽样可视检查，但尚未逐张人工复标，正式 ground-truth 声明前仍需全量人工复核。

当前旧模型在扩充版独立 test 上的微调前基线为：Precision 0.5309、Recall 0.3840、mAP50 0.3851、mAP50-95 0.1971；其中 mouse mAP50 0.464、Recall 0.547。结果保存在 `outputs/evaluation/expanded_v1_baseline_final/`，用于与微调后的模型作同集对比。

## 验收总表

| 验收项 | 要求 | 验证工具 | 当前状态 |
| --- | ---: | --- | --- |
| A. 同时识别类别 | ≥ 2 类 | 图片/视频/摄像头检测 | PASS：独立 MIX 图同时检出 5 类 |
| B. 20 目标正确率 | ≥ 80% | `test_20_objects.py` | PASS：18/20，90.00% |
| C. Jetson 实时速度 | 平均 ≥ 5 FPS | `benchmark.py` | 本机 MPS 58.31 FPS；Jetson 待实测 |
| D. ROS2 结果发布 | 实时 JSON + 图像 | `detector_node` | 静态自检 PASS；ROS2/Jetson 实机待运行 |

## 最简运行流程

```bash
cd desktop_object_detection
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/prepare_dataset.py
python scripts/check_dataset.py --data configs/dataset.yaml
python scripts/train.py --data configs/dataset.yaml --model yolo11n.pt --epochs 100 --batch 16 --imgsz 640 --device 0
python scripts/detect_camera.py --model models/best.pt --camera 0 --device 0 --half --save-video
python scripts/benchmark.py --model models/best.pt --source 0 --device 0 --half

cd ros2_ws
colcon build --symlink-install
source install/setup.bash
ros2 run object_detector detector_node --ros-args -p model_path:=$(pwd)/../models/best.pt -p camera_id:=0
```

Jetson 的 PyTorch 必须按 JetPack 版本单独安装，不能直接依赖通用 pip wheel。完整步骤见 [运行指南](docs/RUN_GUIDE.md)、[Jetson 部署](docs/JETSON_DEPLOYMENT.md)和 [ROS2 指南](docs/ROS2_GUIDE.md)。

## 工程结构

```text
desktop_object_detection/
├── README.md
├── requirements.txt
├── configs/
│   ├── dataset.yaml
│   ├── detector.yaml
│   └── test_samples.csv
├── dataset_view/                  # 软链接，不复制原图
│   ├── images/{train,val,test}/
│   └── labels/{train,val,test}/
├── splits/split_manifest.csv
├── scripts/
│   ├── prepare_dataset.py
│   ├── check_dataset.py
│   ├── train.py
│   ├── evaluate.py
│   ├── export_model.py
│   ├── detect_image.py
│   ├── detect_video.py
│   ├── detect_camera.py
│   ├── benchmark.py
│   └── test_20_objects.py
├── ros2_ws/src/object_detector/
├── models/
├── outputs/{images,videos,errors,evaluation,benchmark,logs}/
└── docs/
```

## 数据集与匹配逻辑

`prepare_dataset.py` 按条件码和场景码做固定种子分层划分。负样本保留空 TXT。`test_20_objects.py` 的单目标样本以最高置信度类别作为最终预测；若 CSV 中用 `|` 或 `;` 写多个 GT 类别，则检测结果必须覆盖全部 GT 类别才判为正确；GT 写为 `none` 时用于统计明显误检。

## 训练参数建议

- Jetson 实时模型：`yolo11n.pt`，若 JetPack/Ultralytics 兼容性异常可用 `yolov8n.pt`。
- 默认：640 px、100 epochs、batch 16、early stopping 25。
- 轻量增强：小角度旋转、平移、缩放、水平翻转、有限 Mosaic；禁用 MixUp。
- 显存不足：先将 batch 调到 8 或 4，不要先降低图像尺寸。

训练产物位于 `outputs/training/<name>/`，并自动复制 `best.pt`、`last.pt` 到 `models/`。Ultralytics 会保存 precision/recall、mAP、混淆矩阵、PR 曲线和训练损失曲线。

## 结果保存

- 图片检测：标注 JPG + CSV 保存到 `outputs/images/`。
- 视频/摄像头：视频保存到 `outputs/videos/`，逐框 CSV 保存到 `outputs/logs/`；运行时按 `s` 截图，`q` 或 ESC 退出。
- 评估：`outputs/evaluation/evaluation_results.csv`。
- 20 样本：结果 CSV 与 `outputs/errors/error_cases.csv`，典型错误图自动写入 `outputs/errors/`。
- Benchmark：`outputs/benchmark/benchmark.csv`。

## 已知硬件边界

当前软件自检不能替代 Jetson 实测。最终报告中的 FPS、摄像头视频和 ROS2 topic 截图必须在目标 Jetson、实际摄像头和对应 JetPack/ROS2 环境中生成。

## 当前实测摘要

- YOLO11n 最佳权重：`models/best.pt`，并提供 `models/best.onnx`。
- 独立 test：Precision 0.8993、Recall 0.8998、mAP50 0.9372、mAP50-95 0.5605。
- 20 样本：18/20，90.00%，错误案例已保存。
- MIX 示例 `P05_S02_MIX_0121.jpg`：阈值 0.5 下同时检出 5 类。
- 本机 MPS 临时视频 benchmark：58.311 FPS；该结果不是 Jetson 证据。
- 项目审计：`outputs/evaluation/project_self_check.json` 为 `PASS_WITH_HARDWARE_PENDING`。
