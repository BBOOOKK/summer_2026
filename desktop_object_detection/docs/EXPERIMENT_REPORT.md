# 实验一：目标检测与识别实验报告

## 1 实验目的

使用轻量级 YOLO 检测五类桌面目标，在 NVIDIA Jetson 上实现实时识别，并通过 ROS2 发布类别、检测框、置信度和带框图像。验收重点为同时识别不少于两类、20 个样本正确率不低于 80%、Jetson 平均 FPS 不低于 5，以及 ROS2 实时发布。

## 2 实验环境

当前开发与训练环境：macOS、Apple M4、Python 3.12.4、PyTorch 2.13.0、Ultralytics 8.4.133、MPS。Jetson 型号、JetPack、CUDA、TensorRT 和 ROS2 发行版需在目标设备上填写。

## 3 数据集

数据集包含 mouse、keyboard、laptop、cup、headphones 五类，YOLO 水平框标注。确定性分层划分如下：

| 集合 | 图片 | 标签 | 空标签 | 目标框 |
| --- | ---: | ---: | ---: | ---: |
| train | 347 | 347 | 35 | 577 |
| val | 100 | 100 | 10 | 170 |
| test | 53 | 53 | 5 | 94 |
| 合计 | 500 | 500 | 50 | 841 |

各类框数为 mouse 168、keyboard 168、laptop 169、cup 168、headphones 168。

来源必须如实披露：453 张 AI 生成图、10 张本地采集图、37 张 Open Images V7 图片。该数据集通过数量、命名、标签格式和模型辅助视觉复核，但不是 500 张全实拍，也没有独立第二人工复核。因此训练结果只能作为课程实验与混合来源数据验证，不能宣称为纯实拍泛化性能。

## 4 模型与训练

模型采用 YOLO11n，原因是网络轻量、6.4 GFLOPs，适合 Jetson 的实时场景。训练输入 640，batch 16，AdamW 自动优化器，使用有限旋转、平移、缩放、水平翻转和 Mosaic，禁用 MixUp。

训练完成 31 个完整 epoch 后停止，最佳 checkpoint 来自第 27 个 epoch（checkpoint 内部 epoch 索引为 26）。最终提供：

- `models/best.pt`
- `models/last.pt`
- `models/best.onnx`
- 训练曲线、PR 曲线、混淆矩阵：`outputs/training/yolo11n_p05/`

## 5 独立测试集结果

| Precision | Recall | mAP50 | mAP50-95 |
| ---: | ---: | ---: | ---: |
| 0.8993 | 0.8998 | 0.9372 | 0.5605 |

| 类别 | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| mouse | 0.829 | 0.889 | 0.927 | 0.477 |
| keyboard | 0.884 | 0.882 | 0.927 | 0.551 |
| laptop | 0.881 | 0.822 | 0.848 | 0.551 |
| cup | 0.947 | 0.942 | 0.990 | 0.548 |
| headphones | 0.955 | 0.964 | 0.993 | 0.676 |

详细 CSV：`outputs/evaluation/evaluation_results.csv`。

## 6 多类别同时识别

在独立 test MIX 图 `P05_S02_MIX_0121.jpg` 上，以置信度阈值 0.5 同时检出 mouse、keyboard、laptop、cup、headphones 共五类，满足“不少于两类”要求。标注结果保存于 `outputs/images/`。

## 7 20 个目标正确率

测试集从独立 test 划分中每类选取 4 张单目标图，共 20 张；最高置信度类别作为最终预测。

| 测试数量 | 正确 | 错误 | 正确率 | 要求 | 结果 |
| ---: | ---: | ---: | ---: | ---: | --- |
| 20 | 18 | 2 | 90.00% | ≥ 80% | PASS |

两个错误均为 cup 漏检；此外记录了两个正确但置信度偏低的样本。相关文件为 `outputs/evaluation/20_object_test_results.csv` 和 `outputs/errors/error_cases.csv`。

## 8 实时性能

本机 MPS 使用 640 输入、50 个计时帧的端到端平均速度为 58.311 FPS，最低 39.874 FPS，证明 benchmark 软件链路可运行，但该结果不能替代 Jetson 验收。

Jetson 必须另行填写：型号、功耗模式、PyTorch/ONNX/TensorRT 后端、平均 FPS、最低 FPS和温度。验收要求为平均 ≥ 5 FPS。

## 9 ROS2 通信

节点 `object_detector` 支持 USB 摄像头和 `/camera/image_raw` 两种输入；发布：

- `/object_detection/result`：`std_msgs/msg/String` JSON。
- `/object_detection/image`：`sensor_msgs/msg/Image` 带框图像。

ROS2 包、消息结构和参数已通过静态自检。由于开发机没有 ROS2/colcon 环境，仍需在 Jetson 上完成 `colcon build`、`ros2 topic echo`、`ros2 topic hz` 和图像显示截图。

## 10 结果视频与错误分析

已生成 15 秒、150 帧的检测结果视频 `outputs/videos/detection_20260831_101614.mp4`，包含框、类别、置信度和 FPS。典型错误主要为 cup 漏检，可能与杯子外观差异、背景对比度或置信度阈值有关。改进顺序应为补充真实杯子样本、复核边界框、分析置信度分布，再谨慎调整阈值。

## 11 四项验收结论

| 验收项 | 要求 | 当前结果 | 状态 |
| --- | ---: | ---: | --- |
| A. 同时识别类别 | ≥ 2 类 | 5 类 | PASS |
| B. 20 目标正确率 | ≥ 80% | 90.00% | PASS |
| C. Jetson 平均 FPS | ≥ 5 | 本机 58.311；Jetson 未测 | PENDING |
| D. ROS2 实时发布 | 正常 | 软件完成，实机未测 | PENDING |

## 12 总结

本实验已完成数据接入、YOLO11n 训练、独立评估、图片/视频/摄像头推理、ONNX 导出、20 样本统计、错误案例保存、benchmark 和 ROS2 节点开发。软件侧自检结论为 `PASS_WITH_HARDWARE_PENDING`。最终课程验收仍需在指定 Jetson 与摄像头上生成 TensorRT Engine、记录平均 FPS、保存现场视频，并补充 ROS2 topic 截图。

